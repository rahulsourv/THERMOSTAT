"""
Database connection for ThermoStats.

Why a connection POOL instead of connecting each time:
a new database connection over the internet takes a few hundred
milliseconds to open. If every API request opened its own, the API would
feel slow for no reason. A pool opens a few connections once, then hands
them out and takes them back.

The pool is created lazily - on first use, not at import - so that other
scripts can import this module's settings without opening connections.

THREE FAILURE MODES THIS HANDLES, ALL SEEN IN PRODUCTION LOGS:

  1. A pooled connection has quietly died. Supabase's pooler drops idle
     connections and psycopg2 hands them out anyway, so the caller only finds
     out when the query fails. _healthy() checks with one cheap round trip.

  2. A NEW connection cannot be opened at all - DNS failure, network drop,
     database asleep. getconn() raises before _healthy() is ever reached, so
     checking borrowed connections does nothing for this case. It is retried
     with backoff and then reported as a typed error the API turns into a
     clean 503 instead of a 500 with a stack trace.

  3. Concurrent requests. FastAPI runs sync endpoints in a threadpool, so
     several requests share this pool at the same time. SimpleConnectionPool
     is explicitly NOT thread-safe - its internal free-list can be corrupted
     by concurrent getconn/putconn. ThreadedConnectionPool takes a lock.
"""

import time
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from .settings import connection_kwargs

_pool = None

BORROW_ATTEMPTS = 3
BACKOFF_SECONDS = 0.25


class DatabaseUnavailable(RuntimeError):
    """The database cannot be reached right now.

    Distinct from a query error: this means we never got a usable connection,
    so the request should surface as 503 (try again) rather than 500 (bug).
    """


def get_pool():
    global _pool
    if _pool is None:
        # Threaded, not Simple: endpoints run in FastAPI's threadpool and
        # share this object concurrently.
        _pool = pool.ThreadedConnectionPool(
            minconn=1, maxconn=8, **connection_kwargs()
        )
    return _pool


def reset_pool():
    """Drop the pool so the next call builds a fresh one.

    Used when the pool itself is unusable - every connection in it was opened
    against a network that has since gone away.
    """
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception:
            pass
    _pool = None


def _healthy(conn):
    """Is this pooled connection still usable?

    A one-round-trip SELECT 1 is far cheaper than discovering the answer
    halfway through a real query.
    """
    if conn.closed:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        return True
    except Exception:
        return False


def _borrow():
    """Take a LIVE connection from the pool, or say clearly why we cannot.

    Two distinct problems are retried here, because from the caller's point of
    view they look the same and both are usually transient:
      - getconn() raised: no connection could be opened (network/DNS/exhausted)
      - getconn() returned a corpse: the connection existed but is dead
    """
    last_error = None

    for attempt in range(BORROW_ATTEMPTS):
        try:
            pool_ = get_pool()
            conn = pool_.getconn()
        except psycopg2.OperationalError as exc:
            # Cannot open a connection - DNS, network, or the database is down.
            # The pool object may hold handles to a network that no longer
            # exists, so rebuild it rather than retrying against stale state.
            last_error = exc
            reset_pool()
            time.sleep(BACKOFF_SECONDS * (attempt + 1))
            continue
        except pool.PoolError as exc:
            # Exhausted: every connection is checked out. Waiting is the right
            # response; rebuilding would abandon connections still in use.
            last_error = exc
            time.sleep(BACKOFF_SECONDS * (attempt + 1))
            continue

        if _healthy(conn):
            return conn

        try:
            pool_.putconn(conn, close=True)
        except Exception:
            pass

    raise DatabaseUnavailable(
        f"no live database connection after {BORROW_ATTEMPTS} attempts: "
        f"{type(last_error).__name__ if last_error else 'all connections dead'}"
    ) from last_error


@contextmanager
def get_cursor():
    """Borrow a connection, give back a cursor, always return it afterwards.

    RealDictCursor makes rows come back as dictionaries
    ({"cell_id": 123, ...}) instead of plain tuples ((123, ...)),
    which FastAPI can turn straight into JSON.
    """
    conn = _borrow()
    broken = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        # The rollback itself fails if the connection died mid-query. Either
        # way the connection is suspect, so it is closed rather than reused.
        try:
            conn.rollback()
        except Exception:
            broken = True
        raise
    finally:
        try:
            get_pool().putconn(conn, close=broken)
        except Exception:
            # The pool was reset underneath us by a concurrent failure. The
            # connection is orphaned either way - close it rather than leak
            # the socket.
            try:
                conn.close()
            except Exception:
                pass
