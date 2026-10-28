# Project progress and continuation

Owner: Danish Ahmed <danishsp21@gmail.com>.
Stack: FastAPI, React/TypeScript, PostgreSQL.
Submission deadline: November 2, 2026; exact time not supplied.
Official sample dataset and surprise twist: not supplied.

## Delivery approach

Work in real increments with truthful commit dates. The handbook requires at
least 25 commits across seven days and three merged PRs. Starting October 28
leaves fewer than seven days until November 2. Ask the organizer how this
requirement applies; do not backdate commits or manufacture activity.

Cloud tasks can continue remotely while active, but do not automatically
resume each day. Resume this chat with "continue the next phase". Read this
file and git history first; never assume live processes survived.

## Phases

1. Foundation: architecture, permissions contract, FastAPI database health,
   React bilingual shell, Docker, PostgreSQL, CI, setup and handover docs.
2. Authentication, role/branch enforcement, transactional append-only auditing.
3. Branches, volunteer applications, acceptance-to-member transaction, members.
4. Collections, seven-day locks, weekly auto-drafts and audited approval cycle.
5. Dashboard totals, CSV/PDF exports, bilingual CMS and seven public pages.
6. End-to-end/security/performance checks, Render validation, documentation,
   sample-data reconciliation, video preparation, submission checklist.

Build tests alongside phases, rather than leaving verification until phase 6.
Aim to deploy the foundation early. Every phase should leave meaningful
commits, reviewable PRs where API access permits, and updated evidence here.
Do not represent planned features as implemented or self-generated data as
organizer-provided sample data.

## Current evidence

### Phase 1 — complete and merged

PR #1 is merged into main as f808347; ancestry verified through the Git proxy.
It preserved the participant's five genuine foundation commits. GitHub API
access is still denied (HTTP proxy 403), so hosted Actions status is not
independently confirmed by the agent.

### Phase 2 — implemented and locally verified

Branch: feat/auth-permissions-audit. Prepared on October 28, 2026.

- Alembic identity migration: branches, users, server sessions, login limits,
  append-only audit events. Repeat migration is safe. Database sequence codes
  are unique under concurrent creation and are not reused after rollback.
- Secure login/logout/me for all five roles; salted scrypt hashes (N=16384,
  r=8, p=5), hashed opaque session tokens, secure production cookie flags,
  stable per-session CSRF and strict origin checks, fixed expiry, revocation,
  inactive-user rejection and PostgreSQL-backed throttling.
- Super Admin user list/create; real scoped branch list/detail and audit reads.
  Valid-CSRF endpoint tests prove role denials rather than merely CSRF denials.
- Transactional audit writes and snapshot allowlists. PostgreSQL rejects direct
  UPDATE, DELETE and TRUNCATE. Explicit CLI admin/demo provisioning validates
  inputs, does not print credentials, and does not overwrite accounts.
- Bilingual login/workspace, role-aware reads, user creation, safe errors,
  session restore and logout. Vite proxy preserves /api and targets current API.
- Independent review: 49 backend tests pass with real PostgreSQL, 98.02%
  implemented-backend coverage, Ruff clean. 11 frontend tests and TS/Vite
  production build pass. One upstream TestClient deprecation warning remains.
- Final Docker image builds with dependency hashes and TLS checks intact.
  Compose applies migration before startup and is healthy. Alembic head is
  0001_identity_audit. Unauthenticated /api/auth/me returns 401 as expected.
- Separate disposable-database/container real HTTP smoke passed: migrations,
  seed, all five logins, stable CSRF/session restore, user creation and role
  denials, missing-CSRF denial, logout and revoked-session rejection. Smoke
  database/container were removed. No demo password or accounts were left in
  the regular Compose database; provision an account explicitly to sign in.
- Saved cloud startup instructions updated for migrations/auth configuration.
  The draft still requires review/save and environment publication. Saving
  instructions has not changed runtime network access or deployed Render.

No member/application, collection/report, dashboard/export, or CMS workflow is
implemented yet. No live Render URL or hosted CI result is confirmed. Tests do
not yet prove permissions for endpoints that do not exist.

## Next phase

Phase 3: branch lifecycle administration, public volunteer applications,
HR acceptance creating members atomically, member records/search/filtering,
and associated audit, permission and concurrency tests. Preserve each phase
as a reviewable PR and continue genuine incremental commits.

## Required external actions

- Create and review the phase 2 PR into main; wait for hosted checks before
  merging with a merge commit. API access remains blocked despite Git pushes.
- Review/save the cloud environment draft and publish it; api.github.com is
  the requested network addition for PR/Actions operations. Retry API access
  afterward before diagnosing any separate authentication problem.
- Connect the repository to Render using render.yaml and validate the live URL.
  No Render API credentials are available to automate this in the current task.
- Confirm the exact November 2 cutoff time and ask the organizer about the
  seven-day commit requirement. Supply official sample data/twist when available.
