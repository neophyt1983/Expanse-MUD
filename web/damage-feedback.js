/* Personal harm is an explicit event, independent of open readers and panels. */
(()=>{
 'use strict';
 const make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
 const storage='expanse.damage.seen.v1';
 let history=[];try{const stored=JSON.parse(sessionStorage.getItem(storage)||'[]');if(Array.isArray(stored))history=stored.filter(x=>typeof x==='string').slice(-256);}catch{}
 const seen=new Set(history);
 const alert=make('aside');alert.id='damage-alert';alert.hidden=true;alert.setAttribute('role','alert');alert.setAttribute('aria-live','assertive');alert.setAttribute('aria-atomic','true');
 alert.popover='manual';
 const heading=make('strong','You are being hurt'),message=make('span'),dismiss=make('button','Dismiss');dismiss.type='button';dismiss.setAttribute('aria-label','Dismiss damage notice');alert.append(heading,message,dismiss);document.body.append(alert);
 let active=null,timer=null;
 function remember(id){
  seen.add(id);history.push(id);while(history.length>256)seen.delete(history.shift());
  try{sessionStorage.setItem(storage,JSON.stringify(history));}catch{}
 }
 function raised(){
  if(alert.hidden)return;
  const modal=[...document.querySelectorAll('dialog[open]')].at(-1);
  const parent=modal||document.body;
  alert.inert=false;
  if(alert.parentElement!==parent){try{if(alert.matches(':popover-open'))alert.hidePopover();}catch{}parent.append(alert);}
  try{if(!alert.matches(':popover-open'))alert.showPopover();}catch{}
 }
 function hide(){alert.hidden=true;try{if(alert.matches(':popover-open'))alert.hidePopover();}catch{}}
 dismiss.onclick=hide;
 new MutationObserver(records=>{if(records.some(r=>r.type==='attributes'))raised();}).observe(document.body,{subtree:true,attributes:true,attributeFilter:['open']});
 function clear(){clearTimeout(timer);active=null;hide();window.ExpanseMap?.redraw();}
 function phrase(event){
  const source=event.source?.name||event.cause||'an unknown source';
  return event.text||('You take '+event.amount+' damage from '+source+'. HP '+event.hp+' / '+event.max_hp+'.');
 }
 function consume(event){
  if(!event||typeof event.event_id!=='string'||!Number.isFinite(event.amount)||event.amount<=0||seen.has(event.event_id))return;
  remember(event.event_id);
  const age=Number.isFinite(event.occurred_at)?Math.max(0,Date.now()/1000-event.occurred_at):0;
  const text=phrase(event),recent=age<=15;
  if(typeof append==='function')append('damage',(recent?'HURT · ':'Earlier damage · ')+text);
  else{const log=document.getElementById('log');if(log){const line=make('div',(recent?'HURT · ':'Earlier damage · ')+text);line.className='line damage';log.append(line);log.scrollTop=log.scrollHeight;}}
  if(!recent)return;
  active={...event,expires:performance.now()+12000};
  heading.textContent=event.hp<=0?'You have fallen':'You are being hurt';message.textContent=text;
  alert.hidden=false;raised();
  window.ExpansePlayerControls?.stopWalking();
  window.ExpanseMap?.redraw();
  clearTimeout(timer);timer=setTimeout(clear,12000);
 }
 function handle(packet){
  if(packet?.type==='damage'){consume(packet);return true;}
  if(packet?.type==='map')for(const event of packet.damage_events||[])consume(event);
  if(['character_required','saved_exit'].includes(packet?.type))clear();
  return false;
 }
 function draw(state,positions,point){
  if(state.options.designer)return;
  let badge=state.damageBadge;
  if(!badge){badge=make('div');badge.className='map-damage-notice';badge.hidden=true;badge.setAttribute('role','status');state.viewport.append(badge);state.damageBadge=badge;}
  const current=active&&active.expires>performance.now()&&(!active.player_id||active.player_id===state.packet?.character?.id)&&point;
  state.viewport.classList.toggle('is-hurt',!!current);
  badge.hidden=!current;
  if(!current)return;
  const label=active.source?.name||active.cause||'Unknown source';
  badge.textContent='−'+active.amount+' HP · '+label;
  badge.title=phrase(active);
  badge.style.left=Math.max(4,Math.min(state.viewport.clientWidth-badge.offsetWidth-4,point.x-badge.offsetWidth/2))+'px';
  badge.style.top=Math.max(4,Math.min(state.viewport.clientHeight-badge.offsetHeight-4,point.y-point.radius-badge.offsetHeight-7))+'px';
  const ctx=state.canvas.getContext('2d');ctx.save();
  ctx.strokeStyle='#ff6c72';ctx.lineWidth=3;ctx.strokeRect(point.x-point.radius-3,point.y-point.radius-3,point.radius*2+6,point.radius*2+6);
  const source=active.source_location&&positions.get(typeof active.source_location==='string'?active.source_location:active.source_location.id);
  if(source&&source!==point&&active.source?.id!==state.packet?.character?.id){ctx.strokeStyle='#ffd06a';ctx.lineWidth=3;ctx.strokeRect(source.x-source.radius,source.y-source.radius,source.radius*2,source.radius*2);ctx.fillStyle='#ffd06a';ctx.font='bold 12px system-ui';ctx.fillText('Attacker',Math.max(3,source.x-source.radius),Math.max(14,source.y-source.radius-5));}
  ctx.restore();
 }
 window.ExpanseDamage={handle,draw,clear};
})();
