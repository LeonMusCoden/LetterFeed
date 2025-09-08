from dateutil import tz
from feedgen.feed import FeedGenerator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.entries import get_all_entries, get_entries_by_newsletter
from app.crud.newsletters import get_newsletter_by_identifier


def generate_feed(db: Session, feed_identifier: str):
    """Generate an Atom feed for a given newsletter."""
    newsletter = get_newsletter_by_identifier(db, feed_identifier)
    if not newsletter:
        return None

    entries = get_entries_by_newsletter(db, newsletter.id)

    feed_url = f"{settings.app_base_url}/feeds/{newsletter.slug or newsletter.id}"
    logo_url = f"{settings.app_base_url}/logo.png"
    icon_url = f"{settings.app_base_url}/favicon.ico"

    fg = FeedGenerator()
    fg.id(f"urn:letterfeed:newsletter:{newsletter.id}")
    fg.title(newsletter.name)
    fg.logo(logo_url)
    fg.icon(icon_url)
    fg.link(href=feed_url, rel="self")
    fg.link(href=f"{settings.app_base_url}/", rel="alternate")
    sender_emails = ", ".join([s.email for s in newsletter.senders])
    fg.description(f"A feed of newsletters from {sender_emails}")

    for entry in entries:
        fe = fg.add_entry()
        fe.id(f"urn:letterfeed:entry:{entry.id}")
        fe.title(entry.subject)
        fe.content(entry.body, type="html")
        if entry.received_at.tzinfo is None:
            timezone_aware_received_at = entry.received_at.replace(tzinfo=tz.tzutc())
            fe.published(timezone_aware_received_at)
        else:
            fe.published(entry.received_at)

    return fg.atom_str(pretty=True)


def generate_master_feed(db: Session):
    """Generate a master Atom feed for all newsletters."""
    entries = get_all_entries(db)

    feed_url = f"{settings.app_base_url}/feeds/all"
    logo_url = f"{settings.app_base_url}/logo.png"
    icon_url = f"{settings.app_base_url}/favicon.ico"

    fg = FeedGenerator()
    fg.id("urn:letterfeed:master")
    fg.title("LetterFeed: All Newsletters")
    fg.logo(logo_url)
    fg.icon(icon_url)
    fg.link(href=feed_url, rel="self")
    fg.link(href=f"{settings.app_base_url}/", rel="alternate")
    fg.description("A master feed of all your newsletters.")

    for entry in entries:
        fe = fg.add_entry()
        fe.id(f"urn:letterfeed:entry:{entry.id}")
        fe.title(f"[{entry.newsletter.name}] {entry.subject}")
        fe.content(entry.body, type="html")
        if entry.received_at.tzinfo is None:
            timezone_aware_received_at = entry.received_at.replace(tzinfo=tz.tzutc())
            fe.published(timezone_aware_received_at)
        else:
            fe.published(entry.received_at)

    return fg.atom_str(pretty=True)
