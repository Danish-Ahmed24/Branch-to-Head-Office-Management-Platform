"""Deny-by-default grants and row scope shared by API handlers."""

from fastapi import HTTPException

ROLES = frozenset({"super_admin", "finance_reviewer", "content_editor", "branch_lead", "hr_lead"})

GRANTS = {
    "branches.manage": frozenset({"super_admin"}),
    "users.manage": frozenset({"super_admin"}),
    "branches.read": frozenset({"super_admin", "finance_reviewer", "branch_lead", "hr_lead"}),
    "audit.read": frozenset({"super_admin", "finance_reviewer", "branch_lead", "hr_lead"}),
}


def require_permission(role: str, action: str) -> None:
    if role not in GRANTS.get(action, frozenset()):
        raise HTTPException(status_code=403, detail="Permission denied")
