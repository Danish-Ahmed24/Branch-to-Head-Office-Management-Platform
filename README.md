# ShipLens — Branch to Head Office

A bilingual volunteer-organisation management platform for ShipLens Challenge
01. Built by Danish Ahmed with FastAPI, React/TypeScript, and PostgreSQL.

**Current milestone: authentication and audit foundation.** Database-aware
health, a bilingual React login workspace, five roles, scoped branch/audit
reads, Super Admin user creation, PostgreSQL migrations, and append-only
auditing are implemented. The October 29 increment adds Super Admin branch
creation, rename, and enforced lifecycle transitions. Membership, money/reporting workflows, seven public
content pages, and official sample-data reconciliation remain future phases.
There is no confirmed live Render deployment yet.

## Local setup

Prerequisites: Docker Engine with Compose v2. From the repository root:

```sh
docker compose up --build -d --wait
curl --fail http://127.0.0.1:8000/health
```

The application is served on port 8000. Compose credentials are local examples,
not production credentials. `docker compose down` stops services and retains
data. `docker compose down -v` permanently deletes local database data.

## Development with hot reload

Use Python 3.12 and Node 24. Install the development dependencies:

```sh
python -m venv .venv
.venv/bin/pip install --require-hashes -r backend/requirements-dev.txt
(cd frontend && npm ci)
```

For this hot-reload workflow, use an existing local PostgreSQL database or
start the development database below instead of the full Compose stack
(which intentionally keeps its database private). Do not use production data:

```sh
docker run -d --name shiplens-postgres -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=shiplens postgres:17-alpine
cp .env.example .env
set -a
. ./.env
set +a
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.asgi:app --host 0.0.0.0 --port 8000 --reload
```

In another terminal, run `cd frontend && npm run dev`. Vite proxies `/api` to
the backend. Open the frontend at port 5173 in your local browser. Never commit
`.env` files. `.env.example` lists supported configuration; backend does not
implicitly load a root `.env` file. The cloud environment has separate saved
startup instructions and may retain dependencies outside the checkout.

## Tests

With the example environment variables exported and PostgreSQL ready:

```sh
cd backend
../.venv/bin/ruff check .
../.venv/bin/pytest --cov=app --cov-report=term-missing
cd ../frontend
npm test
npm run build
```

`TEST_DATABASE_URL` must point to PostgreSQL to run integration checks.
An absent variable means integration tests are skipped, not passed. The CI
pipeline supplies a PostgreSQL test service and enforces backend coverage of
at least 60%. Present coverage describes the implemented phases only; later features
must retain coverage and add permission/business-rule tests.

## Deploy and contribute

See [handover](docs/handover.md) for Render setup and operational checks,
[API](docs/api.md), [permission contract](docs/permissions.md),
[architecture decision](docs/adr/0001-architecture.md), and
[progress/next phases](docs/progress.md). AI assistance is disclosed in
[AI-USAGE.md](AI-USAGE.md). The project is licensed under MIT.

Use feature branches and reviewable PRs. Do not backdate commits. The seven-day
commit requirement needs clarification against the November 2 deadline.

## Open-source credits

FastAPI, SQLAlchemy, React, Vite, and TypeScript are used under their respective
open-source licences. The self-hosted Noto Nastaliq Urdu font is distributed
through Fontsource under the SIL Open Font License 1.1; see
[third-party notices](docs/third-party-notices.md). Dependency versions are
recorded in the Python hash locks and npm lockfile.

## First login

Accounts are created explicitly; no public default password exists. See
[provisioning instructions](docs/handover.md#identity-migrations-and-provisioning-phase-2)
for secure first-admin creation and the synthetic nonproduction demo seed.
Use http://localhost:8000 for local Compose login, or http://localhost:5173
for Vite hot reload. Production requires an exact HTTPS PUBLIC_ORIGIN
(defaults to RENDER_EXTERNAL_URL on Render) and uses Secure cookies.
