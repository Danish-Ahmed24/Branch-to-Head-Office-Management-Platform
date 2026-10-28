# Operations and handover

## Current scope

The foundation is a runnable scaffold, not a submission-ready platform. There
are no demo logins or business tables yet. Do not load real personal data.
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
   `PORT`. The image serves React and FastAPI under one origin. Leave
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
backups and test restore procedures before real use. Schema migrations and
seed-data commands will be documented with the first domain-model phase.

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
