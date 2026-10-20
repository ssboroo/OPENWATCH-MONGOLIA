'use client';
import {useState} from 'react';
/** Cached publisher icons with a readable fallback when an image is unavailable. */
export default function SiteIdentity({domain,name,iconUrl}:{domain:string,name:string,iconUrl?:string}){
 const [attempt,setAttempt]=useState(0);
 const fallback=`https://${domain}/favicon.ico`;
 let discovered='';
 try{const u=new URL(iconUrl||'');if(u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&u.hostname.replace(/^www\./,'')===domain)discovered=u.href}catch{}
 const icons=Array.from(new Set([`/api/v1/source-icons/${encodeURIComponent(domain)}`,discovered,fallback,`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`].filter(Boolean)));
 return <div className="site-identity" aria-label={name+' лого'}>
  <span aria-hidden="true">{name.slice(0,2).toLocaleUpperCase()}</span>
  {attempt<icons.length&&<img src={icons[attempt]} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={()=>setAttempt(i=>i+1)}/>}
 </div>;
}
