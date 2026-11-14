from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.email_processor import _connect_to_imap

IMAP_TIMEOUT_SECONDS = 60


def test_connect_to_imap_sets_a_socket_timeout():
    """The IMAP connection must carry a timeout so a read cannot block forever."""
    settings = SimpleNamespace(imap_server="imap.example.com", imap_username="u", imap_password="p")
    with patch("app.services.email_processor.imaplib.IMAP4_SSL") as mock_ssl:
        mock_ssl.return_value.select.return_value = ("OK", [b"1"])
        _connect_to_imap(settings, "INBOX")
        mock_ssl.assert_called_once_with(
            "imap.example.com", timeout=IMAP_TIMEOUT_SECONDS
        )


def test_health_fails_when_job_runs_too_long(client: TestClient):
    """A job that never returns must turn the health check into a 503."""
    started = datetime.now(UTC) - timedelta(hours=2)
    status = {
        "running": True,
        "job_running": True,
        "interval_minutes": 15,
        "last_started_at": started,
        "last_success_at": started,
        "next_run_at": None,
    }
    with patch("app.routers.health.get_scheduler_status", return_value=status):
        response = client.get("/health")
    assert response.status_code == 503


def test_health_fails_when_last_success_is_stale(client: TestClient):
    """No successful run for more than two intervals must fail health."""
    old = datetime.now(UTC) - timedelta(hours=2)
    status = {
        "running": True,
        "job_running": False,
        "interval_minutes": 15,
        "last_started_at": old,
        "last_success_at": old,
        "next_run_at": None,
    }
    with patch("app.routers.health.get_scheduler_status", return_value=status):
        response = client.get("/health")
    assert response.status_code == 503


def test_health_passes_with_a_recent_success(client: TestClient):
    """A fresh successful run keeps the endpoint green."""
    now = datetime.now(UTC)
    status = {
        "running": True,
        "job_running": False,
        "interval_minutes": 15,
        "last_started_at": now,
        "last_success_at": now,
        "next_run_at": None,
    }
    with patch("app.routers.health.get_scheduler_status", return_value=status):
        response = client.get("/health")
    assert response.status_code == 200
