/* Local guild services use host quotes; the browser never completes a task. */
(()=>{'use strict';
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const owner=m=>JSON.stringify([m?.visual?.travel_world||'',m?.character?.id||'',m?.location?.id||'']);
 let latest=null,scope='',sequence=0,pending=null,timer=null;
 const feedback=new Map(),statusNodes=new Map(),controls=[];
 const guild=id=>latest?.guilds?.guilds?.find(g=>g.id===id);
 const offer=(g,action,id)=>action==='join'?g?.join:(action==='learn'?g?.lessons:g?.quests)?.find(row=>row.id===id);
 const permission=(o,action)=>action==='join'||action==='learn'?o:o?.[action];
 function status(id,text){feedback.set(id,text);const e=statusNodes.get(id);if(e){e.textContent=text;e.hidden=!text;}}
 function refreshButtons(){for(const {button,enabled} of controls)button.disabled=!!pending||!enabled;}
 function send(gid,action,oid,original,here){
  if(scope!==here||pending)return;
  const g=guild(gid),o=offer(g,action,oid),permit=permission(o,action);
  if(!g||!o||JSON.stringify(o)!==original){status(gid,'This offer changed. Read the updated terms before choosing again.');return;}
  if(!permit?.enabled){status(gid,permit?.reason||'That action is not currently available.');return;}
  if(typeof ws==='undefined'||!ws||ws.readyState!==1){status(gid,'Reconnect before using guild services.');return;}
  const id='guild-'+(++sequence),packet={command:'guild action',guild_ui:true,action,sequence,request_id:id,
   actor_id:latest.character.id,room:latest.location.id,guild_id:gid};
  if(oid!==undefined)packet.offer_id=oid;
  if(o.revision!==undefined&&o.revision!==null)packet.revision=o.revision;
  pending={id,gid,scope};status(gid,'Waiting for the guild’s response…');refreshButtons();
  try{ws.send(JSON.stringify(packet));}
  catch{pending=null;status(gid,'The request was not sent. Reconnect and try again.');refreshButtons();return;}
  if(typeof append==='function')append('user','> '+({join:'Join',learn:'Learn',accept:'Accept',complete:'Contribute to / complete'}[action])+' · '+(o.name||g.name));
  timer=setTimeout(()=>{if(pending?.id!==id)return;pending=null;status(gid,'The result has not been confirmed. Check Conversation and the current guild offer before trying again.');refreshButtons();},15000);
 }
 function actionButton(parent,g,action,o,label){
  const permit=permission(o,action),button=node('button',label);button.type='button';button.className='ed-btn';
  button.disabled=!!pending||!permit?.enabled;
  const here=scope,quote=JSON.stringify(o),id=action==='join'?undefined:o.id;
  button.onclick=()=>send(g.id,action,id,quote,here);parent.append(button);
  controls.push({button,enabled:!!permit?.enabled});
  if(permit?.reason){const reason=node('small',permit.reason);reason.id='guild-reason-'+controls.length;
   button.setAttribute('aria-describedby',reason.id);parent.append(reason);}
 }
 function reset(){clearTimeout(timer);timer=null;pending=null;latest=null;scope='';feedback.clear();statusNodes.clear();controls.length=0;}
 function receive(message){
  if(!message?.guild_action||!pending||message.request_id!==pending.id||pending.scope!==scope)return false;
  const gid=pending.gid;clearTimeout(timer);timer=null;pending=null;status(gid,message.text||'The guild returned a result.');refreshButtons();return false;
 }
 window.addEventListener('expanse:build-room-content',({detail:{packet,content,keyed}})=>{
  const next=owner(packet);if(next!==scope){reset();scope=next;}latest=packet;
  controls.length=0;statusNodes.clear();
  for(const g of packet.guilds?.guilds||[]){
   const card=node('section');card.className='action-card guild-card';card.style.overflowWrap='anywhere';card.append(node('h3',g.name));
   card.append(node('p',g.member?'Guild member':'Local guild services'));
   if(g.tasks?.length)card.append(node('p',g.tasks.map(t=>t.name+' '+t.level+'/100').join(' · ')));
   if(!g.member&&g.join)actionButton(card,g,'join',g.join,'Join'+(g.join.fee?' · '+g.join.fee+' gold':''));
   for(const lesson of g.lessons||[]){
    const section=node('div');section.className='guild-offer';section.append(node('h4',lesson.name));
    section.append(node('p','Current skill '+lesson.level+'/100 · training range '+lesson.min_level+'–'+lesson.max_level+
     ' · practice intensity '+lesson.gain+'/5 · '+lesson.cost+' gold. Higher skill levels need more practice.'));
    actionButton(section,g,'learn',lesson,'Learn');card.append(keyed(section,'guild lesson',g.id,lesson.id));
   }
   for(const quest of g.quests||[]){
    const section=node('div');section.className='guild-offer';section.append(node('h4',quest.name));
    if(quest.description)section.append(node('p',quest.description));
    section.append(node('p',(quest.tier||'Task')+' · skill '+quest.difficulty+' · '+quest.status));
    if(typeof quest.remaining==='number')section.append(node('p',quest.remaining>0?
     'Still needed: '+quest.remaining+'. Contributions by players and NPCs reduce this shared need.':
     'This need is met. The request returns only if the need returns.'));
    if(typeof quest.reward==='string'&&quest.reward)section.append(node('p',quest.reward));
    const buttons=node('div');buttons.className='action-buttons';
    if(quest.accept)actionButton(buttons,g,'accept',quest,'Accept quest');
    if(quest.complete)actionButton(buttons,g,'complete',quest,typeof quest.remaining==='number'?'Contribute':'Complete quest');
    section.append(buttons);card.append(keyed(section,'guild quest',g.id,quest.id));
   }
   const report=node('p',feedback.get(g.id)||'');report.setAttribute('role','status');report.setAttribute('aria-live','polite');report.hidden=!report.textContent;
   statusNodes.set(g.id,report);card.append(keyed(report,'guild status',g.id));content.append(keyed(card,'guild',g.id));
  }
 });
 window.addEventListener('expanse:character-reset',reset);
 window.ExpanseGuilds={receive,reset};
})();
