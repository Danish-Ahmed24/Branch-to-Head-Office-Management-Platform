import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { App } from './App';

afterEach(() => vi.unstubAllGlobals());

function mockHealth(status: number, body: unknown) {
  const mock = vi.fn().mockResolvedValue({ ok: status === 200, json: async () => body });
  vi.stubGlobal('fetch', mock);
  return mock;
}

test('switches all page content and document direction to Urdu', async () => {
  mockHealth(200, { status: 'ok' });
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Switch to Urdu' }));
  expect(document.documentElement).toHaveAttribute('dir', 'rtl');
  expect(document.documentElement).toHaveAttribute('lang', 'ur');
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('اچھے کام کے لیے ایک بہتر نظام۔');
  expect(localStorage.getItem('shiplens-language')).toBe('ur');
  await screen.findByText('اے پی آئی اور ڈیٹابیس منسلک ہیں');
});

test('reports readiness only for successful backend health responses', async () => {
  const fetch = mockHealth(200, { status: 'ok' });
  render(<App />);
  await screen.findByText('API and database connected');
  expect(fetch).toHaveBeenCalledWith('/api/health', expect.objectContaining({ signal: expect.any(AbortSignal) }));
});

test('shows failure and retries when database becomes available', async () => {
  const fetch = mockHealth(503, { status: 'unavailable' });
  render(<App />);
  await screen.findByText('Service not ready');
  fetch.mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) });
  fireEvent.click(screen.getByRole('button', { name: 'Check again' }));
  await screen.findByText('API and database connected');
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
});

test('does not present malformed health payloads as ready', async () => {
  mockHealth(200, {});
  render(<App />);
  await screen.findByText('Service not ready');
});
