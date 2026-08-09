import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.database import engine
from app.crud.entries import _latest_timestamp_cache
from app.crud.feed_cache import _feed_memory_cache


@contextmanager
def count_queries():
    """Count SQL statements executed on the app engine within the block."""
    statements: list[str] = []

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)


def test_gzip_compression(client: TestClient, db_session: Session):
    """Test that feeds support Gzip compression when requested."""
    # 1. Create newsletter
    unique_email = f"gzip_test_{uuid.uuid4()}@example.com"
    newsletter_data = {"name": "Gzip Test NL", "sender_emails": [unique_email]}
    create_response = client.post("/newsletters", json=newsletter_data)
    newsletter_id = create_response.json()["id"]

    # 2. Add an entry with a large body to exceed the 1000-byte Gzip threshold
    entry_data = {
        "subject": "Gzip Entry",
        "body": "<p>" + "A" * 1500 + "</p>",
        "message_id": f"<entry_{uuid.uuid4()}@test.com>",
    }
    client.post(f"/newsletters/{newsletter_id}/entries", json=entry_data)

    # Request master feed with Accept-Encoding: gzip
    headers = {"Accept-Encoding": "gzip"}
    response = client.get("/feeds/all", headers=headers)

    # It should succeed and indicate gzip encoding
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"


def test_last_modified_and_if_modified_since(client: TestClient, db_session: Session):
    """Test that Last-Modified and If-Modified-Since headers work correctly."""
    # 1. Create newsletter
    unique_email = f"perf_test_{uuid.uuid4()}@example.com"
    newsletter_data = {"name": "Perf Test NL", "sender_emails": [unique_email]}
    create_response = client.post("/newsletters", json=newsletter_data)
    newsletter_id = create_response.json()["id"]

    # 2. Add an entry
    entry_data = {
        "subject": "Perf Entry",
        "body": "<p>Content</p>",
        "message_id": f"<entry_{uuid.uuid4()}@test.com>",
    }
    client.post(f"/newsletters/{newsletter_id}/entries", json=entry_data)

    # 3. Request the feed to get headers
    response = client.get(f"/feeds/{newsletter_id}")
    assert response.status_code == 200

    last_modified = response.headers.get("Last-Modified")
    etag = response.headers.get("ETag")

    assert last_modified is not None
    assert etag is not None

    # 4. Request with If-Modified-Since matching the Last-Modified header
    headers = {"If-Modified-Since": last_modified}
    response_ims = client.get(f"/feeds/{newsletter_id}", headers=headers)
    assert response_ims.status_code == 304

    # 5. Request with If-None-Match matching ETag
    headers_etag = {"If-None-Match": etag}
    response_etag = client.get(f"/feeds/{newsletter_id}", headers=headers_etag)
    assert response_etag.status_code == 304


def test_in_memory_cache_layer(client: TestClient, db_session: Session):
    """Test that the in-memory cache layer gets populated on a feed request."""
    # 1. Create newsletter
    unique_email = f"mem_test_{uuid.uuid4()}@example.com"
    newsletter_data = {"name": "Mem Test NL", "sender_emails": [unique_email]}
    create_response = client.post("/newsletters", json=newsletter_data)
    newsletter_id = create_response.json()["id"]

    entry_data = {
        "subject": "Mem Entry",
        "body": "<p>Content</p>",
        "message_id": f"<entry_{uuid.uuid4()}@test.com>",
    }
    client.post(f"/newsletters/{newsletter_id}/entries", json=entry_data)

    # Clean caches to start fresh
    _feed_memory_cache.clear()
    _latest_timestamp_cache.clear()

    assert newsletter_id not in _feed_memory_cache
    assert newsletter_id not in _latest_timestamp_cache

    # 2. First fetch: populates both caches
    response_1 = client.get(f"/feeds/{newsletter_id}")
    assert response_1.status_code == 200

    assert newsletter_id in _feed_memory_cache
    assert newsletter_id in _latest_timestamp_cache

    # Verify the cached content matches the response
    cached_etag, cached_content = _feed_memory_cache[newsletter_id]
    assert response_1.headers.get("ETag") == cached_etag
    assert response_1.text == cached_content


def test_newsletter_feed_304_makes_no_db_queries(
    client: TestClient, db_session: Session
):
    """A warm conditional refresh (304) must hit zero database queries.

    This is the RSS-reader hot path: it should be served entirely from the
    in-memory identity/timestamp/metadata caches. Guards against regressions
    that reintroduce per-request DB work on the 304 path.
    """
    unique_email = f"q304_{uuid.uuid4()}@example.com"
    newsletter_id = client.post(
        "/newsletters",
        json={"name": "Query Count NL", "sender_emails": [unique_email]},
    ).json()["id"]
    client.post(
        f"/newsletters/{newsletter_id}/entries",
        json={
            "subject": "Entry",
            "body": "<p>Content</p>",
            "message_id": f"<entry_{uuid.uuid4()}@test.com>",
        },
    )

    # First fetch warms every cache and yields the ETag.
    warm = client.get(f"/feeds/{newsletter_id}")
    assert warm.status_code == 200
    etag = warm.headers["ETag"]

    # Conditional refresh: expect 304 and no SQL at all.
    with count_queries() as statements:
        res = client.get(f"/feeds/{newsletter_id}", headers={"If-None-Match": etag})
    assert res.status_code == 304
    assert statements == [], f"304 path issued DB queries: {statements}"


def test_master_feed_304_makes_no_db_queries(client: TestClient, db_session: Session):
    """A warm conditional refresh of the master feed must hit zero DB queries."""
    unique_email = f"q304master_{uuid.uuid4()}@example.com"
    newsletter_id = client.post(
        "/newsletters",
        json={"name": "Master Query Count NL", "sender_emails": [unique_email]},
    ).json()["id"]
    client.post(
        f"/newsletters/{newsletter_id}/entries",
        json={
            "subject": "Entry",
            "body": "<p>Content</p>",
            "message_id": f"<entry_{uuid.uuid4()}@test.com>",
        },
    )

    warm = client.get("/feeds/all")
    assert warm.status_code == 200
    etag = warm.headers["ETag"]

    with count_queries() as statements:
        res = client.get("/feeds/all", headers={"If-None-Match": etag})
    assert res.status_code == 304
    assert statements == [], f"304 path issued DB queries: {statements}"


def test_missing_feed_identifier_is_negatively_cached(
    client: TestClient, db_session: Session
):
    """Repeated requests for a non-existent feed must not hit the DB every time."""
    missing = f"does-not-exist-{uuid.uuid4()}"

    # First request populates the negative cache.
    assert client.get(f"/feeds/{missing}").status_code == 404

    # Second request must be served from the negative cache: 404, zero queries.
    with count_queries() as statements:
        res = client.get(f"/feeds/{missing}")
    assert res.status_code == 404
    assert statements == [], f"missing-feed path issued DB queries: {statements}"


def test_secured_master_feed_304_makes_no_db_queries(
    client: TestClient, db_session: Session
):
    """A warm 304 on the master feed with auth enabled must hit zero DB queries.

    Exercises the cached master-feed token: with auth on, the token check must
    not fall back to a per-request settings query.
    """
    from app.crud.settings import create_or_update_settings, get_master_feed_token
    from app.schemas.settings import SettingsCreate

    # Create content before enabling auth (newsletter routes become protected).
    unique_email = f"secmaster_{uuid.uuid4()}@example.com"
    newsletter_id = client.post(
        "/newsletters",
        json={"name": "Secured Master NL", "sender_emails": [unique_email]},
    ).json()["id"]
    client.post(
        f"/newsletters/{newsletter_id}/entries",
        json={
            "subject": "Entry",
            "body": "<p>Content</p>",
            "message_id": f"<entry_{uuid.uuid4()}@test.com>",
        },
    )

    # Enable auth, then resolve the (now-required) master feed token.
    create_or_update_settings(
        db_session,
        SettingsCreate(
            imap_server="test.com",
            imap_username="test",
            imap_password="password",
            auth_username="admin",
            auth_password="password",
        ),
    )
    token = get_master_feed_token(db_session)
    assert token

    # Warm every cache with an authorized fetch.
    warm = client.get(f"/feeds/all?token={token}")
    assert warm.status_code == 200
    etag = warm.headers["ETag"]

    with count_queries() as statements:
        res = client.get(f"/feeds/all?token={token}", headers={"If-None-Match": etag})
    assert res.status_code == 304
    assert statements == [], f"secured 304 path issued DB queries: {statements}"


def test_304_response_headers(client: TestClient, db_session: Session):
    """Test that HTTP 304 Not Modified responses include standard caching headers."""
    unique_email = f"head_test_{uuid.uuid4()}@example.com"
    create_response = client.post(
        "/newsletters", json={"name": "Header Test NL", "sender_emails": [unique_email]}
    )
    newsletter_id = create_response.json()["id"]
    client.post(
        f"/newsletters/{newsletter_id}/entries",
        json={
            "subject": "Header Entry",
            "body": "<p>Body</p>",
            "message_id": f"<entry_{uuid.uuid4()}@test.com>",
        },
    )

    resp_200 = client.get(f"/feeds/{newsletter_id}")
    etag = resp_200.headers.get("ETag")
    assert etag is not None

    resp_304 = client.get(
        f"/feeds/{newsletter_id}", headers={"If-None-Match": etag}
    )
    assert resp_304.status_code == 304
    assert resp_304.headers.get("ETag") == etag
    assert "public" in resp_304.headers.get("Cache-Control", "")
    assert "stale-while-revalidate" in resp_304.headers.get("Cache-Control", "")
    assert resp_304.headers.get("Vary") == "Accept-Encoding"
    assert resp_304.headers.get("Last-Modified") is not None


def test_head_method_support(client: TestClient, db_session: Session):
    """Test that HTTP HEAD requests to feed endpoints succeed with empty body."""
    unique_email = f"head_test_{uuid.uuid4()}@example.com"
    create_response = client.post(
        "/newsletters", json={"name": "HEAD Test NL", "sender_emails": [unique_email]}
    )
    newsletter_id = create_response.json()["id"]
    client.post(
        f"/newsletters/{newsletter_id}/entries",
        json={
            "subject": "HEAD Entry",
            "body": "<p>Content</p>",
            "message_id": f"<entry_{uuid.uuid4()}@test.com>",
        },
    )

    # HEAD on individual feed
    head_resp = client.head(f"/feeds/{newsletter_id}")
    assert head_resp.status_code == 200
    assert head_resp.content == b""
    assert head_resp.headers.get("ETag") is not None
    assert head_resp.headers.get("Content-Length") is not None

    # HEAD on master feed
    head_master = client.head("/feeds/all")
    assert head_master.status_code == 200
    assert head_master.content == b""
    assert head_master.headers.get("ETag") is not None


def test_xml_minification(client: TestClient, db_session: Session):
    """Test that Atom feeds are served minified without pretty-printed indents."""
    unique_email = f"minify_test_{uuid.uuid4()}@example.com"
    create_response = client.post(
        "/newsletters", json={"name": "Minify Test NL", "sender_emails": [unique_email]}
    )
    newsletter_id = create_response.json()["id"]
    client.post(
        f"/newsletters/{newsletter_id}/entries",
        json={
            "subject": "Minify Entry",
            "body": "<p>Content</p>",
            "message_id": f"<entry_{uuid.uuid4()}@test.com>",
        },
    )

    resp = client.get(f"/feeds/{newsletter_id}")
    assert resp.status_code == 200
    # Pretty-printed XML includes leading spaces for indentation (e.g. "  <title>")
    assert "\n  <title>" not in resp.text

