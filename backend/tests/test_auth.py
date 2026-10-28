"""Endpoint-level authorization against isolated migrated PostgreSQL schemas."""

import os
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.auth import digest, hash_password, verify_password
from app.config import Settings
from app.main import create_app
from app.models import AuditEvent, AuthSession, Branch, User
from app.permissions import require_permission

PASSWORD = "Synthetic-test-password-25!"
ORIGIN = "http://localhost:5173"
ROLES = ("super_admin", "finance_reviewer", "content_editor", "branch_lead", "hr_lead")


@pytest.fixture(scope="module")
def schema_engine():
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL integration")
    url = make_url(raw).set(drivername="postgresql+psycopg")
    admin = create_engine(url)
    schema = "auth_test_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = url.update_query_dict({"options": f"-csearch_path={schema}"})
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = scoped.render_as_string(hide_password=False)
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    engine = create_engine(scoped)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def api(schema_engine):
    connection = schema_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    with factory() as db:
        first, second = (
            Branch(name="Synthetic North", status="active"),
            Branch(name="Synthetic South", status="active"),
        )
        db.add_all([first, second])
        db.flush()
        hashed = hash_password(PASSWORD)
        users = {}
        for role in ROLES:
            user = User(
                email=f"{role}@example.test",
                display_name=f"Synthetic {role}",
                role=role,
                branch_id=first.id if role == "branch_lead" else None,
                password_hash=hashed,
                is_active=True,
            )
            db.add(user)
            users[role] = user
        db.commit()
    app = create_app(
        Settings(
            database_url=schema_engine.url.render_as_string(hide_password=False), app_env="test"
        )
    )
    app.state.session_factory = factory
    with TestClient(app) as client:
        yield client, factory, users, (first, second)
    transaction.rollback()
    connection.close()


def login(client, role="super_admin", **overrides):
    return client.post(
        "/api/auth/login",
        json={"email": f"{role}@example.test", "password": PASSWORD, **overrides},
        headers={"Origin": ORIGIN},
    )


def test_password_hash_salted_and_tamper_safe():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password("incorrect", first)
    assert not verify_password(PASSWORD, "corrupt")
    assert not verify_password(PASSWORD, first.replace("16384", "999999999"))
    with pytest.raises(HTTPException):
        require_permission("super_admin", "unknown.action")


@pytest.mark.parametrize("origin", [None, "http://example.org", "https://example.org/path", ""])
def test_production_requires_explicit_https_origin(origin):
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://user:password@localhost/db",
            app_env="production",
            public_origin=origin,
        )


def test_session_lifecycle_csrf_and_audit(api):
    client, factory, users, _ = api
    result = login(client)
    assert result.status_code == 200
    assert (
        "HttpOnly" in result.headers["set-cookie"]
        and "SameSite=lax" in result.headers["set-cookie"]
    )
    token, csrf = client.cookies["shiplens_session"], result.json()["csrf_token"]
    assert result.headers["cache-control"] == "no-store" and "password" not in str(result.json())
    with factory() as db:
        stored = db.scalar(select(AuthSession))
        assert stored.token_hash == digest(token) and stored.token_hash != token
        assert stored.csrf_token_hash == digest(csrf) and stored.csrf_token_hash != csrf
    for _ in range(2):
        assert client.get("/api/auth/me").json()["csrf_token"] == csrf
    assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(
            "/api/auth/logout", headers={"Origin": "https://evil.test", "X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("shiplens_session", token)
    assert client.get("/api/auth/me").status_code == 401
    with factory() as db:
        assert list(
            db.scalars(
                select(AuditEvent.action).where(AuditEvent.actor_id == users["super_admin"].id)
            )
        ) == ["auth.login", "auth.logout"]


def test_login_origin_and_generic_failures(api):
    client, factory, _, _ = api
    body = {"email": "super_admin@example.test", "password": PASSWORD}
    assert client.post("/api/auth/login", json=body).status_code == 403
    assert (
        client.post(
            "/api/auth/login", json=body, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    known, unknown = (
        login(client, password="incorrect"),
        login(client, email="missing@example.test", password="incorrect"),
    )
    assert known.status_code == unknown.status_code == 401 and known.json() == unknown.json()
    with factory() as db:
        assert list(db.scalars(select(AuditEvent.action))) == [
            "auth.login_failed",
            "auth.login_failed",
        ]


def test_production_cookie_flags(api):
    client, _, _, _ = api
    client.app.state.settings.app_env = "production"
    client.app.state.settings.public_origin = "https://example.org"
    result = client.post(
        "/api/auth/login",
        json={"email": "super_admin@example.test", "password": PASSWORD},
        headers={"Origin": "https://example.org"},
    )
    assert result.status_code == 200
    cookie = result.headers["set-cookie"]
    assert (
        cookie.startswith("__Host-shiplens_session=")
        and "Secure" in cookie
        and "HttpOnly" in cookie
    )
    assert "Path=/" in cookie and "Domain=" not in cookie


def test_expired_and_inactive_sessions(api):
    client, factory, users, _ = api
    assert login(client).status_code == 200
    with factory() as db:
        db.scalar(select(AuthSession)).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 200
    with factory() as db:
        db.get(User, users["super_admin"].id).is_active = False
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401


def test_fixation_prevention_and_no_validation_secret_echo(api):
    client, factory, _, _ = api
    assert login(client).status_code == 200
    original = client.cookies["shiplens_session"]
    assert login(client).status_code == 200 and client.cookies["shiplens_session"] != original
    with factory() as db:
        assert (
            db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(original))) is None
        )
    secret = "sensitive-" + secrets.token_hex(100)
    result = login(client, password=secret)
    assert result.status_code == 422 and secret not in result.text


@pytest.mark.parametrize("role", ROLES)
def test_role_and_cross_branch_endpoint_checks(api, role):
    client, _, _, branches = api
    result = login(client, role)
    assert result.status_code == 200
    csrf = result.json()["csrf_token"]
    assert client.get("/api/users").status_code == (200 if role == "super_admin" else 403)
    response, audit = client.get("/api/branches"), client.get("/api/audit")
    if role == "content_editor":
        assert response.status_code == audit.status_code == 403
        assert client.get(f"/api/branches/{branches[0].id}").status_code == 403
    else:
        assert response.status_code == audit.status_code == 200
        ids = {entry["id"] for entry in response.json()["items"]}
        expected = (
            {str(branches[0].id)}
            if role == "branch_lead"
            else {str(branch.id) for branch in branches}
        )
        assert ids == expected
        assert client.get(f"/api/branches/{branches[0].id}").status_code == 200
        assert client.get(f"/api/branches/{branches[1].id}").status_code == (
            404 if role == "branch_lead" else 200
        )
    body = {
        "email": "new@example.test",
        "password": PASSWORD,
        "display_name": "Synthetic New",
        "role": "hr_lead",
    }
    assert client.post(
        "/api/users", json=body, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
    ).status_code == (201 if role == "super_admin" else 403)


def test_anonymous_and_forged_cookie(api):
    client, _, _, branches = api
    for path in (
        "/api/users",
        "/api/branches",
        f"/api/branches/{branches[0].id}",
        "/api/audit",
        "/api/auth/me",
    ):
        assert client.get(path).status_code == 401
    client.cookies.set("shiplens_session", secrets.token_urlsafe(32))
    assert client.get("/api/users").status_code == 401


def test_user_creation_audit_constraints_duplicates(api):
    client, factory, _, branches = api
    csrf = login(client).json()["csrf_token"]
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    body = {
        "email": " NEW@EXAMPLE.TEST ",
        "password": PASSWORD,
        "display_name": "Synthetic New",
        "role": "branch_lead",
        "branch_id": str(branches[0].id),
    }
    result = client.post("/api/users", json=body, headers=headers)
    assert (
        result.status_code == 201
        and result.json()["email"] == "new@example.test"
        and "password" not in result.text
    )
    assert client.post("/api/users", json=body, headers=headers).status_code == 409
    for changes in (
        {"branch_id": None},
        {"role": "hr_lead"},
        {"role": "unrecognized"},
        {"password": "short"},
        {"branch_id": str(uuid4())},
    ):
        assert (
            client.post(
                "/api/users",
                json={**body, "email": "another@example.test", **changes},
                headers=headers,
            ).status_code
            == 422
        )
    with factory() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.created"))
        assert event.after["email"] == "new@example.test" and "password_hash" not in event.after
    assert client.get("/api/users?limit=101").status_code == 422
    assert client.get(f"/api/branches/{uuid4()}").status_code == 404


def test_audit_filters(api):
    client, factory, users, branches = api
    with factory() as db:
        db.add_all(
            [
                AuditEvent(
                    actor_id=users["super_admin"].id,
                    action="synthetic.readiness",
                    entity_type=domain,
                    entity_id="synthetic",
                    branch_id=branch.id,
                )
                for domain in ("report", "member", "branch")
                for branch in branches
            ]
        )
        db.commit()
    for role in ("super_admin", "finance_reviewer", "hr_lead", "branch_lead"):
        assert login(client, role).status_code == 200
        items = client.get("/api/audit").json()["items"]
        if role == "finance_reviewer":
            assert len(items) == 2 and all(event["entity_type"] == "report" for event in items)
        elif role == "hr_lead":
            assert len(items) == 2 and all(event["entity_type"] == "member" for event in items)
        elif role == "branch_lead":
            assert len(items) >= 3 and all(
                event["branch_id"] == str(branches[0].id) for event in items
            )
        else:
            assert len(items) >= 6


def test_rate_limit_and_forged_forwarded_for(api):
    client, _, _, _ = api
    for index in range(10):
        result = client.post(
            "/api/auth/login",
            json={"email": "super_admin@example.test", "password": "wrong"},
            headers={"Origin": ORIGIN, "X-Forwarded-For": f"192.0.2.{index}"},
        )
        assert result.status_code == 401
    result = login(client)
    assert result.status_code == 429 and result.headers["retry-after"] == "900"


def test_unavailable_auth_database_returns_sanitized_503():
    app = create_app(
        Settings(
            database_url="postgresql://user:secret-never-expose@127.0.0.1:1/missing", app_env="test"
        )
    )
    with TestClient(app) as client:
        result = login(client)
    assert result.status_code == 503
    assert result.json() == {"detail": "Service temporarily unavailable"}
    assert result.headers["cache-control"] == "no-store"
    assert "secret-never-expose" not in result.text


def test_user_creation_requires_csrf_and_trusted_origin(api):
    client, _, _, _ = api
    csrf = login(client).json()["csrf_token"]
    body = {
        "email": "new@example.test",
        "password": PASSWORD,
        "display_name": "Synthetic",
        "role": "hr_lead",
    }
    for headers in (
        {"Origin": ORIGIN},
        {"Origin": ORIGIN, "X-CSRF-Token": "0" * 64},
        {"Origin": "https://evil.test", "X-CSRF-Token": csrf},
    ):
        assert client.post("/api/users", json=body, headers=headers).status_code == 403
