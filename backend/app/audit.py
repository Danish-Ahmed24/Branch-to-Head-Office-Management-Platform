"""Append an audit event in the caller's transaction, excluding sensitive fields."""

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent

_USER_FIELDS = {"id", "email", "display_name", "role", "branch_id", "is_active"}
_BRANCH_FIELDS = {"id", "code", "name", "status"}
_SESSION_FIELDS = {"id", "user_id", "email", "role", "expires_at", "is_active", "success", "reason"}
_SNAPSHOT_FIELDS = {
    "user": _USER_FIELDS,
    "users": _USER_FIELDS,
    "branch": _BRANCH_FIELDS,
    "branches": _BRANCH_FIELDS,
    "auth_session": _SESSION_FIELDS,
    "session": _SESSION_FIELDS,
    "auth": _SESSION_FIELDS,
}


def _snapshot(entity_type: str, values: dict | None) -> dict | None:
    if values is None:
        return None
    allowed = _SNAPSHOT_FIELDS.get(entity_type)
    if allowed is None:
        raise ValueError("Audit snapshots require a registered field allowlist")
    result = {}
    for field, value in values.items():
        if field not in allowed:
            continue
        if isinstance(value, UUID | datetime | date):
            value = str(value)
        elif isinstance(value, Enum):
            value = value.value
        if value is not None and not isinstance(value, str | bool | int | float):
            raise ValueError("Audit snapshot fields must be scalar values")
        result[field] = value
    return result


def record_audit(
    session: Session,
    *,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: str,
    branch_id: UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        branch_id=branch_id,
        before=_snapshot(entity_type, before),
        after=_snapshot(entity_type, after),
    )
    session.add(event)
    return event
