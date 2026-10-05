import { fail,redirect,isRedirect } from '@sveltejs/kit';import { api } from '$lib/api.server';import type {Actions,PageServerLoad} from './$types';
export const load:PageServerLoad=async({cookies,url})=>{
 const token=cookies.get('campus_session');if(!token)redirect(303,'/');
 try{const classes=await api('/classes',token);if(classes.status===401)redirect(303,'/');const cid=url.searchParams.get('class')||classes.payload[0]?.id;
 if(!cid)return {classes:[],academic:null,ai:null,nonce:crypto.randomUUID(),error:'Belum ada kelas.'};
 const [academic,ai]=await Promise.all([api(`/classes/${encodeURIComponent(cid)}/academic`,token),api(`/classes/${encodeURIComponent(cid)}/ai`,token)]);
 return {classes:classes.ok?classes.payload:[],academic:academic.ok?academic.payload:null,ai:ai.ok?ai.payload:null,nonce:crypto.randomUUID(),error:ai.ok?'':'Provider tidak dapat diakses.'};
 }catch(e){if(isRedirect(e))throw e;return {classes:[],academic:null,ai:null,nonce:crypto.randomUUID(),error:'Backend tidak tersedia.'};}
};
export const actions:Actions={generate:async({request,cookies})=>{const f=await request.formData();try{const r=await api(`/classes/${encodeURIComponent(String(f.get('class_id')))}/interventions/ai`,cookies.get('campus_session'),{method:'POST',body:JSON.stringify({student_id:f.get('student_id'),idempotency_key:f.get('key')})});if(!r.ok)return fail(r.status,{error:typeof r.payload.detail==='string'?r.payload.detail:'JEV menahan tindakan; periksa kelengkapan bukti.'});return {success:`Run ${r.payload.status}. Draft yang berhasil tersedia di menu Intervensi.`};}catch{return fail(503,{error:'Provider/backend tidak tersedia.'});}}};
