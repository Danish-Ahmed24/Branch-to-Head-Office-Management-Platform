import { useState, type FormEvent } from 'react';
import { api, ApiError, type Branch, type Session } from './api';
import type { en } from './i18n/en';
import './BranchAdmin.css';

type Copy = typeof en.auth;
const transitions: Record<string, string[]> = { forming: ['active', 'closed'], active: ['paused', 'closed'], paused: ['active', 'closed'], closed: [] };

export function BranchAdmin({ branches, session, t, onChanged, onExpired }: {
  branches: Branch[]; session: Session; t: Copy; onChanged: (message: string, error?: boolean) => void; onExpired: () => void;
}) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || name.trim().length > 200) { setError(t.branchAdmin.nameInvalid); return; }
    setError(''); setBusy(true);
    try {
      await api<Branch>('/branches', { method: 'POST', headers: { 'X-CSRF-Token': session.csrf_token }, body: JSON.stringify({ name: name.trim() }) });
      setName(''); onChanged(t.branchAdmin.created);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setError(cause instanceof ApiError && cause.status === 403 ? t.forbidden : t.requestFailed);
    } finally { setBusy(false); }
  }
  return <section aria-labelledby="branches-heading">
    <h3 id="branches-heading">{t.branchRecords}</h3>
    <form className="branch-create-form" onSubmit={create} noValidate>
      <div className="form-field"><label htmlFor="new-branch-name">{t.branchAdmin.newName}</label><input id="new-branch-name" maxLength={200} required value={name} onChange={(event) => setName(event.target.value)} aria-invalid={!!error} aria-describedby={error ? 'branch-create-error' : 'branch-code-help'} /><p id="branch-code-help" className="form-help">{t.branchAdmin.codeHelp}</p></div>
      {error && <p id="branch-create-error" role="alert" className="form-error">{error}</p>}
      <button className="primary-button" disabled={busy} type="submit">{busy ? t.creating : t.branchAdmin.create}</button>
    </form>
    {branches.length ? <ul className="branch-admin-list">{branches.map((branch) => <BranchRow key={`${branch.id}-${branch.name}-${branch.status}`} branch={branch} session={session} t={t} onChanged={onChanged} onExpired={onExpired} />)}</ul> : <p>{t.noBranches}</p>}
  </section>;
}

function BranchRow({ branch, session, t, onChanged, onExpired }: { branch: Branch; session: Session; t: Copy; onChanged: (message: string, error?: boolean) => void; onExpired: () => void }) {
  const [name, setName] = useState(branch.name);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const choices = transitions[branch.status] ?? [];
  const label = (value: string) => t.branchStatuses[value as keyof Copy['branchStatuses']] ?? value;
  async function mutate(kind: 'rename' | 'transition') {
    if (kind === 'rename' && (!name.trim() || name.trim().length > 200)) { setError(t.branchAdmin.nameInvalid); return; }
    if (kind === 'transition' && !choices.includes(status)) { setError(t.branchAdmin.statusRequired); return; }
    setBusy(true); setError('');
    try {
      await api<Branch>(`/branches/${branch.id}${kind === 'transition' ? '/transition' : ''}`, {
        method: kind === 'rename' ? 'PATCH' : 'POST', headers: { 'X-CSRF-Token': session.csrf_token },
        body: JSON.stringify(kind === 'rename' ? { name: name.trim() } : { status, expected_status: branch.status }),
      });
      onChanged(kind === 'rename' ? t.branchAdmin.renamed : t.branchAdmin.transitioned);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else if (cause instanceof ApiError && (cause.status === 409 || cause.status === 404)) onChanged(t.branchAdmin.conflict, true);
      else setError(cause instanceof ApiError && cause.status === 403 ? t.forbidden : t.requestFailed);
    } finally { setBusy(false); setConfirming(false); }
  }
  return <li className="branch-admin-card" aria-label={branch.name}>
    <div className="branch-admin-heading"><strong>{branch.name}</strong><span className="record-code" dir="ltr">{branch.code}</span><span className="step-status">{label(branch.status)}</span></div>
    <form className="branch-inline-form" onSubmit={(event) => { event.preventDefault(); void mutate('rename'); }} noValidate>
      <div className="form-field"><label htmlFor={`branch-name-${branch.id}`}>{t.branchAdmin.renameLabel}</label><input id={`branch-name-${branch.id}`} value={name} maxLength={200} required onChange={(event) => setName(event.target.value)} /></div>
      <button className="secondary-button" disabled={busy || name.trim() === branch.name} type="submit">{t.branchAdmin.rename}</button>
    </form>
    {choices.length > 0 ? <form className="branch-inline-form" onSubmit={(event) => { event.preventDefault(); if (status === 'closed') setConfirming(true); else void mutate('transition'); }}>
      <div className="form-field"><label htmlFor={`branch-status-${branch.id}`}>{t.branchAdmin.nextStatus}</label><select id={`branch-status-${branch.id}`} value={status} onChange={(event) => { setStatus(event.target.value); setConfirming(false); }} required><option value="">{t.branchAdmin.selectStatus}</option>{choices.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></div>
      <button className="secondary-button" disabled={busy || !status} type="submit">{t.branchAdmin.changeStatus}</button>
    </form> : <p className="form-help">{t.branchAdmin.terminal}</p>}
    {confirming && <div className="branch-close-confirm" role="alertdialog" aria-modal="false" aria-labelledby={`close-title-${branch.id}`} aria-describedby={`close-description-${branch.id}`}><strong id={`close-title-${branch.id}`}>{t.branchAdmin.closeTitle}</strong><p id={`close-description-${branch.id}`}>{t.branchAdmin.closeWarning}</p><button className="primary-button" type="button" disabled={busy} onClick={() => void mutate('transition')}>{t.branchAdmin.confirmClose}</button><button className="secondary-button" type="button" disabled={busy} onClick={() => setConfirming(false)}>{t.branchAdmin.cancel}</button></div>}
    {error && <p role="alert" className="form-error">{error}</p>}
  </li>;
}
