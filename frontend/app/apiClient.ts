/** Shared public GET transport: coalesce concurrent reads, cap requests and honor 429. */
const pending=new Map<string,Promise<Response>>();
let active=0,resumeAt=0;
const queue:Array<()=>void>=[];
export function retryDelay(value:string|null,now=Date.now()){if(!value)return 60000;const number=Number(value);const ms=Number.isFinite(number)?number*1000:Date.parse(value)-now;return Number.isFinite(ms)?Math.max(1000,ms):60000}
function announce(){if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('openwatch:api-cooldown',{detail:resumeAt}))}
async function cooldown(){while(resumeAt>Date.now())await new Promise(r=>setTimeout(r,Math.min(60000,resumeAt-Date.now())))}
async function slot(){if(active<4){active++;return}await new Promise<void>(r=>queue.push(r))}
function release(){const next=queue.shift();if(next)next();else active--}
function observed(p:Promise<Response>,signal?:AbortSignal|null):Promise<Response>{if(!signal)return p.then(r=>r.clone());if(signal.aborted)return Promise.reject(new DOMException('Aborted','AbortError'));return new Promise((resolve,reject)=>{const abort=()=>reject(new DOMException('Aborted','AbortError'));signal.addEventListener('abort',abort,{once:true});p.then(r=>{signal.removeEventListener('abort',abort);if(!signal.aborted)resolve(r.clone())},e=>{signal.removeEventListener('abort',abort);if(!signal.aborted)reject(e)})})}
export function apiFetch(url:string,init:RequestInit={}):Promise<Response>{
 const method=(init.method||'GET').toUpperCase();
 // Never replay mutations or share authenticated responses.
 if(method!=='GET'||new Headers(init.headers).has('authorization'))return fetch(url,init);
 const key=url;const existing=pending.get(key);if(existing)return observed(existing,init.signal);
 const run=(async()=>{for(let attempt=0;;attempt++){await cooldown();await slot();let response:Response;try{await cooldown();response=await fetch(url,{...init,signal:undefined})}finally{release()}
 if(response.status!==429)return response;
 resumeAt=Math.max(resumeAt,Date.now()+retryDelay(response.headers.get('Retry-After')));announce();
 if(attempt>=1)return response;
 await response.body?.cancel();
 }})();
 pending.set(key,run);run.then(()=>pending.delete(key),()=>pending.delete(key));return observed(run,init.signal);
}
