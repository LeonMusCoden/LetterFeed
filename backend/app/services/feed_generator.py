from typing import List

from dateutil import tz
from feedgen.feed import FeedGenerator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.entries import get_all_entries, get_entries_by_newsletter
from app.crud.newsletters import get_newsletter_by_identifier
from app.models.entries import Entry


def _create_feed_generator(
    feed_id: str, title: str, feed_url: str, description: str
) -> FeedGenerator:
    """Initialize and configures a FeedGenerator instance."""
    logo_url = f"{settings.app_base_url}/logo.png"
    icon_url = f"{settings.app_base_url}/favicon.ico"

    fg = FeedGenerator()
    fg.id(feed_id)
    fg.title(title)
    fg.logo(logo_url)
    fg.icon(icon_url)
    fg.link(href=feed_url, rel="self")
    fg.link(href=f"{settings.app_base_url}/", rel="alternate")
    fg.description(description)
    return fg


def _add_entries_to_feed(
    fg: FeedGenerator, entries: List[Entry], is_master_feed: bool = False
):
    """Add a list of entries to a FeedGenerator instance."""
    for entry in entries:
        fe = fg.add_entry()
        fe.id(f"urn:letterfeed:entry:{entry.id}")
        fe.title(
            f"[{entry.newsletter.name}] {entry.subject}"
            if is_master_feed
            else entry.subject
        )
        fe.content(entry.body, type="html")

        if entry.received_at.tzinfo is None:
            timezone_aware_received_at = entry.received_at.replace(tzinfo=tz.tzutc())
            fe.published(timezone_aware_received_at)
            fe.updated(timezone_aware_received_at)
        else:
            fe.published(entry.received_at)
            fe.updated(entry.received_at)


def generate_feed(db: Session, feed_identifier: str):
    """Generate an Atom feed for a given newsletter."""
    newsletter = get_newsletter_by_identifier(db, feed_identifier)
    if not newsletter:
        return None

    entries = get_entries_by_newsletter(db, newsletter.id)

    feed_url = f"{settings.app_base_url}/feeds/{newsletter.slug or newsletter.id}"
    sender_emails = ", ".join([s.email for s in newsletter.senders])
    description = f"A feed of newsletters from {sender_emails}"

    fg = _create_feed_generator(
        feed_id=f"urn:letterfeed:newsletter:{newsletter.id}",
        title=newsletter.name,
        feed_url=feed_url,
        description=description,
    )

    _add_entries_to_feed(fg, entries)

    return fg.atom_str(pretty=True)


def generate_master_feed(db: Session):
    """Generate a master Atom feed for all newsletters."""
    entries = get_all_entries(db)

    feed_url = f"{settings.app_base_url}/feeds/all"

    fg = _create_feed_generator(
        feed_id="urn:letterfeed:master",
        title="LetterFeed: All Newsletters",
        feed_url=feed_url,
        description="A master feed of all your newsletters.",
    )

    _add_entries_to_feed(fg, entries, is_master_feed=True)

    return fg.atom_str(pretty=True)
