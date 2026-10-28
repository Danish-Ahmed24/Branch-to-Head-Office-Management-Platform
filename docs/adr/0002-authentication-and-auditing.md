# ADR 0002: Opaque sessions, scoped authorization, and append-only auditing

Status: accepted for phase 2; 2026-10-28.

## Decisions

Use server-side PostgreSQL sessions and opaque random cookie tokens. Store
only token hashes. Production cookies use the `__Host-` prefix, Secure,
HttpOnly, SameSite=Lax, and Path=/ with no Domain attribute. Development
cookies intentionally omit Secure for the local HTTP workflow. Passwords are
salted and hashed using scrypt; passwords and session/CSRF secrets are never
included in audit snapshots or API user representations.

All browser mutation requests require an exact approved Origin, including
login. Authenticated mutations also require a session-bound CSRF token.
The CSRF value is returned in authentication JSON and kept in memory by the
frontend; fetching the current session does not invalidate other browser tabs.
Production accepts only PUBLIC_ORIGIN (or Render's injected external URL),
not arbitrary request Host headers. Development additionally permits explicit
configured CORS origins. Production uses HTTPS.

Rate-limit login attempts in PostgreSQL, not process-local memory. Do not
trust client-supplied forwarding headers for access-control decisions. Check
session expiry and active user status on every protected request. Auth
responses must not be cached. Use generic authentication errors and redact
validation input values.

Permissions default to denied. Query branch rows within the authenticated
user's allowed branch scope, including direct identifier lookups. Never treat
frontend visibility as authorization. Financial/HR audit readers receive only
their permitted event categories; branch users receive only their branch.

Use Alembic to apply schema changes explicitly. Store users, branch identities,
sessions, login attempts, and audit events in PostgreSQL. Domain services add
audit events inside the same transaction as the change. Field allowlists
exclude sensitive snapshot values. PostgreSQL triggers reject audit UPDATE,
DELETE, and TRUNCATE, including direct SQL during tests. No application role
can edit or delete audit records.

## Trade-offs and operational limits

Schema-owner/database-superuser access can alter schema and triggers; database
operator credentials remain an infrastructure trust boundary. Migrations run
before the single application instance starts. A future multi-replica rollout
must run migrations once as a separate deployment step, rather than racing
multiple entrypoints. Expired sessions and old login-attempt rows need an
operational retention/cleanup policy as usage grows; never prune audit history
through ordinary application endpoints.

Phase 2 establishes security infrastructure and user administration. It does
not implement collection/report state machines or prove permissions for
endpoints that do not exist yet. Add tests and audit field allowlists when
those domains are introduced. Password reset, MFA, and recovery workflows
remain future hardening work.
