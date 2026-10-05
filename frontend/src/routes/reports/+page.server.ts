import { fail, redirect, isRedirect } from '@sveltejs/kit';
import { api } from '$lib/api.server';
import type { Actions, PageServerLoad } from './$types';
export const load: PageServerLoad = async ({ cookies, url }) => {
  const token = cookies.get('campus_session');
  if (!token) redirect(303, '/');
  try {
    const classes = await api('/classes', token);
    if (classes.status === 401) redirect(303, '/');
    const cid = url.searchParams.get('class') || classes.payload[0]?.id;
    if (!cid) return { classes: [], dashboard: null, error: 'Belum ada kelas.' };
    const r = await api(`/classes/${encodeURIComponent(cid)}/dashboard`, token);
    return { classes: classes.ok ? classes.payload : [], dashboard: r.ok ? r.payload : null, error: r.ok ? '' : 'Kelas tidak dapat diakses.' };
  } catch (e) { if (isRedirect(e)) throw e; return { classes: [], dashboard: null, error: 'Backend belum tersedia.' }; }
};
export const actions: Actions = {
  scenario: async ({ request, cookies }) => {
    const f = await request.formData();
    const fields = ['baseline_hours_month','new_work_hours_month','review_hours_month','correction_hours_month','value_per_hour','monthly_operating_cost','initial_cost','horizon_months'];
    try {
      const r = await api(`/classes/${encodeURIComponent(String(f.get('class_id')))}/roi/scenario`, cookies.get('campus_session'), { method: 'POST', body: JSON.stringify(Object.fromEntries(fields.map(k => [k, Number(f.get(k))]))) });
      if (!r.ok) return fail(r.status, { error: 'Input skenario tidak valid.' });
      return { scenario: r.payload };
    } catch { return fail(503, { error: 'Backend tidak tersedia.' }); }
  }
};
