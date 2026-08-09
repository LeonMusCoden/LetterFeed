from datetime import UTC, datetime
from typing import List
from urllib.parse import urlsplit

from dateutil import tz
from fastapi import Request
from feedgen.feed import FeedGenerator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.entries import get_all_entries, get_entries_by_newsletter
from app.crud.newsletters import get_newsletter_by_identifier
from app.models.entries import Entry


def _trusted_hosts() -> set[str]:
    """Hostnames we are willing to reflect into generated feed URLs.

    Derived from the operator-configured APP_BASE_URL and CORS origins. Any
    Host / X-Forwarded-Host outside this set is attacker-controllable and must
    NOT be trusted: it would otherwise be baked into the cached feed's self /
    alternate / logo links and served to every subscriber (cache poisoning).
    """
    hosts: set[str] = set()
    for origin in (settings.app_base_url, *settings.cors_origins_list):
        netloc = urlsplit(origin if "://" in origin else f"//{origin}").netloc.lower()
        if netloc and "backend:8000" not in netloc:
            hosts.add(netloc)
    return hosts


def _get_base_url(
    request: Request | None = None, base_url_param: str | None = None
) -> str:
    """Determine the application base URL dynamically from request headers or config."""
    if request is not None:
        trusted = _trusted_hosts()
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto", "http")
        # Only reflect a forwarded/Host header if it matches a configured host,
        # so an arbitrary attacker-supplied header can't poison the feed.
        if forwarded_host and forwarded_host.lower() in trusted:
            return f"{forwarded_proto}://{forwarded_host}".rstrip("/")

        # If base_url_param is provided, use it if it's not the internal backend host
        if base_url_param and "backend:8000" not in base_url_param:
            return base_url_param.rstrip("/")

        # Fallback to standard Host header if it is a configured host
        host = request.headers.get("host")
        if host and host.lower() in trusted:
            return f"{request.url.scheme}://{host}".rstrip("/")

    if base_url_param and "backend:8000" not in base_url_param:
        return base_url_param.rstrip("/")

    # Fallback to settings.app_base_url
    url = settings.app_base_url.rstrip("/")
    if url.endswith("/api"):
        url = url[:-4]
    return url


def _create_feed_generator(
    feed_id: str,
    title: str,
    feed_url: str,
    description: str,
    base_url: str | None = None,
) -> FeedGenerator:
    """Initialize and configures a FeedGenerator instance."""
    url = (base_url or settings.app_base_url).rstrip("/")
    logo_url = f"{url}/logo.png"
    icon_url = f"{url}/favicon.ico"

    fg = FeedGenerator()
    fg.id(feed_id)
    fg.title(title)
    fg.logo(logo_url)
    fg.icon(icon_url)
    fg.link(href=feed_url, rel="self")
    fg.link(href=f"{url}/", rel="alternate")
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

        received_at = entry.received_at
        if received_at is None:
            received_at = datetime.now(UTC)

        if received_at.tzinfo is None:
            timezone_aware_received_at = received_at.replace(tzinfo=tz.tzutc())
            fe.published(timezone_aware_received_at)
            fe.updated(timezone_aware_received_at)
        else:
            fe.published(received_at)
            fe.updated(received_at)


def generate_feed(
    db: Session,
    feed_identifier: str,
    base_url: str | None = None,
    request: Request | None = None,
    limit: int | None = None,
):
    """Generate an Atom feed for a given newsletter."""
    newsletter = get_newsletter_by_identifier(db, feed_identifier)
    if not newsletter:
        return None

    entries = get_entries_by_newsletter(db, newsletter.id, limit=limit)

    url = _get_base_url(request, base_url)
    feed_url = f"{url}/api/feeds/{newsletter.slug or newsletter.id}"
    sender_emails = ", ".join([s.email for s in newsletter.senders])
    description = f"A feed of newsletters from {sender_emails}"

    fg = _create_feed_generator(
        feed_id=f"urn:letterfeed:newsletter:{newsletter.id}",
        title=newsletter.name,
        feed_url=feed_url,
        description=description,
        base_url=url,
    )

    _add_entries_to_feed(fg, entries)

    return fg.atom_str(pretty=False)


def generate_master_feed(
    db: Session,
    base_url: str | None = None,
    request: Request | None = None,
):
    """Generate a master Atom feed for all newsletters."""
    entries = get_all_entries(db, limit=settings.master_feed_limit)

    url = _get_base_url(request, base_url)
    feed_url = f"{url}/api/feeds/all"

    fg = _create_feed_generator(
        feed_id="urn:letterfeed:master",
        title="LetterFeed: All Newsletters",
        feed_url=feed_url,
        description="A master feed of all your newsletters.",
        base_url=url,
    )

    _add_entries_to_feed(fg, entries, is_master_feed=True)

    return fg.atom_str(pretty=False)
