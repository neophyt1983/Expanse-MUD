/* Host-priced work, medical care and art; refreshes never perform an action. */
(()=>{'use strict';
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const owner=m=>JSON.stringify([m?.visual?.travel_world||'',m?.character?.id||'',m?.location?.id||'']);
 let latest=null,scope='',sequence=0,pending=null,timer=null;
 const notices=new Map(),statusNodes=new Map(),controls=[];
 function status(id,text){notices.set(id,text);const e=statusNodes.get(id);if(e){e.textContent=text;e.hidden=!text;}}
 function buttons(){for(const {button,enabled} of controls)button.disabled=!!pending||!enabled;}
 function current(id){for(const card of latest?.work_services?.cards||[])for(const row of card.entries||[]){
  const action=row.actions?.find(a=>a.id===id);if(action)return {card,action};}return null;}
 function send(id,quote,here){
  if(here!==scope||pending)return;
  const offer=current(id);if(!offer)return;
  const {card,action}=offer;
  if(JSON.stringify(action)!==quote){status(card.id,'This offer changed. Read the updated terms before choosing again.');return;}
  if(!action.enabled){status(card.id,action.reason||'That action is not available now.');return;}
  if(typeof ws==='undefined'||!ws||ws.readyState!==1){status(card.id,'Reconnect before choosing this service.');return;}
  const request_id='work-'+(++sequence),packet={command:'work action',work_ui:true,service:action.service,
   action:action.action,sequence,request_id,actor_id:latest.character.id,room:latest.location.id,
   offer_id:action.id,revision:action.revision};
  pending={id:request_id,card:card.id,scope};status(card.id,'Waiting for a response…');buttons();
  try{ws.send(JSON.stringify(packet));}catch{pending=null;status(card.id,'The request was not sent. Reconnect and try again.');buttons();return;}
  if(typeof append==='function')append('user','> '+action.label);
  timer=setTimeout(()=>{if(pending?.id!==request_id)return;pending=null;
   status(card.id,'The result has not been confirmed. Check Conversation and the current offer before trying again.');buttons();},15000);
 }
 function reset(){clearTimeout(timer);timer=null;pending=null;latest=null;scope='';notices.clear();statusNodes.clear();controls.length=0;}
 function receive(message){
  if(!message?.work_action||!pending||message.request_id!==pending.id||pending.scope!==scope)return false;
  const card=pending.card;clearTimeout(timer);timer=null;pending=null;
  status(card,message.text||'The service returned a result.');buttons();return false;
 }
 window.addEventListener('expanse:build-room-content',({detail:{packet,content,keyed}})=>{
  const next=owner(packet);if(next!==scope){reset();scope=next;}latest=packet;controls.length=0;statusNodes.clear();
  for(const data of packet.work_services?.cards||[]){
   const card=node('section');card.className='action-card work-service-card';card.style.overflowWrap='anywhere';
   card.append(node('h3',data.title));for(const text of data.lines||[])card.append(node('p',text));
   for(const row of data.entries||[]){
    const section=node('div');section.className='work-service-entry';section.append(node('h4',row.title));
    for(const text of row.lines||[])section.append(node('p',text));
    for(const action of row.actions||[]){
     const group=node('div');group.className='work-service-action';
     const button=node('button',action.label);button.type='button';button.className='ed-btn';button.disabled=!!pending||!action.enabled;
     const here=scope,quote=JSON.stringify(action);button.onclick=()=>send(action.id,quote,here);group.append(button);
     controls.push({button,enabled:!!action.enabled});
     if(action.reason){const reason=node('small',action.reason);reason.id='work-service-reason-'+controls.length;
      button.setAttribute('aria-describedby',reason.id);group.append(reason);}
     section.append(group);
    }
    card.append(keyed(section,'work entry',data.id,row.id));
   }
   const report=node('p',notices.get(data.id)||'');report.hidden=!report.textContent;
   report.setAttribute('role','status');report.setAttribute('aria-live','polite');statusNodes.set(data.id,report);
   card.append(keyed(report,'work status',data.id));content.append(keyed(card,'work service',data.id));
  }
 });
 window.addEventListener('expanse:character-reset',reset);
 window.ExpanseWorkServices={receive,reset};
})();
