/* Bounded, witnessed spell presentations. Game content and successful actions
 * come from the server; this module never creates an actor or sends a command. */
(()=>{
 'use strict';
 const styles=new Set(['glow','ground_rise','portal_rise','projectile','ward','burst','fade']);
 const active=new Map(),seen=new Set(),lastActors=new Map();
 let binding=null,delivered=0,cleanupTimer=null;
 const clock=()=>performance.now();
 const finite=(n,min,max)=>typeof n==='number'&&Number.isFinite(n)&&n>=min&&n<=max;
 const id=value=>typeof value==='string'&&value.length>0&&value.length<=256;
 const reduced=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)').matches===true;
 const redraw=()=>window.ExpanseMap?.redraw();
 function visible(){
  if(document.hidden)return false;
  for(const name of ['tab-game','play','player-map-panel']){
   const node=document.getElementById(name);
   if(node&&(node.hidden||node.style.display==='none'||(name==='tab-game'&&!node.classList.contains('active'))))return false;
  }
  return true;
 }
 function stop(){clearTimeout(cleanupTimer);cleanupTimer=null;active.clear();lastActors.clear();redraw();}
 function reset(){stop();binding=null;delivered=0;seen.clear();}
 function expire(){
  clearTimeout(cleanupTimer);cleanupTimer=null;
  const now=clock();for(const [key,event] of active)if(event.ends<=now)active.delete(key);
  for(const [key,point] of lastActors)if(point.until<=now)lastActors.delete(key);
  if(active.size)cleanupTimer=setTimeout(()=>{expire();redraw();},Math.max(1,Math.min(...[...active.values()].map(event=>event.ends-now))));
 }
 function context(packet){
  const session=packet?.magic_visuals?.session;
  const character=packet?.character?.id,room=packet?.location?.id||packet?.visual?.center;
  if(!id(session)||!id(character)||!id(room)||packet?.visual?.version!==1){reset();return;}
  const plane=JSON.stringify([packet.visual.context?.id,packet.visual.floor]);
  if(!binding||session!==binding.session||character!==binding.character){
   reset();binding={session,character,room,plane};
   // The server has already established the connection's history cursor.
   // A map immediately before a fresh event can include that event's sequence.
   // Never copy this map high-water mark into the delivered-event cursor.
  }else if(room!==binding.room||plane!==binding.plane){stop();binding.room=room;binding.plane=plane;}
  if(!visible())stop();
 }
 function presentation(value){
  return value&&value.version===1&&styles.has(value.style)&&Array.isArray(value.colors)
   &&value.colors.length>=1&&value.colors.length<=3&&value.colors.every(c=>typeof c==='string'&&/^#[0-9a-f]{6}$/i.test(c))
   &&Number.isInteger(value.duration_ms)&&finite(value.duration_ms,300,5000)&&finite(value.scale,.5,2)
   &&Number.isInteger(value.particles)&&finite(value.particles,0,24);
 }
 function receive(message){
  if(message?.type!=='visual_effect')return false;
  if(!binding||message.session!==binding.session||message.room_id!==binding.room
   ||(message.viewer_id!==undefined&&message.viewer_id!==binding.character))return true;
  if(!id(message.event_id)||!Number.isSafeInteger(message.sequence)||message.sequence<=delivered
   ||!id(message.source_id)||!Array.isArray(message.target_ids)||!message.target_ids.length||message.target_ids.length>128
   ||message.target_ids.some(target=>!id(target))||new Set(message.target_ids).size!==message.target_ids.length
   ||!presentation(message.presentation)||!finite(message.elapsed_ms,0,5000)
   ||(message.phase!==undefined&&!['departure','arrival'].includes(message.phase)))return true;
  const p=message.presentation,rise=p.style==='ground_rise'||p.style==='portal_rise';
  if(rise&&(!id(message.spawned_id)||!message.target_ids.includes(message.spawned_id)))return true;
  const key=message.session+'\n'+message.event_id;
  delivered=message.sequence;
  if(seen.has(key))return true;
  seen.add(key);if(seen.size>512)seen.delete(seen.values().next().value);
  // Hidden or expired effects are consumed, never queued for a later return.
  if(!visible()||message.elapsed_ms>=p.duration_ms)return true;
  const now=clock(),duration=reduced()?Math.min(900,p.duration_ms-message.elapsed_ms):p.duration_ms-message.elapsed_ms;
  active.set(key,{...message,presentation:{...p,colors:[...p.colors]},target_ids:[...message.target_ids],
   start:now-message.elapsed_ms,ends:now+duration,hadTargets:new Set(),retiredTargets:new Set(),seed:hash(key)});
  while(active.size>32)active.delete(active.keys().next().value);
  expire();redraw();return true;
 }
 function hash(text){let value=2166136261;for(const ch of text)value=Math.imul(value^ch.charCodeAt(0),16777619);return value>>>0;}
 function begin(state,placements,rooms){
  if(state.options.designer||!binding||state.packet?.magic_visuals?.session!==binding.session
   ||state.packet?.character?.id!==binding.character||!visible())return null;
  const now=clock(),tileSize=Math.round(24*state.zoom),actors=new Map(placements.filter(p=>id(p.actor.id)).map(p=>[p.actor.id,p]));
  for(const point of placements){
   const tile=rooms.get(point.room);
   if(!id(point.actor.id)||!tile)continue;
   lastActors.set(point.actor.id,{room:point.room,dx:(point.x-tile.x)/tileSize,dy:(point.y-tile.y)/tileSize,
    size:point.size/tileSize,until:now+5000});
  }
  while(lastActors.size>512)lastActors.delete(lastActors.keys().next().value);
  const rows=[],still=reduced();
  function target(event,ident,allowPrevious=false){
   const point=actors.get(ident);
   if(point&&point.room===event.room_id){event.hadTargets.add(ident);return point;}
   if(allowPrevious){
    const prior=lastActors.get(ident),tile=prior&&rooms.get(prior.room);
    if(prior&&prior.until>now&&prior.room===event.room_id&&tile)return {x:tile.x+prior.dx*tileSize,y:tile.y+prior.dy*tileSize,size:prior.size*tileSize,room:prior.room,previous:true};
   }
   return null;
  }
  for(const [key,event] of active){
   if(event.ends<=now){active.delete(key);continue;}
   const style=event.presentation.style,rise=style==='ground_rise'||style==='portal_rise';
   const source=target(event,event.source_id,style==='projectile'||style==='burst');
   const ids=rise?[event.spawned_id]:event.target_ids;
   for(const ident of ids){
    if(event.retiredTargets.has(ident))continue;
    const current=actors.get(ident),previousAllowed=['projectile','burst','fade'].includes(style);
    if(!previousAllowed&&event.hadTargets.has(ident)&&(!current||current.room!==event.room_id)){event.retiredTargets.add(ident);continue;}
    const point=target(event,ident,style==='projectile'||style==='burst'||style==='fade');
    if(!point)continue;
    if(style==='projectile'&&!source)continue;
    const progress=Math.max(0,Math.min(1,(now-event.start)/event.presentation.duration_ms));
    if(rows.length<128)rows.push({event,point,source,ident,progress,style});
   }
   // An absent newly spawned map row can arrive shortly afterward. An actor
   // that was already present and then left must not emerge a second time.
   if(rise&&event.retiredTargets.has(event.spawned_id))active.delete(key);
  }
  const frame={state,ctx:state.canvas.getContext('2d'),rows,still,tileSize,particles:0};
  if(rows.length&&!still)state.schedule();
  return frame;
 }
 const rgba=(color,alpha)=>color+Math.round(Math.max(0,Math.min(1,alpha))*255).toString(16).padStart(2,'0');
 function ring(ctx,x,y,rx,ry,color,alpha,width){
  ctx.beginPath();ctx.ellipse(x,y,Math.max(.25,rx),Math.max(.25,ry),0,0,Math.PI*2);
  ctx.strokeStyle=rgba(color,alpha);ctx.lineWidth=width;ctx.stroke();
 }
 function radius(frame,row){return Math.max(row.point.size*.7,frame.tileSize*.22)*row.event.presentation.scale;}
 function ground(frame){
  if(!frame)return;
  const c=frame.ctx;c.save();
  for(const row of frame.rows){
   if(!['ground_rise','portal_rise','ward'].includes(row.style))continue;
   const {point,progress,event}=row,p=event.presentation,r=radius(frame,row),foot=point.y+point.size*.45;
   const alpha=frame.still?.8:Math.min(1,progress*7,(1-progress)*6),opening=frame.still?1:Math.min(1,.25+progress*4);
   if(row.style==='portal_rise'){
    c.fillStyle=rgba(p.colors[0],alpha*.45);c.beginPath();c.ellipse(point.x,foot,r*opening,r*.3*opening,0,0,Math.PI*2);c.fill();
    ring(c,point.x,foot,r*opening,r*.3*opening,p.colors[1]||p.colors[0],alpha,Math.max(1,frame.state.zoom));
   }else if(row.style==='ground_rise'){
    c.strokeStyle=rgba(p.colors[0],alpha);c.lineWidth=Math.max(1,frame.state.zoom);c.beginPath();
    for(let n=0;n<5;n++){const x=point.x-r+n*r*.5;c.moveTo(x,foot);c.lineTo(x+r*.16,foot-r*.15);c.lineTo(x+r*.25,foot+r*.05);}c.stroke();
   }else ring(c,point.x,foot,r,r*.28,p.colors[0],alpha*.8,Math.max(1,frame.state.zoom));
  }
  c.restore();
 }
 function actor(frame,point,paint){
  if(!frame||frame.still)return false;
  const row=frame.rows.find(row=>row.ident===point.actor.id&&['ground_rise','portal_rise'].includes(row.style));
  if(!row)return false;
  const c=frame.ctx,size=point.size,foot=point.y+size*.5,t=Math.min(1,row.progress/.82),ease=1-(1-t)**2;
  c.save();c.beginPath();c.rect(point.x-size*1.4,point.y-size*1.4,size*2.8,size*1.9);c.clip();
  c.translate(point.x,foot+size*(1-ease)*.7);
  if(row.style==='ground_rise'){
   // The actual sprite first pulls forward close to the ground, then stands.
   c.rotate((1-ease)*-.9);c.scale(1,.42+.58*ease);
   const crawl=Math.sin(t*Math.PI*4)*(1-ease)*size*.08;
   paint(c,point.actor,crawl,-size*.5,size,point.self);
  }else paint(c,point.actor,0,-size*.5,size,point.self);
  c.restore();return true;
 }
 function particles(frame,row,x,y,r,alpha){
  if(frame.still)return;
  const c=frame.ctx,p=row.event.presentation,count=Math.min(p.particles,Math.max(0,256-frame.particles));
  frame.particles+=count;
  for(let n=0;n<count;n++){
   const angle=(n*2.399963+row.event.seed*.00001)%(Math.PI*2),phase=(row.progress+n/Math.max(count,1))%1;
   const distance=r*(.45+phase*.8),xx=x+Math.cos(angle)*distance;
   const yy=y+Math.sin(angle)*r*.55-phase*r*.9,s=Math.max(1,frame.state.zoom*.75);
   c.fillStyle=rgba(p.colors[(n+1)%p.colors.length],alpha*(1-phase)*.85);c.fillRect(xx-s/2,yy-s/2,s,s);
  }
 }
 function front(frame){
  if(!frame)return;
  const c=frame.ctx;c.save();
  for(const row of frame.rows){
   const {point,progress,event,style}=row,p=event.presentation,r=radius(frame,row);
   const alpha=frame.still?.75:Math.max(0,Math.min(1,progress*8,(1-progress)*4));
   if(style==='glow'){
    const pulse=frame.still?1:1+Math.sin(progress*Math.PI*2)*.12;
    c.fillStyle=rgba(p.colors[0],alpha*.13);c.beginPath();c.ellipse(point.x,point.y,r*pulse,r*1.15*pulse,0,0,Math.PI*2);c.fill();
    ring(c,point.x,point.y,r*pulse,r*1.15*pulse,p.colors[1]||p.colors[0],alpha*.85,Math.max(1,frame.state.zoom));
   }else if(style==='ward'){
    c.strokeStyle=rgba(p.colors[1]||p.colors[0],alpha);c.lineWidth=Math.max(1,frame.state.zoom);c.beginPath();
    c.moveTo(point.x-r,point.y-r*.65);c.lineTo(point.x,point.y-r);c.lineTo(point.x+r,point.y-r*.65);
    c.lineTo(point.x+r*.75,point.y+r*.5);c.lineTo(point.x,point.y+r);c.lineTo(point.x-r*.75,point.y+r*.5);c.closePath();c.stroke();
   }else if(style==='projectile'){
    const t=frame.still?1:Math.min(1,progress/.7),source=row.source;
    const x=source.x+(point.x-source.x)*t,y=source.y+(point.y-source.y)*t-Math.sin(t*Math.PI)*Math.min(frame.tileSize*.5,Math.hypot(point.x-source.x,point.y-source.y)*.15);
    if(!frame.still&&t<1){c.strokeStyle=rgba(p.colors[0],alpha*.35);c.lineWidth=Math.max(1,frame.state.zoom);c.beginPath();c.moveTo(source.x+(x-source.x)*.75,source.y+(y-source.y)*.75);c.lineTo(x,y);c.stroke();}
    ring(c,x,y,Math.max(2,r*.23),Math.max(2,r*.23),p.colors[1]||p.colors[0],alpha,Math.max(1,frame.state.zoom*1.2));
    particles(frame,row,x,y,r*.5,alpha);continue;
   }else if(style==='burst'){
    const spread=frame.still?.7:.25+progress;c.strokeStyle=rgba(p.colors[0],alpha);c.lineWidth=Math.max(1,frame.state.zoom);c.beginPath();
    for(let n=0;n<8;n++){const angle=n*Math.PI/4;c.moveTo(point.x+Math.cos(angle)*r*spread*.4,point.y+Math.sin(angle)*r*spread*.4);c.lineTo(point.x+Math.cos(angle)*r*spread,point.y+Math.sin(angle)*r*spread);}c.stroke();
   }else if(style==='fade'){
    const spread=frame.still?1:event.phase==='arrival'?1.5-progress*.5:1+progress*.5;
    ring(c,point.x,point.y,r*spread,r*spread,p.colors[0],alpha*.8,Math.max(1,frame.state.zoom));
   }
   else if(frame.still)ring(c,point.x,point.y+point.size*.45,r,r*.3,p.colors[1]||p.colors[0],alpha,Math.max(1,frame.state.zoom));
   else if(style==='portal_rise'){
    c.strokeStyle=rgba(p.colors[1]||p.colors[0],alpha);c.lineWidth=Math.max(1,frame.state.zoom*1.2);c.beginPath();c.ellipse(point.x,point.y+point.size*.45,r,r*.3,0,0,Math.PI);c.stroke();
   }
   particles(frame,row,point.x,point.y,r,alpha);
  }
  c.restore();
 }
 function visibility(){if(!visible())stop();}
 document.addEventListener('visibilitychange',visibility);
 for(const name of ['play','tab-game','player-map-panel']){
  const node=document.getElementById(name);if(node)new MutationObserver(visibility).observe(node,{attributes:true,attributeFilter:['hidden','style','class']});
 }
 window.addEventListener('pagehide',reset);window.addEventListener('expanse:world-assets',reset);
 window.matchMedia?.('(prefers-reduced-motion: reduce)').addEventListener?.('change',()=>{if(reduced())stop();else redraw();});
 window.ExpanseMapEffects={receive,context,reset,begin,ground,actor,front};
})();
