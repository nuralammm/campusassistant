import { fail, redirect } from '@sveltejs/kit';
import { api } from '$lib/api.server';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ cookies }) => {
  const token = cookies.get('campus_session');
  if (!token) return { dashboard: null, measurement: null, error: '' };
  try {
    const classes = await api('/classes', token);
    if (classes.status === 401) {
      cookies.delete('campus_session', { path: '/' });
      return { dashboard: null, measurement: null, error: 'Sesi berakhir. Silakan masuk kembali.' };
    }
    if (!classes.ok) return { dashboard: null, measurement: null, error: 'Akses kelas ditolak.' };
    const cid = classes.payload[0]?.id;
    if (!cid) return { dashboard: null, measurement: null, error: 'Belum ada kelas yang dapat diakses.' };
    const [dashboard, measurement] = await Promise.all([
      api(`/classes/${encodeURIComponent(cid)}/dashboard`, token),
      api(`/classes/${encodeURIComponent(cid)}/measurements`, token)
    ]);
    return { dashboard: dashboard.ok ? dashboard.payload : null,
      measurement: measurement.ok ? measurement.payload : null, error: dashboard.ok ? '' : 'Dashboard tidak tersedia.' };
  } catch {
    return { dashboard: null, measurement: null, error: 'Backend belum tersedia. Periksa layanan API.' };
  }
};

export const actions: Actions = {
  login: async ({ request, cookies, url }) => {
    const form = await request.formData();
    try {
      const r = await api('/auth/login', undefined, { method: 'POST', body: JSON.stringify({ username: form.get('username'), password: form.get('password') }) });
      if (!r.ok) return fail(r.status, { error: r.payload.detail || 'Gagal masuk.' });
      cookies.set('campus_session', r.payload.token, { path: '/', httpOnly: true, sameSite: 'lax', secure: url.protocol === 'https:', maxAge: 28800 });
    } catch { return fail(503, { error: 'Backend belum tersedia.' }); }
    redirect(303, '/');
  },
  logout: async ({ cookies }) => {
    try { await api('/auth/logout', cookies.get('campus_session'), { method: 'POST' }); } catch { /* Always clear browser session. */ }
    cookies.delete('campus_session', { path: '/' });
    redirect(303, '/');
  },
  draft: async ({ request, cookies }) => {
    const form = await request.formData();
    const cid = encodeURIComponent(String(form.get('class_id')));
    try {
      const r = await api(`/classes/${cid}/interventions`, cookies.get('campus_session'), { method: 'POST', body: JSON.stringify({ student_id: form.get('student_id'), idempotency_key: form.get('key') }) });
      if (!r.ok) return fail(r.status, { error: typeof r.payload.detail === 'string' ? r.payload.detail : 'JEV menahan tindakan. Periksa kelengkapan atau versi data.' });
    } catch { return fail(503, { error: 'Backend belum tersedia.' }); }
    return { success: 'Draft intervensi berhasil dibuat.' };
  },
  approve: async ({ request, cookies }) => {
    const form = await request.formData();
    try {
      const r = await api(`/classes/${encodeURIComponent(String(form.get('class_id')))}/interventions/${encodeURIComponent(String(form.get('id')))}/approve`, cookies.get('campus_session'), { method: 'POST' });
      if (!r.ok) return fail(r.status, { error: 'Persetujuan ditahan. Data mungkin berubah atau kontrol JEV aktif.' });
    } catch { return fail(503, { error: 'Backend belum tersedia.' }); }
    return { success: 'Rencana disetujui dan tercatat.' };
  },
  measure: async ({ request, cookies }) => {
    const form = await request.formData();
    try {
      const r = await api(`/classes/${encodeURIComponent(String(form.get('class_id')))}/measurements`, cookies.get('campus_session'), { method: 'POST', body: JSON.stringify({ case_id: form.get('case_id'), arm: form.get('arm'), minutes: Number(form.get('minutes')), review_minutes: Number(form.get('review')), correction_minutes: Number(form.get('correction')), cost_idr: Number(form.get('cost')) }) });
      if (!r.ok) return fail(r.status, { error: 'Pengukuran tidak valid atau kasus/arm sudah tercatat.' });
    } catch { return fail(503, { error: 'Backend belum tersedia.' }); }
    return { success: 'Pengukuran tersimpan.' };
  }
};
