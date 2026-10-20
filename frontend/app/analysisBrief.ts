import {chronology,formatDate,duration,timestamp} from './chronology';
type Row=Record<string,any>;
export type Brief={title:string,sources:string[],verdict:string,summary:string,facts:{label:string,text:string}[],unknowns:string[],nextSteps:string[],exact:number,partial:number,candidates:number,ready:number,total:number,domains:number,scope:string,checked:string,version:string};
export function buildBrief(data:Row,ai?:Row):Brief{
 const items:Row[]=Array.isArray(data.items)?data.items:[];
 const rows=[{...data,id:data.article_id},...items];
 const exact=items.filter(x=>x.comparison==='normalized_body_equal').length;
 const partial=items.filter(x=>['body_overlap_candidate','body_containment_candidate','observed_body_equal'].includes(x.comparison)).length;
 const ready=rows.filter(x=>x.body?.state==='ready').length;
 const titleOnly=items.filter(x=>x.comparison==='title_only_candidate').length;
 const sourceSet=new Set(rows.map(x=>{try{return new URL(x.url).hostname.replace(/^www\./,'')}catch{return ''}}).filter(Boolean));
 const sources=Array.from(sourceSet);const domains=sources.length;
 let verdict='Өгөгдөл хүрэлцэхгүй',summary='Үндсэн эхийн өгөгдөл хүрэлцэхгүй тул агуулга ижил эсэхийг тогтоох боломжгүй.';
 if(exact){verdict='Үндсэн эхийн давхцал батлагдсан';summary=`Шалгасан нийтлэлүүдээс ${exact} өөр нийтлэлийн нормчилсон үндсэн эх ижил байна.`}
 else if(partial){verdict='Агуулгын давхцлын нэр дэвшигч';summary=`${partial} нийтлэлтэй хэсэгчилсэн эсвэл хязгаарлагдмал эхийн давхцал илэрсэн. Бүтэн эх ижил гэж дүгнээгүй.`}
 else if(titleOnly){verdict='Зөвхөн гарчгийн төстэй байдал';summary=`${titleOnly} нийтлэлийн гарчиг төстэй байна. Үүгээр бүтэн эх хуулбарласан гэж дүгнэхгүй.`}
 else if(data.body?.state==='ready'&&items.some(x=>x.body?.state==='ready')){verdict='Хүчтэй давхцал илрээгүй';summary='Уншсан энэ хүрээнд хүчтэй агуулгын давхцал илрээгүй. Бусад нийтлэлд давхцал байхгүй гэсэн баталгаа биш.'}
 const facts=[{label:'Хамрах хүрээ',text:`Дэлгэрэнгүйд ${rows.length} нийтлэл, ${domains} домэйн байна. ${ready} нийтлэлийн үндсэн эх уншигдсан. Архивын ${data.candidate_count??0} нэр дэвшигчийг шалгасан.`}];
 if(exact)facts.push({label:'Яг ижил эх',text:`${exact} хосын нормчилсон, хязгаарлаагүй үндсэн текстийн SHA-256 ижил. Ижил эх нь хэвлэлийн мэдээ эсвэл зөвшөөрөлтэй дахин нийтлэл байж болно.`});
 if(partial)facts.push({label:'Хэсэгчилсэн давхцал',text:`${partial} хосод хэсэгчилсэн, агуулагдсан эсвэл хязгаарлагдсан эхийн ижил байдал ажиглагдсан. Хосын нотолгоог тусад нь нягтална.`});
 const time=chronology(rows,'published_at');
 if(time.known.length){const first=time.known[0];let domain='Эх сурвалж';try{domain=new URL(first.url||'').hostname.replace(/^www\./,'')}catch{}
  facts.push({label:'Нийтэлсэн цагийн дараалал',text:`Бүртгэгдсэн цагуудаас ${domain} · ${formatDate(first.published_at)} хамгийн эрт байна.${time.earliestCount>1?` ${time.earliestCount} нийтлэл ижил хамгийн эрт цагтай.`:''}${time.span!==null&&time.span>0?` Эрт, оройн зөрүү ${duration(time.span)}.`:''} Энэ нь анхны эхийг тогтоохгүй.`})}
 const labelled=rows.filter(x=>x.body?.state==='ready'&&x.body.disclosures?.length);
 facts.push({label:'Нийтлэгчийн тэмдэглэгээ',text:labelled.length?`${labelled.length} эхэд нийтлэгчийн төлбөртэй/сурталчилгааны ил тод тэмдэглэгээ ажиглагдсан. Тэмдэглэгээний эх, агуулгыг нягтална.`:'Уншсан эхүүдэд төлбөртэй/сурталчилгааны ил тод тэмдэглэгээ ажиглагдаагүй. Төлбөргүй эсвэл захиалгат биш гэсэн баталгаа биш.'});
 if(ai)facts.push({label:'AI задлалын хамрах хүрээ',text:`${ai.status==='ai_complete'?'AI задлал бэлэн.':'AI задлал бүрэн дуусаагүй.'} ${ai.connections?.scope==='headline_only'?'Зөвхөн гарчгийг':'Гарчиг ба архивын хураангуйг'} шинжилсэн; бүтэн эхийн үнэн зөвийг баталгаажуулаагүй.`});
 const unknowns=['Хэн хэнээс хуулсан, захиалагч, төлбөр төлөгч болон буруутай үйлдлийг энэ шинжилгээ тогтоохгүй.','Төстэй мэдээнүүд нь бие даасан баталгаа биш. Мэдэгдлийн үнэн зөвийг анхны баримтаас шалгана.'];
 if(ready<rows.length)unknowns.unshift(`${rows.length-ready} нийтлэлийн үндсэн эх уншигдаагүй тул дүгнэлт хязгаарлагдсан.`);
 if(time.unknown.length)unknowns.push(`${time.unknown.length} нийтлэлийн нийтэлсэн цаг тодорхойгүй. Илрүүлсэн цагаар орлуулаагүй.`);
 if(data.candidate_count>=data.candidate_limit)unknowns.push(`Нэр дэвшигчийн хайлт ${data.candidate_limit} нийтлэлийн хязгаартай.`);
 const checked=rows.map(x=>x.body?.checked_at).filter(x=>timestamp(x)!==null).sort((a,b)=>timestamp(b)!-timestamp(a)!)[0];
 return {title:data.title||'Нийтлэлийн шинжилгээ',sources,verdict,summary,facts,unknowns,nextSteps:['Эх нийтлэлийн холбоос, нийтэлсэн цаг болон нийтлэгчийн эх сурвалжийг нээнэ.','Хосын харьцуулалтаас яг ижил эх, хэсэгчилсэн давхцал, зөвхөн гарчгийн төстэй байдлыг ялгана.','Мэдэгдлийг анхны баримт, албан эх сурвалжтай тулгаж, тодорхойгүй зүйлийг хамт хуваалцана.'],exact,partial,candidates:titleOnly,ready,total:rows.length,domains,scope:'Шууд шинэчлэгддэг автомат шинжилгээ · хүний хянасан тайлан биш',checked:formatDate(checked),version:String(data.body?.version_id||'—')};
}
export function reportBrief(report:Row):Brief{
 const body=report.body||{};
 return {title:report.title,sources:(body.sources||[]).map((s:Row)=>s.name),verdict:report.state==='published'?'Хүний хяналттай нийтэлсэн тайлан':'Тайлан нийтээс татагдсан',summary:report.review_note||'Эх сурвалж, хувилбар, нотолгоонд тулгуурласан тайлан. Нийтэлсэн нь бүх мэдэгдэл үнэн гэсэн баталгаа биш.',facts:[],unknowns:body.limitations||[],nextSteps:[],exact:0,partial:body.matches?.length||0,candidates:0,ready:0,total:body.scope?.article_ids?.length||0,domains:body.scope?.source_count||0,scope:'Хүний хяналттай тайлан · snapshot хувилбар '+report.revision,checked:formatDate(report.reviewed_at||report.created_at),version:String(report.revision)};
}
