"""Explicit provisioning commands. Passwords are read only from process bindings."""

import argparse
import os

from sqlalchemy import select

from app.audit import record_audit
from app.config import Settings
from app.database import make_engine, make_session_factory
from app.models import Branch, User


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Set {name} securely in the process environment")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init-admin", "seed-demo"])
    args = parser.parse_args()
    settings = Settings()
    from app.auth import CreateUserBody, hash_password

    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with make_session_factory(engine).begin() as session:
            if args.command == "init-admin":
                data = CreateUserBody(
                    email=_required("ADMIN_EMAIL"),
                    password=_required("ADMIN_PASSWORD"),
                    display_name=os.environ.get("ADMIN_DISPLAY_NAME", "Administrator"),
                    role="super_admin",
                )
                if session.scalar(select(User).where(User.email == data.email)):
                    raise ValueError("Account already exists; no password or role was changed")
                user = User(
                    email=data.email,
                    display_name=data.display_name,
                    role=data.role,
                    password_hash=hash_password(data.password),
                )
                session.add(user)
                session.flush()
                record_audit(
                    session,
                    actor_id=user.id,
                    action="user.provisioned",
                    entity_type="user",
                    entity_id=str(user.id),
                    after={"id": user.id, "email": user.email, "role": user.role},
                )
            else:
                if settings.app_env == "production":
                    raise ValueError("Demo provisioning is forbidden in production")
                password = _required("DEMO_PASSWORD")
                CreateUserBody(
                    email="validation@example.invalid",
                    password=password,
                    display_name="Validation",
                    role="super_admin",
                )
                if session.scalar(select(User.id).limit(1)):
                    raise ValueError("Demo provisioning requires an empty identity database")
                branch = Branch(name="Synthetic Demo Branch", status="active")
                session.add(branch)
                session.flush()
                record_audit(
                    session,
                    actor_id=None,
                    action="branch.created",
                    entity_type="branch",
                    entity_id=str(branch.id),
                    branch_id=branch.id,
                    after={"code": branch.code, "name": branch.name, "status": branch.status},
                )
                for role in [
                    "super_admin",
                    "finance_reviewer",
                    "content_editor",
                    "branch_lead",
                    "hr_lead",
                ]:
                    data = CreateUserBody(
                        email=f"{role}@example.invalid",
                        display_name=f"Demo {role}",
                        role=role,
                        branch_id=branch.id if role == "branch_lead" else None,
                        password=password,
                    )
                    user = User(
                        **data.model_dump(exclude={"password"}),
                        password_hash=hash_password(data.password),
                    )
                    session.add(user)
                    session.flush()
                    record_audit(
                        session,
                        actor_id=None,
                        action="user.provisioned",
                        entity_type="user",
                        entity_id=str(user.id),
                        branch_id=user.branch_id,
                        after={"id": user.id, "email": user.email, "role": user.role},
                    )
        print(f"{args.command} completed; credentials were not printed")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
