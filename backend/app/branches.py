"""Branch administration with serialized lifecycle transitions and atomic auditing."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.audit import record_audit
from app.auth import Current, Db, branch_json, validate_csrf
from app.models import Branch
from app.permissions import require_permission

router = APIRouter(prefix="/api/branches", tags=["branches"])
Status = Literal["forming", "active", "paused", "closed"]
TRANSITIONS = {
    "forming": frozenset({"active", "closed"}),
    "active": frozenset({"paused", "closed"}),
    "paused": frozenset({"active", "closed"}),
    "closed": frozenset(),
}


class BranchName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Branch name is required")
        return value.strip()


class BranchTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status
    expected_status: Status


def locked_branch(db: Db, branch_id: UUID) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.id == branch_id).with_for_update())
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


@router.post("", status_code=201)
def create_branch(body: BranchName, request: Request, db: Db, current: Current):
    require_permission(current[0].role, "branches.manage")
    validate_csrf(request, current)
    branch = Branch(name=body.name, status="forming")
    db.add(branch)
    db.flush()
    record_audit(
        db,
        actor_id=current[0].id,
        action="branch.created",
        entity_type="branch",
        entity_id=str(branch.id),
        branch_id=branch.id,
        after=branch_json(branch),
    )
    db.commit()
    return branch_json(branch)


@router.patch("/{branch_id}")
def rename_branch(branch_id: UUID, body: BranchName, request: Request, db: Db, current: Current):
    require_permission(current[0].role, "branches.manage")
    validate_csrf(request, current)
    branch = locked_branch(db, branch_id)
    before = branch_json(branch)
    if branch.name == body.name:
        raise HTTPException(status_code=409, detail="Branch name is unchanged")
    branch.name = body.name
    record_audit(
        db,
        actor_id=current[0].id,
        action="branch.renamed",
        entity_type="branch",
        entity_id=str(branch.id),
        branch_id=branch.id,
        before=before,
        after=branch_json(branch),
    )
    db.commit()
    return branch_json(branch)


@router.post("/{branch_id}/transition")
def transition_branch(
    branch_id: UUID, body: BranchTransition, request: Request, db: Db, current: Current
):
    require_permission(current[0].role, "branches.manage")
    validate_csrf(request, current)
    branch = locked_branch(db, branch_id)
    if branch.status != body.expected_status:
        raise HTTPException(status_code=409, detail="Branch status changed; refresh and retry")
    if body.status not in TRANSITIONS[branch.status]:
        raise HTTPException(status_code=409, detail="Branch status transition is not allowed")
    before = branch_json(branch)
    branch.status = body.status
    record_audit(
        db,
        actor_id=current[0].id,
        action="branch.status_changed",
        entity_type="branch",
        entity_id=str(branch.id),
        branch_id=branch.id,
        before=before,
        after=branch_json(branch),
    )
    db.commit()
    return branch_json(branch)
