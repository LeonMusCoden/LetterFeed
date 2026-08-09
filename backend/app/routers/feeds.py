import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import is_auth_enabled
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.crud.entries import get_latest_entry_timestamp_cached, get_metadata_version
from app.crud.feed_cache import get_cached_feed, set_cached_feed
from app.crud.newsletters import get_newsletter_identity
from app.crud.settings import get_master_feed_token
from app.services.feed_generator import generate_feed, generate_master_feed

logger = get_logger(__name__)
router = APIRouter()


def _generate_etag(identifier: str, timestamp: datetime | None) -> str:
    """Generate an ETag from the feed identity, latest entry timestamp, and metadata.

    The newsletter-metadata version is folded in so renames/sender edits/deletes
    (which don't advance the latest timestamp) still change the ETag.
    """
    # isoformat is timezone-independent; .timestamp() on a naive datetime would
    # assume the server's local timezone and change the ETag across environments.
    ts_str = timestamp.isoformat() if timestamp else "empty"
    parts = [identifier, ts_str, get_metadata_version()]
    etag_raw = "-".join(parts)
    return f'"{hashlib.md5(etag_raw.encode()).hexdigest()}"'


def _to_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime, assuming naive values are UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _not_modified(
    latest_timestamp: datetime | None,
    etag: str,
    if_none_match: str | None,
    if_modified_since: str | None,
) -> bool:
    """Return True if the client's cached copy is still current (send 304)."""
    if if_none_match == etag:
        logger.debug("Feed unmodified (ETag match), returning 304")
        return True

    if if_modified_since and latest_timestamp:
        try:
            ims_datetime = parsedate_to_datetime(if_modified_since)
            latest_utc = _to_utc(latest_timestamp)
            if latest_utc.replace(microsecond=0) <= ims_datetime.replace(microsecond=0):
                logger.debug("Feed unmodified since If-Modified-Since, returning 304")
                return True
        except Exception as e:
            logger.warning(f"Error parsing If-Modified-Since header: {e}")

    return False


def _feed_headers(etag: str, latest_timestamp: datetime | None) -> dict[str, str]:
    """Build the response headers common to every feed response."""
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=60, stale-while-revalidate=300",
        "Vary": "Accept-Encoding",
    }
    if latest_timestamp:
        headers["Last-Modified"] = format_datetime(
            _to_utc(latest_timestamp), usegmt=True
        )
    return headers


def _conditional_feed_response(
    db: Session,
    cache_key: str,
    latest_timestamp: datetime | None,
    if_none_match: str | None,
    if_modified_since: str | None,
    generate_fn: Callable[[], str | bytes | None],
    is_head: bool = False,
) -> Response:
    """Serve a feed with ETag/If-Modified-Since handling and DB/memory caching."""
    etag = _generate_etag(cache_key, latest_timestamp)
    headers = _feed_headers(etag, latest_timestamp)

    if _not_modified(latest_timestamp, etag, if_none_match, if_modified_since):
        return Response(status_code=304, headers=headers)

    cached_feed = get_cached_feed(db, cache_key, etag)
    if cached_feed is None:
        feed = generate_fn()
        if not feed:
            raise HTTPException(status_code=404, detail="Newsletter not found")
        set_cached_feed(db, cache_key, etag, feed)
        cached_feed = feed

    if is_head:
        content_bytes = (
            cached_feed.encode("utf-8")
            if isinstance(cached_feed, str)
            else cached_feed
        )
        headers["Content-Length"] = str(len(content_bytes))
        return Response(
            content=b"", media_type="application/atom+xml", headers=headers
        )

    return Response(
        content=cached_feed, media_type="application/atom+xml", headers=headers
    )


@router.api_route("/feeds/all", methods=["GET", "HEAD"])
def get_master_feed(
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
    if_none_match: str | None = Header(default=None),
    if_modified_since: str | None = Header(default=None),
):
    """Generate a master Atom feed for all newsletters."""
    # Authenticate the master feed if auth is enabled. Both is_auth_enabled and
    # the master token are served from in-memory caches, so a warm secured 304
    # still issues zero DB queries.
    if is_auth_enabled(db):
        master_token = get_master_feed_token(db)
        if (
            not token
            or not master_token
            or not secrets.compare_digest(token, master_token)
        ):
            logger.warning(
                "Unauthorized attempt to access master feed (invalid or missing token)"
            )
            raise HTTPException(
                status_code=401, detail="Unauthorized: Invalid or missing token"
            )

    logger.info("Generating master feed for all newsletters")
    latest_timestamp = get_latest_entry_timestamp_cached(db)

    return _conditional_feed_response(
        db,
        "master",
        latest_timestamp,
        if_none_match,
        if_modified_since,
        lambda: generate_master_feed(db, request=request),
        is_head=(request.method == "HEAD"),
    )


@router.api_route("/feeds/{feed_identifier}", methods=["GET", "HEAD"])
def get_newsletter_feed(
    feed_identifier: str,
    request: Request,
    db: Session = Depends(get_db),
    if_none_match: str | None = Header(default=None),
    if_modified_since: str | None = Header(default=None),
):
    """Generate an Atom feed for a specific newsletter."""
    logger.info(f"Generating feed for newsletter with identifier={feed_identifier}")

    # Lightweight identity resolve (cached) — the conditional/304 hot path never
    # needs the entry count or senders that get_newsletter_by_identifier loads.
    identity = get_newsletter_identity(db, feed_identifier)
    if not identity:
        logger.warning(
            f"Newsletter with identifier={feed_identifier} not found, cannot generate feed."
        )
        raise HTTPException(status_code=404, detail="Newsletter not found")

    newsletter_id, newsletter_slug = identity

    # Secure feeds: restrict access to the cryptographically secure ID (NanoID)
    # to prevent slug guessing when authentication is enabled.
    if newsletter_slug == feed_identifier and is_auth_enabled(db):
        logger.warning(
            f"Blocked guessable slug-based feed access for slug '{feed_identifier}'."
        )
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Guessable slug-based feed access is disabled for security. Please use the secure feed ID.",
        )

    latest_timestamp = get_latest_entry_timestamp_cached(
        db, newsletter_id=newsletter_id
    )

    # Always pass the secure newsletter ID to prevent any internal slug mapping issues.
    return _conditional_feed_response(
        db,
        newsletter_id,
        latest_timestamp,
        if_none_match,
        if_modified_since,
        lambda: generate_feed(
            db,
            newsletter_id,
            request=request,
            limit=settings.newsletter_feed_limit,
        ),
        is_head=(request.method == "HEAD"),
    )
