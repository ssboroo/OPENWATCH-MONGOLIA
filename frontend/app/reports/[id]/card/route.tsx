import {shareCard} from '../../../ShareCard';
import {reportBrief} from '../../../analysisBrief';
export const runtime='nodejs';
export async function GET(request:Request,{params}:{params:Promise<{id:string}>}){
 const {id}=await params;if(!/^[1-9]\d{0,9}$/.test(id))return new Response('Not found',{status:404});
 const r=await fetch(`${process.env.BACKEND_URL||'http://backend:8000'}/api/v1/reports/${id}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
 if(!r.ok)return new Response('Public report unavailable',{status:r.status===404?404:503});
 const report=await r.json();if(report.state!=='published'||!report.body)return new Response('Report not public',{status:404});
 const q=new URL(request.url).searchParams;
 return shareCard(reportBrief(report),q.get('format')==='portrait',q.get('download')==='1','report-'+id);
}
