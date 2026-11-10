"""Tests for the newsletter pagination used by the ingestion job."""

from sqlalchemy.orm import Session

from app.crud.newsletters import create_newsletter
from app.schemas.newsletters import NewsletterCreate
from app.services.email_processor import _get_all_newsletters


def test_get_all_newsletters_returns_more_than_the_crud_default(db_session: Session):
    """Every newsletter must be loaded, not only the first hundred."""
    total = 150
    for index in range(total):
        create_newsletter(
            db_session,
            NewsletterCreate(
                name=f"Newsletter {index}",
                sender_emails=[f"sender{index}@example.com"],
            ),
        )

    newsletters = _get_all_newsletters(db_session)

    assert len(newsletters) == total
