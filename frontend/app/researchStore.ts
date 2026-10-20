export type SavedArticle={id:number;title:string;url:string;excerpt:string;published_at:string|null;saved_at:string;folder:string;note:string;archived?:boolean};
export type Topic={id:string;query:string;seen:number[];initialized:boolean;unread:number[];checked_at?:string};
export type ResearchData={version:1;folders:string[];articles:SavedArticle[];topics:Topic[]};
export const key='openwatch:research:v1',event='openwatch:research-changed';
export const empty=():ResearchData=>({version:1,folders:['Ерөнхий'],articles:[],topics:[]});
export function validate(value:any):ResearchData{
 if(value?.version!==1||!Array.isArray(value.folders)||!Array.isArray(value.articles)||!Array.isArray(value.topics))throw Error('Судалгааны файл тохирохгүй.');
 if(value.folders.length>30||value.articles.length>500||value.topics.length>12)throw Error('Судалгааны хязгаар: 30 хавтас, 500 мэдээ, 12 сэдэв.');
 const date=(v:any)=>typeof v==='string'&&Number.isFinite(Date.parse(v))?v:null;
 const folders=Array.from(new Set<string>(['Ерөнхий',...value.folders.filter((x:any)=>typeof x==='string'&&x.trim()&&x.length<=60)])).slice(0,30);
 const articles:SavedArticle[]=value.articles.slice(0,500).map((a:any)=>{if(!Number.isSafeInteger(a.id)||a.id<1||typeof a.title!=='string'||typeof a.url!=='string'||!/^https?:\/\//i.test(a.url))throw Error('Хадгалсан нийтлэлийн мэдээлэл буруу.');let parsed:URL;try{parsed=new URL(a.url)}catch{throw Error('Эх холбоос буруу.')}if(!['https:','http:'].includes(parsed.protocol)||parsed.username||parsed.password||a.url.length>2000)throw Error('Эх холбоос буруу.');return {id:a.id,title:a.title.slice(0,1000),url:a.url.slice(0,2000),excerpt:String(a.excerpt||'').slice(0,600),published_at:date(a.published_at),saved_at:date(a.saved_at)||new Date().toISOString(),folder:folders.includes(a.folder)?a.folder:'Ерөнхий',note:String(a.note||'').slice(0,2000),archived:!!a.archived}});
 const topics:Topic[]=value.topics.slice(0,12).map((t:any)=>({id:String(t.id).slice(0,80),query:String(t.query||'').trim().slice(0,200),seen:Array.isArray(t.seen)?t.seen.filter(Number.isSafeInteger).slice(-200):[],initialized:!!t.initialized,unread:Array.isArray(t.unread)?t.unread.filter(Number.isSafeInteger).slice(-100):[],checked_at:date(t.checked_at)||undefined})).filter((t:Topic)=>t.query);
 return {version:1,folders,articles:[...new Map(articles.map(a=>[a.id,a])).values()],topics};
}
export function readResearch():ResearchData{const raw=localStorage.getItem(key);return raw?validate(JSON.parse(raw)):empty()}
export function writeResearch(data:ResearchData){localStorage.setItem(key,JSON.stringify(validate(data)));window.dispatchEvent(new Event(event))}
export function csvCell(value:any){let s=String(value??'');if(/^[\s]*[=+@\-\t\r]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'}
export function exportCsv(rows:SavedArticle[]){return '\ufeff'+[['Нийтлэл ID','Гарчиг','Эх холбоос','Нийтэлсэн UTC','Хадгалсан UTC','Хавтас','Тэмдэглэл','Хамрах хүрээ'],...rows.map(a=>[a.id,a.title,a.url,a.published_at,a.saved_at,a.folder,a.note,'Гарчиг, эхний ≤600 тэмдэгт; үнэн зөвийг батлаагүй'])].map(r=>r.map(csvCell).join(',')).join('\r\n')}
export function downloadFile(name:string,content:string,type:string){const u=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
export function numbers(text:string){return Array.from(new Set(text.match(/\d+(?:[.,]\d+)*(?:\s*(?:сая|тэрбум|их наяд|хувь|төгрөг|₮|%))?/gu)||[])).slice(0,30)}
