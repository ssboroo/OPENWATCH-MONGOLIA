import {cache} from 'react';
import {notFound} from 'next/navigation';
import {ReportView} from '../../ReportWorkspace';
const load=cache(async(id:string)=>{
 if(!/^[1-9]\d*$/.test(id))notFound();
 const response=await fetch(`${process.env.BACKEND_URL||'http://backend:8000'}/api/v1/reports/${id}`,{cache:'no-store'});
 if(response.status===404)notFound();
 if(!response.ok)throw Error('Public report service unavailable');
 return response.json();
});
export async function generateMetadata({params}:{params:Promise<{id:string}>}){
 const {id}=await params;const report=await load(id);
 return {title:report.title+' — OpenWatch Mongolia',description:'Эх сурвалж, цаг хугацаа, нотолгооны snapshot тайлан.'};
}
export default async function Page({params}:{params:Promise<{id:string}>}){
 const {id}=await params;const report=await load(id);
 return <main className="standalone-report"><a href="/" className="back-button">← OPENWATCH MONGOLIA</a><ReportView id={Number(id)} initialReport={report}/></main>
}
