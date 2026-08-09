import datetime
import email
import fnmatch
import imaplib
import re
import smtplib
import threading
from email.header import decode_header, make_header
from email.message import EmailMessage, Message

import nh3
from bs4 import BeautifulSoup
from readability import Document
from sqlalchemy.orm import Session

from app.core.config import settings as env_settings
from app.core.logging import get_logger
from app.core.sanitization import ALLOWED_ATTRIBUTES, ALLOWED_TAGS, sanitize_html
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
        mail = imaplib.IMAP4_SSL(settings.imap_server, timeout=30)
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


def _find_archive_folder(mail: imaplib.IMAP4_SSL) -> str | None:
    """Auto-detect an Archive folder on the IMAP server."""
    try:
        status, folders = mail.list()
        if status != "OK":
            logger.warning(f"Failed to list IMAP folders for auto-detection: {status}")
            return None

        archive_candidates = []
        for folder in folders:
            try:
                folder_str = folder.decode("utf-8", "ignore")
            except Exception:
                continue

            # Parse folder name by searching for the last quoted string or the last word
            name = None
            match = re.search(r'"([^"]+)"\s*$', folder_str)
            if match:
                name = match.group(1)
            else:
                parts = folder_str.split()
                if parts:
                    name = parts[-1].strip('"')

            if not name:
                continue

            # Standard special-use flag check (\Archive)
            if r"\Archive" in folder_str:
                return name

            name_lower = name.lower()
            # Prioritize exact matches
            if name_lower == "archive":
                return name
            elif name_lower in [
                "archives",
                "archived",
                "all mail",
                "gmail/all mail",
                "[gmail]/all mail",
            ]:
                archive_candidates.append(name)

        if archive_candidates:
            # Prioritize candidates containing "archive" over "all mail"
            archive_candidates.sort(key=lambda x: 0 if "archive" in x.lower() else 1)
            return archive_candidates[0]

    except Exception as e:
        logger.warning(f"Error auto-detecting Archive folder: {e}", exc_info=True)
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


def _sanitize_html(raw_html_content: str) -> str:
    """Strip control chars and sanitize raw HTML to the allowlist."""
    return sanitize_html(raw_html_content)


def _extract_and_clean_html(raw_html_content: str) -> dict[str, str]:
    """Extract and sanitize newsletter HTML (readability)."""
    # Remove NULL bytes and other control characters that can cause lxml to fail.
    clean_html_str = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw_html_content)

    doc = Document(clean_html_str)
    extracted_body = doc.summary(html_partial=True)

    cleaned_body = nh3.clean(
        extracted_body, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES
    )

    title = doc.title()
    if not title or title == "no-title":
        soup = BeautifulSoup(cleaned_body, "html.parser")
        first_headline = soup.find(["h1", "h2", "h3"])
        title = first_headline.get_text(strip=True) if first_headline else "Newsletter"

    return {"title": title, "body": cleaned_body}


def _send_notification_email(
    newsletter_name: str, sender_email: str, rss_feed_url: str
) -> None:
    """Send an SMTP email notification when a new newsletter is detected."""
    if not (env_settings.smtp_server and env_settings.notification_email_to):
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = f"[LetterFeed] New Newsletter: {newsletter_name}"
        # We assume the IMAP user is the From address for notification,
        # unless SMTP username is an email and preferred, but IMAP user usually works.
        msg["From"] = env_settings.imap_username
        msg["To"] = env_settings.notification_email_to

        content = f"""New newsletter detected!

Name: {newsletter_name}
Sender: {sender_email}
RSS Feed: {rss_feed_url}"""
        msg.set_content(content)

        with smtplib.SMTP(
            env_settings.smtp_server, env_settings.smtp_port, timeout=30
        ) as server:
            server.starttls()
            if env_settings.smtp_username and env_settings.smtp_password:
                server.login(env_settings.smtp_username, env_settings.smtp_password)
            server.send_message(msg)
        logger.info(f"Notification email sent to {env_settings.notification_email_to}")
    except Exception as e:
        logger.error(f"Failed to send notification email: {e}")


class ProcessingInProgressError(Exception):
    """Exception raised when an email processing task is already running."""

    pass


_processing_lock = threading.Lock()


def _auto_add_newsletter(
    db: Session,
    sender: str,
    msg: Message,
    settings: Settings,
) -> Newsletter | None:
    """Automatically add a new newsletter."""
    from app.models.newsletters import Sender

    # Check if this sender email already exists in the database
    existing_sender = db.query(Sender).filter(Sender.email == sender).first()
    if existing_sender:
        logger.warning(
            f"Sender {sender} is already registered to newsletter {existing_sender.newsletter_id}. "
            "Reusing existing newsletter to avoid constraint violation."
        )
        return (
            db.query(Newsletter)
            .filter(Newsletter.id == existing_sender.newsletter_id)
            .first()
        )

    logger.info(f"Auto-adding new newsletter for sender: {sender}")
    # Decode the 'From' header to handle non-ASCII characters in the sender's name
    from_header = str(make_header(decode_header(msg.get("From", ""))))
    newsletter_name = email.utils.parseaddr(from_header)[0] or sender
    new_newsletter_schema = NewsletterCreate(
        name=newsletter_name,
        sender_emails=[sender],
    )
    new_nl = create_newsletter(db, new_newsletter_schema)
    if not new_nl:
        return None

    rss_feed_url = f"{env_settings.app_base_url.rstrip('/')}/api/feeds/{new_nl.id}"
    _send_notification_email(new_nl.name, sender, rss_feed_url)

    return new_nl


def _process_single_email(
    num: str,
    mail: imaplib.IMAP4_SSL,
    db: Session,
    sender_map: dict[str, list[Newsletter]],
    settings: Settings,
    detected_archive: str | None = None,
) -> None:
    """Process a single email message."""
    try:
        status, data = mail.fetch(num, "(BODY.PEEK[])")
        if (
            status != "OK"
            or not data
            or not isinstance(data[0], tuple)
            or len(data[0]) < 2
            or data[0][1] is None
        ):
            logger.warning(
                f"Failed to fetch email with id={num} or response data is invalid"
            )
            return

        msg = email.message_from_bytes(data[0][1])
        sender = email.utils.parseaddr(msg["From"])[1]
        message_id = msg.get("Message-ID")

        if not message_id:
            logger.warning(
                f"Email from {sender} with subject '{msg['Subject']}' has no Message-ID, skipping."
            )
            return

        newsletters = sender_map.get(sender, [])

        # If no exact match, check for wildcard matches
        if not newsletters:
            for sender_pattern, nls in sender_map.items():
                if fnmatch.fnmatch(sender, sender_pattern):
                    newsletters = nls
                    break

        if newsletters and not isinstance(newsletters, list | tuple):
            newsletters = [newsletters]

        if not newsletters and settings.auto_add_new_senders:
            new_nl = _auto_add_newsletter(db, sender, msg, settings)
            if new_nl:
                newsletters = [new_nl]
                sender_map[sender] = [new_nl]

        if not newsletters:
            return

        logger.debug(f"Processing email from {sender} with subject '{msg['Subject']}'")
        subject = str(make_header(decode_header(msg["Subject"])))
        body = _get_email_body(msg)
        date_str = msg["Date"]

        received_at = None
        if date_str:
            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except Exception as e:
                logger.warning(
                    f"Failed to parse email date '{date_str}': {e}. Falling back to current UTC time."
                )
                from datetime import UTC

                received_at = datetime.now(UTC)

        # Distribute email to all matching newsletters
        any_success = False
        move_folder = None

        for newsletter in newsletters:
            # Check if the email was already successfully processed for this newsletter
            already_processed = (
                get_entry_by_message_id(db, message_id, newsletter.id) is not None
            )

            if already_processed:
                logger.info(
                    f"Email with Message-ID {message_id} already processed for newsletter {newsletter.name}, skipping database insertion."
                )
                any_success = True
            else:
                # Prepare entry body
                entry_body = body
                if newsletter.extract_content:
                    try:
                        cleaned_data = _extract_and_clean_html(body)
                        entry_body = cleaned_data["body"]
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract content from email '{subject}' from {sender} for newsletter {newsletter.name}: {e}. "
                            "Falling back to the sanitized raw body."
                        )
                        entry_body = _sanitize_html(body)
                else:
                    entry_body = _sanitize_html(body)

                entry_schema = EntryCreate(
                    subject=subject,
                    body=entry_body,
                    message_id=message_id,
                    received_at=received_at,
                )
                new_entry = create_entry(db, entry_schema, newsletter.id)

                if new_entry:
                    logger.info(
                        f"Created new entry for newsletter '{newsletter.name}' from sender {sender}"
                    )
                    any_success = True
                else:
                    logger.error(
                        f"Failed to create entry for newsletter '{newsletter.name}' from sender {sender}."
                    )

            if not move_folder:
                move_folder = newsletter.move_to_folder

        if not any_success:
            logger.error(
                f"Email id={num} could not be successfully processed for any matching newsletters. Leaving it in place."
            )
            return

        if settings.mark_as_read:
            logger.debug(f"Marking email with id={num} as read")
            mail.store(num, "+FLAGS", "\\Seen")

        # Resolve the final archive folder destination
        final_move_folder = move_folder or settings.move_to_folder or detected_archive
        if final_move_folder:
            logger.debug(f"Moving email with id={num} to {final_move_folder}")
            copy_status, copy_response = mail.copy(num, final_move_folder)
            if copy_status == "OK":
                mail.store(num, "+FLAGS", "\\Deleted")
            else:
                logger.error(
                    f"Failed to copy email id={num} to folder '{final_move_folder}' "
                    f"(status={copy_status}, response={copy_response}). "
                    "Leaving it in place to avoid data loss."
                )
        else:
            logger.warning(
                f"Could not archive email with id={num} because no move folder is configured and no Archive folder was auto-detected."
            )
    except Exception as e:
        logger.error(f"Failed to process single email id={num}: {e}", exc_info=True)


def process_emails(db: Session) -> None:
    """Process unread emails, add them as entries, and manage newsletters."""
    if not _processing_lock.acquire(blocking=False):
        logger.warning("Email processing is already in progress. Skipping.")
        raise ProcessingInProgressError("Email processing is already in progress.")

    try:
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
        if (
            settings.auto_add_new_senders
            and settings.search_folder not in folder_groups
        ):
            folder_groups[settings.search_folder] = []

        for search_folder, newsletters_in_folder in folder_groups.items():
            logger.info(
                f"Processing folder '{search_folder}' for {len(newsletters_in_folder)} newsletters."
            )
            # Map sender email to list of newsletters (one-to-many)
            sender_map: dict[str, list[Newsletter]] = {}
            for nl in newsletters_in_folder:
                for sender in nl.senders:
                    if sender.email not in sender_map:
                        sender_map[sender.email] = []
                    sender_map[sender.email].append(nl)

            mail = _connect_to_imap(settings, search_folder)
            if not mail:
                logger.warning(
                    f"Skipping folder '{search_folder}' due to connection issue."
                )
                continue

            try:
                # Check if any newsletter or global setting is missing a configured move folder.
                # If so, we'll try to auto-detect a server Archive folder.
                detected_archive = None
                has_missing_move_folder = any(
                    not (nl.move_to_folder or settings.move_to_folder)
                    for nl in newsletters_in_folder
                )
                if has_missing_move_folder:
                    detected_archive = _find_archive_folder(mail)
                    if detected_archive:
                        logger.info(
                            f"Auto-detected Archive folder for fallback: {detected_archive}"
                        )

                email_ids = _fetch_unread_email_ids(mail)
                logger.info(
                    f"Found {len(email_ids)} unseen emails in folder '{search_folder}'."
                )
                for num in email_ids:
                    _process_single_email(
                        num, mail, db, sender_map, settings, detected_archive
                    )

                # Expunge logic: expunge if any configured or auto-detected folder is used
                should_expunge = any(
                    nl.move_to_folder or settings.move_to_folder or detected_archive
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

        # Clean up old entries based on retention settings (storage purge)
        if env_settings.feed_retention_days is not None:
            from app.crud.entries import purge_old_entries

            purge_old_entries(db)

        # Pre-warm feed caches for instant RSS reader responses
        try:
            from app.crud.entries import get_latest_entry_timestamp_cached
            from app.crud.feed_cache import set_cached_feed
            from app.routers.feeds import _generate_etag
            from app.services.feed_generator import generate_feed, generate_master_feed

            master_ts = get_latest_entry_timestamp_cached(db)
            master_etag = _generate_etag("master", master_ts)
            master_content = generate_master_feed(db)
            if master_content:
                set_cached_feed(db, "master", master_etag, master_content)

            for nl in get_newsletters(db):
                nl_ts = get_latest_entry_timestamp_cached(db, newsletter_id=nl.id)
                nl_etag = _generate_etag(nl.id, nl_ts)
                nl_content = generate_feed(
                    db, nl.id, limit=env_settings.newsletter_feed_limit
                )
                if nl_content:
                    set_cached_feed(db, nl.id, nl_etag, nl_content)
        except Exception as e:
            logger.warning(f"Failed to pre-warm feed cache after email processing: {e}")

        logger.info("Email processing finished successfully.")
    finally:
        _processing_lock.release()
