/* Local theft choices disclose identities already in the room, never pockets. */
(()=>{'use strict';
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 let latest=null,scope='',selected=null,pending=null,sequence=0,timer=null,dialog=null,amount=null,attemptButton=null,notice=null,summary=null,outcomeText='';
 const owner=m=>JSON.stringify([m?.visual?.travel_world||'',m?.character?.id||'',m?.location?.id||'']);
 const visible=()=>dialog&&(window.PhonePopups?.visible?window.PhonePopups.visible(dialog):dialog.open);
 const close=()=>{if(visible()){if(window.PhonePopups)window.PhonePopups.finish(dialog);else dialog.close();}};
 const target=()=>latest?.theft?.targets?.find(row=>row.id===selected?.id);
 function feedback(text){if(notice){notice.textContent=text;notice.hidden=!text;}}
 function refresh(){
  if(!dialog||!selected)return;
  const person=target(),state=latest?.theft;
  if(!person||selected.scope!==scope){clearTimeout(timer);timer=null;pending=null;close();selected=null;outcomeText='';return;}
  summary.textContent='Your Burgling: '+state.level+'/100. The maximum below limits what you try to take. Success and skill determine the actual amount; nearby people use Observation to notice the attempt.';
  attemptButton.disabled=!!pending||!!state.blocked;
  if(!pending)feedback([outcomeText,state.blocked].filter(Boolean).join('\n'));
 }
 function send(){
  if(pending||!selected||selected.scope!==scope||!target())return;
  if(latest.theft.blocked){feedback(latest.theft.blocked);return;}
  const quantity=Number(amount.value);
  if(!Number.isSafeInteger(quantity)||quantity<1||quantity>1000000){feedback('Choose a whole maximum quantity from 1 to 1,000,000.');amount.focus();return;}
  if(typeof ws==='undefined'||!ws||ws.readyState!==1){feedback('Reconnect before attempting theft.');return;}
  const id='theft-'+(++sequence),context=scope;
  const request={command:'steal action',theft_ui:true,action:'steal',sequence,request_id:id,
   actor_id:latest.character.id,room:latest.location.id,target_id:selected.id,quantity};
  outcomeText='';pending={id,scope:context};attemptButton.disabled=true;feedback('Waiting for the result…');
  try{ws.send(JSON.stringify(request));}
  catch{pending=null;attemptButton.disabled=false;feedback('The theft request was not sent. Reconnect and try again.');return;}
  if(typeof append==='function')append('user','> Attempt theft from '+target().name+' · up to '+quantity);
  timer=setTimeout(()=>{if(pending?.id!==id)return;pending=null;outcomeText='The result has not been confirmed. Check Conversation and your inventory before trying again.';refresh();},15000);
 }
 function open(id){
  const person=latest?.theft?.targets?.find(row=>row.id===id);if(!person)return;
  if(pending){if(!visible()){if(window.PhonePopups)window.PhonePopups.open(dialog);else dialog.showModal();}feedback('Wait for the current theft result before choosing another person.');return;}
  close();selected={id,scope};outcomeText='';
  if(!dialog){dialog=node('dialog');dialog.id='theft-action';dialog.className='style-dialog';dialog.style.cssText='width:min(36rem,calc(var(--expanse-viewport-width,100vw) - 2rem));box-sizing:border-box;overflow-wrap:anywhere';document.body.append(dialog);}
  dialog.replaceChildren();dialog.setAttribute('aria-label','Attempt theft from '+person.name);
  dialog.append(node('h2','Attempt theft'),node('p','Steal from '+person.name+'?'));
  dialog.append(node('p','This is theft. A person who notices may shout or report it. The person loses exactly the items you successfully take.'));
  summary=node('p');dialog.append(summary);
  const label=node('label','Maximum quantity ');amount=node('input');amount.type='number';amount.min='1';amount.max='1000000';amount.step='1';amount.value='1';amount.setAttribute('aria-label','Maximum quantity to attempt');amount.style.cssText='max-width:100%;width:8rem';label.append(amount);dialog.append(label);
  notice=node('p');notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');notice.hidden=true;dialog.append(notice);
  attemptButton=node('button','Attempt theft');attemptButton.type='button';attemptButton.className='ed-btn';attemptButton.onclick=send;
  const cancel=node('button','Close');cancel.type='button';cancel.className='ed-btn';cancel.onclick=close;
  const buttons=node('div');buttons.className='action-buttons';
  for(const button of [attemptButton,cancel])button.style.cssText='min-height:44px;max-width:100%;white-space:normal;font-size:14px;padding:8px 12px';
  buttons.append(attemptButton,cancel);dialog.append(buttons);refresh();
  if(window.PhonePopups)window.PhonePopups.open(dialog);else dialog.showModal();
 }
 function reset(){clearTimeout(timer);timer=null;pending=null;selected=null;latest=null;scope='';outcomeText='';close();}
 function receive(message){
  if(!message?.theft_action||!pending||message.request_id!==pending.id||pending.scope!==scope)return false;
  clearTimeout(timer);timer=null;pending=null;outcomeText=message.text||'The host returned a theft result.';refresh();return false;
 }
 window.addEventListener('expanse:build-room-content',({detail:{packet,content,keyed}})=>{
  const next=owner(packet);if(next!==scope){reset();scope=next;}
  latest=packet;
  if(!packet.theft){close();return;}
  const skills=node('section');skills.className='action-card';skills.append(node('h3','Burgling & Observation'),node('p','Burgling '+packet.theft.level+'/100 · Observation '+packet.theft.observation+'/100'));
  skills.append(node('p','Burgling affects theft success and the amount taken. Observation helps you notice theft. These skills improve through relevant experience.'));
  if(packet.theft.blocked)skills.append(node('p',packet.theft.blocked));content.append(keyed(skills,'theft skills'));
  const cards=Array.from(content.querySelectorAll('[data-view-key]'));
  for(const person of packet.theft.targets||[]){
   const key=JSON.stringify([person.kind==='player'?'Players here':'People and creatures',person.id]);
   const card=cards.find(row=>row.dataset.viewKey===key);if(!card)continue;
   const button=node('button','Steal…');button.type='button';button.className='ed-btn';button.disabled=!!packet.theft.blocked;
   button.title=packet.theft.blocked||'Attempt theft from '+person.name;const here=scope;
   button.onclick=()=>{if(scope===here)open(person.id);};card.append(keyed(button,'theft action',person.id));
  }
  refresh();
 });
 window.addEventListener('expanse:character-reset',reset);
 window.ExpanseTheft={open,receive,reset};
})();
