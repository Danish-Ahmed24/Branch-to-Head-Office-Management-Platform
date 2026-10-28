import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError, validSession, type AuditEntry, type Branch, type Role, type Session, type User } from './api';
import type { en } from './i18n/en';
import { BranchAdmin } from './BranchAdmin';

type Copy = typeof en.auth;
type List<T> = { items: T[]; limit: number; offset: number };
const roles: Role[] = ['super_admin', 'finance_reviewer', 'content_editor', 'branch_lead', 'hr_lead'];

function errorText(error: unknown, t: Copy, login = false) {
  if (error instanceof ApiError) {
    if (error.status === 401) return login ? t.invalidLogin : t.sessionExpired;
    if (error.status === 403) return t.forbidden;
    if (error.status === 429) return t.rateLimited;
    if (error.status === 409) return t.userConflict;
  }
  return t.requestFailed;
}

export function Workspace({ t, language }: { t: Copy; language: 'en' | 'ur' }) {
  const [session, setSession] = useState<Session | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: boolean; password?: boolean }>({});
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [restoreFailed, setRestoreFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setRestoring(true);
    setRestoreFailed(false);
    api<Session>('/auth/me', { signal: controller.signal })
      .then((value) => {
        if (!active) return;
        if (validSession(value)) setSession(value);
        else setRestoreFailed(true);
      })
      .catch((error: unknown) => {
        if (active && !(error instanceof ApiError && error.status === 401)) setRestoreFailed(true);
      }).finally(() => { if (active) setRestoring(false); });
    return () => { active = false; controller.abort(); };
  }, [restoreAttempt]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = { email: !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()), password: !password };
    setErrors(invalid);
    setMessage('');
    if (invalid.email || invalid.password) return;
    setBusy(true);
    try {
      const value = await api<Session>('/auth/login', { method: 'POST', body: JSON.stringify({ email: email.trim(), password }) });
      if (!validSession(value)) throw new Error('Invalid response');
      setSession(value);
      setPassword('');
    } catch (error) { setMessage(errorText(error, t, true)); }
    finally { setBusy(false); }
  }

  async function logout() {
    if (!session) return;
    setBusy(true);
    setMessage('');
    try {
      await api<void>('/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': session.csrf_token } });
      setSession(null);
      setPassword('');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setSession(null);
      else setMessage(errorText(error, t));
    } finally { setBusy(false); }
  }

  return <section className="workspace" aria-labelledby="workspace-title">
    <div className="section-heading"><h2 id="workspace-title">{t.title}</h2><p>{session ? t.roleNote : t.subtitle}</p></div>
    {restoring ? <p role="status">{t.restoring}</p> : session ? <>
      <div className="account-card">
        <div><span className="field-caption">{t.signedIn}</span><h3>{session.user.display_name}</h3><p>{session.user.email}</p></div>
        <dl><div><dt>{t.role}</dt><dd>{t.roles[session.user.role]}</dd></div><div><dt>{t.branch}</dt><dd>{session.user.branch_id ? t.branchAccess : t.headOffice}</dd></div></dl>
        <button className="secondary-button" disabled={busy} onClick={logout}>{t.logout}</button>
      </div>
      {message && <p className="form-error" role="alert">{message}</p>}
      <Records session={session} t={t} language={language} onExpired={() => { setSession(null); setMessage(t.sessionExpired); }} />
    </> : <>
      {restoreFailed && <div className="restore-error" role="alert"><p>{t.sessionFailed}</p><button className="secondary-button" onClick={() => setRestoreAttempt(restoreAttempt + 1)}>{t.refresh}</button></div>}
      <form className="login-form" onSubmit={login} noValidate>
        <div className="form-field"><label htmlFor="login-email">{t.email}</label><input id="login-email" name="email" type="email" autoComplete="username" dir="ltr" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} aria-invalid={!!errors.email} aria-describedby={errors.email ? 'email-error' : undefined} />{errors.email && <p id="email-error" className="field-error">{t.emailRequired}</p>}</div>
        <div className="form-field"><label htmlFor="login-password">{t.password}</label><input id="login-password" name="password" type="password" autoComplete="current-password" dir="ltr" maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} aria-invalid={!!errors.password} aria-describedby={errors.password ? 'password-error' : undefined} />{errors.password && <p id="password-error" className="field-error">{t.passwordRequired}</p>}</div>
        {message && <p className="form-error" role="alert">{message}</p>}
        <button className="primary-button" disabled={busy} type="submit">{busy ? t.signingIn : t.signIn}</button>
        <p className="form-help">{t.permissions}</p>
      </form>
    </>}
  </section>;
}

function Records({ session, t, language, onExpired }: { session: Session; t: Copy; language: 'en' | 'ur'; onExpired: () => void }) {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [created, setCreated] = useState(false);
  const [branchNotice, setBranchNotice] = useState<{ message: string; error: boolean } | null>(null);
  const canReadBranches = session.user.role !== 'content_editor';

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setMessage('');
    const tasks: Promise<void>[] = [];
    if (canReadBranches) tasks.push(api<List<Branch>>('/branches?limit=100', { signal: controller.signal }).then((data) => { if (active) setBranches(data.items); }));
    if (canReadBranches) tasks.push(api<List<AuditEntry>>('/audit?limit=50', { signal: controller.signal }).then((data) => { if (active) setAudit(data.items); }));
    if (session.user.role === 'super_admin') tasks.push(api<List<User>>('/users?limit=100', { signal: controller.signal }).then((data) => { if (active) setUsers(data.items); }));
    Promise.all(tasks).catch((error: unknown) => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 401) onExpired();
      else setMessage(errorText(error, t));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [session.user.id, session.user.role, attempt, canReadBranches]);

  return <div className="records">
    <button className="secondary-button refresh-button" disabled={loading} onClick={() => setAttempt(attempt + 1)}>{t.refresh}</button>
    {loading && <p role="status">{t.recordsLoading}</p>}
    {message && <p className="form-error" role="alert">{message}</p>}
    {branchNotice && <p role={branchNotice.error ? 'alert' : 'status'} className={branchNotice.error ? 'form-error' : 'form-help'}>{branchNotice.message}</p>}
    {!loading && !message && <>
      {created && <p role="status">{t.created}</p>}
      {canReadBranches && <p className="form-help">{t.limitedRecords}</p>}
      {session.user.role === 'super_admin' ? <BranchAdmin branches={branches} session={session} t={t} onExpired={onExpired} onChanged={(notice, error = false) => { setBranchNotice({ message: notice, error }); setAttempt(attempt + 1); }} /> : canReadBranches && <section aria-labelledby="branches-heading"><h3 id="branches-heading">{t.branchRecords}</h3>{branches.length ? <ul className="branch-list">{branches.map((branch) => <li key={branch.id}><div><strong>{branch.name}</strong><span className="record-code" dir="ltr">{branch.code}</span></div><span className="step-status">{t.branchStatuses[branch.status as keyof Copy['branchStatuses']] ?? branch.status}</span></li>)}</ul> : <p>{t.noBranches}</p>}</section>}
      {session.user.role === 'super_admin' && <>
        <section aria-labelledby="users-heading"><h3 id="users-heading">{t.users}</h3>{users.length ? <ul className="branch-list">{users.map((user) => <li key={user.id}><div><strong>{user.display_name}</strong><span className="record-code">{user.email}</span></div><span>{t.roles[user.role]}</span></li>)}</ul> : <p>{t.noUsers}</p>}</section>
        <CreateUser session={session} branches={branches} t={t} onCreated={() => { setCreated(true); setAttempt(attempt + 1); }} onExpired={onExpired} />
      </>}
      {canReadBranches && <section aria-labelledby="audit-heading"><h3 id="audit-heading">{t.audit}</h3>{audit.length ? <div className="table-scroll"><table><thead><tr><th>{t.action}</th><th>{t.record}</th><th>{t.actor}</th><th>{t.time}</th></tr></thead><tbody>{audit.map((entry) => <tr key={entry.id}><td>{t.auditActions[entry.action as keyof Copy['auditActions']] ?? entry.action}</td><td>{t.entityTypes[entry.entity_type as keyof Copy['entityTypes']] ?? entry.entity_type} #{entry.entity_id}</td><td>{entry.actor_id ?? t.system}</td><td><time dateTime={entry.created_at}>{new Intl.DateTimeFormat(language === 'ur' ? 'ur-PK' : 'en-PK', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Karachi' }).format(new Date(entry.created_at))}</time></td></tr>)}</tbody></table></div> : <p>{t.noAudit}</p>}</section>}
    </>}
  </div>;
}

function CreateUser({ session, branches, t, onCreated, onExpired }: { session: Session; branches: Branch[]; t: Copy; onCreated: () => void; onExpired: () => void }) {
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState<Role>('content_editor');
  const [message, setMessage] = useState('');
  const [success, setSuccess] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const email = String(fields.get('email') ?? '').trim();
    const display_name = String(fields.get('display_name') ?? '').trim();
    const password = String(fields.get('password') ?? '');
    const branch = String(fields.get('branch_id') ?? '');
    const invalid: Record<string, string> = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) invalid.email = t.emailRequired;
    if (!display_name) invalid.display_name = t.nameRequired;
    if (password.length < 12) invalid.password = t.passwordTooShort;
    if (role === 'branch_lead' && !branch) invalid.branch_id = t.branchRequired;
    setErrors(invalid); setMessage(''); setSuccess(false);
    if (Object.keys(invalid).length) return;
    setBusy(true);
    try {
      await api<User>('/users', { method: 'POST', headers: { 'X-CSRF-Token': session.csrf_token }, body: JSON.stringify({ email, display_name, password, role, branch_id: role === 'branch_lead' ? branch : null }) });
      form.reset(); setRole('content_editor'); setSuccess(true); onCreated();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onExpired();
      else setMessage(errorText(error, t));
    } finally { setBusy(false); }
  }
  return <section className="create-user" aria-labelledby="create-user-heading"><h3 id="create-user-heading">{t.createUser}</h3>
    <form className="user-form" onSubmit={submit} noValidate>
      {(['display_name', 'email', 'password'] as const).map((name) => <div className="form-field" key={name}><label htmlFor={`create-${name}`}>{name === 'display_name' ? t.displayName : name === 'email' ? t.email : t.newPassword}</label><input id={`create-${name}`} name={name} type={name === 'password' ? 'password' : name === 'email' ? 'email' : 'text'} autoComplete={name === 'password' ? 'new-password' : 'off'} maxLength={name === 'password' ? 128 : name === 'email' ? 254 : 100} required aria-invalid={!!errors[name]} aria-describedby={errors[name] ? `create-${name}-error` : name === 'password' ? 'create-password-help' : undefined} />{errors[name] && <p id={`create-${name}-error`} className="field-error">{errors[name]}</p>}{name === 'password' && <p id="create-password-help" className="form-help">{t.passwordHelp}</p>}</div>)}
      <div className="form-field"><label htmlFor="create-role">{t.role}</label><select id="create-role" value={role} onChange={(event) => setRole(event.target.value as Role)}>{roles.map((value) => <option key={value} value={value}>{t.roles[value]}</option>)}</select></div>
      {role === 'branch_lead' && <div className="form-field"><label htmlFor="create-branch">{t.userBranch}</label><select id="create-branch" name="branch_id" required aria-invalid={!!errors.branch_id} aria-describedby={errors.branch_id ? 'create-branch-error' : undefined}><option value="">{t.chooseBranch}</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name} ({branch.code})</option>)}</select>{errors.branch_id && <p id="create-branch-error" className="field-error">{errors.branch_id}</p>}</div>}
      {message && <p role="alert" className="form-error">{message}</p>}{success && <p role="status">{t.created}</p>}
      <button className="primary-button" disabled={busy} type="submit">{busy ? t.creating : t.createUser}</button>
    </form>
  </section>;
}
