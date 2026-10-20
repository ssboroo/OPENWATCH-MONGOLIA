import {loadAnalysis} from '../load';
import {shareCard} from '../../../ShareCard';
export const runtime='nodejs';
export async function GET(request:Request,{params}:{params:Promise<{id:string}>}){
 const {id}=await params;const query=new URL(request.url).searchParams;
 const {brief}=await loadAnalysis(id,query.get('other')||'');
 return shareCard(brief,query.get('format')==='portrait',query.get('download')==='1',id);
}
