# Proposed permission matrix

This is the implementation contract for phase 2, not a claim that roles exist
in the phase 1 application. All permissions default to denied. Public access
is limited to published content, active public branch information, and
submitting volunteer applications. Public health responses contain no secrets.

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

Proposed branch transitions: Forming → Active or Closed; Active → Paused or
Closed; Paused → Active or Closed; Closed is terminal. Codes are never reused.
