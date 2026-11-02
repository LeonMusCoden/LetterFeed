import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.crud.settings import create_or_update_settings
from app.schemas.settings import SettingsCreate
from app.services.email_processor import EmailProcessingError


def test_health_check(client: TestClient):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_update_imap_settings(client: TestClient):
    """Test updating IMAP settings."""
    settings_data = {
        "imap_server": "imap.example.com",
        "imap_username": "test@example.com",
        "imap_password": "password",
        "search_folder": "INBOX",
        "move_to_folder": "Processed",
        "mark_as_read": True,
    }
    response = client.post("/imap/settings", json=settings_data)
    assert response.status_code == 200
    assert response.json()["imap_server"] == "imap.example.com"
    assert response.json()["imap_username"] == "test@example.com"
    assert response.json()["search_folder"] == "INBOX"
    assert response.json()["move_to_folder"] == "Processed"
    assert response.json()["mark_as_read"]


def test_get_imap_settings(client: TestClient):
    """Test getting IMAP settings."""
    settings_data = {
        "imap_server": "imap.example.com",
        "imap_username": "test@example.com",
        "imap_password": "password",
        "search_folder": "INBOX",
        "move_to_folder": "Processed",
        "mark_as_read": True,
    }
    client.post("/imap/settings", json=settings_data)

    response = client.get("/imap/settings")
    assert response.status_code == 200
    assert response.json()["imap_server"] == "imap.example.com"
    assert response.json()["imap_username"] == "test@example.com"


@patch("app.core.imap.imaplib.IMAP4_SSL")
def test_test_imap_connection(mock_imap, client: TestClient, db_session: Session):
    """Test the IMAP connection."""
    mock_imap.return_value.login.return_value = (None, None)
    mock_imap.return_value.logout.return_value = (None, None)

    settings_data = SettingsCreate(
        imap_server="imap.example.com",
        imap_username="test@example.com",
        imap_password="password",
        search_folder="INBOX",
        move_to_folder="Processed",
        mark_as_read=True,
    )
    create_or_update_settings(db_session, settings_data)

    response = client.post("/imap/test")
    assert response.status_code == 200
    assert response.json() == {"message": "Connection successful"}


@patch("app.core.imap.imaplib.IMAP4_SSL")
def test_get_imap_folders(mock_imap, client: TestClient, db_session: Session):
    """Test getting IMAP folders."""
    mock_imap.return_value.login.return_value = (None, None)
    mock_imap.return_value.logout.return_value = (None, None)
    mock_imap.return_value.list.return_value = (
        "OK",
        [b'(NOCONNECT NOSELECT) "/" "INBOX"', b'(NOCONNECT NOSELECT) "/" "Processed"'],
    )

    settings_data = SettingsCreate(
        imap_server="imap.example.com",
        imap_username="test@example.com",
        imap_password="password",
        search_folder="INBOX",
        move_to_folder="Processed",
        mark_as_read=True,
    )
    create_or_update_settings(db_session, settings_data)

    response = client.get("/imap/folders")
    assert response.status_code == 200
    assert response.json() == ["INBOX", "Processed"]


@patch("app.routers.imap.process_emails")
def test_trigger_email_processing(mock_process_emails, client: TestClient):
    """Test triggering email processing manually."""
    response = client.post("/imap/process")
    assert response.status_code == 200
    assert response.json() == {"message": "Email processing triggered successfully."}
    mock_process_emails.assert_called_once()


@patch("app.routers.imap.process_emails")
def test_trigger_email_processing_error(mock_process_emails, client: TestClient):
    """Test that an email processing error is returned to the client."""
    mock_process_emails.side_effect = EmailProcessingError(
        "Could not connect to IMAP server: [AUTHENTICATIONFAILED] Invalid credentials"
    )
    response = client.post("/imap/process")
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Could not connect to IMAP server: [AUTHENTICATIONFAILED] Invalid credentials"
    }


def test_create_newsletter(client: TestClient):
    """Test creating a newsletter."""
    unique_email = f"newsletter_{uuid.uuid4()}@example.com"
    newsletter_data = {"name": "Example Newsletter", "sender_emails": [unique_email]}
    response = client.post("/newsletters", json=newsletter_data)
    assert response.status_code == 200
    assert response.json()["name"] == "Example Newsletter"
    assert response.json()["is_active"]
    assert len(response.json()["senders"]) == 1
    assert response.json()["senders"][0]["email"] == unique_email


def test_get_newsletters(client: TestClient):
    """Test getting all newsletters."""
    unique_email = f"newsletter_{uuid.uuid4()}@example.com"
    newsletter_data = {"name": "Another Newsletter", "sender_emails": [unique_email]}
    client.post("/newsletters", json=newsletter_data)

    response = client.get("/newsletters")
    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert any(
        unique_email in [s["email"] for s in nl["senders"]] for nl in response.json()
    )


def test_get_single_newsletter(client: TestClient):
    """Test getting a single newsletter."""
    unique_email = f"newsletter_{uuid.uuid4()}@example.com"
    newsletter_data = {"name": "Third Newsletter", "sender_emails": [unique_email]}
    create_response = client.post("/newsletters", json=newsletter_data)
    newsletter_id = create_response.json()["id"]

    response = client.get(f"/newsletters/{newsletter_id}")
    assert response.status_code == 200
    assert response.json()["senders"][0]["email"] == unique_email


def test_get_nonexistent_newsletter(client: TestClient):
    """Test getting a nonexistent newsletter."""
    response = client.get("/newsletters/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Newsletter not found"}


def test_get_newsletter_feed(client: TestClient):
    """Test generating a newsletter feed."""
    unique_email = f"feed_test_{uuid.uuid4()}@example.com"
    newsletter_data = {"name": "Feed Test Newsletter", "sender_emails": [unique_email]}
    create_response = client.post("/newsletters", json=newsletter_data)
    newsletter_id = create_response.json()["id"]

    # Add some entries to the newsletter
    entry_data_1 = {
        "subject": "Test Entry 1",
        "body": "<p>Content 1</p>",
        "message_id": f"<entry1_{uuid.uuid4()}@test.com>",
    }
    client.post(f"/newsletters/{newsletter_id}/entries", json=entry_data_1)
    entry_data_2 = {
        "subject": "Test Entry 2",
        "body": "<p>Content 2</p>",
        "message_id": f"<entry2_{uuid.uuid4()}@test.com>",
    }
    client.post(f"/newsletters/{newsletter_id}/entries", json=entry_data_2)

    response = client.get(f"/feeds/{newsletter_id}")
    assert response.status_code == 200
    assert "application/atom+xml" in response.headers["content-type"]
    assert "<title>Feed Test Newsletter</title>" in response.text
    import xml.etree.ElementTree as ET

    root = ET.fromstring(response.text)
    # Atom feed uses a namespace, so we need to include it in our tag searches
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    links = root.findall("atom:link", ns)
    assert any(link.get("rel") == "alternate" and link.get("href") for link in links)
    logo = root.find("atom:logo", ns)
    assert logo is not None
    icon = root.find("atom:icon", ns)
    assert icon is not None
    entry_titles = [
        entry.find("atom:title", ns).text for entry in root.findall("atom:entry", ns)
    ]
    assert "Test Entry 1" in entry_titles
    assert "Test Entry 2" in entry_titles


def test_get_newsletter_feed_nonexistent_newsletter(client: TestClient):
    """Test generating a feed for a nonexistent newsletter."""
    response = client.get("/feeds/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Newsletter not found"}
