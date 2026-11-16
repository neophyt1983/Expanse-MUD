(()=>{
 const make=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
 const button=(label,fn)=>{const b=make('button',label);b.type='button';b.className='ed-btn';b.onclick=fn;return b;};
 function send(command){if(command==='save_exit'&&window.ExpansePlaytest){window.ExpansePlaytest.saveAndQuit();return;}if(command==='save_exit'&&window.ExpansePixelStudio?.canLeave()===false)return;if(!ws||ws.readyState!==WebSocket.OPEN){append('error','Connect to the server before saving.');return;}if(window.expanseSaveStatus)window.expanseSaveStatus('Saving…');ws.send(JSON.stringify({command}));}
 const bar=make('div');bar.id='session-actions';bar.style.cssText='display:flex;gap:8px;flex-wrap:wrap;padding:8px';
 if(!window.ExpanseNativeFileMenu){const leave=button('Save & quit',()=>send('save_exit')),save=button('Save',()=>send('save'));save.id='session-save';leave.id='session-save-quit';leave.dataset.playtestSaveQuit='true';bar.append(save,leave);}
 const saveStatus=make('span');saveStatus.id='save-status';saveStatus.setAttribute('role','status');bar.append(saveStatus);window.expanseSaveStatus=text=>saveStatus.textContent=text;
 document.getElementById('tab-game').prepend(bar);
 const modal=document.getElementById('character-creation'),box=make('section');box.style.cssText='border-bottom:1px solid #486154;padding-bottom:14px;margin-bottom:14px';
 box.append(make('h2','Choose a character'));const list=make('div');box.append(list);
 modal.firstElementChild.prepend(box);
 window.refreshCharacterSaves=async()=>{
  list.replaceChildren(make('p','Reading characters and saved checkpoints…'));
  try{const response=await fetch('/api/character/saves?game='+encodeURIComponent(document.getElementById('cc-game').value||config.running_game||'default'));const data=await response.json();if(data.error)throw Error(data.error);
   list.replaceChildren(make('p','World: '+(data.world||'default')+' · Mode: '+(data.mode||'single')));
   if(!data.characters?.length)list.append(make('p','No saved characters in this world and mode. Create one below.'));
   for(const c of data.characters||[]){const row=make('div');row.style.marginBottom='8px';row.append(make('span',c.name+' · '+(c.mode_label||data.mode)+' · '+(c.unsaved?'Unsaved session':window.expanseSaveDate?window.expanseSaveDate(c.saved_at):c.saved_at||'Date unknown (older save)')+' · '+[c.race,c.char_class,c.location].filter(Boolean).join(' / ')+' '),button('Load',async()=>{if(!ws||ws.readyState!==WebSocket.OPEN){list.prepend(make('p','Still connecting. Please try Load again in a moment.'));return;}const response=await fetch('/api/character/load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({game_slug:data.world,player_id:c.id})});const loaded=await response.json();if(loaded.error){list.prepend(make('p',loaded.error));return;}config.running_game=data.world;localStorage.setItem(`expanse.player_id.${config.running_game||'default'}.${config.mode||'single'}`,c.id);sessionStorage.setItem('expanse.active',c.id);ws.send(JSON.stringify({command:'resume',player_id:c.id,auth_token:localStorage.getItem('expanse.delete_token.'+c.id)}));}));
    const token=localStorage.getItem('expanse.delete_token.'+c.id);
    if(config.can_manage_server||config.internet_accounts||token)row.append(button('Delete Save',async()=>{
      if(!confirm('Permanently delete '+c.name+' in '+data.world+' ('+data.mode+')? This removes the character and its personal progress. Shared-world events and other characters remain.'))return;
      try{const response=await fetch('/api/character/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({game_slug:data.world,player_id:c.id,control_token:config.control_token,delete_token:token})});const deleted=await response.json();if(deleted.error)throw Error(deleted.error);localStorage.removeItem('expanse.delete_token.'+c.id);for(let i=localStorage.length-1;i>=0;i--){const key=localStorage.key(i);if(key.startsWith('expanse.player_id.')&&localStorage.getItem(key)===c.id)localStorage.removeItem(key);}window.refreshCharacterSaves();}catch(e){list.prepend(make('p',e.message));}
    }));
    row.dataset.saveId=c.id;list.append(row);}
  }catch(e){list.replaceChildren(make('p','Could not read saves: '+e.message));}
 };
 document.querySelector('header nav button[data-tab="game"]')?.addEventListener('click',()=>{if(!window.expanseCharacterLoaded)showCreationModal();});
 // Data displayed by the original modal is filled from the server, never a phantom Adventurer.
 if(modal.classList.contains('show'))window.refreshCharacterSaves();
})();
