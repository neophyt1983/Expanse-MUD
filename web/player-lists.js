/* Structured, server-filtered player knowledge. IDs are transport keys, not labels. */
(()=>{'use strict';
 const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const kinds={abilities:'Abilities',inventory:'Inventory',quests:'Quests',adventures:'Adventures',markets:'Markets',survey:'Survey',catalog:'Catalog',wardrobe:'Wardrobe',recipes:'Recipes',condition:'Condition'};
 const state={sequence:0,list:null,focus:null,navigation:null,kind:'quests',expanded:new Set(),restore:null,refreshAfterAction:false};
 const dialog=make('dialog');dialog.id='player-lists';dialog.setAttribute('aria-labelledby','player-lists-title');
 const head=make('header'),title=make('h2','Your quests and belongings');title.id='player-lists-title';head.append(title);
 const form=make('form'),kind=make('select'),query=make('input'),search=make('button','Find'),refresh=make('button','Refresh');kind.id='player-lists-kind';kind.setAttribute('aria-label','List');query.type='search';query.placeholder='Filter known entries';query.setAttribute('aria-label','Filter known entries');query.id='player-lists-query';for(const [id,name] of Object.entries(kinds))kind.append(new Option(name,id));search.type='submit';refresh.type='button';form.append(kind,query,search,refresh);
 const pager=make('div'),previous=make('button','Previous page'),next=make('button','Next page');pager.className='player-list-pager';previous.type=next.type='button';pager.append(previous,next);pager.hidden=true;
 const status=make('p'),content=make('div');status.id='player-lists-status';status.setAttribute('role','status');content.id='player-lists-content';dialog.append(head,form,status,pager,content);document.body.append(dialog);
 const compass=make('dialog');compass.id='quest-compass';compass.className='quest-compass';compass.setAttribute('aria-labelledby','compass-title');
 const compassTitle=make('h2','Quest compass');compassTitle.id='compass-title';
 const guidance=make('div');guidance.id='quest-compass-guidance';guidance.setAttribute('aria-live','polite');
 const manage=button('Choose quests',()=>open('quests'));compass.append(compassTitle,guidance,manage);document.body.append(compass);
 const compassEntry=button('Quest compass',openCompass);compassEntry.id='quest-compass-open';compassEntry.className='action-btn';compassEntry.setAttribute('aria-controls',compass.id);
 (document.querySelector('.quick-actions')||document.getElementById('session-actions'))?.append(compassEntry);
 function openCompass(){if(window.ExpanseSettings?.questCompassVisible()===false)return;
   window.ExpanseWindowControls?.clear(compass);if(!compass.open)compass.showModal();navigation();}
 function closeCompass(){if(compass.open)compass.close();(document.getElementById('conversation-commands')||compassEntry).focus();}
 compass.oncancel=e=>{e.preventDefault();closeCompass();};
 compass.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();closeCompass();}});
 guidance.append(make('p','Select an accepted quest to follow its next known destination.'));
 const abilityEntry=make('button','Abilities');abilityEntry.type='button';abilityEntry.id='abilities-open';abilityEntry.className='action-btn';abilityEntry.onclick=()=>open('abilities');document.querySelector('.quick-actions')?.append(abilityEntry);
 function send(command,requestId){if(typeof ws==='undefined'||!ws||ws.readyState!==1)return false;ws.send(JSON.stringify({command,...(requestId?{request_id:requestId}:{})}));return true;}
 function token(){return 'player-list-'+(++state.sequence);}
 function request(){if(!dialog.open)return;const id=token();state.list={id,kind:state.kind};content.replaceChildren();pager.hidden=true;status.textContent='Loading your known '+kinds[state.kind].toLowerCase()+'…';if(!send('ui list '+state.kind+(query.value.trim()?' '+query.value.trim():''),id)){state.list=null;status.textContent='Connect and load your character first.';}}
 function open(value='quests'){if(value==='journal')value='quests';if(!kinds[value])return;state.kind=value;kind.value=value;query.value='';if(!dialog.open){state.restore=document.activeElement;dialog.showModal();}title.textContent=kinds[value];request();kind.focus();}
 function dismiss(restore=true){state.list=null;state.focus=null;state.refreshAfterAction=false;if(dialog.open)dialog.close();if(restore&&state.restore?.isConnected)state.restore.focus();state.restore=null;}
 function focusLocation(location){if(!location?.id)return;const id=token();state.focus=id;status.textContent='Checking the known map location…';if(!send('ui focus '+location.id,id)){state.focus=null;status.textContent='Connection unavailable.';}}
 function button(label,fn){const b=make('button',label);b.type='button';b.onclick=fn;return b;}
 function node(row,path){const box=make('details'),label=String(row.label||'Entry'),summary=make('summary',label);box.className='player-list-node';const key=state.kind+':'+(row.id||path);box.open=state.expanded.has(key);box.addEventListener('toggle',()=>{if(box.open)state.expanded.add(key);else state.expanded.delete(key);});box.append(summary);
  if(row.detail)box.append(make('p',String(row.detail)));
  if(row.location?.id){const where=button('Show '+(row.location.name||'known location')+' on map',()=>focusLocation(row.location));where.className='player-list-location';box.append(where);}
  for(const action of row.actions||[]){if(!action?.label||typeof action.command!=='string')continue;const b=button(action.label,()=>{const guide=action.command.match(/^interface resume (.+)$/);if(guide&&window.ExpanseInterfaceTour?.openQuest(guide[1]))return;if(!send(action.command)){status.textContent='Connection unavailable.';return;}b.disabled=true;state.refreshAfterAction=true;status.textContent=action.label+' requested…';});b.disabled=!!action.disabled;b.dataset.ruleDisabled=action.disabled?'true':'false';b.title=action.reason||'';box.append(b);}
  for(const [i,child] of (row.children||[]).entries())box.append(node(child,path+'.'+i));return box;
 }
 const mapCompass=make('section');mapCompass.id='map-quest-compass';mapCompass.setAttribute('aria-label','Tracked quest directions');
 const compassHeading=button('Quest compass',openCompass),mapRows=make('div'),emptyTrack=button('Choose quests',()=>open('quests'));
 compassHeading.className='compass-label';mapCompass.append(compassHeading,mapRows);
 document.getElementById('player-map-panel')?.querySelector('.map-view-buttons')?.after(mapCompass);
 function clearMapCompass(){mapRows.replaceChildren(emptyTrack);mapCompass.hidden=window.ExpanseSettings?.questCompassVisible()===false;}
 clearMapCompass();
 const bearings={north:'↑',northeast:'↗',east:'→',southeast:'↘',south:'↓',southwest:'↙',west:'←',northwest:'↖',up:'⇧',down:'⇩',in:'↪',out:'↩'};
 function drawMapCompass(packet){
  clearMapCompass();if(mapCompass.hidden||!packet.quests?.length)return;
  mapRows.replaceChildren();
  for(const q of packet.quests){
   const word=q.direction||({here:'Here',blocked:'Blocked',dark:'Dark',unknown:'Unknown'}[q.status]||'Quests');
   const mark=q.direction?(bearings[q.direction]||'➜'):q.status==='here'?'◆':q.status==='blocked'?'×':'?';
   const pill=button('',openCompass);pill.className='compass-track';pill.dataset.quest=q.id||'';
   const arrow=make('b',mark),label=make('span',q.name+' · '+word);pill.append(arrow,label);
   pill.title=[q.name,q.objective,q.target?.name].filter(Boolean).join(' — ');pill.setAttribute('aria-label',[q.name,word,q.objective,q.target?.name].filter(Boolean).join(', '));mapRows.append(pill);
  }
 }
 function renderNavigation(packet){drawMapCompass(packet);window.ExpanseWorldAtlas?.setKnownPins(packet.pins||[]);guidance.replaceChildren();if(!(packet.quests||[]).length){guidance.append(make('p','Select an accepted quest to follow its next known destination.'));return;}
  const arrows={north:'↑',northeast:'↗',east:'→',southeast:'↘',south:'↓',southwest:'↙',west:'←',northwest:'↖',up:'⇧',down:'⇩',in:'↪',out:'↩'};
  for(const quest of packet.quests){const row=make('div');row.className='quest-guidance';row.append(make('strong',quest.name||'Selected quest'));const direction=quest.direction,statusText={dark:'Darkness conceals the route. Try a direction or use a working lantern.',travel:'Follow the next available exit; this is not a straight-line bearing.',here:'You are at the known destination.',blocked:'No traversable route is currently available.',unknown:'No route through personally visited places is known.',journal:'Open Quests for this objective.'}[quest.status]||quest.status;row.append(make('span',(arrows[direction]?arrows[direction]+' ':'')+(direction?'Next step: '+direction:statusText||'No known destination')));if(quest.objective)row.append(make('small',quest.objective));if(quest.target?.name)row.append(button(quest.target.name,()=>{const id=token();state.focus=id;if(!send('ui focus '+quest.target.id,id)){state.focus=null;guidance.append(make('p','Connection unavailable.'));}}));if(quest.waypoint)row.append(button('Clear destination',()=>{send('waypoint clear');navigation();}));if(direction&&statusText)row.append(make('small',statusText));guidance.append(row);}
 }
 let refreshPending=false;
 function navigation(){if(window.ExpanseSettings?.questCompassVisible()===false)return;if(state.navigation){refreshPending=true;return;}const id=token();if(send('ui navigation',id))state.navigation=id;}
 function receive(packet){
  if(packet?.type==='player_list'){if(!dialog.open||!state.list||packet.request_id!==state.list.id||packet.kind!==state.list.kind)return true;state.list=null;pager.hidden=!packet.pagination||packet.pagination.pages<=1;if(packet.pagination){const {page,pages}=packet.pagination;previous.disabled=page<=1;next.disabled=page>=pages;const go=n=>{query.value=query.value.replace(/(?:^|\s)page(?:\s+|:)\d+/gi,'').trim()+' page:'+n;request();};previous.onclick=()=>go(page-1);next.onclick=()=>go(page+1);}
 title.textContent=packet.title||kinds[state.kind];status.textContent=packet.note||'';content.replaceChildren();for(const [i,row] of (packet.groups||[]).entries())content.append(node(row,String(i)));if(!content.children.length)content.append(make('p','Nothing known in this list yet.'));return true;}
  if(packet?.type==='player_map_focus'){if(packet.request_id!==state.focus)return true;state.focus=null;if(packet.error){status.textContent=packet.error;return true;}const source=dialog.open?dialog:(compass.open?compass:null);
   if(!source){window.ExpanseWorldAtlas?.focusKnown(packet.pin);return true;}
   const viewport=source===dialog?content:guidance,top=viewport.scrollTop,outer=source.scrollTop,focus=document.activeElement;
   const label=source===dialog?kinds[state.kind].toLowerCase():'quest compass';status.textContent='';
   source.close();window.ExpanseWorldAtlas?.focusKnown(packet.pin,{label,dismiss(){dismiss(false);(document.getElementById('conversation-commands')||compassEntry)?.focus();},restore(){
    if(!source.open)source.showModal();if(focus?.isConnected)focus.focus({preventScroll:true});source.scrollTop=outer;viewport.scrollTop=top;
   }});return true;}
  if(packet?.type==='player_navigation'){if(window.ExpanseSettings?.questCompassVisible()===false){state.navigation=null;return true;}if(packet.request_id&&packet.request_id!==state.navigation)return true;state.navigation=null;renderNavigation(packet);if(refreshPending){refreshPending=false;navigation();}return true;}
  if(['character_required','saved_exit'].includes(packet?.type))disconnect();
  if(packet?.type==='map'||(packet?.type==='response'&&/^(Compass destination set|Globe destination cleared)/.test(packet.text||''))){navigation();}
  if(packet?.type==='response'&&state.refreshAfterAction){state.refreshAfterAction=false;request();state.navigation=null;navigation();}
  if(packet?.type==='error'&&state.refreshAfterAction){state.refreshAfterAction=false;status.textContent=packet.text||'That action could not be completed.';for(const b of content.querySelectorAll('button'))b.disabled=b.dataset.ruleDisabled==='true';}
  if(packet?.type==='error'&&packet.request_id){if(packet.request_id===state.list?.id){state.list=null;status.textContent=packet.text||'Could not load this list.';return true;}if(packet.request_id===state.focus){state.focus=null;status.textContent=packet.text||'Could not locate that place.';return true;}if(packet.request_id===state.navigation){state.navigation=null;return true;}}
  return false;
 }
 function disconnect(){refreshPending=false;clearMapCompass();window.ExpansePlayWindows?.disconnect();dismiss(false);if(compass.open)compass.close();window.ExpanseWindowControls?.clear(compass);state.navigation=null;state.sequence++;state.expanded.clear();guidance.replaceChildren(make('p','Load your character to see selected quests.'));window.ExpanseWorldAtlas?.setKnownPins([]);}
 dialog.addEventListener('cancel',e=>{e.preventDefault();dismiss();});form.onsubmit=e=>{e.preventDefault();request();};kind.onchange=()=>{state.kind=kind.value;query.value='';title.textContent=kinds[state.kind];request();};refresh.onclick=request;
 document.querySelector('.quick-actions')?.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const key=Object.entries(kinds).find(([,label])=>label===b.textContent)?.[0];if(key){e.preventDefault();e.stopImmediatePropagation();open(key);}},true);
 window.addEventListener('expanse:preferences',event=>{clearMapCompass();state.navigation=null;if(event.detail?.questCompass)navigation();else{if(compass.open)compass.close();window.ExpanseWindowControls?.clear(compass);}});
 window.ExpansePlayerLists={minimizeCompass:()=>{if(compass.open)compass.close();return true;},openCompass,open,close:dismiss,receive,disconnect,requestNavigation:navigation,minimize:()=>{if(state.refreshAfterAction)return false;state.list=null;dialog.close();return true;},restore:()=>{dialog.showModal();kind.focus();request();}};
})();
