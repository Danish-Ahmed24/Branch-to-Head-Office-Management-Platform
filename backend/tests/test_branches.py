"""Branch mutation permissions, lifecycle, atomicity and concurrent requests."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_auth import ORIGIN, ROLES, login
from test_auth import api as inherited_api
from test_auth import schema_engine as inherited_schema_engine

from app import branches as branch_module
from app.auth import csrf_token, digest
from app.config import Settings
from app.main import create_app
from app.models import AuditEvent, AuthSession, Branch, User

# Explicit aliases expose the shared fixtures to pytest without global plugins.
api = inherited_api
schema_engine = inherited_schema_engine


def authorized(client, role="super_admin"):
    response = login(client, role)
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


@pytest.mark.parametrize("role", ROLES)
def test_branch_mutations_require_super_admin_with_valid_csrf(api, role):
    client, factory, _, existing = api
    headers = authorized(client, role)
    requests = [
        ("POST", "/api/branches", {"name": "Synthetic New"}),
        ("PATCH", f"/api/branches/{existing[0].id}", {"name": "Synthetic Renamed"}),
        (
            "POST",
            f"/api/branches/{existing[0].id}/transition",
            {"status": "paused", "expected_status": "active"},
        ),
    ]
    for method, path, body in requests:
        response = client.request(method, path, json=body, headers=headers)
        assert (
            response.status_code == (201 if method == "POST" and path == "/api/branches" else 200)
            if role == "super_admin"
            else response.status_code == 403
        )
    if role != "super_admin":
        with factory() as db:
            assert db.get(Branch, existing[0].id).name == "Synthetic North"
            assert db.get(Branch, existing[0].id).status == "active"
            assert not list(
                db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "branch"))
            )


def test_create_rename_and_status_changes_are_fully_audited(api):
    client, factory, users, _ = api
    headers = authorized(client)
    created = client.post("/api/branches", json={"name": "  Synthetic Central  "}, headers=headers)
    assert created.status_code == 201
    branch = created.json()
    assert branch["status"] == "forming" and branch["name"] == "Synthetic Central"
    assert branch["code"].startswith("BR-")
    path = f"/api/branches/{branch['id']}"
    renamed = client.patch(path, json={"name": "Synthetic New Central"}, headers=headers).json()
    assert renamed["code"] == branch["code"]
    changed = client.post(
        path + "/transition",
        json={"status": "active", "expected_status": "forming"},
        headers=headers,
    )
    assert changed.status_code == 200 and changed.json()["status"] == "active"
    with factory() as db:
        events = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_id == branch["id"])
                .order_by(AuditEvent.id)
            )
        )
        assert [event.action for event in events] == [
            "branch.created",
            "branch.renamed",
            "branch.status_changed",
        ]
        assert all(
            event.actor_id == users["super_admin"].id and str(event.branch_id) == branch["id"]
            for event in events
        )
        assert events[0].before is None and events[0].after == branch
        assert events[1].before == branch and events[1].after == renamed
        assert events[2].before["status"] == "forming" and events[2].after["status"] == "active"


@pytest.mark.parametrize("source", ["forming", "active", "paused", "closed"])
@pytest.mark.parametrize("target", ["forming", "active", "paused", "closed"])
def test_every_lifecycle_edge(api, source, target):
    client, factory, _, existing = api
    headers = authorized(client)
    with factory() as db:
        db.get(Branch, existing[0].id).status = source
        db.commit()
    response = client.post(
        f"/api/branches/{existing[0].id}/transition",
        json={"status": target, "expected_status": source},
        headers=headers,
    )
    allowed = (
        target
        in {
            "forming": {"active", "closed"},
            "active": {"paused", "closed"},
            "paused": {"active", "closed"},
            "closed": set(),
        }[source]
    )
    assert response.status_code == (200 if allowed else 409)
    with factory() as db:
        assert db.get(Branch, existing[0].id).status == (target if allowed else source)


def test_stale_transition_and_rejected_input_cannot_change_branch(api):
    client, factory, _, existing = api
    headers = authorized(client)
    path = f"/api/branches/{existing[0].id}"
    assert (
        client.post(
            path + "/transition",
            json={"status": "closed", "expected_status": "forming"},
            headers=headers,
        ).status_code
        == 409
    )
    for body in (
        {"name": ""},
        {"name": "  "},
        {"name": "x" * 201},
        {"name": "Valid", "code": "BR-FAKE"},
        {"name": "Valid", "status": "closed"},
    ):
        assert client.post("/api/branches", json=body, headers=headers).status_code == 422
        assert client.patch(path, json=body, headers=headers).status_code == 422
    assert client.patch(path, json={"name": existing[0].name}, headers=headers).status_code == 409
    assert (
        client.patch(
            f"/api/branches/{uuid4()}", json={"name": "Missing"}, headers=headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/branches/{uuid4()}/transition",
            json={"status": "active", "expected_status": "forming"},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            path + "/transition",
            json={"status": "invented", "expected_status": "active"},
            headers=headers,
        ).status_code
        == 422
    )
    assert client.delete(path, headers=headers).status_code == 405
    with factory() as db:
        assert db.get(Branch, existing[0].id).status == "active"


def test_anonymous_origin_and_csrf_checks_on_every_mutation(api):
    client, _, _, existing = api
    calls = [
        ("POST", "/api/branches", {"name": "Synthetic"}),
        ("PATCH", f"/api/branches/{existing[0].id}", {"name": "Synthetic"}),
        (
            "POST",
            f"/api/branches/{existing[0].id}/transition",
            {"status": "closed", "expected_status": "active"},
        ),
    ]
    for method, path, body in calls:
        assert client.request(method, path, json=body).status_code == 401
    headers = authorized(client)
    for bad_headers in (
        {"Origin": ORIGIN},
        {**headers, "Origin": "https://evil.example"},
        {**headers, "X-CSRF-Token": "0" * 64},
    ):
        for method, path, body in calls:
            assert client.request(method, path, json=body, headers=bad_headers).status_code == 403


@pytest.mark.parametrize("mutation", ["create", "rename", "transition"])
def test_audit_failure_rolls_back_business_change(api, monkeypatch, mutation):
    client, factory, _, existing = api
    headers = authorized(client)

    def fail_audit(*args, **kwargs):
        raise SQLAlchemyError("Synthetic audit failure")

    monkeypatch.setattr(branch_module, "record_audit", fail_audit)
    path = f"/api/branches/{existing[0].id}"
    if mutation == "create":
        response = client.post("/api/branches", json={"name": "Never committed"}, headers=headers)
    elif mutation == "rename":
        response = client.patch(path, json={"name": "Never committed"}, headers=headers)
    else:
        response = client.post(
            path + "/transition",
            json={"status": "closed", "expected_status": "active"},
            headers=headers,
        )
    assert response.status_code == 503
    with factory() as db:
        assert db.get(Branch, existing[0].id).name == "Synthetic North"
        assert db.get(Branch, existing[0].id).status == "active"
        assert (
            db.scalar(
                select(func.count()).select_from(Branch).where(Branch.name == "Never committed")
            )
            == 0
        )


def test_database_rejecting_audit_insert_rolls_back_status(api, monkeypatch):
    client, factory, _, existing = api
    headers = authorized(client)
    real_record_audit = branch_module.record_audit

    def invalid_actor_audit(db, **values):
        # A missing actor violates the audit FK at commit, after the branch UPDATE.
        real_record_audit(db, **{**values, "actor_id": uuid4()})

    monkeypatch.setattr(branch_module, "record_audit", invalid_actor_audit)
    response = client.post(
        f"/api/branches/{existing[0].id}/transition",
        json={"status": "closed", "expected_status": "active"},
        headers=headers,
    )
    assert response.status_code == 503
    with factory() as db:
        assert db.get(Branch, existing[0].id).status == "active"
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.entity_type == "branch")
            )
            == 0
        )


def test_concurrent_creates_and_conflicting_transitions(schema_engine):
    factory = sessionmaker(bind=schema_engine, expire_on_commit=False)
    token = secrets.token_urlsafe(32)
    with factory.begin() as db:
        admin = User(
            email=f"concurrent-{uuid4().hex}@example.test",
            display_name="Synthetic Admin",
            role="super_admin",
            password_hash="unused",
        )
        db.add(admin)
        db.flush()
        db.add(
            AuthSession(
                user_id=admin.id,
                token_hash=digest(token),
                csrf_token_hash=digest(csrf_token(token)),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    app = create_app(
        Settings(
            database_url=schema_engine.url.render_as_string(hide_password=False), app_env="test"
        )
    )
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf_token(token)}

    def send(path, body):
        with TestClient(app) as client:
            client.cookies.set("shiplens_session", token)
            return client.post(path, json=body, headers=headers)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda n: send("/api/branches", {"name": f"Concurrent Synthetic {n}"}), range(8)
            )
        )
    assert all(response.status_code == 201 for response in responses)
    assert len({response.json()["code"] for response in responses}) == 8
    branch = responses[0].json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda target: send(
                    f"/api/branches/{branch['id']}/transition",
                    {"status": target, "expected_status": "forming"},
                ),
                ["active", "closed"],
            )
        )
    assert sorted(response.status_code for response in results) == [200, 409]
    with factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.entity_id == branch["id"],
                    AuditEvent.action == "branch.status_changed",
                )
            )
            == 1
        )
