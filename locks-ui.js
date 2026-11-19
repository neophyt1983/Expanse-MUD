/* Physical fixtures belong to the current room, not a remote/global lock list. */
(()=>{'use strict';
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};let sequence=0,scope=null;const drafts=new Map();
 window.addEventListener('expanse:build-room-content', event=>{
  const {packet:m,content,keyed}=event.detail;
  if(!m.character||!m.location)return;
  const current=JSON.stringify([m.media_world||'',m.character.id,m.location.id]);if(current!==scope){scope=current;drafts.clear();}
  const section=node('section');section.id='physical-lock-actions';const rows=m.locks||[],staff=m.locksmiths||[];if(!rows.length&&!staff.length)return;
  const warningIds=new Map(rows.filter(row=>row.permitted===false).map((row,index)=>[row.id,'lock-permission-'+index]));
  section.append(keyed(node('h3','Containers, locks and locksmiths'),'lock heading'),node('p','Your lockpicking skill: '+(m.lock_skill||0)+'/100'));
  function button(label,action,row,npc,extra){const b=node('button',label);b.type='button';b.className='ed-btn';if(warningIds.has(row?.id)&&['take','take_item','put_item','pick'].includes(action))b.setAttribute('aria-describedby',warningIds.get(row.id));b.onclick=()=>{if(typeof ws==='undefined'||!ws||ws.readyState!==1){append('error','Reconnect before using a container or lock.');return;}const fields=extra?extra():{};if(!fields)return;const packet={command:'locks action',lock_ui:true,sequence:++sequence,actor_id:m.character.id,room:m.location.id,action,...fields};if(row){packet.target=row.id;packet.locked=row.locked;}if(npc){packet.npc=npc.id;packet.fee=action==='lesson'?npc.lesson_fee:npc.fee;}try{ws.send(JSON.stringify(packet));}catch{append('error','The action was not sent. Reconnect and try again.');}};return b;}
  function transfer(card,row,action,items){
   const choices=(Array.isArray(items)?items:[]).filter(item=>item&&typeof item.id==='string'&&Number.isSafeInteger(item.count)&&item.count>0&&item.movable!==false);
   if(!choices.length){if(action==='put_item'&&!row.practice)card.append(node('p','No unequipped, movable inventory items to put inside.'));return;}
   const key=row.id+'|'+action,old=drafts.get(key)||{},selected=choices.find(item=>item.id===old.id)||choices[0];
   const draft={id:selected.id,quantity:old.id===selected.id?old.quantity??'1':'1'};drafts.set(key,draft);
   const takeVerb=row.permitted===false?'Steal':'Take';
   const controls=node('div'),itemLabel=node('label',action==='take_item'?takeVerb+' an item ':'Put an inventory item '),pick=node('select');
   controls.className='container-transfer-controls';controls.style.cssText='display:flex;flex-wrap:wrap;gap:6px;align-items:end;margin:8px 0';
   itemLabel.style.cssText='flex:1 1 12rem;min-width:0';pick.style.cssText='display:block;width:100%;min-width:0;box-sizing:border-box';
   pick.setAttribute('aria-label',(action==='take_item'?'Item to '+takeVerb.toLowerCase()+' from ':'Item to put in ')+row.name);
   for(const item of choices)pick.append(new Option(item.name+' × '+item.count,item.id));pick.value=selected.id;itemLabel.append(keyed(pick,'container item',row.id,action));
   const quantityLabel=node('label',action==='take_item'&&row.permitted===false?'Maximum quantity ':'Quantity '),quantity=node('input');quantity.type='number';quantity.min='1';quantity.step='1';quantity.max=String(selected.count);quantity.value=draft.quantity;
   quantityLabel.style.cssText='flex:0 1 5rem;min-width:0';quantity.style.cssText='display:block;width:100%;min-width:0;box-sizing:border-box';quantity.setAttribute('aria-label',(action==='take_item'?'Quantity to take from ':'Quantity to put in ')+row.name);
   quantityLabel.append(keyed(quantity,'container quantity',row.id,action));
   pick.onchange=()=>{const item=choices.find(item=>item.id===pick.value);draft.id=pick.value;draft.quantity='1';quantity.value='1';quantity.max=String(item?.count||1);};quantity.oninput=()=>{draft.quantity=quantity.value;};
   const commit=button(action==='take_item'?takeVerb+' selected':'Put inside',action,row,null,()=>{
    const item=choices.find(item=>item.id===pick.value),count=Number(quantity.value);
    if(!item||!Number.isSafeInteger(count)||count<1||count>item.count){append('error','Choose a whole quantity between 1 and '+(item?.count||0)+'.');quantity.focus();return null;}
    return {item_id:item.id,quantity:count,expected_count:item.count};
   });commit.style.minHeight='40px';controls.append(itemLabel,quantityLabel,keyed(commit,'container transfer',row.id,action));card.append(controls);
  }
  for(const row of rows){const card=node('div');card.className='action-card';card.append(node('strong',row.name+' · '+(row.locked?'locked':'unlocked')),button('Inspect','inspect',row));
   if(row.permitted===false){const warning=node('p',row.permission_warning||(row.kind==='door'?'You do not have permission to alter this lock. Picking it may be reported as lock tampering.':'Taking items from this container without permission is theft. Witnesses may report it.'));warning.id=warningIds.get(row.id);warning.className='lock-permission-warning';card.append(warning);}
   if(row.burglary){const odds=row.burglary;card.append(node('p','Burgling '+odds.level+'/100 · Chance to take one item: '+Math.round(odds.success_chance*100)+'% · Observation risk: '+odds.detection_risk+'. Larger grabs are harder and easier to notice; skill limits how much you take.'));if(odds.cooldown_remaining)card.append(node('p','Wait '+odds.cooldown_remaining+' game minute(s) before another theft attempt.'));}
   if(row.locked){if(row.has_key)card.append(button('Unlock with key','unlock',row));if(row.pickable)card.append(button('Pick lock','pick',row));for(const npc of staff.filter(n=>n.available&&n.locksmith)){const b=button('Ask '+npc.name+' to unlock ('+npc.fee+' gold)','service',row,npc);b.disabled=!row.permitted;card.append(b);}}
   else{if(row.has_key)card.append(button('Lock with key','lock',row));if(row.practice)card.append(button('Reset practice lock','reset',row));if(row.kind==='container'){
    const takeAll=button(row.permitted===false?'Steal contents':'Take contents','take',row);card.append(button('Look inside','open',row),takeAll);
    if(Array.isArray(row.contents)){
     const total=row.contents.reduce((sum,item)=>sum+(Number.isSafeInteger(item.count)?item.count:0),0);
     card.append(node('p',total?'Contains '+total+' item'+(total===1?'':'s')+'.':'This container is empty.'));
     takeAll.disabled=!total||row.contents.some(item=>item.movable===false);
     for(const item of row.contents.filter(item=>item.movable===false))card.append(node('p',item.name+' · '+item.reason));
     transfer(card,row,'take_item',row.contents);transfer(card,row,'put_item',row.deposit_items);
    }
   }}
   section.append(keyed(card,'lock',row.id));
  }
  for(const npc of staff){const card=node('div');card.className='action-card';card.append(node('strong',npc.name),node('p',(npc.available?'On duty':'Off duty')+' · '+npc.hours));if(npc.trainer){const kit=button('Ask for introductory picks','kit',null,npc),lesson=button('Lockpicking lesson ('+npc.lesson_fee+' gold)','lesson',null,npc);kit.disabled=lesson.disabled=!npc.available;card.append(kit,lesson,node('p','One lesson per world day. Empty practice locks can be reset; practice improves skill within their difficulty.'));}section.append(keyed(card,'locksmith',npc.id));}
  content.append(section);
 });
})();
