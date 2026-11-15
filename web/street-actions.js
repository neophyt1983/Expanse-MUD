(()=>{
 'use strict';
 const create=(tag,text)=>Object.assign(document.createElement(tag),{textContent:text||''});
 function send(cmd,label){
   if(typeof act==='function')act(cmd,label);
   else if(window.expanseAtlasSend?.(cmd))append('user','> '+label);
 }
 window.addEventListener('expanse:build-room-content',({detail:{packet,content,keyed}})=>{
   const rows=packet.location;
   if(!rows)return;
   for(const [title,items] of [['Expeditions and civic life',rows.field_actions],['Gathering',rows.gathering],['Carriage stand',rows.services?.filter(r=>r.command.startsWith('carriage '))],['Public events',rows.services?.filter(r=>r.command.startsWith('attend '))]]){
     if(!items?.length)continue;
     const box=create('details'),summary=create('summary',title+' ('+items.length+')');
     box.open=title==='Gathering';box.append(keyed(summary,'local summary',title));
     for(const r of items){
       const action=r.actions?.[0]||r,line=create('div'),b=create('button',action.action||action.label);
       b.className='ed-btn';b.disabled=!!action.disabled;b.type='button';b.onclick=()=>send(action.command,b.textContent+' · '+r.label);
       line.append(create('strong',r.label),create('p',r.detail),b);box.append(keyed(line,'local activity',r.id));
     }
     content.prepend(keyed(box,'local services',title));
   }
 });
 let dialog,marker;
 const open=d=>window.PhonePopups?PhonePopups.open(d):d.showModal();
 const close=d=>window.PhonePopups?PhonePopups.finish(d):d.close();
 function choices(packet){
   const inside=packet.visual.context?.kind==='building';
   const rows=packet.visual.passages||(packet.visual.exits||[]).filter(e=>e.kind!=='path'||!e.target).map(e=>({
     direction:e.direction,label:e.name||e.direction,blocked:e.blocked
   }));
   return rows.map(r=>{
     if(['entry','exit','stairs','passage'].includes(r.kind)&&!(inside&&r.kind==='entry'))return r;
     const d=r.direction;
     if(inside&&(d==='step outside'||d==='out'))return {...r,kind:'exit',label:r.label.startsWith('Exit')?r.label:'Exit building'};
     if(!inside&&(d==='enter building'||d==='in'||d.startsWith('unit ')))return {...r,kind:'entry',label:r.label.startsWith('Enter')?r.label:'Enter building'};
     return {...r,kind:['up','down'].includes(d)?'stairs':'passage',label:inside?r.label.replace(/^Enter\b/i,'Go to'):r.label};
   });
 }
 function choose(title,actions){
   if(!dialog){dialog=create('dialog');dialog.id='street-passage';dialog.className='style-dialog';document.body.append(dialog);}
   if(dialog.open)return;
   dialog.setAttribute('aria-label',title);dialog.replaceChildren(create('h2',title));
   for(const a of actions){
     const b=create('button',a.label+(a.blocked?' · '+a.blocked:''));b.type='button';b.disabled=!!a.blocked;
     b.onclick=()=>{close(dialog);a.run();};dialog.append(b);
   }
   if(!window.PhonePopups){const b=create('button','Close');b.onclick=()=>close(dialog);dialog.append(b);}
   open(dialog);
 }
 function passages(s){
   const origin=s.data.center;
   const rows=choices(s.packet);
   return rows.map(r=>({...r,run:()=>{if(s.packet.location.id===origin)window.ExpansePlayerControls?.move('go '+r.direction);}}));
 }
 function select(s,tile){
   if(tile.scenery)return true;
   if(tile.current){
     const rows=passages(s);if(!rows.length)return false;
     if(rows.length===1&&!rows[0].blocked)rows[0].run();else choose('Passages at '+s.packet.location.name,rows);
     return true;
   }
   if(s.data.context?.kind!=='building'&&tile.exterior&&Array.isArray(s.packet.visual.passages)){choose('Building entrance',[{label:'Enter '+tile.name,run:()=>window.ExpansePlayerControls.walkTo(tile.id)}]);return true;}
   return false;
 }
 function accessibleTiles(s,center){
   if(!s.tileTargets){
     s.tileTargets=create('div');s.tileTargets.className='map-tile-targets';
     s.tileTargets.setAttribute('role','group');s.tileTargets.setAttribute('aria-label','Local map tiles');
     s.viewport.append(s.tileTargets);s.targetButtons=new Map();
   }
   const visible=new Set(),origin=center.tile;
   for(const pos of s.positions){
     const t=pos.tile;visible.add(t.id);let b=s.targetButtons.get(t.id);
     if(!b){b=create('button');b.type='button';b.className='map-tile-target';s.tileTargets.append(b);s.targetButtons.set(t.id,b);}
     const dx=t.x-origin.x,dy=t.y-origin.y,where=t.current?'Your tile':[dy<0?'north':dy>0?'south':'',dx<0?'west':dx>0?'east':''].filter(Boolean).join(' ');
     const blocked=(s.data.exits||[]).find(e=>e.target===t.id&&e.blocked)?.blocked;
     const name=t.current||t.visited||t.exterior||Array.isArray(t.roof_joins)?t.name:(t.terrain||'Terrain');
     const passage=t.current?choices(s.packet).map(a=>a.label).join(', '):'';
     const label=[where,name,passage,blocked].filter(Boolean).join(' · ');
     if(b.getAttribute('aria-label')!==label)b.setAttribute('aria-label',label);
     b.dataset.room=t.id;b.dataset.bearing=where;b.disabled=!!blocked||!!t.scenery;b.title=blocked||label;b.style.width=b.style.height=(2*pos.radius)+'px';b.style.left=(pos.x-pos.radius)+'px';b.style.top=(pos.y-pos.radius)+'px';
     b.onclick=()=>{if(!select(s,t)&&!t.current)window.ExpansePlayerControls?.walkTo(t.id);};
   }
   for(const [id,b] of s.targetButtons)if(!visible.has(id)){b.remove();s.targetButtons.delete(id);}
 }
 function draw(s,point){
   if(s.options.designer||s.canvas.closest('#player-visual-map')===null)return;
   if(point)accessibleTiles(s,point);
   if(!marker){
     marker=create('button');marker.className='tile-passage';marker.type='button';
     marker.onpointerdown=e=>{if(e.button===0)marker.pressedPassage=marker.passageContext;};
     marker.onpointercancel=()=>{marker.pressedPassage=null;};
     marker.onkeydown=e=>{if(e.key==='Enter'||e.key===' ')marker.pressedPassage=null;};
   }
   const actions=choices(s.packet);marker.hidden=!actions.length||!point;
   marker.passageContext=JSON.stringify([s.packet.character?.id,s.packet.location.id,actions.map(a=>[a.direction,a.kind,a.blocked||''])]);
   if(marker.hidden)return;
   if(marker.parentElement!==s.viewport)s.viewport.append(marker);
   const primary=actions.find(r=>r.kind==='exit')||actions.find(r=>r.kind==='entry')||actions[0];
   const labels={exit:'↗ Exit',entry:'⌂ Enter',stairs:primary.direction==='up'?'↑ Stairs':'↓ Stairs'};
   const multiple=actions.length>1;
   marker.textContent=multiple?'Ways out':(labels[primary.kind]||'Ways out');
   marker.title=multiple?actions.map(a=>a.label).join(' · '):primary.label;
   marker.style.maxWidth=Math.max(74,point.radius*2)+'px';
   marker.style.overflow='hidden';
   marker.setAttribute('aria-label',multiple?'Choose a passage · '+marker.title:primary.label);
   marker.style.left=point.x+'px';marker.style.top=(point.y+point.radius*.78)+'px';
   marker.disabled=actions.every(a=>a.blocked);
   marker.onclick=()=>{
     const pressed=marker.pressedPassage;marker.pressedPassage=null;
     if(pressed&&pressed!==marker.passageContext){s.inspect.textContent='Your location or passage changed. Select the passage again.';return;}
     select(s,point.tile);
   };
 }
 function roof(c,t,x,y,size){
   if(!Array.isArray(t.roof_joins))return;
   const sides=t.roof_joins,edge=Math.max(2,Math.round(size*.08));
   c.fillStyle='#926648';c.fillRect(x,y,size,size);
   const interval=Math.max(4,Math.round(size/4));
   c.fillStyle='#78523e';
   for(let j=0;j<4;j++){c.fillRect(x,y+j*interval,size,1);c.fillRect(x+(j%2?interval:2*interval),y+j*interval,1,interval);}
   c.fillStyle='#483b32';
   if(!sides.includes('north'))c.fillRect(x,y,size,edge);
   if(!sides.includes('south'))c.fillRect(x,y+size-edge,size,edge);
   if(!sides.includes('west'))c.fillRect(x,y,edge,size);
   if(!sides.includes('east'))c.fillRect(x+size-edge,y,edge,size);
 }
 window.ExpanseStreet={draw,select,roof};
})();
