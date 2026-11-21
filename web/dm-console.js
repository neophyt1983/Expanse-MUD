(()=>{
'use strict';
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const el=(tag,id,text)=>{const n=node(tag,text);n.id=id;return n;};
const button=(id,text,fn)=>{const n=el('button',id,text);n.type='button';n.onclick=fn;return n;};
let authorized=false,sequence=0,selected='',player=null,preview=null,timer=null,returnFocus=null,destination='',latestPreview='';
const pending=new Map();
const launch=button('dm-open','Dungeon Master',()=>open(launch));launch.hidden=true;
document.getElementById('session-actions').append(launch);
const startLaunch=button('dm-open-start','Dungeon Master (no character needed)',()=>open(startLaunch));startLaunch.hidden=true;document.querySelector('#character-creation .cc-actions')?.append(startLaunch);
const dialog=el('dialog','dm-console');dialog.setAttribute('aria-labelledby','dm-title');
const heading=el('h2','dm-title','Dungeon Master');
const status=el('p','dm-status');status.setAttribute('aria-live','polite');
const close=button('dm-close','Close',()=>dismiss());
const header=node('header');header.append(heading,close);
const notice=node('p','Owner-only controls. Activity shows action categories and locations, not private chat, passwords or calendar details. Inventory adjustments require a reviewed, saved host action.');notice.className='dm-notice';
const grid=el('div','dm-grid');
const rosterPanel=node('section'),roster=el('div','dm-roster');rosterPanel.append(node('h3','Connected players'),button('dm-refresh','Refresh',()=>request('roster')),roster);
const detailPanel=node('section'),detail=el('div','dm-detail');detailPanel.append(node('h3','Selected character'),detail);
const auditPanel=node('section'),activity=el('div','dm-activity'),history=el('div','dm-audit'),bans=el('div','dm-bans');
auditPanel.append(node('h3','Recent activity'),activity,node('h3','Saved DM actions'),button('dm-refresh-audit','Refresh actions and blocks',()=>request('audit')),history,node('h3','Active world blocks'),bans);
grid.append(rosterPanel,detailPanel,auditPanel);
const confirm=el('section','dm-confirmation');confirm.hidden=true;confirm.setAttribute('aria-labelledby','dm-confirm-title');
const summary=el('div','dm-confirm-summary');
confirm.append(el('h3','dm-confirm-title','Review before applying'),summary,button('dm-apply','Confirm action',()=>{if(!preview)return;const token=preview;preview=null;document.getElementById('dm-apply').disabled=true;document.getElementById('dm-cancel').disabled=true;status.textContent='Applying confirmed action…';request('commit',{token});}),button('dm-cancel','Cancel',()=>cancelPreview()));
dialog.append(header,notice,status,confirm,grid);document.body.append(dialog);
function request(operation,data={}){
 if(!authorized||!ws||ws.readyState!==WebSocket.OPEN){status.textContent='Host connection required.';return;}
 const id=String(++sequence);if(operation==='preview')latestPreview=id;pending.set(id,{operation,player:data.player||'',query:data.query||''});
 if(pending.size>100)pending.delete(pending.keys().next().value);
 ws.send(JSON.stringify({command:'dm',operation,request_id:id,...data}));return id;
}
function open(invoker){if(!authorized)return;returnFocus=invoker||document.activeElement;dialog.showModal();close.focus();status.textContent='Loading connected players…';request('roster');request('audit');clearInterval(timer);timer=setInterval(()=>{if(dialog.open)request('roster');},3000);}
function cancelPreview(){if(preview)request('cancel',{token:preview});preview=null;confirm.hidden=true;summary.replaceChildren();}
function dismiss(){cancelPreview();clearInterval(timer);timer=null;pending.clear();dialog.close();returnFocus?.focus?.();}
dialog.addEventListener('cancel',event=>{event.preventDefault();dismiss();});
function field(label,input){const row=node('label',label);row.append(input);return row;}
function renderRoster(rows){
 roster.replaceChildren();if(!rows.length)roster.append(node('p','No players connected.'));
 for(const p of rows){const b=button('',p.name+' · '+p.location+' · '+p.hp+'/'+p.max_hp+' HP',()=>{cancelPreview();selected=p.id;player=null;destination='';detail.textContent='Loading…';request('detail',{player:p.id});});b.dataset.player=p.id;b.setAttribute('aria-pressed',String(selected===p.id));roster.append(b,node('small',(p.action||'No recent action recorded')+(p.time?' · '+new Date(p.time*1000).toLocaleTimeString():'')));}
 if(selected&&!rows.some(p=>p.id===selected)){selected='';player=null;cancelPreview();detail.textContent='That player disconnected. Choose another player.';}
}
function renderDetail(p){
 player=p;detail.replaceChildren();detail.append(node('h4',p.name),node('p',p.race+' · '+p.character_class+' · '+p.location));
 const form=el('div','dm-fields');
 for(const [key,value] of Object.entries(p.fields)){
  const input=key==='description'?node('textarea'):node('input');input.dataset.dmField=key;input.value=value??'';
  if(['hp','max_hp','attack','defense','gold'].includes(key)){input.type='number';input.step='1';input.min=key==='max_hp'?1:0;input.max=key==='gold'?100000000:['attack','defense'].includes(key)?10000:100000;}
  else input.maxLength=key==='description'?2000:80;
  form.append(field(key.replaceAll('_',' '),input));
 }
 const reason=el('input','dm-reason');reason.placeholder='Reason for change or moderation';reason.maxLength=240;
 detail.append(form,field('Reason',reason),button('dm-preview-edit','Review character changes',()=>{
  const fields={};for(const input of form.querySelectorAll('[data-dm-field]')){const key=input.dataset.dmField,value=input.type==='number'?Number(input.value):input.value;if(value!==(p.fields[key]??''))fields[key]=value;}
  request('preview',{action:'edit',player:selected,fields,reason:reason.value});
 }));
 const inventory=node('details');inventory.append(node('summary','Current inventory and equipment'));
 for(const i of p.inventory)inventory.append(node('p',i.name+' × '+i.quantity+(i.equipped?' · equipped':'')));
 for(const item of p.equipment)inventory.append(node('p',item.slot+': '+item.name));detail.append(inventory);
 const itemQuery=el('input','dm-item-query');itemQuery.placeholder='Find an item by name';itemQuery.maxLength=100;
 const itemChoice=el('select','dm-item-choice');itemChoice.setAttribute('aria-label','Inventory item');itemChoice.append(new Option('Search the world item catalog',''));itemChoice.onchange=()=>{cancelPreview();elRestriction.textContent=itemChoice.selectedOptions[0]?.dataset.restriction||'';};
 const elRestriction=el('p','dm-item-restriction');
 const quantity=el('input','dm-item-quantity');quantity.type='number';quantity.min=1;quantity.max=100;quantity.step=1;quantity.value=1;
 detail.append(node('h4','Inventory adjustments'),node('p','Creates or destroys catalog units only after confirmation. Enchanted, damaged, unique or unknown types cannot be granted/removed. Resolve active player trades first. Collection quests may be affected.'),itemQuery,button('dm-search-items','Search items',()=>request('items',{player:selected,query:itemQuery.value})),itemChoice,elRestriction,field('Quantity (grant/remove only)',quantity));
 for(const [action,label] of [['grant_item','Review grant'],['remove_item','Review removal'],['equip_item','Review equip'],['unequip_item','Review unequip']]){
  detail.append(button('dm-'+action,label,()=>request('preview',{action,player:selected,item:itemChoice.value,quantity:action==='grant_item'||action==='remove_item'?Number(quantity.value):1,reason:reason.value})));
 }
 const query=el('input','dm-destination-query');query.placeholder='Find a destination by name';query.maxLength=100;
 const places=el('select','dm-destination');places.setAttribute('aria-label','Teleport destination');places.append(new Option('Search for a destination',''));places.onchange=()=>{destination=places.value;cancelPreview();};
 detail.append(node('h4','Teleport'),query,button('dm-search-destination','Search destinations',()=>{destination='';request('destinations',{query:query.value});}),places,button('dm-preview-teleport','Review teleport',()=>request('preview',{action:'teleport',player:selected,destination,reason:reason.value})));
 const message=el('textarea','dm-message');message.placeholder='Message';message.maxLength=2000;
 const recipients=el('select','dm-message-recipient');recipients.append(new Option('Selected player','selected'),new Option('All connected players','all'));
 detail.append(node('h4','Host chat'),message,recipients,button('dm-preview-message','Review message',()=>request('preview',{action:'message',player:recipients.value==='all'?'all':selected,text:message.value})));
 const hours=el('input','dm-ban-hours');hours.type='number';hours.min=0;hours.max=8760;hours.step=1;hours.value=24;
 const scope=p.ban_scope==='account'?'Blocks this public account and all its characters from this world.':'LAN limitation: blocks only this character. It cannot identify or block the person from creating another character.';
 detail.append(node('h4','Moderation'),node('p',scope),field('Block hours (0 = until revoked)',hours));
 const kick=button('dm-preview-kick','Review kick',()=>request('preview',{action:'kick',player:selected,reason:reason.value}));
 const ban=button('dm-preview-ban',p.ban_scope==='account'?'Review account block':'Review LAN character block',()=>request('preview',{action:'ban',player:selected,hours:Number(hours.value),reason:reason.value}));
 kick.disabled=ban.disabled=p.is_host;detail.append(kick,ban);if(p.is_host)detail.append(node('p','The local host cannot be kicked or blocked.'));
}
function elQueryValue(id){return document.getElementById(id)?.value;}
function receive(msg){
 if(msg.type==='host_ready'){authorized=true;launch.hidden=false;startLaunch.hidden=false;return false;}
 if(!['dm_result','dm_error'].includes(msg.type))return false;
 const req=pending.get(String(msg.request_id));pending.delete(String(msg.request_id));
 if(!dialog.open||!req)return true;
 if(msg.type==='dm_error'){status.textContent=msg.text;confirm.hidden=true;preview=null;return true;}
 if(req.operation==='roster'){
  renderRoster(msg.players||[]);activity.replaceChildren();for(const a of (msg.activity||[]).slice(-20).reverse())activity.append(node('p',a.name+' · '+a.action+' · '+a.room));if(status.textContent==='Loading connected players…')status.textContent='Connected-player state updated.';
 }else if(req.operation==='detail'){if(req.player===selected)renderDetail(msg.player);}
 else if(req.operation==='items'){
  if(req.player!==selected||!player||elQueryValue('dm-item-query')!==req.query)return true;
  const select=document.getElementById('dm-item-choice');select.replaceChildren(new Option('Choose exact item',''));
  for(const item of msg.items||[]){const option=new Option(item.name+' ['+item.id+'] · '+item.type+' · '+(item.slot||'no slot')+' · owned '+item.owned,item.id);option.dataset.restriction=item.restriction||'';select.append(option);}
  document.getElementById('dm-item-restriction').textContent='Choose an item to review its restrictions. Results are limited to 60; narrow the name search if necessary.';
 }else if(req.operation==='destinations'){
  if(!player||document.getElementById('dm-destination-query')?.value!==req.query)return true;
  const select=document.getElementById('dm-destination');select.replaceChildren(new Option('Choose destination',''));for(const r of msg.destinations||[])select.append(new Option(r.name+(r.floor!==null?' · level '+r.floor:''),r.id));
 }else if(req.operation==='preview'){
  if(String(msg.request_id)!==latestPreview){request('cancel',{token:msg.preview.token});return true;}
  if(req.player&&req.player!=='all'&&req.player!==selected){request('cancel',{token:msg.preview.token});return true;}
  cancelPreview();preview=msg.preview.token;summary.replaceChildren(...msg.preview.summary.map(s=>node('p',s)));if(msg.preview.reason)summary.append(node('p','Reason: '+msg.preview.reason));summary.append(node('small','Expires after 60 seconds. A changing character may require a fresh preview.'));confirm.hidden=false;document.getElementById('dm-apply').disabled=false;document.getElementById('dm-cancel').disabled=false;document.getElementById('dm-cancel').focus();
 }else if(req.operation==='commit'){
  confirm.hidden=true;status.textContent=msg.text;request('roster');request('audit');if(selected)request('detail',{player:selected});
 }else if(req.operation==='audit'){
  history.replaceChildren();for(const row of msg.audit||[]){const entry=node('details');entry.append(node('summary',new Date(row.time*1000).toLocaleString()+' · '+row.action+' · '+row.name+' · '+row.reason),node('pre',JSON.stringify(row.summary,null,2)));history.append(entry);}
  bans.replaceChildren();for(const b of msg.bans||[]){const row=node('div'),reason=node('input');reason.placeholder='Reason for removing block';reason.maxLength=240;row.append(node('p',b.name+' · '+b.scope+' block · '+(b.expires?'until '+new Date(b.expires*1000).toLocaleString():'until revoked')),reason,button('','Review unblock',()=>request('preview',{action:'unban',ban:b.id,reason:reason.value})));bans.append(row);}
 }
 return true;
}
function disconnect(){authorized=false;launch.hidden=true;startLaunch.hidden=true;preview=null;pending.clear();clearInterval(timer);timer=null;if(dialog.open)dialog.close();selected='';player=null;detail.replaceChildren();roster.replaceChildren();activity.replaceChildren();history.replaceChildren();bans.replaceChildren();confirm.hidden=true;}
window.ExpanseDM={receive,disconnect,open,close:dismiss};
// This controls presentation only. The shared host rechecks the current role
// on every request and never grants legacy local-host authority to this socket.
fetch('/api/config').then(r=>r.json()).then(settings=>{
 if(settings.shared_staging&&settings.mmo_role==='Admin'){
  authorized=true;launch.hidden=false;startLaunch.hidden=false;
  notice.textContent='Shared-world Admin controls. Actions require review; character ownership remains separate from moderation authority.';
 }
}).catch(()=>{});
})();
