from datetime import datetime
from unittest.mock import ANY, MagicMock, patch

from sqlalchemy.orm import Session

from app.core.imap import _test_imap_connection, get_folders
from app.crud.newsletters import create_newsletter
from app.crud.settings import create_or_update_settings
from app.schemas.newsletters import NewsletterCreate
from app.schemas.settings import SettingsCreate
from app.services.email_processor import process_emails


@patch("app.core.imap.imaplib.IMAP4_SSL")
def test_test_imap_connection_success(mock_imap):
    """Test IMAP connection success."""
    mock_imap.return_value.login.return_value = (None, None)
    mock_imap.return_value.logout.return_value = (None, None)
    success, message = _test_imap_connection("imap.test.com", "user", "pass")
    assert success
    assert message == "Connection successful"


@patch("app.core.imap.imaplib.IMAP4_SSL")
def test_test_imap_connection_failure(mock_imap):
    """Test IMAP connection failure."""
    mock_imap.return_value.login.side_effect = Exception("Auth failed")
    success, message = _test_imap_connection("imap.test.com", "user", "pass")
    assert not success
    assert message == "Auth failed"


@patch("app.core.imap.imaplib.IMAP4_SSL")
def test_get_folders(mock_imap):
    """Test fetching IMAP folders."""
    mock_imap.return_value.login.return_value = (None, None)
    mock_imap.return_value.logout.return_value = (None, None)
    mock_imap.return_value.list.return_value = (
        "OK",
        [b'(NOCONNECT NOSELECT) "/" "INBOX"', b'(NOCONNECT NOSELECT) "/" "Processed"'],
    )
    folders = get_folders("imap.test.com", "user", "pass")
    assert folders == ["INBOX", "Processed"]


@patch("app.services.email_processor.imaplib.IMAP4_SSL")
def test_process_emails(mock_imap, db_session: Session):
    """Test processing emails."""
    # Setup settings
    settings_data = SettingsCreate(
        imap_server="imap.test.com",
        imap_username="test@test.com",
        imap_password="password",
        search_folder="INBOX",
        move_to_folder="Processed",
        mark_as_read=True,
    )
    create_or_update_settings(db_session, settings_data)

    # Setup newsletter
    newsletter_data = NewsletterCreate(
        name="Test Newsletter", sender_emails=["newsletter@example.com"]
    )
    create_newsletter(db_session, newsletter_data)

    # Mock IMAP connection and email fetching
    mock_mail = MagicMock()
    mock_imap.return_value = mock_mail
    mock_mail.login.return_value = ("OK", [b"Login successful"])
    mock_mail.select.return_value = ("OK", [b"1"])
    mock_mail.search.return_value = ("OK", [b"1"])

    # Mock email content
    mock_msg_bytes = b"From: newsletter@example.com\nSubject: Test Subject\nMessage-ID: <test@test.com>\n\n<p>Test Body</p>"
    mock_mail.fetch.return_value = ("OK", [(None, mock_msg_bytes)])

    process_emails(db_session)

    # Assertions
    mock_mail.login.assert_called_once_with("test@test.com", "password")
    mock_mail.select.assert_called_once_with("INBOX")
    mock_mail.search.assert_called_once_with(None, "(UNSEEN)")
    mock_mail.fetch.assert_called_once_with(b"1", "(BODY.PEEK[])")
    mock_mail.store.assert_any_call(b"1", "+FLAGS", "\\Seen")
    mock_mail.copy.assert_called_once_with(b"1", "Processed")
    mock_mail.store.assert_any_call(b"1", "+FLAGS", "\\Deleted")
    mock_mail.expunge.assert_called_once()
    mock_mail.logout.assert_called_once()

    # Verify entry in DB
    from app.crud.entries import get_entries_by_newsletter
    from app.crud.newsletters import get_newsletters

    newsletters = get_newsletters(db_session)
    assert len(newsletters) == 1
    entries = get_entries_by_newsletter(db_session, newsletters[0].id)
    assert len(entries) == 1
    assert entries[0].subject == "Test Subject"
    assert entries[0].body == "<p>Test Body</p>"


@patch("app.core.scheduler.job")
@patch("app.core.scheduler.SessionLocal")
@patch("app.core.scheduler.scheduler")
@patch("app.core.scheduler.datetime")
def test_start_scheduler_with_interval(
    mock_datetime, mock_scheduler, mock_session_local, mock_job, db_session: Session
):
    """Test starting the scheduler with an interval."""
    fixed_now = datetime(2025, 10, 20, 12, 0, 0)
    mock_datetime.now.return_value = fixed_now

    mock_session_local.return_value = db_session
    mock_scheduler.running = False
    settings_data = SettingsCreate(
        imap_server="imap.test.com",
        imap_username="test@test.com",
        imap_password="password",
        email_check_interval=30,
    )
    create_or_update_settings(db_session, settings_data)

    from app.core.scheduler import start_scheduler_with_interval

    start_scheduler_with_interval()

    mock_scheduler.add_job.assert_called_with(
        ANY,
        "date",
        run_date=fixed_now,
        id="initial_email_check",
        replace_existing=True,
    )
    mock_scheduler.start.assert_called_once()


@patch("app.core.scheduler.SessionLocal")
@patch("app.core.scheduler.process_emails")
def test_scheduler_job(mock_process_emails, mock_session_local, db_session: Session):
    """Test the scheduler job."""
    mock_session_local.return_value = db_session
    from app.core.scheduler import job

    job()
    mock_process_emails.assert_called_once_with(db_session)


@patch("app.services.email_processor.imaplib.IMAP4_SSL")
def test_process_emails_auto_add_sender(mock_imap, db_session: Session):
    """Test processing emails with auto add sender enabled."""
    settings_data = SettingsCreate(
        imap_server="imap.test.com",
        imap_username="test@test.com",
        imap_password="password",
        auto_add_new_senders=True,
    )
    create_or_update_settings(db_session, settings_data)

    mock_mail = MagicMock()
    mock_imap.return_value = mock_mail
    mock_mail.login.return_value = ("OK", [b"Login successful"])
    mock_mail.select.return_value = ("OK", [b"1"])
    mock_mail.search.return_value = ("OK", [b"1"])
    mock_msg_bytes = b"From: New Sender <new@example.com>\nSubject: New Email\nMessage-ID: <new@new.com>\n\nHello"
    mock_mail.fetch.return_value = ("OK", [(None, mock_msg_bytes)])

    process_emails(db_session)

    from app.crud.newsletters import get_newsletters

    newsletters = get_newsletters(db_session)
    assert len(newsletters) == 1
    assert len(newsletters[0].senders) == 1
    assert newsletters[0].senders[0].email == "new@example.com"
    assert newsletters[0].name == "New Sender"


@patch("app.services.email_processor.imaplib.IMAP4_SSL")
def test_process_emails_no_settings(mock_imap, db_session: Session):
    """Test processing emails with no settings configured."""
    # This test ensures that email processing is skipped if settings are not configured.
    # In the new flow, initial settings are created at startup, so we call it here.
    from app.crud.settings import create_initial_settings

    create_initial_settings(db_session)
    process_emails(db_session)
    mock_imap.assert_not_called()


@patch("app.services.email_processor.imaplib.IMAP4_SSL")
def test_process_emails_no_move_or_read(mock_imap, db_session: Session):
    """Test processing emails with no move or read."""
    settings_data = SettingsCreate(
        imap_server="imap.test.com",
        imap_username="test@test.com",
        imap_password="password",
        mark_as_read=False,
        move_to_folder=None,
    )
    create_or_update_settings(db_session, settings_data)
    create_newsletter(
        db_session,
        NewsletterCreate(name="Test", sender_emails=["newsletter@example.com"]),
    )

    mock_mail = MagicMock()
    mock_imap.return_value = mock_mail
    mock_mail.login.return_value = ("OK", [b"Login successful"])
    mock_mail.select.return_value = ("OK", [b"1"])
    mock_mail.search.return_value = ("OK", [b"1"])
    mock_msg_bytes = b"From: newsletter@example.com\nSubject: Test Subject\nMessage-ID: <test@test.com>\n\nTest Body"
    mock_mail.fetch.return_value = ("OK", [(None, mock_msg_bytes)])

    process_emails(db_session)

    mock_mail.store.assert_not_called()
    mock_mail.copy.assert_not_called()


@patch("app.services.email_processor.imaplib.IMAP4_SSL")
def test_process_emails_avoids_duplicates(mock_imap, db_session: Session):
    """Test that process_emails avoids processing duplicate emails."""
    settings_data = SettingsCreate(
        imap_server="imap.test.com",
        imap_username="test@test.com",
        imap_password="password",
    )
    create_or_update_settings(db_session, settings_data)
    newsletter_data = NewsletterCreate(
        name="Test Newsletter", sender_emails=["newsletter@example.com"]
    )
    newsletter = create_newsletter(db_session, newsletter_data)

    # Create an entry that already exists
    from app.crud.entries import create_entry
    from app.schemas.entries import EntryCreate

    create_entry(
        db_session,
        EntryCreate(
            subject="Existing Subject",
            body="Existing Body",
            message_id="<existing@message.com>",
        ),
        newsletter.id,
    )

    mock_mail = MagicMock()
    mock_imap.return_value = mock_mail
    mock_mail.login.return_value = ("OK", [b"Login successful"])
    mock_mail.select.return_value = ("OK", [b"1"])
    mock_mail.search.return_value = ("OK", [b"1"])
    # This email has the same Message-ID as the one we just created
    mock_msg_bytes = b"From: newsletter@example.com\nSubject: Test Subject\nMessage-ID: <existing@message.com>\n\nTest Body"
    mock_mail.fetch.return_value = ("OK", [(None, mock_msg_bytes)])

    process_emails(db_session)

    # Verify that no new entry was created
    from app.crud.entries import get_entries_by_newsletter

    entries = get_entries_by_newsletter(db_session, newsletter.id)
    assert len(entries) == 1
    assert entries[0].subject == "Existing Subject"
