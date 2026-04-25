"""Pytest fixtures: honest Postgres test DB + per-test truncation isolation.

Strategy
--------
Session-scoped:
  * Point Flask at `${TEST_DATABASE_URL}` (defaults to the dev Postgres
    instance, different database name).
  * Create the test database if it doesn't exist (Postgres can't CREATE
    DATABASE inside a transaction, so we connect to `postgres` with
    AUTOCOMMIT to issue it).
  * Run Alembic migrations once — using `flask_migrate.upgrade`, not
    `db.create_all`, so the tests exercise the real migration graph
    (composite indexes, FK RESTRICT from §9.17/9.19, JSONB RNG columns
    from §9.20). If migrations diverge from the models we want to fail.

Function-scoped:
  * TRUNCATE sim tables at teardown so no state leaks between tests.
  * Call `simulation_service._reset_cache()` before and after — the
    module-level sim cache (§9.20) is a single-worker affordance, and
    tests need a lever to reset it.

Why not transactional rollback?
-------------------------------
The canonical "SAVEPOINT + begin_nested + after_transaction_end listener"
pattern from SQLAlchemy docs works only when app code shares the same
scoped_session. Flask-SQLAlchemy 3.x creates a fresh session per app
context, and the Flask test client pushes a new app context per request.
By the time the route code runs, our rebound session has been replaced.
Result: app commits actually commit, and the outer transaction has
nothing to roll back. TRUNCATE avoids that whole mess — slightly slower
than rollback, but reliably isolated and honest about how writes land.

Why not SQLite
--------------
`SimulationState.rng_*_state` is JSONB; the `tuple_((x,y)).in_(...)`
composite-IN filter in `_update_dirty_tiles` has driver-specific SQL;
the migrations themselves use `postgresql.JSONB`. Running tests on SQLite
would mean testing a different engine than prod — the whole point of
integration tests is to catch divergence, not mask it.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app import db as _db
from app.app import create_app
from app.services import simulation_service

# Resolve migrations dir relative to this file so `pytest` works from
# either /app (container) or backend/ (host). conftest.py lives at
# backend/tests/conftest.py → migrations at backend/migrations.
_MIGRATIONS_DIR = str(Path(__file__).resolve().parent.parent / 'migrations')


def _test_db_url() -> str:
    """Derive the test DB URL from DATABASE_URL by swapping the db name.

    Dev URL:  postgresql://tunnels:pw@db:5432/tunnels
    Test URL: postgresql://tunnels:pw@db:5432/tunnels_test

    Allow override via TEST_DATABASE_URL for CI setups that want to
    point at a dedicated instance.
    """
    override = os.environ.get('TEST_DATABASE_URL')
    if override:
        return override
    dev = os.environ.get('DATABASE_URL')
    if not dev:
        raise RuntimeError(
            'Neither TEST_DATABASE_URL nor DATABASE_URL is set — '
            'cannot derive test database URL.'
        )
    parsed = urlparse(dev)
    new_path = parsed.path.rsplit('/', 1)[0] + '/tunnels_test'
    return urlunparse(parsed._replace(path=new_path))


def _ensure_test_db(url: str) -> None:
    """CREATE DATABASE tunnels_test if absent. Must be outside a transaction."""
    parsed = urlparse(url)
    target = parsed.path.lstrip('/')
    admin_url = urlunparse(parsed._replace(path='/postgres'))
    conn = psycopg2.connect(admin_url)
    try:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', (target,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{target}"')
    finally:
        conn.close()


@pytest.fixture(scope='session')
def app():
    """Flask app pointing at the test DB, with schema migrated up to head."""
    test_url = _test_db_url()
    _ensure_test_db(test_url)

    os.environ['DATABASE_URL'] = test_url  # create_app reads this at call time
    # The background tick loop (§9.27) mutates sim state every ~1s.
    # Tests drive the sim explicitly via POST /step; a parallel auto-tick
    # would corrupt test expectations. Disable it before create_app.
    os.environ['DISABLE_TICK_LOOP'] = '1'
    flask_app = create_app()
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        from flask_migrate import upgrade as migrate_upgrade
        migrate_upgrade(directory=_MIGRATIONS_DIR)

    yield flask_app


# Ordering matters: events FK-restricts to agents, so events must die first.
# SimulationState has no incoming FKs. One statement keeps it atomic and lets
# RESTRICT and cascade semantics speak if the invariant ever flips.
_TRUNCATE_TABLES = (
    'events, agents, world_tiles, colonies, simulation_state'
)


def _truncate_all(engine):
    """Wipe every sim table. Close the session first so no open transaction
    holds a lock that blocks the TRUNCATE.

    Safety guard: refuse to TRUNCATE unless the bound DB name ends in
    `_test`. A typo in `_test_db_url` or a misconfigured `TEST_DATABASE_URL`
    that pointed at the dev DB would otherwise silently wipe real data.
    """
    db_name = engine.url.database or ''
    assert db_name.endswith('_test'), (
        f'refusing to TRUNCATE a non-test database: {db_name!r}'
    )
    _db.session.remove()
    with engine.begin() as conn:
        conn.exec_driver_sql(f'TRUNCATE TABLE {_TRUNCATE_TABLES} RESTART IDENTITY CASCADE')


@pytest.fixture()
def db_session(app):
    """Per-test DB isolation via TRUNCATE + cache reset.

    Teardown wipes *all* sim tables so the next test starts cold — both
    from the DB's perspective and from the in-memory sim cache.
    """
    with app.app_context():
        simulation_service._reset_cache()
        _truncate_all(_db.engine)
        yield _db.session
        simulation_service._reset_cache()
        _truncate_all(_db.engine)


@pytest.fixture()
def client(app, db_session):
    """Flask test client with DB truncation isolation."""
    return app.test_client()
