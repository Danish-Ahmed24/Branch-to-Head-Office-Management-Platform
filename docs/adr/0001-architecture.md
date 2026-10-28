# ADR 0001: FastAPI, React, and PostgreSQL

Status: accepted for the foundation; 2026-10-28.

## Context

The ShipLens challenge requires a bilingual public website and five-role
management platform with transactional financial and membership workflows.
The participant selected FastAPI and React. PostgreSQL, Docker, GitHub Actions,
and Render are mandated by the handbook.

## Decision

Use a modular monolith: FastAPI with service-layer business rules, SQLAlchemy
and PostgreSQL, and a React/TypeScript frontend. Deploy the built frontend and
API under one origin where practical. Use Alembic for schema migrations when
persistent domain models are introduced. Keep authorization and audit writes
in the same application service path as each mutation.

Production authentication will use secure, HttpOnly cookie sessions, CSRF
protection for mutations, and server-side role and branch checks. This is a
planned decision, not an implemented capability in phase 1.

Store timestamps in UTC and display Asia/Karachi. Proposed reporting weeks are
Monday 00:00 through the following Monday 00:00 in Asia/Karachi, using half-open
intervals. Store money as integer paisa, never floating point. Approval must
freeze report figures. Use database-generated non-reused identifiers,
constraints, and transactions for concurrent changes.

## Consequences

A single deployment reduces CORS and operational complexity. FastAPI provides
OpenAPI documentation; React needs explicit translation and accessibility
checks. PostgreSQL is required in integration tests rather than substituting
SQLite. Domain migrations, sessions, and business workflows remain future work.
