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
| `POST /api/branches` | Super Admin + Origin + CSRF; `{name}` creates a Forming branch with a database-generated code; returns 201 |
| `PATCH /api/branches/{uuid}` | Super Admin + Origin + CSRF; `{name}` renames a branch without changing its code |
| `POST /api/branches/{uuid}/transition` | Super Admin + Origin + CSRF; `{status,expected_status}` performs a permitted lifecycle transition |
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

## Branch administration — October 29

Branch names are trimmed and must contain 1–200 characters. Unknown fields
are rejected (422); callers cannot supply or modify branch codes. Creation
always begins in `forming`. There is no branch deletion endpoint.

| Current status | Permitted next statuses |
| --- | --- |
| `forming` | `active`, `closed` |
| `active` | `paused`, `closed` |
| `paused` | `active`, `closed` |
| `closed` | None |

Transitions require the status the caller last read as `expected_status`.
A stale value, invalid transition, or same-state transition returns 409.
Refresh the branch before retrying; do not blindly resubmit a conflicting
request. The server locks the row while validating and changing status.
Each successful change and its before/after audit entry share a transaction.
Closing retains the branch record and code permanently. Rename does not
reopen a closed branch. Duplicate display names are permitted; codes identify
branches uniquely.

A rename to the existing name is also a no-op conflict (409). Rename uses
serialized last-writer-wins semantics; only lifecycle updates require an
expected current status. See ADR 0003 for concurrency trade-offs.
