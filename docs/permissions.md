# Permission matrix and implementation status

Phase 2 implements login for all five roles, user list/create permissions,
scoped branch reads, and scoped audit reads. The remaining rows are the
contract for future domain endpoints. The October 29 phase additionally
implements Super Admin branch creation, rename, and lifecycle changes.
All permissions default to denied. Published content and volunteer applications
are planned public capabilities; those endpoints do not exist yet. Public
health responses contain no secrets.

| Action | Super Admin | Finance Reviewer | Content Editor | Branch Lead | HR Lead |
| --- | --- | --- | --- | --- | --- |
| Manage users and role assignments | All | No | No | No | No |
| Create branches / change lifecycle | All | No | No | No | No |
| Read internal branch register | All | All | No | Own | All |
| Review / accept / decline applications | All | No | No | No | All |
| Read members | All | No | No | Own | All |
| Manage members, teams and statuses | All | No | No | Own | All |
| Read collections | All | All | No | Own | No |
| Log / edit collections before lock | All | No | No | Own | No |
| Mark collections transferred | All | All | No | No | No |
| Read weekly reports | All | All | No | Own | No |
| Submit / resubmit weekly reports | No | No | No | Own | No |
| Return / approve weekly reports | All | All | No | No | No |
| Read head office dashboard | All | All | No | No | No |
| Export permitted financial reports | All | All | No | Own | No |
| Manage / publish bilingual content | All | No | All | No | No |
| Read audit records | All | Finance scope | No | Own branch | HR scope |
| Modify or delete audit records | No | No | No | No | No |

Own = authenticated user's assigned branch, enforced on server queries and
mutations. Role checks alone are insufficient. Time locks and approved-report
locks apply even to Super Admin. Finance scope covers collections/reports;
HR scope covers applications/members. Separate tests must cover every grant,
denial, cross-branch identifier substitution, export, and state transition.

Enforced branch transitions: Forming → Active or Closed; Active → Paused or
Closed; Paused → Active or Closed; Closed is terminal. Codes are never reused.

Phase 2 has no audit mutation endpoints. PostgreSQL also rejects direct audit
UPDATE, DELETE, and TRUNCATE. Role/session, branch scope, and mutation CSRF
checks are exercised against a real PostgreSQL database. User update, role
reassignment, and remaining domain operations are pending. Branch mutations
require both Super Admin permission and valid CSRF/Origin, and are audited
atomically. Other roles cannot mutate even their own assigned branch.
