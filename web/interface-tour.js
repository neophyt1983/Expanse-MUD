/* World-authored interface lessons. Targets are capabilities, never selectors
 * or executable commands supplied by the game file. Progress is server-owned. */
(()=>{'use strict';
 if(window.ExpanseInterfaceTour)return;
 const $=id=>document.getElementById(id),make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
 const button=(text,fn)=>{const node=make('button',text);node.type='button';node.onclick=fn;return node;};
 const menu=$('conversation-menu');if(!menu)return;
 const entry=button('Interface guide',()=>open());entry.id='interface-guide-open';entry.dataset.action='interface-tour';entry.setAttribute('role','menuitem');entry.setAttribute('aria-controls','interface-tour');
 if(!$('interface-guide-open'))menu.append(entry);
 const card=make('section');card.id='interface-tour';card.popover='manual';card.hidden=true;card.setAttribute('role','region');card.setAttribute('aria-labelledby','interface-tour-title');
 const content=make('div');content.id='interface-tour-content';content.tabIndex=0;content.setAttribute('aria-label','Guide instructions');
 const heading=make('h2');heading.id='interface-tour-title';
 const progress=make('p');progress.id='interface-tour-progress';
 const body=make('p');body.id='interface-tour-text';
 const message=make('p');message.id='interface-tour-status';message.setAttribute('role','status');message.setAttribute('aria-live','polite');
 const choices=make('div');choices.className='interface-tour-choices';
 const footer=make('div');footer.className='interface-tour-buttons';
 const show=button('Show me',()=>reveal(true)),next=button('Next',()=>advance()),later=button('Later',()=>pause()),replay=button('Replay guide',()=>request('restart'));
 show.id='interface-tour-show';next.id='interface-tour-next';later.id='interface-tour-later';replay.id='interface-tour-replay';
 footer.append(show,next,replay,later);content.append(progress,heading,body,choices,message);card.append(content,footer);
 const ring=make('div');ring.id='interface-tour-highlight';ring.popover='manual';ring.hidden=true;ring.setAttribute('aria-hidden','true');
 document.body.append(card,ring);
 const state={player:null,data:null,current:null,visible:false,localPause:false,forceOpen:false,sequence:0,pending:null,timer:null,target:null,owned:null,key:null,frame:null,returnFocus:null,latestRequest:null,acceptMaps:true,menuOwned:false};
 const watchedDialogs=new WeakSet();
 const action=name=>menu.querySelector('[data-action="'+name+'"]');
 const targets={
  conversation:{panel:'conversation',find:()=>$('log')},
  command:{panel:'conversation',find:()=>$('input-form')},
  actions:{panel:'conversation',find:()=>$('conversation-commands'),open:openActions},
  quests:{dialog:'player-lists',find:()=>$('player-lists-title'),open:()=>window.ExpansePlayerLists?.open('quests')},
  map:{panel:'map',find:()=>$('player-visual-map')},
  compass:{panel:'map',find:()=>$('map-quest-compass')||$('quest-compass-open')},
  location:{panel:'location',find:()=>$('location-panel')},
  books:{panel:'location',find:()=>readingSection()||$('location-panel'),open:()=>{const section=readingSection();if(section)section.open=true;}},
  inventory:{dialog:'player-lists',find:()=>$('player-lists-title'),open:()=>window.ExpansePlayerLists?.open('inventory')},
  status:{panel:'conversation',find:()=>action('score'),open:openActions},
  condition:{dialog:'player-lists',find:()=>$('player-lists-title'),open:()=>window.ExpansePlayerLists?.open('condition')},
  save:{find:()=>$('session-save')},
  save_quit:{find:()=>$('session-save-quit')},
  panels:{dialog:'panels-game',find:()=>$('panels-game-title'),open:()=>window.ExpansePanels?.open()},
  help:{panel:'conversation',find:()=>action('help'),open:openActions}
 };
 function readingSection(){return $('location-panel')?.querySelector('details[data-section="Posted reading"]')||$('location-panel')?.querySelector('details[data-section="Bookshelves"]');}
 function openActions(){const control=$('conversation-commands');if(control&&!menu.matches(':popover-open')){control.click();state.menuOwned=true;}}
 function closeActions(){if(state.menuOwned&&menu.matches(':popover-open'))menu.hidePopover();state.menuOwned=false;}
 function send(packet){
  if(typeof window.expanseAssetSend==='function')return window.expanseAssetSend(packet)===true;
  if(typeof ws==='undefined'||!ws||ws.readyState!==1)return false;
  ws.send(JSON.stringify(packet));return true;
 }
 function surface(node,visible){
  if(!visible){if(node.matches(':popover-open'))node.hidePopover();node.hidden=true;return;}
  node.hidden=false;if(typeof node.showPopover==='function'&&!node.matches(':popover-open'))node.showPopover();
 }
 function activeModal(){return [...document.querySelectorAll('dialog:modal')].at(-1)||null;}
 function portal(){
  const parent=activeModal()||document.body;
  if(parent!==document.body&&!watchedDialogs.has(parent)){watchedDialogs.add(parent);parent.addEventListener('close',()=>{
   if(state.owned===parent)state.owned=null;
   if(!state.visible||card.parentElement!==parent)return;
   clearTarget();surface(card,false);document.body.append(card,ring);portal();surface(card,true);message.textContent='Window closed. Choose Show me to reveal this control again.';position();show.focus({preventScroll:true});
  });}
  for(const node of [card,ring])if(node.parentElement!==parent){surface(node,false);parent.append(node);}
 }
 function clearTarget(){if(state.target)state.target.classList.remove('interface-tour-target');state.target=null;surface(ring,false);}
 function closeOwned(){
  if(!state.owned)return;const owned=state.owned;state.owned=null;
  // Move our controls out before closing a dialog we opened. Other dialogs and
  // unsaved forms are left entirely under the player's control.
  for(const node of [card,ring])if(owned.contains(node)){surface(node,false);document.body.append(node);}
  if(owned.id==='player-lists')window.ExpansePlayerLists?.close(false);
  else if(owned.open)owned.close();
 }
 function hide(restore=false){
  state.visible=false;clearTarget();surface(card,false);closeOwned();closeActions();
  if(restore){const target=state.returnFocus?.isConnected?state.returnFocus:$('conversation-commands');target?.focus({preventScroll:true});}
 }
 function finishPending(){clearTimeout(state.timer);state.timer=null;state.pending=null;next.disabled=false;replay.disabled=false;}
 function request(actionName,questId=state.current?.quest_id){
  const current=state.current,requestId='interface-tour-'+(++state.sequence);
  const packet={command:'interface tour',action:actionName,request_id:requestId};
  if(state.player)packet.player_id=state.player;
  if(questId)packet.quest_id=questId;
  if(actionName==='next'){if(!current||current.completed||state.pending)return false;packet.revision=current.revision;packet.step_id=current.step_id;}
  if(!send(packet)){message.textContent='Connect and load your character to use this guide.';return false;}
  state.latestRequest=requestId;
  if(actionName==='pause')return true;
  finishPending();state.pending={id:requestId,action:actionName,quest:questId,step:current?.step_id,player:state.player};
  next.disabled=replay.disabled=true;message.textContent='Waiting for the server…';
  state.timer=setTimeout(()=>{if(state.pending?.id!==requestId)return;finishPending();message.textContent='The server has not confirmed yet. You can retry this step; it will only count once.';},15000);
  return true;
 }
 function advance(){request('next');}
 function pause(){state.localPause=true;state.forceOpen=false;if(state.current)request('pause');finishPending();hide(true);}
 function open(){
  if(menu.matches(':popover-open'))menu.hidePopover();
  state.returnFocus=$('conversation-commands');state.localPause=false;state.forceOpen=true;
  if(!request(state.current?'resume':'view')){
   heading.textContent='Interface guide';body.textContent='Load a character and accept a quest with an interface lesson to begin.';show.hidden=next.hidden=replay.hidden=true;later.textContent='Close';choices.replaceChildren();state.visible=true;portal();surface(card,true);position();later.focus();
  }
 }
 function choose(questId){state.localPause=false;state.forceOpen=true;request('resume',questId);}
 function openQuest(questId){if(typeof questId!=='string'||!questId)return false;window.ExpansePlayerLists?.close(false);state.returnFocus=$('conversation-commands');choose(questId);return true;}
 function drawChoices(data){
  choices.replaceChildren();const rows=(data.choices||[]).filter(row=>typeof row.quest_id==='string'&&typeof row.title==='string');
  if(rows.length<=1&&data.current)return;
  for(const row of rows){const b=button(row.title+(row.completed?' · completed':''),()=>choose(row.quest_id));b.dataset.tourQuest=row.quest_id;choices.append(b);}
 }
 function render(){
  const current=state.current;drawChoices(state.data||{});message.textContent='';content.scrollTop=0;
  if(!current){heading.textContent='Interface guide';progress.textContent='';body.textContent=(state.data?.choices||[]).length?'Choose a learned quest to open its interface lesson.':'Accept an introductory quest with an interface lesson to begin. Guides from learned quests will appear here.';show.hidden=next.hidden=replay.hidden=true;later.textContent='Close';clearTarget();portal();surface(card,true);position();later.focus();return;}
  heading.textContent=current.completed?current.title:current.step_title;
  progress.textContent=current.completed?'Guide complete':current.title+' · '+(current.index+1)+' of '+current.total;
  body.textContent=current.text;show.hidden=next.hidden=!!current.completed;replay.hidden=!current.completed;later.textContent=current.completed?'Close':'Later';
  next.textContent=current.index+1===current.total?'Finish guide':'Next';
  state.visible=true;reveal(false);(current.completed?later:next).focus({preventScroll:true});
 }
 function reveal(userInitiated){
  if(!state.visible)return;
  const current=state.current,spec=targets[current?.target];clearTarget();
  if(!spec){portal();surface(card,true);position();return;}
  if(spec.open!==openActions)closeActions();
  let modal=activeModal();
  if(modal&&modal.id!==spec.dialog){
   if(modal===state.owned){closeOwned();modal=activeModal();}
   else{portal();surface(card,true);message.textContent='Close the open window, then choose Show me to reveal this control.';position();return;}
  }
  if(spec.panel)window.ExpansePanels?.reveal(spec.panel);
  if(['save','save_quit'].includes(current.target)&&document.activeElement===$('input')&&!window.ExpanseMobileLayout?.isComposing())document.activeElement.blur();
  const before=spec.dialog?$(spec.dialog)?.open:false;
  spec.open?.();
  if(spec.dialog&&!before&&$(spec.dialog)?.open)state.owned=$(spec.dialog);
  state.target=spec.find();
  if(state.target){state.target.classList.add('interface-tour-target');if(userInitiated)state.target.scrollIntoView({block:'center',inline:'nearest',behavior:'auto'});}
  portal();surface(card,true);position();
  if(userInitiated)show.focus({preventScroll:true});
  schedulePosition();
 }
 function viewport(){const v=window.visualViewport;return {left:v?.offsetLeft||0,top:v?.offsetTop||0,width:v?.width||window.innerWidth,height:v?.height||window.innerHeight};}
 function overlap(a,b){return Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));}
 function visibleRect(node){if(!node?.isConnected||node.closest('[hidden]')||!node.getClientRects().length)return null;const r=node.getBoundingClientRect();return r.width>0&&r.height>0?r:null;}
 function position(){
  if(!state.visible||card.hidden)return;
  if(state.current?.target&&state.target&&!state.target.isConnected){clearTarget();const target=targets[state.current.target]?.find();if(target){state.target=target;target.classList.add('interface-tour-target');}}
  const v=viewport(),gap=10,width=Math.max(180,Math.min(390,v.width-gap*2));card.style.width=width+'px';card.style.maxHeight=Math.max(120,Math.min(350,v.height*.46))+'px';
  const size=card.getBoundingClientRect(),height=Math.min(size.height||230,Math.max(120,Math.min(350,v.height*.46))),target=visibleRect(state.target),input=visibleRect($('input-form'));
  const clamp=(x,y)=>({left:Math.max(v.left+gap,Math.min(v.left+v.width-width-gap,x)),top:Math.max(v.top+gap,Math.min(v.top+v.height-height-gap,y)),width,height});
  const candidates=target?[clamp(target.right+gap,target.top),clamp(target.left-width-gap,target.top),clamp(target.left,target.bottom+gap),clamp(target.left,target.top-height-gap)]:[];
  candidates.push(clamp(v.left+v.width-width-gap,v.top+gap),clamp(v.left+gap,v.top+gap),clamp(v.left+v.width-width-gap,v.top+v.height-height-gap));
  for(const r of candidates){r.right=r.left+r.width;r.bottom=r.top+r.height;r.score=(target?overlap(r,target):0)+(input?overlap(r,input)*12:0);}
  const best=candidates.reduce((a,b)=>b.score<a.score?b:a);card.style.left=best.left+'px';card.style.top=best.top+'px';
  if(target){const left=Math.max(v.left+3,target.left-3),top=Math.max(v.top+3,target.top-3),right=Math.min(v.left+v.width-3,target.right+3),bottom=Math.min(v.top+v.height-3,target.bottom+3);if(right>left&&bottom>top){Object.assign(ring.style,{left:left+'px',top:top+'px',width:(right-left)+'px',height:(bottom-top)+'px'});surface(ring,true);}else surface(ring,false);}else{surface(ring,false);if(state.current?.target&&!message.textContent)message.textContent='Choose Show me to reveal the control. On a small screen you can close the keyboard first.';}
 }
 function schedulePosition(){if(state.frame!==null)return;state.frame=requestAnimationFrame(()=>{state.frame=null;position();});}
 function update(data,packet){
  if(!data||typeof data.player_id!=='string'||!Array.isArray(data.choices))return;
  if(packet.type==='map'&&!state.acceptMaps)return;
  if(packet.type==='map'&&packet.character?.id&&packet.character.id!==data.player_id)return;
  if(state.player!==null&&data.player_id!==state.player)return;
  if(packet.type==='interface_tour'&&packet.request_id&&packet.request_id!==state.latestRequest)return;
  if(state.player===null&&packet.type!=='map'&&!(state.pending?.action==='view'&&packet.request_id===state.pending.id))return;
  const previous=state.current,current=data.current;
  if(current&&(!Number.isInteger(current.index)||!Number.isInteger(current.total)||current.index<0||current.index>current.total||current.total<1||current.total>24||typeof current.quest_id!=='string'||typeof current.revision!=='string'||(!current.completed&&!Object.hasOwn(targets,current.target))))return;
  state.player=data.player_id;state.data=data;
  state.current=current||null;
  const key=current?[data.player_id,current.quest_id,current.revision,current.index,current.completed,current.paused].join('|'):data.player_id+'|choices';
  if(state.pending&&(packet.request_id===state.pending.id||(current&&current.quest_id===state.pending.quest&&current.step_id!==state.pending.step)||(current?.paused&&!previous?.paused)))finishPending();
  const wanted=state.forceOpen||(!state.localPause&&current&&!current.paused&&!current.completed&&(current.required||state.visible));
  if(!wanted&&!(state.visible&&current?.completed&&!state.localPause)){hide();state.key=key;return;}
  state.forceOpen=false;
  if(state.key!==key||!state.visible){closeOwned();state.visible=true;state.key=key;render();}else{drawChoices(data);schedulePosition();}
 }
 function receive(packet){
  if(packet?.event==='character_entered'){disconnect();state.player=typeof packet.player_id==='string'?packet.player_id:null;state.acceptMaps=true;return false;}
  if(['character_required','saved_exit'].includes(packet?.type)){disconnect();return false;}
  if(packet?.type==='error'&&packet.request_id===state.pending?.id){finishPending();state.forceOpen=false;message.textContent=packet.text||'The guide could not be updated.';return false;}
  if(packet?.type==='interface_tour'||(packet?.type==='map'&&Object.hasOwn(packet,'interface_tour'))){update(packet.interface_tour,packet);return packet.type==='interface_tour';}
  return false;
 }
 function disconnect(){finishPending();hide();state.player=state.data=state.current=state.key=state.latestRequest=null;state.localPause=state.forceOpen=false;state.returnFocus=null;state.acceptMaps=false;choices.replaceChildren();message.textContent='';}
 card.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();pause();}else if(event.key!=='Tab')event.stopPropagation();});
 window.addEventListener('resize',schedulePosition);window.addEventListener('scroll',schedulePosition,{capture:true,passive:true});window.addEventListener('expanse:display',schedulePosition);
 window.visualViewport?.addEventListener('resize',schedulePosition);window.visualViewport?.addEventListener('scroll',schedulePosition);
 window.addEventListener('expanse:character-reset',disconnect);
 window.ExpanseInterfaceTour={open,openQuest,receive,disconnect,targets:Object.freeze(Object.keys(targets)),version:'1.9.9'};
})();
