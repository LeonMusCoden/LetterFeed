import uuid
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.crud.entries import create_entry, get_entries_by_newsletter
from app.crud.newsletters import (
    create_newsletter,
    get_newsletter_by_identifier,
    get_newsletters,
)
from app.crud.settings import create_or_update_settings, get_settings
from app.schemas.entries import EntryCreate
from app.schemas.newsletters import NewsletterCreate
from app.schemas.settings import SettingsCreate


def test_create_or_update_settings(db_session: Session):
    """Test creating or updating settings."""
    settings_data = SettingsCreate(
        imap_server="imap.test.com",
        imap_username="test@test.com",
        imap_password="password",
        search_folder="INBOX",
        move_to_folder="Archive",
        mark_as_read=True,
        auth_username="user",
        auth_password="password",
    )
    settings = create_or_update_settings(db_session, settings_data)
    assert settings.imap_server == "imap.test.com"
    assert settings.mark_as_read
    assert settings.auth_username == "user"

    # check password hash
    from app.models.settings import Settings as SettingsModel

    db_settings = db_session.query(SettingsModel).first()
    assert db_settings.auth_password_hash is not None

    updated_settings_data = SettingsCreate(
        imap_server="imap.updated.com",
        imap_username="updated@test.com",
        imap_password="new_password",
        search_folder="Inbox",
        move_to_folder=None,
        mark_as_read=False,
        auth_username="new_user",
    )
    updated_settings = create_or_update_settings(db_session, updated_settings_data)
    assert updated_settings.imap_server == "imap.updated.com"
    assert not updated_settings.mark_as_read
    assert updated_settings.move_to_folder is None
    assert updated_settings.auth_username == "new_user"


def test_get_settings(db_session: Session):
    """Test getting settings."""
    settings_data = SettingsCreate(
        imap_server="imap.get.com",
        imap_username="get@test.com",
        imap_password="get_password",
        search_folder="INBOX",
        move_to_folder=None,
        mark_as_read=False,
    )
    create_or_update_settings(db_session, settings_data)
    settings = get_settings(db_session)
    assert settings.imap_server == "imap.get.com"


def test_get_settings_with_env_override(db_session: Session):
    """Test getting settings with environment variable override."""
    # 1. Create initial settings in the database
    db_settings_data = SettingsCreate(
        imap_server="db.imap.com",
        imap_username="db_user",
        imap_password="db_pass",
        email_check_interval=15,
        auth_username="db_user",
        auth_password="db_password",
    )
    create_or_update_settings(db_session, db_settings_data)

    # 2. Patch the env_settings to simulate environment variables
    with patch("app.crud.settings.env_settings") as mock_env_settings:
        mock_env_settings.model_dump.return_value = {
            "imap_server": "env.imap.com",
            "imap_username": "env_user",
            "imap_password": "env_pass",
            "email_check_interval": 30,
            "auth_username": "env_auth_user",
            "auth_password": "env_auth_password",
        }
        mock_env_settings.imap_password = "env_pass"
        mock_env_settings.auth_password = "env_auth_password"

        # 3. Call get_settings and assert the override
        settings = get_settings(db_session, with_password=True)
        assert settings.imap_server == "env.imap.com"
        assert settings.imap_username == "env_user"
        assert settings.imap_password == "env_pass"
        assert settings.email_check_interval == 30
        assert settings.auth_username == "env_auth_user"
        assert "imap_server" in settings.locked_fields
        assert "imap_username" in settings.locked_fields
        assert "auth_username" in settings.locked_fields

        # 4. Call create_or_update_settings and assert that locked fields are not updated
        update_data = SettingsCreate(
            imap_server="new.imap.com",
            imap_username="new_user",
            imap_password="new_pass",
            email_check_interval=45,
            auth_username="new_auth_user",
            auth_password="new_auth_password",
        )
        updated_settings = create_or_update_settings(db_session, update_data)
        assert updated_settings.imap_server == "env.imap.com"  # Should not change
        assert updated_settings.imap_username == "env_user"  # Should not change
        assert updated_settings.email_check_interval == 30  # Should not change
        assert updated_settings.auth_username == "env_auth_user"  # Should not change


def test_create_newsletter(db_session: Session):
    """Test creating a newsletter."""
    unique_email = f"sender_{uuid.uuid4()}@test.com"
    newsletter_data = NewsletterCreate(
        name="Test Newsletter 1", sender_emails=[unique_email]
    )
    newsletter = create_newsletter(db_session, newsletter_data)
    assert newsletter.name == "Test Newsletter 1"
    assert newsletter.is_active
    assert len(newsletter.senders) == 1
    assert newsletter.senders[0].email == unique_email


def test_create_newsletter_with_move_to_folder(db_session: Session):
    """Test creating a newsletter with the move_to_folder attribute."""
    unique_email = f"sender_{uuid.uuid4()}@test.com"
    newsletter_data = NewsletterCreate(
        name="Test Newsletter with Folder",
        sender_emails=[unique_email],
        move_to_folder="Archive/Test",
        extract_content=True,
    )
    newsletter = create_newsletter(db_session, newsletter_data)
    retrieved_newsletter = get_newsletter_by_identifier(db_session, newsletter.id)

    assert retrieved_newsletter.name == "Test Newsletter with Folder"
    assert retrieved_newsletter.move_to_folder == "Archive/Test"
    assert retrieved_newsletter.extract_content is True


def test_get_newsletter_by_identifier(db_session: Session):
    """Test getting a single newsletter."""
    unique_email = f"sender_{uuid.uuid4()}@test.com"
    newsletter_data = NewsletterCreate(
        name="Test Newsletter 2", sender_emails=[unique_email]
    )
    created_newsletter = create_newsletter(db_session, newsletter_data)
    newsletter = get_newsletter_by_identifier(db_session, created_newsletter.id)
    assert newsletter.name == "Test Newsletter 2"
    assert len(newsletter.senders) == 1
    assert newsletter.senders[0].email == unique_email


def test_get_newsletters(db_session: Session):
    """Test getting multiple newsletters."""
    create_newsletter(
        db_session,
        NewsletterCreate(
            name="Test Newsletter 3", sender_emails=[f"sender_{uuid.uuid4()}@test.com"]
        ),
    )
    create_newsletter(
        db_session,
        NewsletterCreate(
            name="Test Newsletter 4", sender_emails=[f"sender_{uuid.uuid4()}@test.com"]
        ),
    )
    newsletters = get_newsletters(db_session)
    assert len(newsletters) >= 2


def test_create_entry(db_session: Session):
    """Test creating a newsletter entry."""
    unique_email = f"sender_{uuid.uuid4()}@test.com"
    newsletter_data = NewsletterCreate(
        name="Test Newsletter 5", sender_emails=[unique_email]
    )
    newsletter = create_newsletter(db_session, newsletter_data)
    entry_data = EntryCreate(
        subject="Test Subject",
        body="Test Body",
        message_id=f"<{uuid.uuid4()}@test.com>",
    )
    entry = create_entry(db_session, entry_data, newsletter.id)
    assert entry.subject == "Test Subject"
    assert entry.newsletter_id == newsletter.id


def test_get_entries_by_newsletter(db_session: Session):
    """Test getting entries for a newsletter."""
    unique_email = f"sender_{uuid.uuid4()}@test.com"
    newsletter_data = NewsletterCreate(
        name="Test Newsletter 6", sender_emails=[unique_email]
    )
    newsletter = create_newsletter(db_session, newsletter_data)
    create_entry(
        db_session,
        EntryCreate(
            subject="Entry 1", body="Body 1", message_id=f"<{uuid.uuid4()}@test.com>"
        ),
        newsletter.id,
    )
    create_entry(
        db_session,
        EntryCreate(
            subject="Entry 2", body="Body 2", message_id=f"<{uuid.uuid4()}@test.com>"
        ),
        newsletter.id,
    )
    entries = get_entries_by_newsletter(db_session, newsletter.id)
    assert len(entries) == 2
    assert entries[0].subject == "Entry 1"


def test_update_newsletter(db_session: Session):
    """Test updating a newsletter."""
    unique_email = f"sender_{uuid.uuid4()}@test.com"
    newsletter_data = NewsletterCreate(
        name="Newsletter to Update",
        sender_emails=[unique_email],
        move_to_folder="OldFolder",
        extract_content=False,
    )
    newsletter = create_newsletter(db_session, newsletter_data)

    from app.schemas.newsletters import NewsletterUpdate

    updated_email = f"updated_sender_{uuid.uuid4()}@test.com"
    updated_newsletter_data = NewsletterUpdate(
        name="Updated Newsletter",
        sender_emails=[updated_email],
        move_to_folder="NewFolder",
        extract_content=True,
    )
    from app.crud.newsletters import update_newsletter

    updated_newsletter = update_newsletter(
        db_session, newsletter.id, updated_newsletter_data
    )

    assert updated_newsletter.name == "Updated Newsletter"
    assert len(updated_newsletter.senders) == 1
    assert updated_newsletter.senders[0].email == updated_email
    assert updated_newsletter.move_to_folder == "NewFolder"
    assert updated_newsletter.extract_content is True


def test_delete_newsletter(db_session: Session):
    """Test deleting a newsletter."""
    unique_email = f"sender_{uuid.uuid4()}@test.com"
    newsletter_data = NewsletterCreate(
        name="Newsletter to Delete", sender_emails=[unique_email]
    )
    newsletter = create_newsletter(db_session, newsletter_data)

    from app.crud.newsletters import delete_newsletter

    deleted_newsletter = delete_newsletter(db_session, newsletter.id)

    assert deleted_newsletter.id == newsletter.id
    assert deleted_newsletter.name == "Newsletter to Delete"

    # Verify it's actually deleted
    from app.crud.newsletters import get_newsletter_by_identifier

    assert get_newsletter_by_identifier(db_session, newsletter.id) is None
