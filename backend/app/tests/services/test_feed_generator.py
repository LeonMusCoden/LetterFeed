from unittest.mock import MagicMock, patch

import pytest
from feedgen.feed import FeedGenerator

from app.services.feed_generator import generate_feed, generate_master_feed


@pytest.fixture
def mock_db_session():
    """Fixture for a mock database session."""
    return MagicMock()


@patch("app.services.feed_generator.settings")
def test_generate_master_feed_respects_limit(mock_settings, mock_db_session):
    """Test that the master feed generation respects the MASTER_FEED_LIMIT."""
    # Arrange
    limit = 5
    mock_settings.master_feed_limit = limit

    # Create more mock entries than the limit
    mock_entries = [MagicMock() for _ in range(limit + 5)]

    with (
        patch(
            "app.services.feed_generator.get_all_entries", return_value=mock_entries
        ) as mock_get_all_entries,
        patch(
            "app.services.feed_generator._create_feed_generator"
        ) as mock_create_feed_generator,
        patch(
            "app.services.feed_generator._add_entries_to_feed"
        ) as mock_add_entries_to_feed,
    ):
        mock_fg = MagicMock(spec=FeedGenerator)
        mock_create_feed_generator.return_value = mock_fg
        mock_fg.atom_str.return_value = "fake_atom_string"

        # Act
        result = generate_master_feed(mock_db_session)

        # Assert
        mock_get_all_entries.assert_called_once_with(mock_db_session, limit=limit)
        mock_create_feed_generator.assert_called_once()
        mock_add_entries_to_feed.assert_called_once_with(
            mock_fg, mock_entries, is_master_feed=True
        )
        assert result == "fake_atom_string"


@patch("app.services.feed_generator.settings")
def test_generate_feed_respects_newsletter_limit(mock_settings, mock_db_session):
    """Test that a newsletter feed generation respects NEWSLETTER_FEED_LIMIT."""
    # Arrange
    limit = 5
    mock_settings.newsletter_feed_limit = limit
    mock_settings.app_base_url = "http://backend:8000"

    mock_newsletter = MagicMock()
    mock_newsletter.id = "abc123"
    mock_newsletter.slug = "newsletter"
    mock_newsletter.name = "Newsletter"
    mock_newsletter.senders = []

    mock_entries = [MagicMock() for _ in range(limit)]

    with (
        patch(
            "app.services.feed_generator.get_newsletter_by_identifier",
            return_value=mock_newsletter,
        ),
        patch(
            "app.services.feed_generator.get_entries_by_newsletter",
            return_value=mock_entries,
        ) as mock_get_entries,
        patch(
            "app.services.feed_generator._create_feed_generator"
        ) as mock_create_feed_generator,
        patch(
            "app.services.feed_generator._add_entries_to_feed"
        ) as mock_add_entries_to_feed,
    ):
        mock_fg = MagicMock(spec=FeedGenerator)
        mock_create_feed_generator.return_value = mock_fg
        mock_fg.atom_str.return_value = "fake_atom_string"

        # Act
        result = generate_feed(mock_db_session, "abc123")

        # Assert
        mock_get_entries.assert_called_once_with(
            mock_db_session, mock_newsletter.id, limit=limit
        )
        mock_add_entries_to_feed.assert_called_once_with(mock_fg, mock_entries)
        assert result == "fake_atom_string"
