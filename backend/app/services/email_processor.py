import email
import imaplib
import quopri
from email.header import decode_header, make_header
from email.message import Message

import nh3
from bs4 import BeautifulSoup
from readability import Document
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.crud.entries import create_entry, get_entry_by_message_id
from app.crud.newsletters import create_newsletter, get_newsletters
from app.crud.settings import get_settings
from app.models.newsletters import Newsletter
from app.schemas.entries import EntryCreate
from app.schemas.newsletters import NewsletterCreate
from app.schemas.settings import Settings

logger = get_logger(__name__)


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
        mail = imaplib.IMAP4_SSL(settings.imap_server)
        mail.login(settings.imap_username, settings.imap_password)
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


def _auto_add_newsletter(
    db: Session,
    sender: str,
    msg: Message,
    settings: Settings,
) -> Newsletter:
    """Automatically add a new newsletter."""
    logger.info(f"Auto-adding new newsletter for sender: {sender}")
    # Decode the 'From' header to handle non-ASCII characters in the sender's name
    from_header = str(make_header(decode_header(msg.get("From", ""))))
    newsletter_name = email.utils.parseaddr(from_header)[0] or sender
    new_newsletter_schema = NewsletterCreate(
        name=newsletter_name,
        sender_emails=[sender],
    )
    return create_newsletter(db, new_newsletter_schema)


def _process_single_email(
    num: str,
    mail: imaplib.IMAP4_SSL,
    db: Session,
    sender_map: dict[str, Newsletter],
    settings: Settings,
) -> None:
    """Process a single email message."""
    status, data = mail.fetch(num, "(BODY.PEEK[])")
    if status != "OK":
        logger.warning(f"Failed to fetch email with id={num}")
        return

    msg = email.message_from_bytes(data[0][1])
    sender = email.utils.parseaddr(msg["From"])[1]
    message_id = msg.get("Message-ID")

    if not message_id:
        logger.warning(
            f"Email from {sender} with subject '{msg['Subject']}' has no Message-ID, skipping."
        )
        return

    if get_entry_by_message_id(db, message_id):
        logger.info(f"Email with Message-ID {message_id} already processed, skipping.")
        return

    logger.debug(f"Processing email from {sender} with subject '{msg['Subject']}'")

    newsletter = sender_map.get(sender)
    if not newsletter and settings.auto_add_new_senders:
        newsletter = _auto_add_newsletter(db, sender, msg, settings)
        sender_map[sender] = newsletter

    if not newsletter:
        return

    subject = str(make_header(decode_header(msg["Subject"])))
    body = _get_email_body(msg)
    date_str = msg["Date"]
    received_at = email.utils.parsedate_to_datetime(date_str) if date_str else None

    if newsletter.extract_content:
        cleaned_data = _extract_and_clean_html(body)
        # The subject from the email itself is often better than what readability extracts
        # so we only override the body.
        body = cleaned_data["body"]

    entry_schema = EntryCreate(
        subject=subject, body=body, message_id=message_id, received_at=received_at
    )
    new_entry = create_entry(db, entry_schema, newsletter.id)

    if not new_entry:
        logger.error(
            f"Failed to create entry for newsletter '{newsletter.name}' from sender {sender}, email will not be marked as read or moved."
        )
        return

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


def process_emails(db: Session) -> None:
    """Process unread emails, add them as entries, and manage newsletters."""
    logger.info("Starting email processing...")
    settings = get_settings(db, with_password=True)
    if not _is_configured(settings):
        return

    all_newsletters = get_newsletters(db)
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
            for num in email_ids:
                _process_single_email(num, mail, db, sender_map, settings)

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

    logger.info("Email processing finished successfully.")
