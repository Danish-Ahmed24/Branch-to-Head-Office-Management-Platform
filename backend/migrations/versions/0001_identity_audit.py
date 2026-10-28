"""Identity, branch code sequence, server sessions, and append-only audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_identity_audit"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SEQUENCE branch_code_seq")
    op.execute("""
        CREATE FUNCTION next_branch_code() RETURNS text LANGUAGE plpgsql AS $$
        DECLARE number bigint;
        BEGIN
            number := nextval('branch_code_seq');
            RETURN 'BR-' || lpad(number::text, greatest(4, length(number::text)), '0');
        END;
        $$
    """)
    op.create_table(
        "branches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "code",
            sa.String(32),
            nullable=False,
            unique=True,
            server_default=sa.text("next_branch_code()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="forming"),
        sa.CheckConstraint(
            "status IN ('forming','active','paused','closed')", name="branch_status"
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="branch_name_nonempty"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("branch_id", sa.Uuid(), sa.ForeignKey("branches.id")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.CheckConstraint("email = lower(trim(email))", name="user_email_normalized"),
        sa.CheckConstraint(
            "role IN ('super_admin','finance_reviewer','content_editor','branch_lead','hr_lead')",
            name="user_role",
        ),
        sa.CheckConstraint(
            "role != 'branch_lead' OR branch_id IS NOT NULL", name="branch_lead_scope"
        ),
    )
    op.create_index("ix_users_branch_id", "users", ["branch_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_login_attempt_key_time", "login_attempts", ["key", "attempted_at"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("branch_id", sa.Uuid(), sa.ForeignKey("branches.id")),
        sa.Column("before", JSONB(none_as_null=True)),
        sa.Column("after", JSONB(none_as_null=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_events_branch_id", "audit_events", ["branch_id"])
    op.create_index("ix_audit_event_created", "audit_events", ["created_at", "id"])
    op.execute("""
        CREATE FUNCTION prevent_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only' USING ERRCODE = '42501';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER audit_events_immutable
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER audit_events_immutable ON audit_events")
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION prevent_audit_mutation()")
    op.drop_table("login_attempts")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_table("branches")
    op.execute("DROP FUNCTION next_branch_code()")
    op.execute("DROP SEQUENCE branch_code_seq")
