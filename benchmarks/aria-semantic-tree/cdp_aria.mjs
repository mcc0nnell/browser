// WPT-derived CDP AX property snapshot; NOT WPT harness.
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import path from 'node:path';
const root = path.dirname(new URL(import.meta.url).pathname);
const [exe,label] = process.argv.slice(2);
if (!exe || !label) { console.error('usage: node cdp_aria.mjs /abs/path/to/lightpanda label'); process.exit(2); }
const source = fs.readFileSync(path.join(root,'fixtures','wpt_checked_source.html'),'utf8');
const cases = [...source.matchAll(/<div data-testname="([^"]+)" role="checkbox"[^>]*data-expectedproperties='([^']+)'/g)].map(m=>({name:m[1],expected:JSON.parse(m[2]).checked}));
if(cases.length!==4)throw new Error('Unexpected WPT fixture case count');
const page = fs.readFileSync(path.join(root,'fixtures','wpt_checked_local.html'));
const server = http.createServer((req,res)=>{res.setHeader('content-type','text/html');res.end(page)});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const fixtureUrl='http://127.0.0.1:'+server.address().port+'/wpt_checked_local.html';
const port=await new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',reject);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p))});});
const bin=spawn(exe,['serve','--port',String(port),'--log-level','error'],{stdio:['ignore','ignore','pipe'],detached:true});
let errors='';
bin.stderr.on('data',b=>{errors+=String(b).slice(0,200)});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let ws;
try{
  let ready=false;
  for(let i=0;i<60;i++){
    if (bin.exitCode!==null) throw new Error('CDP server exited: '+errors);
    try {let resp=await fetch('http://127.0.0.1:'+port+'/json/version');if(resp.ok){ready=true;break;}}catch{}
    await sleep(75);
  }
  if(!ready)throw new Error('CDP endpoint not ready: '+errors);
  ws=new WebSocket('ws://127.0.0.1:'+port+'/');
  await new Promise((resolve,reject)=>{const fail=setTimeout(()=>reject(Error('WS open timeout')),4000);ws.addEventListener('open',()=>{clearTimeout(fail);resolve()},{once:true});ws.addEventListener('error',e=>{clearTimeout(fail);reject(e)},{once:true});});
  let next=0;const inflight=new Map();
  ws.addEventListener('message',ev=>{
    let data;try{data=JSON.parse(ev.data)}catch{return}
    if (!data.id||!inflight.has(data.id))return;
    const {resolve,reject,timer}=inflight.get(data.id);inflight.delete(data.id);clearTimeout(timer);
    if(data.error)reject(Error(JSON.stringify(data.error)));else resolve(data.result||{});
  });
  const send=(method,params={},sessionId)=>{
    const id=++next;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{inflight.delete(id);reject(Error('CDP timeout '+method))},8000);
      inflight.set(id,{resolve,reject,timer});
      ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
    });
  };
  const t=await send('Target.createTarget',{url:'about:blank'});
  const a=await send('Target.attachToTarget',{targetId:t.targetId,flatten:true});
  const sid=a.sessionId;
  await send('Page.enable',{},sid);
  await send('Page.navigate',{url:fixtureUrl},sid);
  let nodes;
  for(let i=0;i<40;i++){
    const tree=await send('Accessibility.getFullAXTree',{},sid);
    nodes=tree.nodes||[];
    if(nodes.some(n=>n.name?.value===cases[0].name))break;
    await sleep(70);
  }
  const findings=cases.map(c=>{
    const matches=nodes.filter(n=>n.name?.value===c.name&&n.role?.value==='checkbox');
    const props=matches.length===1?(matches[0].properties||[]):[];
    const checked=props.find(p=>p.name==='checked')?.value?.value??null;
    return {...c, observed:checked, matchedNodes:matches.length, match:String(checked)===c.expected};
  });
  const out={label,measurement:'CDP Accessibility.getFullAXTree WPT source-derived 4-case projection; not official WPT',
    binarySha256:crypto.createHash('sha256').update(fs.readFileSync(exe)).digest('hex'),
    sourceSha256:crypto.createHash('sha256').update(source).digest('hex'),
    correct:findings.filter(x=>x.match).length,total:findings.length,findings};
  fs.writeFileSync(path.join(root,'results',label+'-cdp-wpt.json'),JSON.stringify(out,null,2)+'\n');
  console.log(JSON.stringify(out,null,2));
}finally{
  try{ws?.close()}catch{}
  try{process.kill(-bin.pid,'SIGKILL')}catch{}
  server.close();
}
