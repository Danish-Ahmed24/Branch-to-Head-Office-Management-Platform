# ADR 0003: Branch identity and lifecycle

Status: accepted; October 29, 2026.

Branches start Forming, with an immutable code allocated by the existing
PostgreSQL sequence. Codes remain unique under concurrency and are not
reused after rollback or closure. Display names are editable; duplicate names
are allowed because codes, rather than names, identify branches.

Only Super Admin can create, rename, or transition a branch. Forming can
become Active or Closed; Active can become Paused or Closed; Paused can
become Active or Closed. Closed is terminal. The application has no delete
operation. Renaming a closed branch does not change its lifecycle.

Transitions require an expected current status and acquire a row lock before
checking it. Conflicts return 409 so a stale browser cannot silently apply a
transition against a different current state. The expected value detects
status differences, not a full edit history: a branch that moves away and
returns to the same status can still match. Name edits follow serialized
last-writer-wins behavior. A future version field could detect all intervening
edits if the organisation requires that stronger contract.

Branch mutation and audit insertion occur in the same transaction. No schema
migration is needed for this phase because phase 2 already established branch
identity, status constraints, and the code sequence. Member/application and
financial behavior for paused/closed branches will be defined with those
domains; this phase does not invent them in advance.
