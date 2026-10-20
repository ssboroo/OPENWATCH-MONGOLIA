'use client';
import {useEffect,useState} from 'react';
const event='openwatch:refresh-workspace';
export function refreshWorkspace(){window.dispatchEvent(new Event(event))}
// Refresh data without resetting the active filters, page or selected article.
export function useWorkspaceRefresh(){
 const [revision,setRevision]=useState(0);
 useEffect(()=>{const update=()=>setRevision(n=>n+1);window.addEventListener(event,update);return()=>window.removeEventListener(event,update)},[]);
 return revision;
}
