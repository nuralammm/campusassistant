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
    if (!cid) return { classes: [], academic: null, audit: [], error: 'Buat kelas pertama Anda.' };
    const [academic, audit] = await Promise.all([api(`/classes/${encodeURIComponent(cid)}/academic`, token), api(`/classes/${encodeURIComponent(cid)}/audit`, token)]);
    return { classes: classes.ok ? classes.payload : [], academic: academic.ok ? academic.payload : null, audit: audit.ok ? audit.payload : [], error: academic.ok ? '' : 'Kelas tidak dapat diakses.' };
  } catch (e) { if (isRedirect(e)) throw e; return { classes: [], academic: null, audit: [], error: 'Backend belum tersedia.' }; }
};
function message(payload: any): string {
  if (typeof payload.detail === 'string') return payload.detail;
  return 'Validasi gagal. Periksa nilai 0–100, ID unik, pemetaan dan jumlah bobot.';
}
export const actions: Actions = {
  save: async ({ request, cookies }) => {
    const f = await request.formData();
    const op = String(f.get('op'));
    const cid = encodeURIComponent(String(f.get('class_id')));
    let path = '', method = 'POST', body: any;
    try {
      if (op === 'class') { path = '/classes'; body = { id: f.get('id'), name: f.get('name') }; }
      else if (op === 'student') { path = `/classes/${cid}/students`; body = { id: f.get('id'), name: f.get('name') }; }
      else if (op === 'rename') { path = `/classes/${cid}/students/${encodeURIComponent(String(f.get('id')))}`; method = 'PUT'; body = { name: f.get('name') }; }
      else if (op === 'policy') { path = `/classes/${cid}/policy`; method = 'PUT'; body = { expected_revision: Number(f.get('revision')), policy: JSON.parse(String(f.get('policy'))) }; }
      else if (op === 'scores') {
        const r = await api(`/classes/${cid}/academic`, cookies.get('campus_session'));
        if (!r.ok) return fail(r.status, { error: 'Kelas tidak dapat diakses.' });
        const rows = r.payload.students.flatMap((s: any) => r.payload.policy.assessments.map((a: any) => {
          const value = f.get(`score_${s.id}_${a.id}`);
          return { student_id: s.id, assessment_id: a.id, value: value === '' || value === null ? null : Number(value) };
        }));
        path = `/classes/${cid}/scores`; method = 'PUT'; body = { expected_revision: Number(f.get('revision')), rows };
      } else if (op === 'preview') {
        const file = f.get('file');
        if (!(file instanceof File) || file.size > 200000) return fail(422, { error: 'Pilih CSV maksimal 200 KB.' });
        const r = await api(`/classes/${cid}/scores/preview`, cookies.get('campus_session'), { method: 'POST', body: JSON.stringify({ csv_text: await file.text() }) });
        if (!r.ok) return fail(r.status, { error: message(r.payload) });
        return { preview: r.payload, success: r.payload.valid ? 'Preview valid. Periksa sebelum konfirmasi.' : 'CSV memiliki kesalahan; belum ada data disimpan.' };
      } else if (op === 'import') { path = `/classes/${cid}/scores`; method = 'PUT'; body = JSON.parse(String(f.get('batch'))); }
      else return fail(400, { error: 'Tindakan tidak dikenal.' });
      const r = await api(path, cookies.get('campus_session'), { method, body: JSON.stringify(body) });
      if (!r.ok) return fail(r.status, { error: message(r.payload) });
      return { success: 'Data berhasil disimpan. Capaian akan dihitung dari data terbaru.' };
    } catch { return fail(400, { error: 'Data tidak valid atau backend tidak tersedia.' }); }
  }
};
