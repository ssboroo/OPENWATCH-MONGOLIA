import {cache} from 'react';
import {notFound} from 'next/navigation';
import {buildBrief} from '../../analysisBrief';
export const siteUrl=process.env.NEXT_PUBLIC_SITE_URL||'https://openwatch-mongolia-production.up.railway.app';
export const loadAnalysis=cache(async(id:string,other='')=>{
 if(!/^[1-9]\d{0,9}$/.test(id)||(other&&(!/^[1-9]\d{0,9}$/.test(other)||other===id)))notFound();
 const base=process.env.BACKEND_URL||'http://backend:8000';
 const read=async(path:string)=>{const r=await fetch(base+'/api/v1/'+path,{next:{revalidate:60},signal:AbortSignal.timeout(25000)});if(r.status===404)notFound();if(!r.ok)throw Error('Шинжилгээний мэдээлэл түр боломжгүй байна.');return r.json()};
 const [data,ai]=await Promise.all([read(`articles/${id}/comparison`+(other?'?other_id='+other:'')),read(`articles/${id}/analysis`)]);
 return {data,ai,brief:buildBrief(data,ai),path:`/analysis/${id}`+(other?'?other='+other:''),cardPath:`/analysis/${id}/card`+(other?'?other='+other:'')};
});
