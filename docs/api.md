# API — authentication and permission foundation

Development OpenAPI is at `/docs` and `/openapi.json`; production disables
those routes. All management routes are under `/api`, and responses are
`Cache-Control: no-store`. Lists return `{items, limit, offset}` with default
limit 50 and maximum 100. Identifiers are UUID strings except numeric audit IDs.

| Method and path | Access / result |
| --- | --- |
| `GET /health`, `GET /api/health` | Public database readiness: 200 `{status:"ok",database:"ok"}`, or sanitized 503 |
| `POST /api/auth/login` | Exact approved Origin; JSON `{email,password}`; returns `{user,csrf_token}` and HttpOnly session cookie |
| `GET /api/auth/me` | Valid active session; same `{user,csrf_token}` shape; no CSRF rotation |
| `POST /api/auth/logout` | Session, approved Origin, `X-CSRF-Token`; revokes session, clears cookie, returns 204 |
| `GET /api/users` | Super Admin only; paginated user list, never password hashes |
| `POST /api/users` | Super Admin, session + Origin + CSRF; creates user and audit entry atomically; returns 201 |
| `GET /api/branches` | Admin/Finance/HR: all; Branch Lead: assigned branch; Content Editor denied |
| `GET /api/branches/{uuid}` | Same scope; inaccessible/nonexistent branch returns 404 |
| `GET /api/audit` | Admin: all; Finance: collections/reports; HR: applications/members; Branch Lead: own branch; Content Editor denied |

User creation accepts `email`, `password` (12–128 characters), `display_name`,
`role`, and nullable `branch_id`. Roles are `super_admin`, `finance_reviewer`,
`content_editor`, `branch_lead`, and `hr_lead`. Branch Leads must receive an
existing branch UUID; other roles cannot receive a branch assignment. Invalid
input returns 422; duplicate accounts return 409. Responses exclude passwords.

Login requires a real user provisioned explicitly via CLI or a Super Admin.
Email is normalized to lowercase. Invalid and inactive credentials return the
same 401 response. The PostgreSQL limiter returns 429 with Retry-After after
10 attempts per email or 30 per peer in 15 minutes. Client-supplied forwarding
headers are not directly trusted by the application. Secure the ASGI proxy
trust configuration before deployment behind additional proxies.

The frontend keeps the CSRF value in memory and restores it via `/auth/me`;
never store the session token in localStorage. Missing/invalid sessions return
401; forbidden roles/origins/CSRF return 403. Production cookies require HTTPS.
A successful `/health` does not establish deployment or business readiness.

This phase has no member, application, collection, report, export, or publishing
endpoints. Their permission and transaction tests must be added in later phases.
