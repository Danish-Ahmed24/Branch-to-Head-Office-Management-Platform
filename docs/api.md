# API — foundation

The interactive FastAPI OpenAPI documentation is at `/docs`, with the schema
at `/openapi.json` in development. They are disabled with
`APP_ENV=production`. These expose the current API, not planned endpoints.

## GET /health and GET /api/health

Unauthenticated readiness check. Runs a PostgreSQL `SELECT 1` and returns
HTTP 200 only when the database is reachable. Database failures return 503
with a generic body, without connection strings or exception details. `/api`
provides the same-origin prefix used by the React client.

The frontend production assets are optionally served from `STATIC_DIR`;
without it, the backend can run independently. There are no login, application,
collection, report, or management endpoints in this milestone.

## Future API contract

Future mutations require authentication, CSRF protection, role and branch
checks, validated inputs, transactional audit writes, and explicit state
transitions. Tests must verify both allowed and forbidden actions. Exports
must obey the same permissions and protect against spreadsheet formulas.
