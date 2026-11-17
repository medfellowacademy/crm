"""Thread-safe HTTP connections for the Supabase client.

supabase-py (postgrest 0.17 / storage3) builds ONE httpx client with HTTP/2 switched on and every
request thread shares it. HTTP/2 multiplexes all those requests over a single connection, and the
`h2` state machine is not safe to drive from many threads at once. Under real traffic that shows up
as "deque mutated during iteration", "ConnectionTerminated" and "[Errno 11] Resource temporarily
unavailable", i.e. failed requests (and a "failing closed" login check turning into a 503) exactly
when several people use the CRM at the same time.

This swaps those clients for plain HTTP/1.1 with a connection pool, which httpx documents as
thread-safe, and a keep-alive pool big enough that busy periods reuse connections instead of
opening a fresh TLS connection for every request.
"""

import httpx

from logger_config import logger

MAX_CONNECTIONS = 100
KEEPALIVE_CONNECTIONS = 60
KEEPALIVE_SECONDS = 30.0


def limits() -> httpx.Limits:
    return httpx.Limits(max_connections=MAX_CONNECTIONS, max_keepalive_connections=KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=KEEPALIVE_SECONDS)


def install() -> bool:
    """Patch the Supabase sub-clients to build HTTP/1.1 pooled sessions. Safe to call twice; if a
    library upgrade moves things, it logs and leaves the defaults rather than breaking start-up."""
    ok = True
    try:
        from postgrest import SyncPostgrestClient
        from postgrest.utils import SyncClient as PgClient

        def pg_session(self, base_url, headers, timeout, verify=True, proxy=None):
            return PgClient(base_url=base_url, headers=headers, timeout=timeout, verify=verify, proxy=proxy,
                            follow_redirects=True, http2=False, limits=limits())

        SyncPostgrestClient.create_session = pg_session
    except Exception as e:
        ok = False
        logger.warning(f"http_pool: could not patch the database client ({e}); HTTP/2 stays on")
    try:
        from storage3._sync.client import SyncStorageClient
        from storage3.utils import SyncClient as StorageClient

        def storage_session(self, base_url, headers, timeout, verify=True, proxy=None):
            return StorageClient(base_url=base_url, headers=headers, timeout=timeout, proxy=proxy,
                                 verify=bool(verify), follow_redirects=True, http2=False, limits=limits())

        SyncStorageClient._create_session = storage_session
    except Exception as e:
        ok = False
        logger.warning(f"http_pool: could not patch the storage client ({e}); HTTP/2 stays on")
    return ok
