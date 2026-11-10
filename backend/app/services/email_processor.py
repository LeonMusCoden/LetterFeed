import email
import imaplib
import quopri
import re
from email.header import decode_header, make_header
from email.message import Message

import nh3
from bs4 import BeautifulSoup
from readability import Document
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.imap import send_client_id
from app.core.logging import get_logger
from app.crud.entries import create_entry, get_entry_by_message_id
from app.crud.newsletters import create_newsletter, get_newsletters
from app.crud.settings import get_settings
from app.models.newsletters import Newsletter, Sender
from app.schemas.entries import EntryCreate
from app.schemas.newsletters import NewsletterCreate
from app.schemas.settings import Settings

logger = get_logger(__name__)

# IMAP socket timeout (seconds). Without it a stalled read blocks forever and
# the scheduled job never returns, so every later run is skipped.
_IMAP_TIMEOUT_SECONDS = 60

# Page size used to iterate over every newsletter row.
_NEWSLETTER_PAGE_SIZE = 100


def _is_configured(settings: Settings | None) -> bool:
    """Check if IMAP settings are configured."""
    if (
        not settings
        or not settings.imap_server
        or not settings.imap_username
        or not settings.imap_password
    ):
        logger.warning("IMAP settings are not configured. Skipping email processing.")
        return False
    return True


def _connect_to_imap(
    settings: Settings, search_folder: str
) -> imaplib.IMAP4_SSL | None:
    """Connect to the IMAP server and select the mailbox."""
    try:
        logger.info(f"Connecting to IMAP server: {settings.imap_server}")
        mail = imaplib.IMAP4_SSL(
            settings.imap_server, timeout=_IMAP_TIMEOUT_SECONDS
        )
        mail.login(settings.imap_username, settings.imap_password)
        send_client_id(mail)
        status, messages = mail.select(search_folder)
        if status != "OK":
            logger.error(
                f"Failed to select mailbox: {search_folder}, status: {status}, messages: {messages}"
            )
            mail.logout()
            return None
        logger.info(f"Selected mailbox: {search_folder}")
        return mail
    except Exception as e:
        logger.error(f"Failed to connect to IMAP server: {e}", exc_info=True)
        return None


def _fetch_unread_email_ids(mail: imaplib.IMAP4_SSL) -> list[str]:
    """Fetch IDs of unread emails."""
    status, messages = mail.search(None, "(UNSEEN)")
    if status != "OK":
        logger.error(f"Failed to search for unseen emails, status: {status}")
        return []
    return messages[0].split()


def _get_email_body(msg: Message) -> str:
    """Extract the HTML body from an email message, falling back to plain text."""
    html_body = ""
    text_body = ""
    for part in msg.walk():
        ctype = part.get_content_type()
        cdispo = str(part.get("Content-Disposition"))
        if "attachment" in cdispo:
            continue

        if ctype == "text/html":
            try:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html_body = payload.decode(charset, "ignore")
            except Exception:
                pass
        elif ctype == "text/plain":
            try:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                text_body = payload.decode(charset, "ignore")
            except Exception:
                pass

    # Prefer HTML body, but fall back to plain text if HTML is empty
    return html_body or text_body


def _extract_and_clean_html(raw_html_content: str) -> dict[str, str]:
    """Decode, extract, and sanitize newsletter HTML."""
    try:
        decoded_bytes = quopri.decodestring(raw_html_content.encode("utf-8"))
        clean_html_str = decoded_bytes.decode("utf-8", "ignore")
    except Exception:
        # If quopri fails, assume it's already decoded.
        clean_html_str = raw_html_content

    # Remove NULL bytes and other control characters that can cause lxml to fail.
    # We keep tab (\x09), newline (\x0a), and carriage return (\x0d)
    clean_html_str = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_html_str)

    doc = Document(clean_html_str)
    extracted_body = doc.summary(html_partial=True)

    ALLOWED_TAGS = {
        "p",
        "strong",
        "em",
        "u",
        "h3",
        "h4",
        "ul",
        "ol",
        "li",
        "a",
        "img",
        "br",
        "div",
        "span",
        "figure",
        "figcaption",
    }
    ALLOWED_ATTRIBUTES = {
        "a": {"href", "title"},
        "img": {"src", "alt", "width", "height"},
        "*": {"style"},
    }
    cleaned_body = nh3.clean(
        extracted_body, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES
    )

    title = doc.title()
    if not title or title == "no-title":
        soup = BeautifulSoup(cleaned_body, "html.parser")
        first_headline = soup.find(["h1", "h2", "h3"])
        title = first_headline.get_text(strip=True) if first_headline else "Newsletter"

    return {"title": title, "body": cleaned_body}


def _get_all_newsletters(db: Session) -> list[Newsletter]:
    """Return every newsletter, paginating through the table.

    The crud helper defaults to `limit=100`. With more rows than that, senders
    outside the window were treated as new and the auto-add aborted the batch
    with a UNIQUE constraint failure.
    """
    all_nl: list[Newsletter] = []
    skip = 0
    while True:
        page = get_newsletters(db, skip=skip, limit=_NEWSLETTER_PAGE_SIZE)
        if not page:
            break
        all_nl.extend(page)
        if len(page) < _NEWSLETTER_PAGE_SIZE:
            break
        skip += _NEWSLETTER_PAGE_SIZE
    return all_nl


def _find_newsletter_by_sender(db: Session, sender: str) -> Newsletter | None:
    """Return the newsletter that owns a sender, if any.

    Safety net for senders missing from the in-memory map (stale map or a
    previous failure), so they are not auto-added twice.
    """
    row = db.query(Sender).filter(Sender.email == sender).first()
    if not row:
        return None
    return db.query(Newsletter).filter(Newsletter.id == row.newsletter_id).first()


def _cleanup_orphan_newsletters(db: Session, name: str, keep_id: str) -> None:
    """Delete orphan newsletters with the same name and no entries.

    `create_newsletter()` commits the newsletter before inserting its senders.
    When that insert hits a UNIQUE constraint, the newsletter stays behind as an
    orphan. Remove those rows so they do not pile up.
    """
    try:
        orphans = (
            db.query(Newsletter)
            .filter(Newsletter.name == name, Newsletter.id != keep_id)
            .all()
        )
        from app.models.entries import Entry

        for nl in orphans:
            n_entries = (
                db.query(Entry).filter(Entry.newsletter_id == nl.id).count()
            )
            if n_entries == 0:
                logger.warning(
                    f"Removing orphan newsletter '{name}' id={nl.id} (no entries, "
                    f"canonical kept: {keep_id})"
                )
                db.delete(nl)
        db.commit()
    except Exception as e:
        logger.warning(f"Orphan cleanup for '{name}' failed (non-fatal): {e}")
        db.rollback()


def _auto_add_newsletter(
    db: Session,
    sender: str,
    msg: Message,
    settings: Settings,
) -> Newsletter | None:
    """Add a new newsletter, reusing an existing one when possible.

    Return the existing newsletter if the sender is already registered. If the
    insert still collides (race), roll back, reuse the existing row and clean up
    the orphan. Return None only when neither path succeeds.
    """
    existing = _find_newsletter_by_sender(db, sender)
    if existing:
        logger.info(
            f"Sender {sender} already owned by newsletter '{existing.name}' "
            f"id={existing.id}, reusing (no auto-add)."
        )
        return existing

    logger.info(f"Auto-adding new newsletter for sender: {sender}")
    # Decode the 'From' header to handle non-ASCII characters in the sender's name
    from_header = str(make_header(decode_header(msg.get("From", ""))))
    newsletter_name = email.utils.parseaddr(from_header)[0] or sender
    new_newsletter_schema = NewsletterCreate(
        name=newsletter_name,
        sender_emails=[sender],
    )
    try:
        return create_newsletter(db, new_newsletter_schema)
    except IntegrityError:
        db.rollback()
        logger.warning(
            f"Auto-add for {sender} collided (sender already registered); "
            "reusing existing newsletter."
        )
        existing = _find_newsletter_by_sender(db, sender)
        if existing:
            _cleanup_orphan_newsletters(db, newsletter_name, existing.id)
        return existing
    except Exception:
        db.rollback()
        logger.error(f"Auto-add for {sender} failed.", exc_info=True)
        return None


def _process_single_email(
    num: str,
    mail: imaplib.IMAP4_SSL,
    db: Session,
    sender_map: dict[str, Newsletter],
    settings: Settings,
) -> str:
    """Process one email message, isolating failures.

    Return "created", "skipped" or "failed". Exceptions never propagate: a
    single malformed email is logged and the batch continues, so one bad message
    cannot stall the whole mailbox.
    """
    try:
        status, data = mail.fetch(num, "(BODY.PEEK[])")
        if status != "OK":
            logger.warning(f"Failed to fetch email with id={num}")
            return "skipped"

        msg = email.message_from_bytes(data[0][1])
        sender = email.utils.parseaddr(msg["From"])[1]
        message_id = msg.get("Message-ID")

        if not message_id:
            logger.warning(
                f"Email from {sender} with subject '{msg['Subject']}' has no Message-ID, skipping."
            )
            return "skipped"

        if get_entry_by_message_id(db, message_id):
            logger.info(f"Email with Message-ID {message_id} already processed, skipping.")
            return "skipped"

        logger.debug(f"Processing email from {sender} with subject '{msg['Subject']}'")

        newsletter = sender_map.get(sender)
        if not newsletter:
            # Fall back to the database when the in-memory map is stale.
            newsletter = _find_newsletter_by_sender(db, sender)
            if newsletter:
                sender_map[sender] = newsletter
        if not newsletter and settings.auto_add_new_senders:
            newsletter = _auto_add_newsletter(db, sender, msg, settings)
            if newsletter:
                sender_map[sender] = newsletter

        if not newsletter:
            return "skipped"

        subject = str(make_header(decode_header(msg["Subject"])))
        body = _get_email_body(msg)
        date_str = msg["Date"]
        received_at = email.utils.parsedate_to_datetime(date_str) if date_str else None

        if newsletter.extract_content:
            try:
                cleaned_data = _extract_and_clean_html(body)
                # The subject from the email itself is often better than what readability extracts
                # so we only override the body.
                body = cleaned_data["body"]
            except Exception as e:
                logger.warning(
                    f"Failed to extract content from email '{subject}' from {sender}: {e}. Using raw body."
                )

        entry_schema = EntryCreate(
            subject=subject, body=body, message_id=message_id, received_at=received_at
        )
        new_entry = create_entry(db, entry_schema, newsletter.id)

        if not new_entry:
            logger.error(
                f"Failed to create entry for newsletter '{newsletter.name}' from sender {sender}, email will not be marked as read or moved."
            )
            return "failed"

        logger.info(
            f"Created new entry for newsletter '{newsletter.name}' from sender {sender}"
        )

        if settings.mark_as_read:
            logger.debug(f"Marking email with id={num} as read")
            mail.store(num, "+FLAGS", "\\Seen")

        move_folder = newsletter.move_to_folder or settings.move_to_folder
        if move_folder:
            logger.debug(f"Moving email with id={num} to {move_folder}")
            mail.copy(num, move_folder)
            mail.store(num, "+FLAGS", "\\Deleted")

        return "created"
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error processing single email id={num}, continuing with next: {e}",
            exc_info=True,
        )
        return "failed"


def process_emails(db: Session) -> None:
    """Process unread emails, add them as entries, and manage newsletters."""
    logger.info("Starting email processing...")
    settings = get_settings(db, with_password=True)
    if not _is_configured(settings):
        return

    # Load every newsletter; the crud default limit of 100 is not enough.
    all_newsletters = _get_all_newsletters(db)
    logger.info(f"Processing emails for {len(all_newsletters)} newsletters.")

    # Group newsletters by search folder
    folder_groups: dict[str, list[Newsletter]] = {}
    for nl in all_newsletters:
        folder = nl.search_folder or settings.search_folder
        if folder not in folder_groups:
            folder_groups[folder] = []
        folder_groups[folder].append(nl)

    # If auto-adding is enabled, ensure the default search folder is always checked.
    if settings.auto_add_new_senders and settings.search_folder not in folder_groups:
        folder_groups[settings.search_folder] = []

    total_created = 0
    total_failed = 0
    total_skipped = 0

    for search_folder, newsletters_in_folder in folder_groups.items():
        logger.info(
            f"Processing folder '{search_folder}' for {len(newsletters_in_folder)} newsletters."
        )
        sender_map = {
            sender.email: nl for nl in newsletters_in_folder for sender in nl.senders
        }

        mail = _connect_to_imap(settings, search_folder)
        if not mail:
            logger.warning(
                f"Skipping folder '{search_folder}' due to connection issue."
            )
            continue

        try:
            email_ids = _fetch_unread_email_ids(mail)
            logger.info(
                f"Found {len(email_ids)} unseen emails in folder '{search_folder}'."
            )
            # One failing email must not abort the rest of the batch.
            for num in email_ids:
                try:
                    result = _process_single_email(num, mail, db, sender_map, settings)
                except Exception as e:
                    db.rollback()
                    logger.error(
                        f"Unhandled error on email id={num}, continuing: {e}",
                        exc_info=True,
                    )
                    result = "failed"
                if result == "created":
                    total_created += 1
                elif result == "failed":
                    total_failed += 1
                else:
                    total_skipped += 1

            # Expunge logic needs to be carefully considered.
            # If any newsletter in this folder group has a move_to_folder, we expunge.
            # This is an approximation. A more robust solution might require per-email expunge.
            should_expunge = any(
                nl.move_to_folder or settings.move_to_folder
                for nl in newsletters_in_folder
            )
            if should_expunge:
                logger.info(f"Expunging deleted emails from '{search_folder}'")
                mail.expunge()

        except Exception as e:
            logger.error(
                f"Error processing emails in folder '{search_folder}': {e}",
                exc_info=True,
            )
        finally:
            mail.logout()

    # Report real counters instead of a blanket success.
    if total_failed:
        logger.warning(
            f"Email processing finished WITH ERRORS: "
            f"created={total_created} failed={total_failed} skipped={total_skipped}."
        )
    else:
        logger.info(
            f"Email processing finished successfully: "
            f"created={total_created} skipped={total_skipped}."
        )
