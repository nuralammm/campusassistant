import { env } from '$env/dynamic/private';
export async function api(path: string, token: string | undefined, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${env.API_URL || 'http://127.0.0.1:8000'}${path}`, { ...init, headers, signal: AbortSignal.timeout(path.endsWith('/interventions/ai') ? 65000 : 10000) });
  const payload = await response.json();
  return { ok: response.ok, status: response.status, payload };
}
