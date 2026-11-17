/* Manual world checkpoints, available on the title screen and during play. */
(()=>{
 const start=location.pathname.endsWith('mode.html');
 const pendingKey='expanse.pending-save';
 const el=(tag,txt)=>{const node=document.createElement(tag);if(txt)node.textContent=txt;return node;};
 const button=(caption,action)=>{const node=el('button',caption);node.type='button';node.className='ed-btn';node.onclick=action;return node;};
 window.expanseSaveDate=value=>{
   if(!value)return 'Date unknown (older save)';
   const d=new Date(value), z=n=>String(n).padStart(2,'0');
   return Number.isNaN(d.getTime())?'Date unknown':z(d.getDate())+'/'+z(d.getMonth()+1)+'/'+z(d.getFullYear()%100)+' '+z(d.getHours())+':'+z(d.getMinutes());
 };
 async function request(url,body){
   const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
   const data=await r.json();if(!r.ok||data.error)throw Error(data.error||'Could not read saves.');return data;
 }
 const dialog=el('dialog');dialog.id='save-browser';dialog.setAttribute('aria-labelledby','save-title');
 const heading=el('h2','Saved games');heading.id='save-title';
 const close=button('Close',()=>dialog.close()),head=el('header');head.append(heading,close);
 const status=el('p');status.setAttribute('role','status');
 const form=el('form'),label=el('label','New save name');const name=el('input');name.maxLength=80;name.required=true;name.id='new-save-name';label.htmlFor=name.id;
 const create=el('button','Create save');create.type='submit';create.className='ed-btn';form.append(label,name,create);
 const filter=el('select');filter.setAttribute('aria-label','Save mode');
 for(const [val,text] of [['all','All games'],['single','Single-player'],['host','Online']])filter.append(new Option(text,val));
 const tools=el('div');tools.className='save-tools';tools.append(filter,button('Refresh',()=>run(refresh)));
 const list=el('div');list.className='save-entries';dialog.append(head,form,tools,list,status);document.body.append(dialog);
 let entries=[],cfg={},busy=false,sequence=0,current=null,selecting=false;
 const marked=new Set();
 const selectMode=button('Select saves',()=>{selecting=!selecting;marked.clear();render();});
 const remove=button('Delete selected',()=>run(deleteMarked));tools.append(selectMode,remove);
 const replies=new Map();
 window.ExpanseSaveSlots={async reload(){
   if(!playing())return;
   if(busy)return;
   try{
     cfg=await request('/api/config');
     if(!cfg.can_manage_server)throw Error('Only the host can reload the shared world.');
     const data=await live('list');const c=data.slots.find(s=>s.slot===data.current);
     if(!c)throw Error('Choose a saved game to load.');
     await run(()=>load(c));
     if(status.textContent&&!window.expanseLeaving&&!dialog.open)dialog.showModal();
   }catch(e){openManager();status.textContent=e.message;}
 },receive(msg){
   if(msg.type!=='save_slots')return false;
   const pending=replies.get(msg.request_id);if(pending){replies.delete(msg.request_id);msg.error?pending.reject(Error(msg.error)):pending.resolve(msg);}
   return true;
 }};
 function live(action,fields={}){
   if(typeof ws==='undefined'||ws?.readyState!==WebSocket.OPEN)throw Error('Reconnect to the game before managing saves.');
   return new Promise((resolve,reject)=>{
     const request_id='save-'+(++sequence),socket=ws;
     const finish=()=>{socket.removeEventListener('close',lost);replies.delete(request_id);};
     const lost=()=>{finish();reject(Error('Connection lost. Refresh saved games after reconnecting.'));};
     replies.set(request_id,{resolve:v=>{finish();resolve(v);},reject:e=>{finish();reject(e);}});
     socket.addEventListener('close',lost,{once:true});
     try{socket.send(JSON.stringify({command:'save slots',action,request_id,...fields}));}catch(e){finish();reject(e);}
   });
 }
 const playing=()=>!start&&window.expanseCharacterLoaded===true;
 function setBusy(on){busy=on;for(const n of dialog.querySelectorAll('button,input,select'))if(!n.closest('.expanse-window-bar'))n.disabled=on;dialog.setAttribute('aria-busy',String(on));}
 async function run(fn){
   if(busy)return;setBusy(true);status.textContent='';
   try{await fn();}catch(e){status.textContent=e.message;}finally{setBusy(false);render();}
 }
 async function refresh(){
   cfg=await request('/api/config');
   const data=playing()?await live('list'):await request(cfg.can_manage_server?'/api/application/saves':'/api/character/saves');
   entries=data.slots||data.characters||[];if(start)updateContinue(entries[0]);current=data.current||null;form.hidden=!playing();render();
 }
 async function resume(c){
   if(!c.slot||c.legacy)await request('/api/character/load',{game_slug:c.world,player_id:c.player||c.id});
   const pid=c.player||c.id;
   config.running_game=c.world;
   localStorage.setItem('expanse.player_id.'+c.world+'.'+c.mode,pid);sessionStorage.setItem('expanse.active',pid);
   ws.send(JSON.stringify({command:'resume',player_id:pid,auth_token:localStorage.getItem('expanse.delete_token.'+pid)}));
   sessionStorage.removeItem(pendingKey);dialog.close();
 }
 async function load(c){
   if(!cfg.can_manage_server){await resume(c);return;}
   if(window.ExpansePixelStudio?.canLeave()===false)return;
   if((playing()||cfg.game_status==='ready')&&!confirm('Load “'+c.name+'” and leave the current session? Unsaved progress will be lost.'))return;
   window.expanseLeaving=true;
   try{
     status.textContent='Opening saved world…';
     const data=await request('/api/save-slots/open',{slot:c.slot,revision:c.revision,control_token:cfg.control_token});
     sessionStorage.setItem(pendingKey,JSON.stringify(c));location.href=data.redirect;
   }catch(e){window.expanseLeaving=false;if(!start&&typeof ws!=='undefined'&&ws?.readyState===WebSocket.CLOSED)retryConnection();throw e;}
 }
 async function change(action,c){
   if(action==='delete'&&!confirm('Delete “'+c.name+'”? Your current session will stay open.'))return;
   if(action==='overwrite'&&!confirm('Replace “'+c.name+'” with your current character and world?'))return;
   status.textContent=action==='delete'?'Deleting…':'Saving…';
   const fields=c?{slot:c.slot,revision:c.revision}:{name:name.value.trim()};
   const result=playing()?await live(action,fields):await request('/api/save-slots/delete',{...fields,control_token:cfg.control_token});
   if(action==='create')name.value='';
   await refresh();status.textContent=result.text||'Save deleted.';
 }
 async function deleteMarked(){
   const selected=entries.filter(c=>marked.has(c.slot));
   if(!selected.length||!confirm('Delete '+selected.length+' selected saved game'+(selected.length===1?'?':'s?')))return;
   const fields={entries:selected.map(c=>({slot:c.slot,revision:c.revision}))};
   if(playing())await live('delete',fields);
   else await request('/api/save-slots/delete',{...fields,control_token:cfg.control_token});
   selecting=false;marked.clear();await refresh();status.textContent='Deleted '+selected.length+' saved game'+(selected.length===1?'.':'s.');
 }
 function render(){
   list.replaceChildren();
   selectMode.hidden=entries.length<2&&!selecting;selectMode.textContent=selecting?'Cancel selection':'Select saves';
   remove.hidden=!selecting;remove.disabled=busy||!marked.size;remove.textContent='Delete selected ('+marked.size+')';
   for(const c of entries.filter(e=>filter.value==='all'||e.mode===filter.value)){
     const row=el('section');row.dataset.saveId=c.slot||c.id;
     const title=el('strong',c.name),stamp=el('span',(c.mode==='host'?'Online':'Single-player')+' · '+window.expanseSaveDate(c.saved_at));
     const place=c.place||c.location;
     const details=el('small',[c.character!==c.name?c.character:'',c.world_name||c.world,place].filter(Boolean).join(' · '));
     const actions=el('div');actions.className='save-row-actions';
     if(cfg.can_manage_server||c.legacy||!c.slot)actions.append(button('Load',()=>run(()=>load(c))));
     if(playing())actions.append(button('Overwrite',()=>run(()=>change('overwrite',c))));
     if(cfg.can_manage_server||playing())actions.append(button('Delete',()=>run(()=>change('delete',c))));
     if(selecting){const check=el('input');check.type='checkbox';check.checked=marked.has(c.slot);check.setAttribute('aria-label','Select '+c.name);
       check.onchange=()=>{if(check.checked)marked.add(c.slot);else marked.delete(c.slot);remove.disabled=!marked.size;remove.textContent='Delete selected ('+marked.size+')';};
       const label=el('label');label.append(check,title);row.append(label,stamp,details);
     }else{if(c.slot===current)stamp.append(document.createTextNode(' · Current'));row.append(title,stamp,details,actions);}
     list.append(row);
   }
   if(!list.children.length)list.append(el('p','No saved games in this list.'));
   if(playing()&&cfg.can_manage_server===false)list.prepend(el('small','The host can load a named checkpoint for the shared world.'));
 }
 form.onsubmit=e=>{e.preventDefault();run(()=>change('create'));};filter.onchange=render;
 const open=start?document.getElementById('open-save-browser'):button('Saves',openManager);
 function openManager(){selecting=false;marked.clear();if(!dialog.open)dialog.showModal();form.hidden=!playing();run(refresh);}
 open.id='open-save-browser';open.onclick=openManager;
 if(!start)(document.getElementById('session-actions')||document.querySelector('header')).prepend(open);
 function updateContinue(c){
   const recent=document.getElementById('start-continue');
   recent.hidden=!c;recent.className=c?'primary-option':'';
   document.getElementById('open-adventures').classList.toggle('primary-option',!c);
   if(!c){recent.onclick=null;return;}
   recent.title='Continue '+c.name+' · '+window.expanseSaveDate(c.saved_at);
   recent.onclick=async()=>{
     if(busy)return;recent.disabled=true;
     try{cfg=await request('/api/config');await load(c);}
     catch(e){openManager();status.textContent=e.message;}
     finally{recent.disabled=false;}
   };
 }
 if(start)request('/api/application/saves').then(data=>updateContinue(data.slots?.[0])).catch(()=>{});
 if(!start&&!window.ExpanseNativeFileMenu)window.addEventListener('keydown',e=>{
   if(e.key==='F9'&&!e.repeat&&!document.querySelector('dialog:modal')){e.preventDefault();window.ExpanseSaveSlots.reload();}
 });
 const pending=sessionStorage.getItem(pendingKey);
 if(!start&&pending){
   let c;try{c=JSON.parse(pending);}catch{sessionStorage.removeItem(pendingKey);return;}
   const until=Date.now()+120000;
   const timer=setInterval(async()=>{
     if(typeof ws!=='undefined'&&ws?.readyState===WebSocket.OPEN){
       clearInterval(timer);try{await resume(c);}catch(e){sessionStorage.removeItem(pendingKey);openManager();status.textContent=e.message;}
     }else if(Date.now()>until){clearInterval(timer);sessionStorage.removeItem(pendingKey);openManager();status.textContent='Connection timed out. Choose Load to try again.';}
   },200);
 }
})();
