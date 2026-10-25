const CLIENT_BUILD='2026.10.25.10';
const $=s=>document.querySelector(s);
let state=null,selected=null,polling=false,installEvent,agents=[],tile=32,lastFrame=0;
const positions=new Map(),canvas=$('#fortress'),ctx=canvas.getContext('2d');
const dwarves=new Image(),geology=new Image();dwarves.src='/dwarves.png';geology.src='/geology.png';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,body){
 const controller=new AbortController();const timer=body===undefined?setTimeout(()=>controller.abort(),6000):null;
 try{
  const r=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',cache:'no-store',signal:controller.signal,headers:{'X-Watch-Build':CLIENT_BUILD,'X-Watch-Mode':matchMedia('(display-mode: standalone)').matches?'standalone':'browser','X-Watch-Rendered-At':String(state?.now||0),'X-Watch-Rendered-Active':String(agents.filter(a=>a.live_running).length),...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json();if(!r.ok){if(r.status===401)showLogin();throw Error(data.error||'Request failed')}return data;
 }finally{if(timer)clearTimeout(timer)}
}
function showLogin(){$('#login').hidden=false;$('#dashboard').hidden=true;$('#logout').hidden=true;$('#connection').textContent='locked · r10';$('#detail').close();state=null;agents=[]}
function age(t){if(!t)return '?';const s=Math.max(0,Date.now()/1000-t);return s<60?'now':s<3600?Math.floor(s/60)+'m':s<86400?Math.floor(s/3600)+'h':Math.floor(s/86400)+'d'}
function notice(text){$('#notice').textContent=text}
function render(){if(!state)return;$('#login').hidden=true;$('#dashboard').hidden=false;$('#logout').hidden=false;
 const linked=new Set(state.runs.map(r=>r.session_id).filter(Boolean));
 agents=[...state.runs.map(r=>({...r,key:'run:'+r.id,kind:'run',live:true,live_running:['starting','working'].includes(r.status),title:r.prompt,source:'app'})),...state.sessions.filter(s=>!linked.has(s.id)).map(s=>({...s,key:'session:'+s.id,kind:'session',phase:s.phase||'idle',title:s.title||s.last_activity_description||'Unnamed agent',status:s.status||'unknown',action:s.action||s.last_activity_description||'No live events',updated:s.last_activity_at||s.started_at}))];
 const previousOrder=new Map([...positions.keys()].map((key,i)=>[key,i]));
 agents.sort((a,b)=>(previousOrder.get(a.key)??Infinity)-(previousOrder.get(b.key)??Infinity));
 const active=agents.filter(a=>a.live_running).length;
 $('#stats').textContent=active+' working · '+agents.length+' sessions · idle <6m';
 $('#accessible-agents').replaceChildren();for(const a of agents){const b=document.createElement('button');b.textContent=a.title+' · '+a.status;b.onclick=()=>inspect(a);$('#accessible-agents').append(b)}
 resize();if(selected?.kind==='run')renderRun(selected.id);if(state.error)notice(state.error)
}
// Complete each requested crossing, even when a brief state change requests a return
// before arrival. The status label always shows the latest live state, not the queue.
function moveDwarf(previous,phase,left,right,now){
 const p=previous||{fraction:0,from:0,to:0,desired:0,queue:[],started:now,duration:1800,walking:false,direction:1,holdUntil:0};
 if(phase==='unknown'){
  if(p.pausedAt===undefined)p.pausedAt=now;
  return Object.assign(p,{x:left+(right-left)*p.fraction,paused:true});
 }
 if(p.pausedAt!==undefined){const gap=now-p.pausedAt;p.started+=gap;p.holdUntil+=gap;delete p.pausedAt}
 p.paused=false;
 if(p.walking){const progress=Math.min(1,Math.max(0,(now-p.started)/p.duration));p.fraction=p.from+(p.to-p.from)*progress;if(progress===1){p.walking=false;p.holdUntil=now+250}}
 const desired=['working','outbound','thinking','waiting'].includes(phase)?1:0;
 if(desired!==p.desired){p.queue.push(desired);p.desired=desired}
 if(!p.walking&&now>=p.holdUntil){
  while(p.queue.length){const next=p.queue.shift();if(next===p.fraction)continue;p.from=p.fraction;p.to=next;p.started=now;p.duration=Math.max(800,Math.abs(p.to-p.from)*1800);p.direction=p.to>p.from?1:-1;p.walking=true;break}
 }
 p.x=left+(right-left)*p.fraction;
 return p;
}
function activityLabel(a,pos){
 const elapsed=Math.max(0,Math.floor(Date.now()/1000-(a.live_updated||a.updated||Date.now()/1000)));
 const clock=elapsed<60?elapsed+'s':Math.floor(elapsed/60)+'m '+elapsed%60+'s';
 const status=a.phase==='thinking'?'THINKING':a.phase==='working'?'USING TOOL':a.phase==='returning'?'REPLYING':(a.status||'unknown').toUpperCase();
 const direction=pos.walking&&!pos.paused?(pos.direction>0?'→ workshop · ':'← chat · '):'';
 const action=(a.action||'').replace(/^(Using |Executing )/,'');
 return {status,headline:status+' · '+clock,detail:direction+action};
}
// Original built-in pixel art; optional custom sheets are never required.
function drawDefaultDwarf(index,pos,y,t,now){
 const scale=t/16,x=Math.round(pos.x);ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);
 const coat=['#b7a45e','#6e9f9a','#ac7755','#899361','#9d7c9d'][index%5];
 const rect=(x,y,w,h,color)=>{ctx.fillStyle=color;ctx.fillRect(x,y,w,h)};
 rect(5,1,7,3,'#b6b9a9');rect(4,3,9,2,'#ddd3a0');rect(6,5,5,3,'#d3a776');rect(pos.direction<0?6:10,5,1,1,'#171911');rect(5,8,7,5,coat);rect(3,9,2,3,coat);rect(12,9,2,3,coat);rect(6,7,5,3,'#d1c3a1');
 const step=pos.walking&&!pos.paused?[-1,0,1,0][Math.floor(now/110)%4]:0;
 rect(5+step,13,3,2,'#bba883');rect(9-step,13,3,2,'#bba883');ctx.restore();
}
function drawWalker(index,pos,y,t,now){
 if(!dwarves.complete||!dwarves.naturalWidth){drawDefaultDwarf(index,pos,y,t,now);return;}
 const sx=(index%6)*16;ctx.save();ctx.translate(Math.round(pos.x)+t/2,y);ctx.scale(pos.direction<0?-1:1,1);
 if(pos.walking&&!pos.paused){
  const stride=[-1,0,1,0][Math.floor(now/110)%4]*Math.max(1,t/16);
  ctx.drawImage(dwarves,sx,0,16,13,-t/2,0,t,t*13/16);
  ctx.drawImage(dwarves,sx,13,8,3,-t/2+stride,t*13/16,t/2,t*3/16);
  ctx.drawImage(dwarves,sx+8,13,8,3,-stride,t*13/16,t/2,t*3/16);
 }else ctx.drawImage(dwarves,sx,0,16,16,-t/2,0,t,t);
 ctx.restore();
}
function activityBubble(a,pos,y,t,w){
 if(!a.live_running&&!pos.walking&&a.phase!=='unknown')return;
 const label=activityLabel(a,pos);ctx.font='16px "Courier New",monospace';
 const width=Math.min(w-t*2,Math.max(170,Math.min(340,Math.max(ctx.measureText(label.headline).width,ctx.measureText(label.detail).width)+10)));
 const x=Math.max(t,Math.min(w-t-width,pos.x+t/2-width/2));
 ctx.fillStyle='#080a07';ctx.fillRect(x,y,width,39);ctx.strokeStyle=pos.walking?'#d2b865':a.phase==='unknown'?'#9d6450':'#9fa86b';ctx.strokeRect(x+.5,y+.5,width-1,38);
 text(label.headline,x+4,y+16,width-8,'#ffe39a');text(label.detail,x+4,y+33,width-8,'#d3d9c4');
 const anchor=Math.max(x+5,Math.min(x+width-5,pos.x+t/2));ctx.beginPath();ctx.moveTo(anchor,y+39);ctx.lineTo(anchor,y+44);ctx.stroke();
}
function resize(){const w=$('#world').clientWidth;if(!w)return;const h=Math.max($('#world').clientHeight,(agents.length||1)*tile*4+tile*2);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;ctx.imageSmoothingEnabled=false}draw(performance.now())}
function texture(x,y,sx,sy,t=tile){if(geology.complete&&geology.naturalWidth)ctx.drawImage(geology,sx,sy,32,32,x,y,t,t);else{const tone=((Math.floor(x/t)*7+Math.floor(y/t)*3)%5);ctx.fillStyle=['#302d24','#353226','#292c25','#39352a','#2a2c27'][tone];ctx.fillRect(x,y,t,t);ctx.strokeStyle='#131710';ctx.strokeRect(x+.5,y+.5,t-1,t-1);ctx.fillStyle='#514c36';ctx.fillRect(x+3,y+3,t-7,1);if(sx===737){ctx.fillStyle='#669999';ctx.fillRect(x+t*.25,y+t*.25,t*.5,t*.5)}if(sx===97){ctx.fillStyle='#bb783b';ctx.fillRect(x+t*.2,y+t*.35,t*.6,t*.3)}}}
function text(value,x,y,max,color='#c6c4b3'){ctx.font='16px "Courier New",monospace';ctx.fillStyle=color;let v=String(value);while(v.length>1&&ctx.measureText(v).width>max)v=v.slice(0,-2)+'…';ctx.fillText(v,x,y)}
function draw(now){if(!state||$('#dashboard').hidden)return;const w=canvas.width,t=tile,row=t*4;ctx.imageSmoothingEnabled=false;ctx.fillStyle='#000';ctx.fillRect(0,0,w,canvas.height);
 // Original supplied geology sheet is sampled directly: no generated replacement tiles.
 for(let x=0;x<w;x+=t)texture(x,0,33,707);
 text('CHAT',t+2,t-5,t*4,'#85afaf');text('WORKSHOP',w-t*4,t-5,t*4,'#c6a356');
 agents.forEach((a,i)=>{const y=t+i*row;const left=t*2,right=w-t*3;const col=i%5;
  for(let x=0;x<w;x+=t)for(let j=0;j<4;j++)texture(x,y+j*t,33+((Math.floor(x/t)+i)%3)*32,707+(j%3)*32)
  // Chamber edges and a horizontal path; no agent ever changes its lane.
  const walkY=y+t*2.35;
  ctx.fillStyle='#000e';ctx.fillRect(t,y,w-t*2,row);
  ctx.fillStyle='#15140f';ctx.fillRect(t,walkY,w-t*2,t);ctx.strokeStyle='#4b432d';ctx.strokeRect(t+.5,walkY+.5,w-t*2-1,t-1);
  texture(t,walkY,737,291);texture(w-t*2,walkY,97,291);
  const channel=a.source==='telegram'?'TG':a.source==='app'?'APP':(a.source||'hermes').slice(0,4).toUpperCase();
  ctx.fillStyle=a.source==='telegram'?'#6faaa9':'#6d695b';ctx.fillRect(t,y+7,2,row-14);
  const label=String(i+1).padStart(2,'0')+' '+channel+' '+(a.parent_session_id?'↳ ':'')+a.title;
  const status=a.phase==='thinking'?'THINKING':a.phase==='working'?'USING TOOL':a.phase==='returning'?'REPLYING':(a.status||'unknown').toUpperCase();
  const statusWidth=Math.min(112,w*.36);
  text(label,t+2,y+21,w-t*2-statusWidth-8,'#d1caa6');text(status,w-t-statusWidth,y+21,statusWidth,a.live_running?'#ffdb65':a.status==='unknown'?'#ce9774':'#a7b594');
  const phase=a.phase;
  const pos=moveDwarf(positions.get(a.key),phase,left,right,now);
  positions.set(a.key,pos);
  drawWalker(i,pos,walkY,t,now);
  activityBubble(a,pos,y+t,t,w);
  if(phase==='working'||phase==='thinking'){ctx.fillStyle=Math.floor(now/400)%2?'#ffc43d':'#a56720';ctx.fillRect(w-t*2+3,walkY+3,3,3)}
  const description=a.source+' · '+(pos.walking&&!pos.paused?(pos.direction>0?'Walking to workshop':'Walking back to chat'):a.action);
  text(description,t+2,y+row-5,w-t*3-14,a.live_running?'#e0d3a0':'#b4b8a9');text(age(a.live_updated||a.updated),w-t*2,y+row-5,t,'#b4ad8d');
 });
 const end=t+(agents.length||1)*row;
 for(let x=0;x<w;x+=t)texture(x,end,33,707);
 if(!agents.length){text('No active or recently used sessions.',t,t*3,w-t*2,'#d1caa6');text('Send a command below.',t,t*4,w-t*2,'#b9ac72')}
 for(const key of positions.keys())if(!agents.some(a=>a.key===key))positions.delete(key)
}
function frame(now){if(!document.hidden&&now-lastFrame>65){draw(now);lastFrame=now}requestAnimationFrame(frame)}requestAnimationFrame(frame);
canvas.addEventListener('click',e=>{const r=canvas.getBoundingClientRect();const i=Math.floor((e.clientY-r.top-tile)/(tile*4));if(agents[i])inspect(agents[i])});
function inspect(a){a.kind==='run'?openRun(a.id):openSession(a.id)}
function renderRun(id){const r=state?.runs.find(r=>r.id===id);if(!r)return;$('#detail-title').textContent=r.status+' / '+r.action;$('#stop').hidden=!['starting','working'].includes(r.status);$('#detail-body').innerHTML=`<p>${esc(r.prompt)}</p><pre>${esc(r.text||'Waiting for response…')}</pre><hr>${r.events.slice(-20).reverse().map(e=>`<p class="muted">${esc(e.type)} ${esc(e.name||'')} · ${age(e.at)}</p>`).join('')}`}
function openRun(id){selected={kind:'run',id};renderRun(id);$('#detail').showModal()}
async function openSession(id){selected={kind:'session',id};$('#stop').hidden=true;$('#detail-title').textContent='Session / recorded history';$('#detail-body').textContent='Loading…';$('#detail').showModal();try{const messages=await api('session/'+encodeURIComponent(id));if(selected?.id!==id)return;$('#detail-body').innerHTML=messages.map(m=>`<div class="message"><b>${esc(m.role)} ${esc(m.tool_name||'')}</b><pre>${esc(m.content)}</pre></div>`).join('')||'No messages recorded.'}catch(e){$('#detail-body').textContent=e.message}}
async function refresh(){if(polling)return;polling=true;try{state=await api('state');$('#connection').textContent=state.gateway?.connected?'● live · r10':'○ status offline · r10';render()}catch(e){if(state){$('#connection').textContent='○ offline · r10';for(const a of agents){a.phase='unknown';a.status='unknown';a.action='Connection lost · reconnecting';a.live_running=false}draw(performance.now())}else if($('#login').hidden)notice(e.message)}finally{polling=false}}
$('#login-form').onsubmit=async e=>{e.preventDefault();try{await api('login',{key:$('#key').value});$('#key').value='';notice('');await refresh()}catch(e){notice(e.message)}};
$('#task-form').onsubmit=async e=>{e.preventDefault();$('#send').disabled=true;try{await api('runs',{prompt:$('#prompt').value});$('#prompt').value='';notice('');await refresh()}catch(e){notice(e.message)}finally{$('#send').disabled=false}};
$('#stop').onclick=async()=>{if(selected?.kind!=='run')return;$('#stop').disabled=true;try{await api('cancel/'+selected.id,{});await refresh()}catch(e){notice(e.message)}finally{$('#stop').disabled=false}};
$('#logout').onclick=async()=>{try{await api('logout',{});showLogin()}catch(e){notice(e.message)}};
$('#close').onclick=()=>$('#detail').close();$('#detail').addEventListener('close',()=>selected=null);
$('#zoom-in').onclick=()=>{tile=Math.min(48,tile+16);positions.clear();resize()};$('#zoom-out').onclick=()=>{tile=Math.max(32,tile-16);positions.clear();resize()};
$('#update').onclick=async()=>{
 $('#update').disabled=true;notice('Loading the latest app…');
 try{if('serviceWorker'in navigator){const registrations=await navigator.serviceWorker.getRegistrations();await Promise.all(registrations.map(r=>r.update()))}}catch{}
 location.replace('/?refresh='+Date.now());
};
$('#help').onclick=()=>{selected=null;$('#stop').hidden=true;$('#detail-title').textContent='Fortress / controls';$('#detail-body').innerHTML='<p>App '+CLIENT_BUILD+' · last successful sync '+(state?new Date(state.now*1000).toLocaleTimeString():'none')+' · gateway '+(state?.gateway?.connected?'connected':'unavailable')+'</p><p>Tap a dwarf or its lane to inspect. Scroll to see all agents. + / − changes tile size.</p><p>Left: chat. Right: tool workshop. Dwarves move only horizontally.</p><p>Thinking and tool execution → walk to workshop. Replying or idle → walk back to chat. Each crossing finishes even if the state changes quickly. The label above the dwarf always shows its current activity and tool.</p><p>Live status comes from the Hermes gateway. Unknown means the live feed is unavailable. Reply ready does not confirm Telegram delivery.</p><p>Original pixel graphics are built in. Optional custom sheets are sampled directly, with smoothing disabled. Teal TG markers distinguish Telegram from other session types. Idle dwarves leave after six minutes.</p>';$('#detail').showModal()};
window.addEventListener('resize',resize);window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installEvent=e;$('#install').hidden=false});$('#install').onclick=async()=>{await installEvent?.prompt();$('#install').hidden=true};document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});window.addEventListener('online',refresh);if('serviceWorker'in navigator){navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'}).then(reg=>{setInterval(()=>reg.update().catch(()=>{}),60000);window.addEventListener('focus',()=>reg.update().catch(()=>{}))}).catch(()=>{});navigator.serviceWorker.addEventListener('controllerchange',()=>location.reload())}refresh();setInterval(()=>{if(!document.hidden)refresh()},1000);
