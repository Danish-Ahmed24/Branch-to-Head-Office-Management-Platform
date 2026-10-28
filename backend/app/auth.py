"""Opaque cookie sessions, CSRF protection and scoped administration endpoints."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.models import AuditEvent, AuthSession, Branch, LoginAttempt, User
from app.permissions import require_permission

router = APIRouter(prefix="/api")
Role = Literal["super_admin", "finance_reviewer", "content_editor", "branch_lead", "hr_lead"]
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 5


def hash_password(password: str) -> str:
    """Salted scrypt with fixed, versioned work factors; never stored as plaintext."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P)
    return f"scrypt${PASSWORD_N}${PASSWORD_R}${PASSWORD_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        # Refuse arbitrary database-supplied work factors to bound resource use.
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (
            PASSWORD_N,
            PASSWORD_R,
            PASSWORD_P,
        ):
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P
        )
        return hmac.compare_digest(candidate, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password("not-a-user-password-" + secrets.token_hex(16))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(raw_session: str) -> str:
    return hmac.new(raw_session.encode(), b"shiplens-csrf", hashlib.sha256).hexdigest()


def cookie_name(request: Request) -> str:
    return (
        "__Host-shiplens_session"
        if request.app.state.settings.app_env == "production"
        else "shiplens_session"
    )


def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session


Db = Annotated[Session, Depends(get_db)]


def validate_origin(request: Request) -> None:
    settings = request.app.state.settings
    allowed = {settings.public_origin} if settings.public_origin else set()
    if settings.app_env != "production":
        allowed.update(settings.cors_origins)
    if request.headers.get("origin") not in allowed:
        raise HTTPException(status_code=403, detail="Request origin denied")


def current_session(request: Request, db: Db) -> tuple[User, AuthSession, str]:
    token = request.cookies.get(cookie_name(request), "")
    if not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="Authentication required")
    found = db.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == digest(token),
            AuthSession.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
    ).first()
    if found is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return found[0], found[1], token


Current = Annotated[tuple[User, AuthSession, str], Depends(current_session)]


def validate_csrf(request: Request, current: tuple[User, AuthSession, str]) -> None:
    validate_origin(request)
    provided = request.headers.get("x-csrf-token", "")
    if len(provided) != 64 or not hmac.compare_digest(digest(provided), current[1].csrf_token_hash):
        raise HTTPException(status_code=403, detail="CSRF token invalid")


def user_json(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "is_active": user.is_active,
    }


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count("@") != 1 or any(c.isspace() for c in value):
            raise ValueError("Invalid email address")
        local, domain = value.split("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Invalid email address")
        return value


class CreateUserBody(LoginBody):
    password: str = Field(min_length=12, max_length=128, repr=False)
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    branch_id: UUID | None = None

    @field_validator("display_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Display name is required")
        return value.strip()

    @model_validator(mode="after")
    def valid_branch(self):
        if (self.role == "branch_lead") != (self.branch_id is not None):
            raise ValueError("Only branch leads must have a branch assignment")
        return self


def record_attempt(db: Session, request: Request, email: str) -> bool:
    """Serialize per-account and per-peer limits in PostgreSQL, shared by workers."""
    now = datetime.now(UTC)
    # Ignore X-Forwarded-For: only a trusted server/proxy may set ASGI peer identity.
    peer = request.client.host if request.client else "unknown"
    keys = [(digest("email:" + email), 10), (digest("ip:" + peer), 30)]
    for key, _ in sorted(keys):
        lock = int(key[:15], 16)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    blocked = False
    for key, maximum in keys:
        count = db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.key == key, LoginAttempt.attempted_at > now - timedelta(minutes=15))
        )
        if count >= maximum:
            blocked = True
    if not blocked:
        for key, _ in keys:
            db.add(LoginAttempt(key=key, attempted_at=now))
    # Bounded retention. Deletion is transactionally scoped to the current keys.
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.key.in_([key for key, _ in keys]),
            LoginAttempt.attempted_at < now - timedelta(days=1),
        )
    )
    return not blocked


@router.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response, db: Db):
    validate_origin(request)
    if not record_attempt(db, request, body.email):
        record_audit(
            db,
            actor_id=None,
            action="auth.login_throttled",
            entity_type="auth",
            entity_id=digest(body.email),
            after={"success": False, "reason": "rate_limit"},
        )
        db.commit()
        raise HTTPException(
            status_code=429, detail="Too many login attempts", headers={"Retry-After": "900"}
        )
    user = db.scalar(select(User).where(User.email == body.email))
    valid_password = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid_password or not user.is_active:
        record_audit(
            db,
            actor_id=None,
            action="auth.login_failed",
            entity_type="auth",
            entity_id=digest(body.email),
            after={"success": False},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    previous = request.cookies.get(cookie_name(request), "")
    if previous:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(previous)))
    token = secrets.token_urlsafe(32)
    csrf = csrf_token(token)
    expires = datetime.now(UTC) + timedelta(seconds=request.app.state.settings.session_ttl_seconds)
    session = AuthSession(
        user_id=user.id, token_hash=digest(token), csrf_token_hash=digest(csrf), expires_at=expires
    )
    db.add(session)
    record_audit(
        db,
        actor_id=user.id,
        action="auth.login",
        entity_type="auth",
        entity_id=str(user.id),
        branch_id=user.branch_id,
        after={"success": True},
    )
    db.commit()
    response.set_cookie(
        cookie_name(request),
        token,
        httponly=True,
        secure=request.app.state.settings.app_env == "production",
        samesite="lax",
        max_age=request.app.state.settings.session_ttl_seconds,
        path="/",
    )
    return {"user": user_json(user), "csrf_token": csrf}


@router.get("/auth/me")
def me(current: Current):
    return {"user": user_json(current[0]), "csrf_token": csrf_token(current[2])}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Db, current: Current):
    validate_csrf(request, current)
    user, session, _ = current
    db.delete(session)
    record_audit(
        db,
        actor_id=user.id,
        action="auth.logout",
        entity_type="auth",
        entity_id=str(user.id),
        branch_id=user.branch_id,
    )
    db.commit()
    response.delete_cookie(
        cookie_name(request),
        path="/",
        httponly=True,
        secure=request.app.state.settings.app_env == "production",
        samesite="lax",
    )


@router.get("/users")
def list_users(
    db: Db, current: Current, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    require_permission(current[0].role, "users.manage")
    users = db.scalars(select(User).order_by(User.email).limit(limit).offset(offset)).all()
    return {"items": [user_json(user) for user in users], "limit": limit, "offset": offset}


@router.post("/users", status_code=201)
def create_user(body: CreateUserBody, request: Request, db: Db, current: Current):
    require_permission(current[0].role, "users.manage")
    validate_csrf(request, current)
    if body.branch_id and db.get(Branch, body.branch_id) is None:
        raise HTTPException(status_code=422, detail="Branch does not exist")
    user = User(
        email=body.email,
        display_name=body.display_name,
        role=body.role,
        branch_id=body.branch_id,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
        record_audit(
            db,
            actor_id=current[0].id,
            action="user.created",
            entity_type="user",
            entity_id=str(user.id),
            branch_id=user.branch_id,
            after=user_json(user),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="User already exists or assignment is invalid"
        ) from None
    return user_json(user)


def branch_json(branch: Branch) -> dict:
    return {"id": str(branch.id), "code": branch.code, "name": branch.name, "status": branch.status}


@router.get("/branches")
def list_branches(
    db: Db, current: Current, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    user = current[0]
    require_permission(user.role, "branches.read")
    query = select(Branch)
    if user.role == "branch_lead":
        query = query.where(Branch.id == user.branch_id)
    branches = db.scalars(query.order_by(Branch.code).limit(limit).offset(offset)).all()
    return {"items": [branch_json(branch) for branch in branches], "limit": limit, "offset": offset}


@router.get("/branches/{branch_id}")
def get_branch(branch_id: UUID, db: Db, current: Current):
    user = current[0]
    require_permission(user.role, "branches.read")
    query = select(Branch).where(Branch.id == branch_id)
    if user.role == "branch_lead":
        query = query.where(Branch.id == user.branch_id)
    branch = db.scalar(query)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch_json(branch)


@router.get("/audit")
def list_audit(
    db: Db, current: Current, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    user = current[0]
    require_permission(user.role, "audit.read")
    query = select(AuditEvent)
    if user.role == "branch_lead":
        query = query.where(AuditEvent.branch_id == user.branch_id)
    elif user.role == "finance_reviewer":
        query = query.where(
            AuditEvent.entity_type.in_(["collection", "report", "collections", "reports"])
        )
    elif user.role == "hr_lead":
        query = query.where(
            AuditEvent.entity_type.in_(["application", "member", "applications", "members"])
        )
    events = db.scalars(query.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).all()
    return {
        "items": [
            {
                "id": event.id,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "branch_id": str(event.branch_id) if event.branch_id else None,
                "before": event.before,
                "after": event.after,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
        "limit": limit,
        "offset": offset,
    }
