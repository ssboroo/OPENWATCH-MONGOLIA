// Short archived excerpts only. Matching is lexical, never a claim of semantic equivalence.
export function sentenceAlignment(left:string,right:string){
 const split=(s:string)=>(s.match(/[^.!?。！？\n]+(?:[.!?。！？]+|$)/gu)||[]).map(x=>x.trim()).filter(Boolean).slice(0,20);
 const norm=(s:string)=>s.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,' ').trim();
 const a=split(left),b=split(right),used=new Set<number>();
 const rows:{left:string,right:string,kind:'same'|'changed'|'left_only'|'right_only'}[]=[];
 for(const text of a){let best=-1,score=0;const exact=b.findIndex((s,i)=>!used.has(i)&&norm(s)===norm(text));
 if(exact>=0){used.add(exact);rows.push({left:text,right:b[exact],kind:'same'});continue}
 const words=new Set(norm(text).match(/[\p{L}\p{N}]+/gu)||[]);
 b.forEach((s,i)=>{if(used.has(i))return;const other=new Set(norm(s).match(/[\p{L}\p{N}]+/gu)||[]);const intersection=[...words].filter(w=>other.has(w)).length;const similarity=intersection/Math.max(1,new Set([...words,...other]).size);if(similarity>score){score=similarity;best=i}});
 if(best>=0&&score>=.35){used.add(best);rows.push({left:text,right:b[best],kind:'changed'})}else rows.push({left:text,right:'',kind:'left_only'});
 }
 b.forEach((s,i)=>{if(!used.has(i))rows.push({left:'',right:s,kind:'right_only'})});return rows;
}
