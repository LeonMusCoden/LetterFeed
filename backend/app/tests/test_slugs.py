from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.slug import sanitize_slug, slugify_name
from app.crud.newsletters import create_newsletter
from app.schemas.newsletters import NewsletterCreate


@pytest.mark.parametrize(
    "input_slug, expected_slug",
    [
        ("Hello World", "hello-world"),
        ("  leading and trailing spaces  ", "leading-and-trailing-spaces"),
        ("!@#$%^&*()", None),
        ("a-b_c d", "a-b-c-d"),
        ("SLUG IN CAPS", "slug-in-caps"),
        (None, None),
        ("", None),
    ],
)
def test_sanitize_slug(input_slug, expected_slug):
    """Test the slug sanitization function with various inputs."""
    assert sanitize_slug(input_slug) == expected_slug


@pytest.mark.parametrize(
    "name, expected_slug",
    [
        ("Foo & Bar", "foo-bar"),
        ("Caf\u00e9 D\u00e9j\u00e0 Vu", "cafe-deja-vu"),
        ("What's New?", "whats-new"),
        ("Morning\u2014Brief", "morning-brief"),
        ("\u041a\u0438\u0440\u0438\u043b\u043b", None),
    ],
)
def test_slugify_name(name, expected_slug):
    """Test creating pretty, URL-safe slugs from newsletter names."""
    assert slugify_name(name) == expected_slug


def test_sanitize_slug_preserves_legacy_repeated_hyphens():
    """Test keeping existing custom feed URLs stable when they are revalidated."""
    assert sanitize_slug("daily--brief") == "daily--brief"


def test_create_newsletter_with_slug(client: TestClient, db_session: Session):
    """Test creating a newsletter with a custom slug."""
    newsletter_data = {
        "name": "My Test Newsletter",
        "slug": "my-custom-slug",
        "sender_emails": ["test@example.com"],
    }
    response = client.post("/newsletters", json=newsletter_data)
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "my-custom-slug"

    # Verify the feed URL uses the slug
    feed_response = client.get(f"/feeds/{data['slug']}")
    assert feed_response.status_code == 200


def test_create_newsletter_with_sanitization(client: TestClient, db_session: Session):
    """Test creating a newsletter with a slug that needs sanitization."""
    newsletter_data = {
        "name": "Another Test",
        "slug": "  Another Slug With Spaces!  ",
        "sender_emails": ["test2@example.com"],
    }
    response = client.post("/newsletters", json=newsletter_data)
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "another-slug-with-spaces"


def test_create_newsletter_without_slug(client: TestClient, db_session: Session):
    """Test deriving a slug from the name when one is not supplied."""
    newsletter_data = {
        "name": "No Slug Newsletter",
        "sender_emails": ["no-slug@example.com"],
    }
    response = client.post("/newsletters", json=newsletter_data)
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "no-slug-newsletter"

    # Verify the feed URL uses the generated slug
    feed_response = client.get(f"/feeds/{data['slug']}")
    assert feed_response.status_code == 200


def test_create_newsletter_with_blank_slug(client: TestClient, db_session: Session):
    """Test the blank slug sent by the manual add form."""
    response = client.post(
        "/newsletters",
        json={
            "name": "The Daily & Weekly",
            "slug": "",
            "sender_emails": ["daily-weekly@example.com"],
        },
    )

    assert response.status_code == 200
    assert response.json()["slug"] == "the-daily-weekly"


def test_create_newsletters_with_duplicate_generated_slugs(
    client: TestClient, db_session: Session
):
    """Test suffixing generated slugs when newsletter names match."""
    first_response = client.post(
        "/newsletters",
        json={
            "name": "Daily Brief",
            "sender_emails": ["first-daily@example.com"],
        },
    )
    second_response = client.post(
        "/newsletters",
        json={
            "name": "Daily Brief",
            "sender_emails": ["second-daily@example.com"],
        },
    )

    assert first_response.status_code == 200
    assert first_response.json()["slug"] == "daily-brief"
    assert second_response.status_code == 200
    assert second_response.json()["slug"] == "daily-brief-2"


def test_generated_slug_retries_after_unique_constraint_race():
    """Test retrying when a generated slug is taken during insertion."""
    db = MagicMock(spec=Session)
    db.commit.side_effect = [
        IntegrityError("INSERT", {}, Exception("unique constraint")),
        None,
        None,
    ]
    newsletter_data = NewsletterCreate(
        name="Daily Brief", sender_emails=["race@example.com"]
    )

    with patch(
        "app.crud.newsletters._generate_unique_slug",
        side_effect=["daily-brief", "daily-brief-2"],
    ):
        newsletter = create_newsletter(db, newsletter_data)

    assert newsletter.slug == "daily-brief-2"
    db.rollback.assert_called_once()


def test_generated_slug_avoids_reserved_feed_path(
    client: TestClient, db_session: Session
):
    """Test avoiding the master feed's reserved `all` path."""
    response = client.post(
        "/newsletters",
        json={"name": "All", "sender_emails": ["all@example.com"]},
    )

    assert response.status_code == 200
    assert response.json()["slug"] == "all-2"


def test_non_slugifiable_name_falls_back_to_id(
    client: TestClient, db_session: Session
):
    """Test retaining the ID fallback when a safe ASCII slug cannot be made."""
    response = client.post(
        "/newsletters",
        json={"name": "\u041a\u0438\u0440\u0438\u043b\u043b", "sender_emails": ["cyrillic@example.com"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] is None
    assert client.get(f"/feeds/{data['id']}").status_code == 200


def test_create_newsletter_with_conflicting_slug(
    client: TestClient, db_session: Session
):
    """Test creating a newsletter with a slug that already exists."""
    # Create the first newsletter
    client.post(
        "/newsletters",
        json={
            "name": "First",
            "slug": "conflict-slug",
            "sender_emails": ["first@example.com"],
        },
    )

    # Attempt to create a second one with the same slug
    response = client.post(
        "/newsletters",
        json={
            "name": "Second",
            "slug": "conflict-slug",
            "sender_emails": ["second@example.com"],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Slug already in use"


def test_update_newsletter_with_conflicting_slug(
    client: TestClient, db_session: Session
):
    """Test updating a newsletter to a slug that is already in use by another newsletter."""
    # Create two newsletters
    response1 = client.post(
        "/newsletters",
        json={"name": "First", "slug": "first-slug", "sender_emails": ["1@test.com"]},
    )
    newsletter1_id = response1.json()["id"]

    client.post(
        "/newsletters",
        json={"name": "Second", "slug": "second-slug", "sender_emails": ["2@test.com"]},
    )

    # Try to update the first newsletter to use the second's slug
    update_data = {
        "name": "First Updated",
        "slug": "second-slug",
        "sender_emails": ["1@test.com"],
    }
    response = client.put(f"/newsletters/{newsletter1_id}", json=update_data)
    assert response.status_code == 409
    assert response.json()["detail"] == "Slug already in use"


def test_update_newsletter_keeps_generated_slug_when_slug_is_omitted(
    client: TestClient, db_session: Session
):
    """Test preserving a generated feed URL when only the name changes."""
    create_response = client.post(
        "/newsletters",
        json={"name": "Original Name", "sender_emails": ["rename@example.com"]},
    )
    newsletter_id = create_response.json()["id"]

    update_response = client.put(
        f"/newsletters/{newsletter_id}",
        json={"name": "Renamed", "sender_emails": ["rename@example.com"]},
    )

    assert update_response.status_code == 200
    assert update_response.json()["slug"] == "original-name"


def test_update_newsletter_rejects_reserved_slug(
    client: TestClient, db_session: Session
):
    """Test preventing updates from shadowing the master feed route."""
    create_response = client.post(
        "/newsletters",
        json={"name": "Original", "sender_emails": ["reserved@example.com"]},
    )
    newsletter_id = create_response.json()["id"]

    update_response = client.put(
        f"/newsletters/{newsletter_id}",
        json={
            "name": "Original",
            "slug": "all",
            "sender_emails": ["reserved@example.com"],
        },
    )

    assert update_response.status_code == 409
    assert update_response.json()["detail"] == "Slug already in use"
