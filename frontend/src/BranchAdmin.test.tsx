import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { BranchAdmin } from './BranchAdmin';
import { Workspace } from './Workspace';
import { en } from './i18n/en';
import { ur } from './i18n/ur';
import type { Branch, Session } from './api';

const branch: Branch = { id: 'branch-uuid', name: 'Synthetic North', code: 'BR-0001', status: 'forming' };
const session: Session = { user: { id: 'admin-uuid', email: 'admin@example.test', display_name: 'Synthetic Admin', role: 'super_admin', branch_id: null }, csrf_token: 'test-csrf' };
afterEach(() => vi.unstubAllGlobals());
function setup(status = 200, copy = en.auth, branches = [branch]) {
  const fetch = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => branch });
  vi.stubGlobal('fetch', fetch);
  const onChanged = vi.fn();
  render(<BranchAdmin branches={branches} session={session} t={copy} onChanged={onChanged} onExpired={vi.fn()} />);
  return { fetch, onChanged };
}

test('validates branch name and creates a forming branch without supplying a code', async () => {
  const { fetch, onChanged } = setup(201);
  fireEvent.click(screen.getByRole('button', { name: 'Create branch' }));
  expect(screen.getByRole('alert')).toHaveTextContent(en.auth.branchAdmin.nameInvalid);
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('New branch name'), { target: { value: '  Synthetic South  ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create branch' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledWith(en.auth.branchAdmin.created));
  expect(fetch).toHaveBeenCalledWith('/api/branches', expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: 'Synthetic South' }), headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf' }) }));
});

test('renames a branch with CSRF and keeps generated code read-only', async () => {
  const { fetch, onChanged } = setup();
  expect(screen.queryByLabelText('Branch code')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Branch name'), { target: { value: 'Synthetic Central' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save name' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledWith(en.auth.branchAdmin.renamed));
  expect(fetch).toHaveBeenCalledWith('/api/branches/branch-uuid', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ name: 'Synthetic Central' }), headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf' }) }));
});

test('transitions include the displayed expected status and only allowed targets', async () => {
  const { fetch, onChanged } = setup();
  const status = screen.getByLabelText('Next status');
  expect(within(status).queryByRole('option', { name: 'Paused' })).not.toBeInTheDocument();
  fireEvent.change(status, { target: { value: 'active' } });
  fireEvent.click(screen.getByRole('button', { name: 'Change status' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledWith(en.auth.branchAdmin.transitioned));
  expect(fetch).toHaveBeenCalledWith('/api/branches/branch-uuid/transition', expect.objectContaining({ method: 'POST', body: JSON.stringify({ status: 'active', expected_status: 'forming' }), headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf' }) }));
});

test('closure requires explicit confirmation and closed branches have no transition controls', async () => {
  const { fetch } = setup();
  fireEvent.change(screen.getByLabelText('Next status'), { target: { value: 'closed' } });
  fireEvent.click(screen.getByRole('button', { name: 'Change status' }));
  expect(screen.getByRole('alertdialog')).toHaveTextContent(en.auth.branchAdmin.closeWarning);
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Change status' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm closure' }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
});

test('stale transition requests trigger translated notice and parent refresh without exposing server details', async () => {
  const { onChanged } = setup(409);
  fireEvent.change(screen.getByLabelText('Next status'), { target: { value: 'active' } });
  fireEvent.click(screen.getByRole('button', { name: 'Change status' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledWith(en.auth.branchAdmin.conflict, true));
});

test('closed branch displays terminal state and Urdu administration labels', () => {
  setup(200, ur.auth, [{ ...branch, status: 'closed' }]);
  expect(screen.getByText(ur.auth.branchAdmin.terminal)).toBeInTheDocument();
  expect(screen.getByLabelText(ur.auth.branchAdmin.newName)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: ur.auth.branchAdmin.changeStatus })).not.toBeInTheDocument();
});

test('branch lead sees own records without administrative controls', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => ({ ok: true, status: 200, json: async () => url === '/api/auth/me' ? { ...session, user: { ...session.user, role: 'branch_lead', branch_id: branch.id } } : { items: url.startsWith('/api/branches') ? [branch] : [] } })));
  render(<Workspace t={en.auth} language="en" />);
  await screen.findByText(branch.name);
  expect(screen.queryByRole('button', { name: 'Create branch' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save name' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Change status' })).not.toBeInTheDocument();
});
