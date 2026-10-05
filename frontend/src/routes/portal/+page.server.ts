import { fail, redirect, isRedirect } from '@sveltejs/kit';
import { api } from '$lib/api.server';
import type { Actions, PageServerLoad } from './$types';
export const load: PageServerLoad = async ({ cookies }) => {
  const token=cookies.get('campus_session');
  if(!token) redirect(303,'/');
  try {
    const me=await api('/auth/me',token);
    if(me.status===401) {cookies.delete('campus_session',{path:'/'});redirect(303,'/');}
    if(me.payload.role==='lecturer') redirect(303,'/');
    const r=await api(me.payload.role==='student'?'/portal/student':'/portal/prodi',token);
    return { role:me.payload.role, username:me.payload.username, portal:r.ok?r.payload:null,error:r.ok?'':'Portal belum terhubung atau tidak dapat diakses.' };
  } catch(e) {if(isRedirect(e))throw e;return {role:'',username:'',portal:null,error:'Backend tidak tersedia.'};}
};
export const actions: Actions = {
  logout:async({cookies})=>{try{await api('/auth/logout',cookies.get('campus_session'),{method:'POST'});}catch{}cookies.delete('campus_session',{path:'/'});redirect(303,'/');},
  submit:async({request,cookies})=>{
    const f=await request.formData();
    try {
      const r=await api(`/portal/student/interventions/${encodeURIComponent(String(f.get('id')))}/submit`,cookies.get('campus_session'),{method:'POST',body:JSON.stringify({notes:f.get('notes')})});
      if(!r.ok)return fail(r.status,{error:'Laporan tidak dapat dikirim: rencana tidak aktif atau sudah dilaporkan.'});
      return {success:'Laporan pelaksanaan dikirim. Dosen akan meninjau hasilnya.'};
    }catch{return fail(503,{error:'Backend tidak tersedia.'});}
  }
};
