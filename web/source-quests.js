/* One visible path from the conversation to an acknowledged quest acceptance. */
(()=>{'use strict';
 const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const panel=make('dialog');panel.id='quest-offers';panel.className='resident-window';panel.setAttribute('aria-labelledby','quest-offers-title');
 const title=make('h2','Quest offers');title.id='quest-offers-title';
 const instructions=make('p');instructions.id='quest-offers-instructions';
 const list=make('div');list.className='offer-list';
 const status=make('p');status.id='quest-offers-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const close=make('button','Back to conversation');close.type='button';close.className='ed-btn';
 panel.append(title,instructions,list,status,close);document.body.append(panel);
 let room=null,entry=null,callout=null,note=null,rows=[],pending=null,timer=null,sequence=0,previewQuest=null;
 const accepted=new Set(),buttons=new Map(),alternativeButtons=new Map(),alternatives=new Map();
 function send(body){if(typeof window.expanseAssetSend==='function')return window.expanseAssetSend(body)===true;if(typeof ws==='undefined'||!ws||ws.readyState!==1)return false;ws.send(JSON.stringify(body));return true;}
 function dismiss(){if(panel.open)panel.close();if(entry?.isConnected&&!entry.disabled)entry.focus();}
 close.onclick=dismiss;panel.addEventListener('cancel',event=>{event.preventDefault();dismiss();});
 function syncButtons(){for(const table of [buttons,alternativeButtons])for(const [id,b] of table)b.disabled=!!pending||previewQuest!==null||accepted.has(id);}
 function settle(){clearTimeout(timer);timer=null;pending=null;syncButtons();}
 function clear(){previewQuest=null;settle();for(const table of [buttons,alternativeButtons]){for(const b of table.values())b.disabled=true;table.clear();}alternatives.clear();accepted.clear();rows=[];if(callout)callout.remove();callout=entry=note=null;if(panel.open)panel.close();window.ExpanseWindowControls?.clear(panel);}
 function locationChanged(id){if(room!==null&&id!==room)clear();room=id;}
 function open(){if(!entry||entry.disabled)return;if(!panel.open){window.ExpanseWindowControls?.clear(panel);panel.showModal();}const target=[...buttons.values()].find(b=>!b.disabled);(target||close).focus();}
 function updateEntry(){
  if(!entry)return;const remaining=rows.filter(row=>!accepted.has(row.id));entry.disabled=!remaining.length;
  if(!remaining.length){entry.textContent=alternatives.size?'Other quest accepted':'Quest accepted';if(note)note.textContent=alternatives.size?'Your other starting quest is in Actions → Quests. Complete its objectives to earn the reward.':rows.some(row=>row.interface_guide)?'Accepted. Your interface guide will open next. You can reopen it from Actions → Interface guide.':'Accepted. Open Actions → Quests to review your objectives.';}
  else entry.textContent='Open quest offers'+(remaining.length>1?' ('+remaining.length+')':'');
 }
 function accept(row){
  if(pending||previewQuest!==null||accepted.has(row.id))return;const id='source-quest-'+(++sequence);
  if(!send({command:'accept '+row.id,request_id:id})){status.textContent='Connect to the server, then try Accept again.';return;}
  pending={id,quest:row.id,guided:row.interface_guide===true};syncButtons();
  status.textContent='Accepting '+row.name+'… Waiting for confirmation.';
  timer=setTimeout(()=>{if(pending?.id!==id)return;settle();status.textContent='The server has not confirmed yet. Try Accept again; an already accepted quest will not be awarded twice.';},15000);
 }
 function show(values,automatic=true){
  if(!Array.isArray(values)||!values.length)return;
  const seen=new Set(),valid=values.filter(row=>typeof row?.id==='string'&&typeof row.name==='string'&&!seen.has(row.id)&&(seen.add(row.id),true));
  if(!valid.length)return;
  const position=window.ExpanseTranscript?.beforeAppend();clear();rows=valid;list.replaceChildren();status.textContent='';
  const guided=rows.some(row=>row.interface_guide===true);panel.dataset.guided=String(guided);
  title.textContent=guided?'Step 2 of 2 — accept your first quest':'Quest offers';
  const hasAlternative=rows.some(row=>row.interface_guide===true&&typeof row.alternative_quest==='string'&&row.alternative_quest);
  instructions.textContent=hasAlternative?'Start the interface guide, or choose “Take another quest…” to review work with the same reward. Rewards are earned by completing the quest.':guided?'Read the quest below. Choose “Accept quest & start guide” to begin the interface walkthrough.':'Read an offer, then choose Accept. Accepted quests appear in Actions → Quests.';
  for(const row of rows){
   const section=make('section');section.className='source-quest-offer';section.append(make('h3',row.name));
   if(typeof row.description==='string'&&row.description.trim())section.append(make('p',row.description));
   const b=make('button',row.interface_guide?'Accept quest & start guide':'Accept quest');b.type='button';b.className='ed-btn source-quest-accept';b.dataset.sourceQuest=row.id;b.setAttribute('aria-label',(row.interface_guide?'Accept quest and start guide: ':'Accept quest: ')+row.name);b.onclick=()=>accept(row);section.append(b);buttons.set(row.id,b);list.append(section);
   if(row.interface_guide===true&&typeof row.alternative_quest==='string'&&row.alternative_quest){const other=make('button','Take another quest…');other.type='button';other.className='ed-btn source-quest-alternative';other.dataset.sourceQuestAlternative=row.id;other.setAttribute('aria-label','Review another quest instead of '+row.name);other.onclick=()=>{if(pending||previewQuest!==null||accepted.has(row.id))return;if(!window.ExpanseInterfaceTour?.openAlternative?.(row.id))status.textContent='Finish the current request, then try this choice again.';};alternativeButtons.set(row.id,other);section.append(other);}
  }
  const log=document.getElementById('log');callout=make('section');callout.className='source-quest-callout';callout.dataset.guided=String(guided);callout.setAttribute('aria-label',guided?'Start your first quest':'Available quest offers');
  callout.append(make('strong',guided?'Step 1 of 2 — open your quest offer':'A quest is ready to view'));
  note=make('p',hasAlternative?'Click or tap “Open quest offers” below. The popup lets you start the interface guide or review another starting quest.':guided?'Click or tap the highlighted “Open quest offers” button below. A popup will open; accept the quest there to start your interface guide.':'Choose “Open quest offers” to read and accept the available work.');callout.append(note);
  entry=make('button');entry.type='button';entry.className='ed-btn source-quest-open';entry.setAttribute('aria-haspopup','dialog');entry.setAttribute('aria-controls',panel.id);entry.onclick=open;callout.append(entry);updateEntry();log.append(callout);
  if(window.ExpanseTranscript)window.ExpanseTranscript.afterAppend(position);else log.scrollTop=log.scrollHeight;
  if(automatic&&!guided&&!document.querySelector('dialog:modal'))open();
 }
 function alternativePreview(questId,opening){
  if(opening){if(!rows.some(row=>row.id===questId)||accepted.has(questId)||pending)return;previewQuest=questId;}
  else if(previewQuest===questId)previewQuest=null;
  syncButtons();
 }
 function alternativeAccepted(questId,replacement){
  if(!rows.some(row=>row.id===questId))return;
  previewQuest=null;settle();accepted.add(questId);alternatives.set(questId,replacement.id);
  const primary=buttons.get(questId),other=alternativeButtons.get(questId);if(primary)primary.textContent='Other quest chosen';if(other)other.textContent='Quest accepted';syncButtons();status.textContent='Accepted '+replacement.name+'. Complete its objectives to earn the reward.';updateEntry();dismiss();
 }
 function receive(packet){
  if(packet?.event==='character_entered'||['character_required','saved_exit'].includes(packet?.type)){clear();return false;}
  const result=packet?.quest_accept;
  if(!pending||packet.request_id!==pending.id)return false;
  if(result&&result.quest_id===pending.quest){
   const chosen=rows.find(row=>row.id===pending.quest),guided=pending.guided;settle();
   if(result.accepted===true){accepted.add(result.quest_id);const b=buttons.get(result.quest_id);if(b)b.textContent='Quest accepted';syncButtons();status.textContent='Accepted '+(chosen?.name||'quest')+'.';updateEntry();if(guided||accepted.size===rows.length)dismiss();}
   else{status.textContent=packet.text||result.reason||'This quest could not be accepted. Review the offer and try again.';buttons.get(result.quest_id)?.focus();}
  }else if(packet.type==='error'){settle();status.textContent=packet.text||'The quest could not be accepted. Please try again.';}
  return false;
 }
 window.ExpanseSourceQuests={show,clear,open,locationChanged,receive,alternativePreview,alternativeAccepted};
})();
