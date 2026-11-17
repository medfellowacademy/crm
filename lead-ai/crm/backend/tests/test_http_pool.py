"""The Supabase clients must use thread-safe HTTP/1.1 pools, not one shared HTTP/2 connection."""

import threading

import http_pool

KEY = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.c2lnbmF0dXJl"


def _pool(client):
    return client._transport._pool


def test_database_and_storage_sessions_are_http1_with_a_big_keepalive_pool():
    assert http_pool.install() is True
    from supabase import create_client
    c = create_client("https://example.supabase.co", KEY)
    for session in (c.postgrest.session, c.storage.session):
        pool = _pool(session)
        assert pool._http2 is False and pool._http1 is True
        assert pool._max_connections == http_pool.MAX_CONNECTIONS
        assert pool._max_keepalive_connections == http_pool.KEEPALIVE_CONNECTIONS


def test_install_is_idempotent():
    assert http_pool.install() and http_pool.install()


def test_pool_is_shared_safely_across_threads():
    """Many threads building queries against the same client must not raise (the old HTTP/2 client
    shared one connection state machine between them)."""
    from supabase import create_client
    client = create_client("https://example.supabase.co", KEY)
    errors = []

    def work():
        try:
            for _ in range(50):
                client.table("leads").select("id").eq("status", "Hot").limit(1)
        except Exception as e:   # pragma: no cover - only on failure
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
