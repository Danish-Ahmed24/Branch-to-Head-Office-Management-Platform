# Operations and handover

## Current scope

The authentication/audit foundation is runnable, but not submission-ready.
There are identity tables and explicitly provisioned login accounts; member,
collection, reporting, and CMS workflows remain pending. Do not load real personal data.
Only synthetic demo data is allowed. Official sample data and the twist are
pending from the organizer.

## Render deployment

1. Connect the GitHub repository in your Render account and create a Blueprint
   using `render.yaml`. Review current pricing and free-plan availability
   before creating resources. The blueprint requests a web service and a
   PostgreSQL database; it has not itself deployed anything.
2. Choose the feature branch for a temporary foundation preview or merge the
   reviewed foundation into `main` before creating the final deployment.
3. Render injects `DATABASE_URL` from the database connection and provides
   `PORT` and `RENDER_EXTERNAL_URL` (the default approved browser origin). The image serves React and FastAPI under one origin. Leave
   `CORS_ORIGINS=[]` for this production configuration.
4. Check build logs and request `/health`: it must return 200 with a healthy
   database. Open the page and switch English/Urdu. An unavailable database
   must cause a 503 readiness response.
5. Record the live URL in README only after validating it. Keep the service
   and database available until judging ends. Free services may sleep and
   free databases may expire; verify Render's current policies and budget
   before submission. Wake the service before the defense.

No Render API credentials are presently configured. Do not paste credentials
into chat or commit them. Use the hosting provider's secure environment UI.
The cloud environment's development services are not a public deployment.

## Runtime and data

`docker compose up --build -d --wait` starts the complete local stack. The
production image runs as a non-root user and checks database readiness.
`docker compose logs web` inspects startup failures. Do not publish logs
containing sensitive connection information.

PostgreSQL data is stored in the `postgres_data` volume. Stopping services
retains it; removing volumes destroys it. For production, configure database
backups and test restore procedures before real use. Identity migrations and explicit account provisioning are documented below.
Official sample-data loading remains pending.

## Continuation and submission

Read `docs/progress.md` before resuming. Follow a real feature branch/PR workflow
and preserve participant authorship. Track official updates yourself: an AI
agent does not continuously monitor the ShipLens channel. The participant
must record and submit the final five-minute video and defend the work.
The final checklist must include all four acceptance gates, full bilingual
workflows, backend coverage, live demo users, and a green main-branch CI run.

## Codex cloud environment

This isolated task uses the existing checkout under
`/workspace/Branch-to-Head-Office-Management-Platform`; no Git worktree is
needed. Reusable configuration saves `scripts/cloud_install.sh` as the install
command. Python dependencies are retained in `/workspace/.venvs/shiplens`.
Node dependencies are retained in `frontend/node_modules`.

The cloud Docker build needs the platform's supplied proxy to be resolvable
inside build containers. `scripts/cloud_build.py` forwards existing proxy
bindings by name, resolves the supplied proxy hostname, and mounts the supplied
CA bundle as a temporary BuildKit secret. It preserves TLS and package-hash
verification and does not persist credentials or the CA bundle in the image.
It is cloud-specific; ordinary local development uses Compose directly.
Use `DOCKER_CONFIG=/tmp/shiplens-docker` here because the home directory is
read-only. After installation:

```sh
DOCKER_CONFIG=/tmp/shiplens-docker docker compose up --no-build -d --wait
curl --fail http://127.0.0.1:8000/health
```

Git pushes use the platform Git proxy. GitHub API access is separately scoped:
`api.github.com` must be allowed to create PRs or inspect Actions runs. A saved
network draft alone does not prove access has changed. Render deployment also
requires access to the participant's Render account; a blueprint is not a
live service.

## Identity migrations and provisioning (phase 2)

The container now runs `alembic upgrade head` before starting its single web
process. Migration failure stops startup. For host development, from `backend`
with DATABASE_URL exported:

```sh
../.venv/bin/alembic upgrade head
```

The schema contains branch identities, users, sessions, login attempts, and
append-only audit records. Migrations are repeatable, and do not automatically
create accounts. Never use `create_all` to substitute for migrations. Do not
run application migrations concurrently across multiple replicas; use a single
release job if scaling beyond this initial deployment model.

To create a first administrator, supply ADMIN_EMAIL, ADMIN_DISPLAY_NAME, and
ADMIN_PASSWORD securely to the process, then run `python -m app.cli init-admin`
from `backend` using the activated virtual environment. The password must be
12–128 characters. No password values belong in Git or shell history. Provisioning
refuses to overwrite an existing account. For example, enter the password
through a terminal's hidden prompt rather than embedding it in a command:

```sh
read -r -s -p 'Admin password: ' ADMIN_PASSWORD
export ADMIN_PASSWORD
python -m app.cli init-admin
unset ADMIN_PASSWORD
```

For a separate, empty development database only, set DEMO_PASSWORD securely
and run `python -m app.cli seed-demo`. It creates a synthetic branch and five
accounts: super_admin@example.invalid, finance_reviewer@example.invalid,
content_editor@example.invalid, branch_lead@example.invalid, hr_lead@example.invalid.
They share the supplied demo password; no default is built in. This is not the
official sample dataset, and the command refuses production and nonempty
identity databases. Use unique strong credentials for any public judge accounts.

A Super Admin can create users through the bilingual interface. Existing
branch assignments are selectable; branch creation/lifecycle administration
will arrive in the next domain phase. There are no password reset or user
update/deactivation interfaces yet. Recover administrative access through an
explicitly reviewed operator procedure, never by silently resetting passwords
in the seed command.

Production requires PUBLIC_ORIGIN with an exact HTTPS origin; on Render the
injected RENDER_EXTERNAL_URL is the fallback. Changing to a custom domain
requires updating PUBLIC_ORIGIN. Local Compose intentionally sets development
mode and http://localhost:8000; use that origin for browser login. Hot reload
also permits the explicitly configured http://localhost:5173 origin. Do not
carry the local development override into Render.
