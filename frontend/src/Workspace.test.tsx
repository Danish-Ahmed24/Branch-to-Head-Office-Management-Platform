import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { Workspace } from './Workspace';
import { App } from './App';
import { en } from './i18n/en';
import type { Session, Role } from './api';

const session = (role: Role = 'branch_lead'): Session => ({
  user: { id: '9dd8d108-6967-4ad7-a2c9-86930948410a', email: 'lead@example.test', display_name: 'Demo Lead', role, branch_id: role === 'branch_lead' ? '0b4e0475-dff6-4c84-b5fa-b73d4fcbdc24' : null },
  csrf_token: 'csrf-test-token',
});
function response(status: number, body?: unknown) {
  return { status, ok: status >= 200 && status < 300, json: async () => body };
}
function mockApi(handler: (url: string, options?: RequestInit) => ReturnType<typeof response>) {
  const mock = vi.fn().mockImplementation(async (url: string, options?: RequestInit) => handler(url, options));
  vi.stubGlobal('fetch', mock);
  return mock;
}
afterEach(() => vi.unstubAllGlobals());

async function fillLogin() {
  const email = await screen.findByLabelText('Email address');
  fireEvent.change(email, { target: { value: 'lead@example.test' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-secret-do-not-store' } });
}

test('expired or absent session displays login without an error', async () => {
  mockApi(() => response(401));
  render(<Workspace t={en.auth} language="en" />);
  await screen.findByRole('button', { name: 'Sign in' });
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('validates required fields before sending a login request', async () => {
  const fetch = mockApi(() => response(401));
  render(<Workspace t={en.auth} language="en" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }));
  expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
  expect(screen.getByText('Enter your password.')).toBeInTheDocument();
  expect(fetch.mock.calls.some(([url]) => url === '/api/auth/login')).toBe(false);
});

test('failed login shows a safe message, never raw backend errors', async () => {
  const fetch = mockApi((url) => response(401, { detail: 'internal database secret' }));
  render(<Workspace t={en.auth} language="en" />);
  await fillLogin();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.');
  expect(screen.queryByText('internal database secret')).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({ method: 'POST', credentials: 'same-origin', body: JSON.stringify({ email: 'lead@example.test', password: 'test-secret-do-not-store' }) }));
});

test('successful branch lead login shows scoped records and logs out with CSRF', async () => {
  const current = session();
  const fetch = mockApi((url) => {
    if (url === '/api/auth/me') return response(401);
    if (url === '/api/auth/login') return response(200, current);
    if (url === '/api/auth/logout') return response(204);
    if (url.startsWith('/api/branches')) return response(200, { items: [{ id: current.user.branch_id, name: 'Demo Lahore', code: 'BR-0001', status: 'active' }] });
    return response(200, { items: [] });
  });
  render(<Workspace t={en.auth} language="en" />);
  await fillLogin();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByText('Demo Lahore');
  expect(screen.getByText('Branch Lead')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Create user' })).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([url]) => url.startsWith('/api/users'))).toBe(false);
  expect(localStorage.getItem('csrf_token')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  await screen.findByRole('button', { name: 'Sign in' });
  expect(fetch).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({ method: 'POST', credentials: 'same-origin', headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-test-token' }) }));
});

test('content editor session does not request branch, users, or audit data', async () => {
  const fetch = mockApi(() => response(200, session('content_editor')));
  render(<Workspace t={en.auth} language="en" />);
  await screen.findByText('Content Editor');
  expect(screen.queryByRole('heading', { name: 'Audit trail' })).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
});

test('super admin creates user with a UUID branch assignment and CSRF header', async () => {
  const fetch = mockApi((url, options) => {
    if (url === '/api/auth/me') return response(200, session('super_admin'));
    if (url.startsWith('/api/branches')) return response(200, { items: [{ id: 'test-branch-uuid', code: 'BR-0001', name: 'Demo Lahore', status: 'active' }] });
    if (url === '/api/users' && options?.method === 'POST') return response(201, { id: 'new-user-uuid' });
    return response(200, { items: [] });
  });
  render(<Workspace t={en.auth} language="en" />);
  const heading = await screen.findByRole('heading', { name: 'Create user' });
  const form = within(heading.closest('section')!);
  fireEvent.change(form.getByLabelText('Display name'), { target: { value: 'Demo New Lead' } });
  fireEvent.change(form.getByLabelText('Email address'), { target: { value: 'new@example.test' } });
  fireEvent.change(form.getByLabelText('Initial password'), { target: { value: 'new-password-private' } });
  fireEvent.change(form.getByLabelText('Role'), { target: { value: 'branch_lead' } });
  fireEvent.change(form.getByLabelText('Assigned branch'), { target: { value: 'test-branch-uuid' } });
  fireEvent.click(form.getByRole('button', { name: 'Create user' }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/users', expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-test-token' }), body: JSON.stringify({ email: 'new@example.test', display_name: 'Demo New Lead', password: 'new-password-private', role: 'branch_lead', branch_id: 'test-branch-uuid' }) })));
});

test('login form translates to Urdu and switches document direction', async () => {
  mockApi((url) => url === '/api/health' ? response(200, { status: 'ok' }) : response(401));
  render(<App />);
  await screen.findByRole('button', { name: 'Sign in' });
  fireEvent.click(screen.getByRole('button', { name: 'Switch to Urdu' }));
  expect(document.documentElement).toHaveAttribute('dir', 'rtl');
  expect(screen.getByLabelText('ای میل پتہ')).toBeInTheDocument();
  expect(screen.getByLabelText('پاس ورڈ')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'لاگ ان کریں' })).toBeInTheDocument();
});
