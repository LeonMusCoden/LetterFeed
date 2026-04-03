import imaplib
from email.message import Message
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.crud.newsletters import create_newsletter
from app.crud.settings import create_or_update_settings
from app.models.newsletters import Newsletter
from app.schemas.newsletters import NewsletterCreate
from app.schemas.settings import Settings, SettingsCreate
from app.services.email_processor import _process_single_email, process_emails


def _setup_test_email_processing(
    db_session: Session,
    newsletter_create_data: NewsletterCreate,
    settings_create_data: SettingsCreate,
) -> tuple[MagicMock, Newsletter, Settings]:
    """Help to set up mocks and data for email processing tests."""
    settings = create_or_update_settings(db_session, settings_create_data)
    newsletter = create_newsletter(db_session, newsletter_create_data)

    mock_mail = MagicMock(spec=imaplib.IMAP4_SSL)
    msg = Message()
    msg["From"] = newsletter_create_data.sender_emails[0]
    msg["Subject"] = "Test Email"
    msg["Message-ID"] = "<test-message-id>"
    msg.set_payload("<html><body><p>Original Body</p></body></html>", "utf-8")
    mock_mail.fetch.return_value = ("OK", [(b"1 (RFC822)", msg.as_bytes())])

    return mock_mail, newsletter, settings


def test_process_single_email_with_newsletter_move_folder(db_session: Session):
    """Test that the per-newsletter move_to_folder is used, overriding the global setting."""
    # 1. ARRANGE
    settings_data = SettingsCreate(
        imap_server="test.com",
        imap_username="test",
        imap_password="password",
        move_to_folder="GlobalArchive",
    )
    newsletter_data = NewsletterCreate(
        name="Test Newsletter",
        sender_emails=["test@example.com"],
        move_to_folder="NewsletterArchive",
    )
    mock_mail, newsletter, settings = _setup_test_email_processing(
        db_session, newsletter_data, settings_data
    )
    sender_map = {newsletter.senders[0].email: newsletter}

    # 2. ACT
    _process_single_email("1", mock_mail, db_session, sender_map, settings)

    # 3. ASSERT
    mock_mail.copy.assert_called_once_with("1", '"NewsletterArchive"')
    mock_mail.store.assert_any_call("1", "+FLAGS", "\\Deleted")


def test_process_single_email_with_global_move_folder(db_session: Session):
    """Test that the global move_to_folder is used when the per-newsletter one is not set."""
    # 1. ARRANGE
    settings_data = SettingsCreate(
        imap_server="test.com",
        imap_username="test",
        imap_password="password",
        move_to_folder="GlobalArchive",
    )
    newsletter_data = NewsletterCreate(
        name="Test Newsletter", sender_emails=["test@example.com"]
    )
    mock_mail, newsletter, settings = _setup_test_email_processing(
        db_session, newsletter_data, settings_data
    )
    sender_map = {newsletter.senders[0].email: newsletter}

    # 2. ACT
    _process_single_email("1", mock_mail, db_session, sender_map, settings)

    # 3. ASSERT
    mock_mail.copy.assert_called_once_with("1", '"GlobalArchive"')
    mock_mail.store.assert_any_call("1", "+FLAGS", "\\Deleted")


@patch("app.services.email_processor._connect_to_imap")
def test_process_emails_uses_newsletter_search_folder(
    mock_connect_to_imap,
    db_session: Session,
):
    """Test that the per-newsletter search_folder is used, overriding the global setting."""
    # 1. ARRANGE
    settings_data = SettingsCreate(
        imap_server="test.com",
        imap_username="test",
        imap_password="password",
        search_folder="GlobalInbox",
    )
    create_or_update_settings(db_session, settings_data)

    newsletter_data = NewsletterCreate(
        name="Test Newsletter",
        sender_emails=["test@example.com"],
        search_folder="NewsletterInbox",
    )
    create_newsletter(db_session, newsletter_data)

    # Mock the return of _connect_to_imap to avoid a real IMAP connection
    mock_connect_to_imap.return_value = None

    # 2. ACT
    process_emails(db_session)

    # 3. ASSERT
    # Check that _connect_to_imap was called with the newsletter's specific folder
    mock_connect_to_imap.assert_called_once()
    call_args = mock_connect_to_imap.call_args[0]
    assert call_args[1] == "NewsletterInbox"


@patch("app.services.email_processor._connect_to_imap")
def test_process_emails_uses_global_search_folder(
    mock_connect_to_imap,
    db_session: Session,
):
    """Test that the global search_folder is used when the per-newsletter one is not set."""
    # 1. ARRANGE
    settings_data = SettingsCreate(
        imap_server="test.com",
        imap_username="test",
        imap_password="password",
        search_folder="GlobalInbox",
    )
    create_or_update_settings(db_session, settings_data)

    newsletter_data = NewsletterCreate(
        name="Test Newsletter",
        sender_emails=["test@example.com"],
        search_folder=None,  # Explicitly not set
    )
    create_newsletter(db_session, newsletter_data)

    mock_connect_to_imap.return_value = None

    # 2. ACT
    process_emails(db_session)

    # 3. ASSERT
    mock_connect_to_imap.assert_called_once()
    call_args = mock_connect_to_imap.call_args[0]
    assert call_args[1] == "GlobalInbox"


@patch("app.services.email_processor._extract_and_clean_html")
def test_process_single_email_with_content_extraction(
    mock_extract_clean,
    db_session: Session,
):
    """Test that the cleaning function is called when extract_content is True."""
    # 1. ARRANGE
    mock_extract_clean.return_value = {
        "title": "Extracted Title",
        "body": "Extracted Body",
    }
    settings_data = SettingsCreate(
        imap_server="test.com", imap_username="test", imap_password="password"
    )
    newsletter_data = NewsletterCreate(
        name="Test Newsletter",
        sender_emails=["test@example.com"],
        extract_content=True,
    )
    mock_mail, newsletter, settings = _setup_test_email_processing(
        db_session, newsletter_data, settings_data
    )
    sender_map = {newsletter.senders[0].email: newsletter}

    # 2. ACT
    with patch("app.services.email_processor.create_entry") as mock_create_entry:
        _process_single_email("1", mock_mail, db_session, sender_map, settings)

    # 3. ASSERT
    mock_extract_clean.assert_called_once()
    # Check that create_entry was called with the extracted body
    mock_create_entry.assert_called_once()
    entry_create_arg = mock_create_entry.call_args[0][1]
    assert entry_create_arg.body == "Extracted Body"
    # Subject should still come from the email, not the extracted title
    assert entry_create_arg.subject == "Test Email"


def test_process_single_email_with_encoded_from_header(db_session: Session):
    """Test that an encoded From header is correctly decoded for the newsletter name."""
    # 1. ARRANGE
    settings_data = SettingsCreate(
        imap_server="test.com",
        imap_username="test",
        imap_password="password",
        auto_add_new_senders=True,
    )
    settings = create_or_update_settings(db_session, settings_data)

    mock_mail = MagicMock(spec=imaplib.IMAP4_SSL)
    msg = Message()
    # "Кирилл" in Cyrillic, base64 encoded for UTF-8
    from_header = "=?utf-8?B?0JrQuNGA0LjQu9C7?= <test@example.com>"
    msg["From"] = from_header
    msg["Subject"] = "Test Email"
    msg["Message-ID"] = "<test-message-id-encoded-from>"
    msg.set_payload("<html><body><p>Body</p></body></html>", "utf-8")
    mock_mail.fetch.return_value = ("OK", [(b"1 (RFC822)", msg.as_bytes())])

    sender_map = {}  # empty, to trigger auto-add

    # 2. ACT
    _process_single_email("1", mock_mail, db_session, sender_map, settings)

    # 3. ASSERT
    from app.crud.newsletters import get_newsletters

    newsletters = get_newsletters(db_session)
    assert len(newsletters) == 1
    assert newsletters[0].name == "Кирилл"
    assert newsletters[0].senders[0].email == "test@example.com"
