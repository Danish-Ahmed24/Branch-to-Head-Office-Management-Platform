import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.audit import record_audit
from app.database import make_engine, make_session_factory
from app.models import AuditEvent, Base, Branch, User

pytestmark = pytest.mark.integration


@pytest.fixture
def migrated_database(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run migration/audit integration tests")
    schema = "audit_test_" + uuid4().hex
    admin_engine = make_engine(database_url)
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(database_url).update_query_dict({"options": f"-csearch_path={schema}"})
    isolated_url = url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", isolated_url)
    monkeypatch.delenv("STATIC_DIR", raising=False)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    engine = make_engine(isolated_url)
    try:
        command.upgrade(config, "head")
        # Do not expose the URL in fixture reprs or failing test output.
        yield engine, config, None
    finally:
        engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def test_migrations_repeatable_and_match_models(migrated_database):
    engine, config, _ = migrated_database
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0001_identity_audit"
        )
        diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert diffs == []


def test_branch_codes_are_unique_across_concurrent_creates_and_rollback(migrated_database):
    engine, _, _ = migrated_database
    factory = make_session_factory(engine)

    def create_branch(number):
        with factory.begin() as session:
            branch = Branch(name=f"Synthetic {number}")
            session.add(branch)
            session.flush()
            return branch.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(create_branch, range(16)))
    assert len(set(codes)) == 16
    assert all(code.startswith("BR-") for code in codes)
    with factory() as session:
        branch = Branch(name="Rolled back")
        session.add(branch)
        session.flush()
        unused_code = branch.code
        session.rollback()
    assert create_branch(17) != unused_code


def test_audit_and_business_changes_commit_and_rollback_together(migrated_database):
    engine, _, _ = migrated_database
    factory = make_session_factory(engine)
    with factory.begin() as session:
        branch = Branch(name="Committed")
        session.add(branch)
        session.flush()
        record_audit(
            session,
            actor_id=None,
            action="branch.created",
            entity_type="branch",
            entity_id=str(branch.id),
            after={"name": branch.name},
        )
    with factory() as session:
        branch = Branch(name="Rolled back")
        session.add(branch)
        session.flush()
        record_audit(
            session,
            actor_id=None,
            action="branch.created",
            entity_type="branch",
            entity_id=str(branch.id),
            after={"name": branch.name},
        )
        session.flush()
        session.rollback()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Branch)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


@pytest.mark.parametrize(
    "operation",
    [
        "UPDATE audit_events SET action = 'changed'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
def test_audit_is_append_only_at_database_level(migrated_database, operation):
    engine, _, _ = migrated_database
    with make_session_factory(engine).begin() as session:
        record_audit(session, actor_id=None, action="test", entity_type="auth", entity_id="test")
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text(operation))


def test_audit_snapshots_drop_passwords_tokens_and_unapproved_fields(migrated_database):
    engine, _, _ = migrated_database
    with make_session_factory(engine).begin() as session:
        event = record_audit(
            session,
            actor_id=None,
            action="user.created",
            entity_type="user",
            entity_id="test",
            after={
                "email": "fake@example.invalid",
                "role": "hr_lead",
                "password_hash": "secret",
                "password": "secret",
                "token_hash": "secret",
                "unexpected": {"password": "secret"},
            },
        )
        session.flush()
        assert event.after == {"email": "fake@example.invalid", "role": "hr_lead"}
        with pytest.raises(ValueError, match="allowlist"):
            record_audit(
                session,
                actor_id=None,
                action="x",
                entity_type="unregistered",
                entity_id="test",
                after={"something": "unsafe"},
            )


@pytest.mark.parametrize(
    "email,role",
    [
        ("UPPER@example.invalid", "hr_lead"),
        ("fake@example.invalid", "invented"),
        ("fake@example.invalid", "branch_lead"),
    ],
)
def test_user_constraints_enforced_in_database(migrated_database, email, role):
    engine, _, _ = migrated_database
    with pytest.raises(IntegrityError), make_session_factory(engine).begin() as session:
        session.add(User(email=email, role=role, display_name="Synthetic", password_hash="unused"))
        session.flush()


def test_cli_never_changes_existing_admin(migrated_database, monkeypatch, capsys):
    from app.cli import main

    engine, _, _ = migrated_database
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.invalid")
    monkeypatch.setenv("ADMIN_PASSWORD", "synthetic-test-password")
    monkeypatch.setattr("sys.argv", ["app.cli", "init-admin"])
    main()
    assert "synthetic-test-password" not in capsys.readouterr().out
    with make_session_factory(engine)() as session:
        original = session.scalar(select(User)).password_hash
    with pytest.raises(ValueError, match="already exists"):
        main()
    with make_session_factory(engine)() as session:
        assert session.scalar(select(User)).password_hash == original
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_demo_cli_requires_nonproduction_and_empty_database(migrated_database, monkeypatch):
    from app.cli import main

    engine, _, _ = migrated_database
    monkeypatch.setattr("sys.argv", ["app.cli", "seed-demo"])
    monkeypatch.setenv("DEMO_PASSWORD", "synthetic-test-password")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://example.invalid")
    with pytest.raises(ValueError, match="forbidden"):
        main()
    monkeypatch.setenv("APP_ENV", "test")
    main()
    with make_session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 5
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 6
    with pytest.raises(ValueError, match="empty"):
        main()


@pytest.mark.parametrize(
    "variable,value",
    [("ADMIN_EMAIL", "invalid"), ("ADMIN_PASSWORD", "x" * 129), ("ADMIN_DISPLAY_NAME", " ")],
)
def test_cli_uses_same_validation_as_user_api(migrated_database, monkeypatch, variable, value):
    from app.cli import main

    engine, _, _ = migrated_database
    monkeypatch.setattr("sys.argv", ["app.cli", "init-admin"])
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.invalid")
    monkeypatch.setenv("ADMIN_PASSWORD", "synthetic-test-password")
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        main()
    with make_session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
