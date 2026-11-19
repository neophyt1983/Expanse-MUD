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
 let dialog,marker,dialogStatus,menu,lastView,movementFeedback;
 const open=d=>window.PhonePopups?PhonePopups.open(d):d.showModal();
 const close=d=>window.PhonePopups?PhonePopups.finish(d):d.close();
 const visible=d=>d&&(window.PhonePopups?.visible?PhonePopups.visible(d):d.open);
 const context=s=>JSON.stringify([s.packet.character?.id,s.packet.location.id]);
 const movementObserver=new MutationObserver(()=>{
   const pending=movementFeedback;if(!pending)return;
   const message=pending.source.textContent;
   if(message===pending.message)return;
   stopMovementFeedback();
   if(pending.s.packet?.visual&&context(pending.s)===pending.origin)
     feedback(pending.s,message||'Ready. Choose a passage again.');
 });
 function stopMovementFeedback(){movementObserver.disconnect();movementFeedback=null;}
 function rejectedMovement(s){
   stopMovementFeedback();
   const source=document.getElementById('movement-status');
   feedback(s,source?.textContent||'Movement is not ready. Try again after the current step finishes.');
   if(source){
     movementFeedback={s,source,origin:context(s),message:source.textContent};
     movementObserver.observe(source,{childList:true,characterData:true,subtree:true});
   }
 }
 function feedback(s,message){
   s.inspect.textContent=message;
   if(!s.passageStatus){
     s.passageStatus=create('div');s.passageStatus.className='atlas-passage-status';
     s.passageStatus.setAttribute('role','status');s.passageStatus.setAttribute('aria-live','polite');
     (s.locationStatus?.parentElement||s.viewport).append(s.passageStatus);
   }
   s.passageStatus.textContent=message;s.passageStatus.hidden=!message;
   if(visible(dialog)&&dialogStatus){dialogStatus.textContent=message;dialogStatus.hidden=!message;}
 }
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
 function choose(title,actions,message=''){
   if(!dialog){dialog=create('dialog');dialog.id='street-passage';dialog.className='style-dialog';document.body.append(dialog);}
   const wasOpen=visible(dialog);
   // The optional phone adapter moves children into its own popup. Return them
   // before rebuilding so an already-open phone menu cannot retain old actions.
   if(wasOpen&&window.PhonePopups)close(dialog);
   dialog.setAttribute('aria-label',title);dialog.replaceChildren(create('h2',title));
   dialogStatus=create('p',message);dialogStatus.setAttribute('role','status');dialogStatus.hidden=!message;dialog.append(dialogStatus);
   for(const a of actions){
     const b=create('button',a.label+(a.blocked?' · '+a.blocked:''));b.type='button';b.disabled=!!a.blocked;
     b.onclick=()=>{if(a.run()!==false)close(dialog);};dialog.append(b);
   }
   if(!actions.length)dialog.append(create('p','There are no special passages here. Use the map to walk to a nearby tile.'));
   if(!window.PhonePopups){const b=create('button','Close');b.onclick=()=>close(dialog);dialog.append(b);}
   if(!wasOpen||window.PhonePopups)open(dialog);
 }
 function passages(s){
   const origin=context(s);
   const rows=choices(s.packet);
   return rows.map(r=>({...r,run:()=>{
     if(!s.packet?.visual||!s.data){reset();return false;}
     if(context(s)!==origin){refreshMenu(s,'Your location changed. Choose a route from your current room.');return false;}
     const current=choices(s.packet).find(a=>a.direction===r.direction&&a.kind===r.kind);
     if(!current||current.label!==r.label||current.blocked){refreshMenu(s,current?.blocked||'That passage changed. Choose an available route.');return false;}
     const accepted=window.ExpansePlayerControls?.move('go '+r.direction)===true;
     if(accepted){stopMovementFeedback();feedback(s,'');}else rejectedMovement(s);
     return accepted;
   }}));
 }
 function refreshMenu(s,message=''){
   const rows=passages(s);
   menu={s,signature:JSON.stringify([context(s),choices(s.packet)])};
   const title=(s.data.context?.kind==='building'?'Passages':'Routes')+' at '+s.packet.location.name;
   choose(title,rows,message);if(message)feedback(s,message);
 }
 function select(s,tile){
   if(!s.packet?.visual||!s.data){reset();return true;}
   if(tile.scenery)return true;
   if(tile.current){
     const rows=passages(s);if(!rows.length)return false;
     if(rows.length===1&&!rows[0].blocked){if(!rows[0].run())refreshMenu(s,s.passageStatus?.textContent||'');}
     else refreshMenu(s);
     return true;
   }
   if(s.data.context?.kind!=='building'&&tile.exterior&&Array.isArray(s.packet.visual.passages)){menu=null;choose('Building entrance',[{label:'Enter '+tile.name,run:()=>window.ExpansePlayerControls.walkTo(tile.id)}]);return true;}
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
   lastView=s;
   if(point)accessibleTiles(s,point);
   if(!marker){
     marker=create('button');marker.className='tile-passage';marker.type='button';
     marker.onpointerdown=e=>{if(e.button===0)marker.pressedPassage=marker.passageContext;};
     marker.onpointercancel=()=>{marker.pressedPassage=null;};
     marker.onkeydown=e=>{if(e.key==='Enter'||e.key===' ')marker.pressedPassage=null;};
   }
   const actions=choices(s.packet);marker.hidden=!actions.length||!point;
   const here=context(s);
   if(s.passageContext!==here){if(movementFeedback?.s===s)stopMovementFeedback();if(s.passageStatus)s.passageStatus.hidden=true;s.passageContext=here;}
   if(menu?.s===s&&visible(dialog)&&menu.signature!==JSON.stringify([here,actions]))
     refreshMenu(s,'Your location or available routes changed. Choose a current route.');
   marker.passageContext=JSON.stringify([s.packet.character?.id,s.packet.location.id,actions.map(a=>[a.direction,a.kind,a.label,a.blocked||''])]);
   if(marker.hidden)return;
   if(marker.parentElement!==s.viewport)s.viewport.append(marker);
   const primary=actions.find(r=>r.kind==='exit')||actions.find(r=>r.kind==='entry')||actions[0];
   const labels={exit:'↗ Exit',entry:'⌂ Enter',stairs:primary.direction==='up'?'↑ Stairs':'↓ Stairs'};
   const multiple=actions.length>1;
   const inside=s.data.context?.kind==='building';
   marker.textContent=inside&&primary.kind==='exit'?'↗ Exit'+(multiple?'…':''):
     multiple?(inside?'Passages':'Routes'):(labels[primary.kind]||(inside?'Passage':'Route'));
   marker.title=actions.map(a=>a.label+(a.blocked?' · '+a.blocked:'')).join(' · ');
   marker.style.maxWidth=Math.max(74,point.radius*2)+'px';
   marker.style.overflow='hidden';
   marker.setAttribute('aria-label',multiple?'Choose a passage · '+marker.title:primary.label);
   marker.style.left=point.x+'px';marker.style.top=(point.y+point.radius*.78)+'px';
   // A blocked exit still opens its explanation instead of becoming a dead control.
   marker.disabled=false;
   marker.onclick=()=>{
     const pressed=marker.pressedPassage;marker.pressedPassage=null;
     if(pressed&&pressed!==marker.passageContext){feedback(s,'Your location or passage changed. Select the passage again.');return;}
     select(s,point.tile);
   };
 }
 function reset(){
   stopMovementFeedback();
   menu=null;
   if(visible(dialog))close(dialog);
   if(marker){marker.hidden=true;marker.pressedPassage=null;marker.onclick=null;}
   if(lastView){
     if(lastView.passageStatus){lastView.passageStatus.hidden=true;lastView.passageStatus.textContent='';}
     lastView.tileTargets?.replaceChildren();lastView.targetButtons?.clear();lastView.passageContext=null;
   }
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
 window.ExpanseStreet={draw,select,roof,reset};
})();
