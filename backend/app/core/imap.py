import imaplib
import ssl

from app.core.config import settings as env_settings
from app.core.logging import get_logger

"""IMAP utility functions for connecting to mail servers and fetching folders."""

logger = get_logger(__name__)


def imap_ssl_context() -> ssl.SSLContext:
    """Return the TLS context used for IMAP connections.

    The server certificate and hostname are verified against the system CA store,
    unless LETTERFEED_IMAP_TLS_INSECURE is enabled.
    """
    if env_settings.imap_tls_insecure:
        logger.warning(
            "LETTERFEED_IMAP_TLS_INSECURE is enabled: the IMAP server certificate is not verified"
        )
        return ssl._create_unverified_context()
    return ssl.create_default_context()


def connect_imap(server: str) -> imaplib.IMAP4_SSL:
    """Open an IMAP over TLS connection with certificate verification."""
    try:
        return imaplib.IMAP4_SSL(server, ssl_context=imap_ssl_context())
    except ssl.SSLCertVerificationError as e:
        reason = str(e.verify_message or e).rstrip(".")
        raise ConnectionError(
            f"TLS certificate verification failed for {server}: {reason}. "
            "If the server uses a self-signed certificate, set LETTERFEED_IMAP_TLS_INSECURE=true."
        ) from e


def send_client_id(mail: imaplib.IMAP4_SSL) -> None:
    """Send IMAP client identity for providers that require RFC 2971 ID."""
    imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))
    try:
        mail._simple_command(
            "ID", '("name" "LetterFeed" "version" "0.4.0" "vendor" "LetterFeed")'
        )
    except Exception as e:
        logger.warning(f"Failed to send IMAP ID command: {e}")


def _test_imap_connection(server, username, password):
    """Test the IMAP connection with the given credentials."""
    logger.info(f"Testing IMAP connection to {server} for user {username}")
    try:
        mail = connect_imap(server)
        mail.login(username, password)
        send_client_id(mail)
        mail.logout()
        logger.info("IMAP connection successful")
        return True, "Connection successful"
    except Exception as e:
        logger.error(f"IMAP connection failed: {e}")
        return False, str(e)


def get_folders(server, username, password):
    """Fetch a list of IMAP folders from the mail server."""
    logger.info(f"Fetching IMAP folders from {server} for user {username}")
    try:
        mail = connect_imap(server)
        mail.login(username, password)
        send_client_id(mail)
        status, folders = mail.list()
        mail.logout()
        if status == "OK":
            folder_list = [
                folder.decode().split(' "/" ')[1].strip('"') for folder in folders
            ]
            logger.info(f"Found {len(folder_list)} folders")
            return folder_list
        logger.warning(f"Failed to list IMAP folders, status: {status}")
        return []
    except Exception as e:
        logger.error(f"Error fetching IMAP folders: {e}")
        return []
