import { env } from '$env/dynamic/private';
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
export const GET: RequestHandler = async ({ cookies, url }) => {
  const token = cookies.get('campus_session');
  if (!token) error(401, 'Silakan login.');
  const cid = encodeURIComponent(url.searchParams.get('class') || '');
  const r = await fetch(`${env.API_URL || 'http://127.0.0.1:8000'}/classes/${cid}/report.csv`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(10000) });
  if (!r.ok) error(r.status, 'Laporan tidak dapat diakses.');
  return new Response(await r.text(), { headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="campus-outcomes.csv"', 'Cache-Control': 'no-store' } });
};
