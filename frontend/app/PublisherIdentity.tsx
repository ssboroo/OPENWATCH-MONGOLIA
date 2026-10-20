'use client';
import {useState} from 'react';
import registry from './publisherRegistry.json';
export default function PublisherIdentity({domain}:{domain:string}){
 const [attempt,setAttempt]=useState(0);const entry=(registry as Record<string,{name:string,iconUrl:string}>)[domain];
 const safe=/^[a-z0-9.-]+$/.test(domain)&&!!entry;const choices=safe?[`/api/v1/source-icons/${domain}`,`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`]:[];
 return <span className="cx-avatar cx-publisher-logo" aria-label={`${entry?.name||domain} лого`}><span aria-hidden="true">{(entry?.name||domain).slice(0,2).toUpperCase()}</span>{attempt<choices.length&&<img key={choices[attempt]} src={choices[attempt]} alt="" decoding="async" loading="lazy" referrerPolicy="no-referrer" onError={()=>setAttempt(a=>a+1)}/>}</span>
}

export const host=(u:string)=>{try{return new URL(u).hostname.replace(/^www\./,'')}catch{return 'Эх сурвалж'}};
export function SourceIcon({domain}:{domain:string}){return <PublisherIdentity key={domain} domain={domain}/>}
