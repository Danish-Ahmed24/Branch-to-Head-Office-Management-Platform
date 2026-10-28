export type Role = 'super_admin' | 'finance_reviewer' | 'content_editor' | 'branch_lead' | 'hr_lead';
export type User = { id: string; email: string; display_name: string; role: Role; branch_id: string | null };
export type Session = { user: User; csrf_token: string };
export type Branch = { id: string; code: string; name: string; status: string };
export type AuditEntry = { id: number; action: string; entity_type: string; entity_id: string; actor_id: string | null; created_at: string };
export class ApiError extends Error {
  constructor(public status: number) { super('Request could not be completed'); }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new ApiError(response.status);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function validSession(value: unknown): value is Session {
  if (!value || typeof value !== 'object') return false;
  const session = value as Session;
  return typeof session.csrf_token === 'string' && !!session.user && typeof session.user.display_name === 'string' &&
    ['super_admin', 'finance_reviewer', 'content_editor', 'branch_lead', 'hr_lead'].includes(session.user.role);
}
