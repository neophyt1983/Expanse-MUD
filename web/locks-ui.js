/* Physical fixtures belong to the current room, not a remote/global lock list. */
(()=>{'use strict';
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};let sequence=0;
 window.addEventListener('expanse:build-room-content', event=>{
  const {packet:m,content,keyed}=event.detail;
  const section=node('section');section.id='physical-lock-actions';const rows=m.locks||[],staff=m.locksmiths||[];if(!rows.length&&!staff.length)return;
  section.append(keyed(node('h3','Locks and locksmiths'),'lock heading'),node('p','Your lockpicking skill: '+(m.lock_skill||0)+'/100'));
  function button(label,action,row,npc){const b=node('button',label);b.type='button';b.className='ed-btn';b.onclick=()=>{if(!ws||ws.readyState!==1){append('error','Reconnect before using a lock.');return;}const packet={command:'locks action',lock_ui:true,sequence:++sequence,actor_id:m.character.id,room:m.location.id,action};if(row){packet.target=row.id;packet.locked=row.locked;}if(npc){packet.npc=npc.id;packet.fee=action==='lesson'?npc.lesson_fee:npc.fee;}ws.send(JSON.stringify(packet));};return b;}
  for(const row of rows){const card=node('div');card.className='action-card';card.append(node('strong',row.name+' · '+(row.locked?'locked':'unlocked')),button('Inspect','inspect',row));
   if(!row.permitted)card.append(node('p','Private property: tampering or taking contents may be noticed.'));
   if(row.locked){if(row.has_key)card.append(button('Unlock with key','unlock',row));if(row.pickable)card.append(button('Pick lock','pick',row));for(const npc of staff.filter(n=>n.available&&n.locksmith)){const b=button('Ask '+npc.name+' to unlock ('+npc.fee+' gold)','service',row,npc);b.disabled=!row.permitted;card.append(b);}}
   else{if(row.has_key)card.append(button('Lock with key','lock',row));if(row.practice)card.append(button('Reset practice lock','reset',row));if(row.kind==='container')card.append(button('Look inside','open',row),button('Take contents','take',row));}
   section.append(keyed(card,'lock',row.id));
  }
  for(const npc of staff){const card=node('div');card.className='action-card';card.append(node('strong',npc.name),node('p',(npc.available?'On duty':'Off duty')+' · '+npc.hours));if(npc.trainer){const kit=button('Ask for introductory picks','kit',null,npc),lesson=button('Lockpicking lesson ('+npc.lesson_fee+' gold)','lesson',null,npc);kit.disabled=lesson.disabled=!npc.available;card.append(kit,lesson,node('p','One lesson per world day. Empty practice locks can be reset; practice improves skill within their difficulty.'));}section.append(keyed(card,'locksmith',npc.id));}
  content.append(section);
 });
})();
