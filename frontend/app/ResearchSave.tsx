'use client';
import {useEffect,useState} from 'react';
import {BookmarkCheck,BookmarkPlus} from 'lucide-react';
import {event,readResearch,writeResearch} from './researchStore';
export default function ResearchSave({article}:{article:{id:number;title:string;url:string;excerpt?:string;published_at?:string|null}}){
 const [saved,setSaved]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{const load=()=>{try{setSaved(readResearch().articles.some(a=>a.id===article.id&&!a.archived))}catch{}};load();window.addEventListener(event,load);return()=>window.removeEventListener(event,load)},[article.id]);
 const save=()=>{try{const d=readResearch();const old=d.articles.find(a=>a.id===article.id);if(old)old.archived=false;else {if(d.articles.length>=500)throw Error('Хадгалсан 500 нийтлэлийн хязгаарт хүрсэн. Нөөцөө экспортлоно уу.');d.articles.unshift({...article,excerpt:(article.excerpt||'').slice(0,600),published_at:article.published_at||null,saved_at:new Date().toISOString(),folder:'Ерөнхий',note:''})}writeResearch(d);setSaved(true);setMessage('Энэ браузерын “Миний судалгаа” хэсэгт хадгаллаа.')}catch(e){setMessage('Хадгалж чадсангүй. '+(e as Error).message)}};
 return <div className="ow-save-control"><button onClick={save} disabled={saved}>{saved?<BookmarkCheck size={15}/>:<BookmarkPlus size={15}/>} {saved?'Судалгаанд хадгалсан':'Миний судалгаанд хадгалах'}</button><a href="/?view=research">Миний судалгаа →</a>{message&&<small role="status">{message}</small>}</div>
}
