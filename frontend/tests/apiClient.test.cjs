const assert=require('node:assert/strict');
const {apiFetch,retryDelay}=require(process.argv[2]);
(async()=>{
 let count=0,active=0,peak=0;
 global.fetch=async(url,init)=>{count++;active++;peak=Math.max(peak,active);await new Promise(r=>setTimeout(r,12));active--;return new Response(JSON.stringify({url}),{headers:{'content-type':'application/json'}})};
 const same=await Promise.all(Array.from({length:20},()=>apiFetch('/same')));assert.equal(count,1);assert.equal((await same[0].json()).url,'/same');assert.equal((await same[19].json()).url,'/same');
 await Promise.all(Array.from({length:20},(_,i)=>apiFetch('/distinct/'+i)));assert.ok(peak<=4,`Concurrency reached ${peak}`);
 const before=count;const abort=new AbortController();const cancelled=apiFetch('/abort',{signal:abort.signal});const other=apiFetch('/abort');abort.abort();await assert.rejects(cancelled,{name:'AbortError'});assert.equal((await other).status,200);assert.equal(count,before+1);
 let posts=0;global.fetch=async()=>{posts++;return new Response('{}',{status:429})};await apiFetch('/mutation',{method:'POST'});assert.equal(posts,1,'POST must never replay');
 assert.equal(retryDelay('2'),2000);assert.equal(retryDelay('300'),300000);assert.equal(retryDelay('invalid'),60000);assert.equal(retryDelay('Thu, 01 Jan 1970 00:00:02 GMT',1000),1000);
 let reads=0;global.fetch=async()=>{reads++;return reads===1?new Response('{}',{status:429,headers:{'Retry-After':'1'}}):new Response('{}')};const started=Date.now();await Promise.all([apiFetch('/limited'),apiFetch('/limited')]);assert.equal(reads,2);assert.ok(Date.now()-started>=950,'Retry-After must be respected');
 console.log('PASS: GET deduplication, independent response bodies, concurrency <=4, abort isolation, mutation non-replay and Retry-After recovery');
})().catch(e=>{console.error(e);process.exitCode=1});
