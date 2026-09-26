"""Docker initialises the database, then migrates, then applies the table grants.

`deploy/db/init-roles.sql` used to run only once, on the empty database, where every table GRANT
failed (`relation "customer" does not exist`). It now creates the roles on an empty database,
skips the table grants, and is applied again as `collectai_owner` after the migrations (the
`grants` Compose service). These tests replay that order against real PostgreSQL and check the
result through the readiness check `app_role_grants` and through real connections as the
application and read-only roles.

The migrated, not-yet-granted schema is built once as a template database; every test clones it,
so each starts from "migrations applied, grants not applied yet". Roles are cluster-wide; the
table privileges under test live in each cloned database.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import embedded_postgres as ep
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from collectai.domain_services import readiness_service
from collectai.domain_services.readiness_service import check_readiness

pytestmark = pytest.mark.db

_BACKEND = Path(__file__).resolve().parents[2]
_INIT_ROLES_SQL = (_BACKEND.parent / "deploy" / "db" / "init-roles.sql").read_text(
    encoding="utf-8"
)
_MIGRATIONS_DIR = _BACKEND / "src" / "collectai" / "persistence" / "migrations"
_INSERT_ONLY = ("audit_event", "chat_message", "payment_event", "review_decision")


# `pg_server.get_uri()` is `postgresql://postgres:@localhost:<port>/postgres` where the server
# listens on TCP (Windows) but `postgresql://postgres:@/postgres?host=<socket dir>` where it
# listens on a unix socket (Linux, macOS, CI). Both helpers parse the URI with the drivers' own
# parsers and change only the role, the password and the database, so whichever transport the
# server uses is carried over unchanged.


def _dsn(server_uri: str, *, user: str, database: str) -> str:
    """A libpq connection string for the same server, as another role and database."""
    params = conninfo_to_dict(server_uri)
    params.pop("password", None)  # embedded PostgreSQL trusts every local connection
    params.update(user=user, dbname=database)
    return make_conninfo(**params)


def _async_url(server_uri: str, *, user: str, database: str) -> URL:
    """The same server for SQLAlchemy's asyncpg driver, as another role and database."""
    # the server URI carries an empty password (trust authentication), which is kept as is
    return make_url(server_uri).set(
        drivername="postgresql+asyncpg", username=user, database=database
    )


def _run(dsn: str, sql: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql)  # type: ignore[call-overload]


def _one(dsn: str, sql: str) -> object:
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute(sql).fetchone()  # type: ignore[call-overload]
    assert row is not None
    return row[0]


def _privileges(dsn: str, role: str) -> dict[str, set[str]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = %s AND table_schema = 'public'",
            (role,),
        ).fetchall()
    result: dict[str, set[str]] = {}
    for table, privilege in rows:
        result.setdefault(table, set()).add(privilege)
    return result


def _tables(dsn: str) -> set[str]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        ).fetchall()
    return {row[0] for row in rows}


class _Databases:
    def __init__(self, server_uri: str) -> None:
        self._server_uri = server_uri
        self._created: list[str] = []
        self.template = self.new_name("template")

    def new_name(self, label: str) -> str:
        name = f"grants_{label}_{uuid.uuid4().hex[:8]}"
        self._created.append(name)
        return name

    def dsn(self, database: str, user: str = "postgres") -> str:
        return _dsn(self._server_uri, user=user, database=database)

    def async_url(self, database: str, user: str) -> URL:
        return _async_url(self._server_uri, user=user, database=database)

    def admin(self, sql: str) -> None:
        _run(self.dsn("postgres"), sql)

    def build_template(self) -> None:
        """Empty database -> roles only (docker init) -> migrations as collectai_owner."""
        self.admin(f"CREATE DATABASE {self.template}")
        # Docker init step: the same file, on an empty database. Must not fail.
        _run(self.dsn(self.template), _INIT_ROLES_SQL)
        # What deploy/db/02-init-app-passwords.sh does for the owner: no superuser needed after.
        _run(
            self.dsn(self.template),
            f"ALTER DATABASE {self.template} OWNER TO collectai_owner;"
            "GRANT ALL ON SCHEMA public TO collectai_owner;"
            "GRANT USAGE ON SCHEMA public TO collectai_app, collectai_readonly;",
        )
        config = Config(str(_BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(_MIGRATIONS_DIR))
        url = self.async_url(self.template, "collectai_owner").render_as_string(hide_password=False)
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # ConfigParser escaping
        command.upgrade(config, "head")

    def clone(self) -> str:
        """A database migrated as the owner whose grants have not been applied yet."""
        name = self.new_name("db")
        self.admin(f"CREATE DATABASE {name} TEMPLATE {self.template} OWNER collectai_owner")
        return name

    def drop_all(self) -> None:
        for name in reversed(self._created):
            self.admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


@pytest.fixture(scope="module")
def databases(pg_server: ep.PostgresServer) -> Iterator[_Databases]:
    dbs = _Databases(pg_server.get_uri())
    dbs.build_template()
    yield dbs
    dbs.drop_all()


@pytest.fixture
def granted_db(databases: _Databases) -> str:
    """The `grants` service has run: the same file, applied again as the owner."""
    name = databases.clone()
    _run(databases.dsn(name, "collectai_owner"), _INIT_ROLES_SQL)
    return name


async def _app_role_grants(databases: _Databases, database: str) -> tuple[bool, str | None]:
    engine = create_async_engine(databases.async_url(database, "collectai_app"))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            result = await check_readiness(session)
    finally:
        await engine.dispose()
    check = next(c for c in result.checks if c.name == "app_role_grants")
    return check.ok, check.detail


# ---- the URI helpers (no server needed) -----------------------------------------------------

_TCP_URI = "postgresql://postgres:@localhost:54321/postgres"
_SOCKET_URI = "postgresql://postgres:@/postgres?host=/tmp/pytest-of-runner/pytest-0/pgdata0"


def test_dsn_keeps_the_tcp_host_and_port() -> None:
    params = conninfo_to_dict(_dsn(_TCP_URI, user="collectai_owner", database="grants_db"))

    assert params == {
        "host": "localhost",
        "port": "54321",
        "user": "collectai_owner",
        "dbname": "grants_db",
    }


def test_dsn_keeps_the_unix_socket_directory() -> None:
    dsn = _dsn(_SOCKET_URI, user="collectai_owner", database="grants_db")

    assert conninfo_to_dict(dsn) == {
        "host": "/tmp/pytest-of-runner/pytest-0/pgdata0",
        "user": "collectai_owner",
        "dbname": "grants_db",
    }
    assert "None" not in dsn  # the bug: host and port were rebuilt from a URI that had neither


def test_async_url_keeps_the_tcp_host_and_port() -> None:
    url = _async_url(_TCP_URI, user="collectai_app", database="grants_db")

    assert (url.drivername, url.username, url.host, url.port, url.database) == (
        "postgresql+asyncpg",
        "collectai_app",
        "localhost",
        54321,
        "grants_db",
    )
    assert not url.password
    assert dict(url.query) == {}


def test_async_url_keeps_the_unix_socket_directory() -> None:
    url = _async_url(_SOCKET_URI, user="collectai_app", database="grants_db")

    assert (url.drivername, url.username, url.database) == (
        "postgresql+asyncpg",
        "collectai_app",
        "grants_db",
    )
    assert (url.host, url.port) == (None, None)
    assert dict(url.query) == {"host": "/tmp/pytest-of-runner/pytest-0/pgdata0"}


@pytest.mark.parametrize("server_uri", [_TCP_URI, _SOCKET_URI])
def test_the_alembic_url_survives_configparser_interpolation(server_uri: str) -> None:
    """Alembic keeps the URL in a ConfigParser value, where a bare `%` (the encoding of `/` in
    the socket directory) would be read as interpolation."""
    url = _async_url(server_uri, user="collectai_owner", database="grants_db")
    rendered = url.render_as_string(hide_password=False)
    config = Config()

    config.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))

    assert config.get_main_option("sqlalchemy.url") == rendered
    assert make_url(rendered) == url


# ---- the init sequence ----------------------------------------------------------------------


def test_the_first_phase_on_an_empty_database_creates_roles_and_grants_nothing(
    databases: _Databases,
) -> None:
    empty = databases.new_name("empty")
    databases.admin(f"CREATE DATABASE {empty}")

    _run(databases.dsn(empty), _INIT_ROLES_SQL)  # would raise on a GRANT against a missing table

    roles = _one(
        databases.dsn(empty),
        "SELECT count(*) FROM pg_roles WHERE rolname IN "
        "('collectai_owner', 'collectai_app', 'collectai_readonly')",
    )
    assert roles == 3
    assert _tables(databases.dsn(empty)) == set()


def test_the_owner_is_not_a_superuser_so_the_grants_step_needs_none(
    databases: _Databases,
) -> None:
    is_superuser = _one(
        databases.dsn("postgres"),
        "SELECT rolsuper FROM pg_roles WHERE rolname = 'collectai_owner'",
    )
    assert is_superuser is False


def test_before_the_grants_step_the_app_role_cannot_read_the_business_tables(
    databases: _Databases,
) -> None:
    name = databases.clone()

    assert "customer" not in _privileges(databases.dsn(name), "collectai_app")
    assert _tables(databases.dsn(name))  # the migrations really did create tables


def test_the_grants_step_gives_exactly_the_least_privilege_the_design_names(
    databases: _Databases, granted_db: str
) -> None:
    dsn = databases.dsn(granted_db)
    tables = _tables(dsn)
    app = _privileges(dsn, "collectai_app")
    readonly = _privileges(dsn, "collectai_readonly")

    assert set(app) == tables, "the app role must have a grant on every application table"
    for table in tables:
        if table in _INSERT_ONLY:
            assert app[table] == {"INSERT", "SELECT"}, table
        else:
            assert app[table] == {"INSERT", "SELECT", "UPDATE"}, table
    for table, privileges in readonly.items():
        assert privileges == {"SELECT"}, table
    assert set(readonly) == tables - {"audit_event"}


def test_the_grants_step_is_idempotent(databases: _Databases, granted_db: str) -> None:
    owner = databases.dsn(granted_db, "collectai_owner")
    before = _privileges(owner, "collectai_app")

    _run(owner, _INIT_ROLES_SQL)

    assert _privileges(owner, "collectai_app") == before


def test_the_grants_step_fails_loudly_when_an_expected_table_is_missing(
    databases: _Databases,
) -> None:
    name = databases.clone()
    owner = databases.dsn(name, "collectai_owner")
    _run(owner, "ALTER TABLE customer RENAME TO customer_renamed")

    with pytest.raises(psycopg.errors.UndefinedTable, match="customer"):
        _run(owner, _INIT_ROLES_SQL)


def test_the_application_role_can_use_the_tables_and_is_denied_what_it_should_be(
    databases: _Databases, granted_db: str
) -> None:
    app = databases.dsn(granted_db, "collectai_app")

    assert _one(app, "SELECT count(*) FROM customer") == 0
    for denied in (
        "UPDATE audit_event SET event_type = event_type",
        "DELETE FROM audit_event",
        "UPDATE payment_event SET amount = amount",
        "DELETE FROM payment_event",
        "DELETE FROM customer",
        "DROP TABLE customer",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _run(app, denied)


def test_the_read_only_role_can_read_but_not_write(
    databases: _Databases, granted_db: str
) -> None:
    readonly = databases.dsn(granted_db, "collectai_readonly")

    assert _one(readonly, "SELECT count(*) FROM customer") == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _run(readonly, "DELETE FROM customer")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _run(readonly, "SELECT count(*) FROM audit_event")


# ---- readiness: app_role_grants -------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_flags_the_state_docker_used_to_be_left_in(
    databases: _Databases,
) -> None:
    """Migrated, but the table grants never ran: only audit_event (migration 0007) is granted."""
    name = databases.clone()

    ok, detail = await _app_role_grants(databases, name)

    assert ok is False
    assert detail is not None
    assert "collectai_app lacks required privileges on:" in detail
    assert "collectai_owner" not in detail  # table names only; no connection detail


@pytest.mark.asyncio
async def test_readiness_passes_after_the_grants_step(
    databases: _Databases, granted_db: str
) -> None:
    assert await _app_role_grants(databases, granted_db) == (True, None)


@pytest.mark.asyncio
async def test_readiness_names_a_table_the_app_role_can_no_longer_update(
    databases: _Databases, granted_db: str
) -> None:
    owner = databases.dsn(granted_db, "collectai_owner")
    _run(owner, "REVOKE UPDATE ON customer FROM collectai_app")

    ok, detail = await _app_role_grants(databases, granted_db)

    assert ok is False
    assert detail is not None
    assert "lacks required privileges on: customer" in detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statement", "table"),
    [
        ("GRANT UPDATE ON payment_event TO collectai_app", "payment_event"),
        ("GRANT UPDATE ON audit_event TO collectai_app", "audit_event"),
        ("GRANT DELETE ON customer TO collectai_app", "customer"),
        ("GRANT DELETE ON audit_event TO collectai_app", "audit_event"),
    ],
)
async def test_readiness_does_not_accept_more_privilege_than_least_privilege_allows(
    databases: _Databases, granted_db: str, statement: str, table: str
) -> None:
    _run(databases.dsn(granted_db, "collectai_owner"), statement)

    ok, detail = await _app_role_grants(databases, granted_db)

    assert ok is False
    assert detail is not None
    assert f"forbidden UPDATE/DELETE on: {table}" in detail


@pytest.mark.asyncio
async def test_readiness_fails_closed_when_the_app_role_does_not_exist(
    databases: _Databases, granted_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(readiness_service, "_APP_ROLE", "collectai_no_such_role")

    ok, detail = await _app_role_grants(databases, granted_db)

    assert ok is False
    assert detail == "role collectai_no_such_role does not exist"


@pytest.mark.asyncio
async def test_readiness_lists_at_most_a_few_table_names(databases: _Databases) -> None:
    name = databases.clone()

    _, detail = await _app_role_grants(databases, name)

    assert detail is not None
    assert re.search(r"\(\+\d+ more\)$", detail)
