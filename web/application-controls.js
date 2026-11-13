/* Local application lifetime controls, shared by the play and start screens. */
(async()=>{
 const make=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
 let settings;try{settings=await fetch('/api/config').then(r=>r.json());}catch{return;}
 const box=make('div','');box.style.cssText='display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px';
 const status=make('span','');status.setAttribute('role','status');
 const quitting=make('button','Save & Quit Completely');quitting.className='ed-btn';quitting.type='button';
 const isStart=location.pathname.endsWith('mode.html');
 if(isStart){
  const quit=document.getElementById('start-quit');
  quit.onclick=async()=>{
   if(!settings.can_manage_server){status.textContent='Only the local owner can close this application.';return;}
   const state=await fetch('/api/config').then(r=>r.json()).catch(()=>settings);
   if((state.game_status==='ready'||state.game_status==='starting')&&!confirm('Quit Expanse without saving the running world?'))return;
   try{const r=await fetch('/api/application/discard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({control_token:settings.control_token})});
    const data=await r.json();if(data.error)throw Error(data.error);setStatus('Closing Expanse…');}
   catch(e){setStatus(e.message,'error');}
  };
  return;
 }
 if(settings.mode==='host'){
  const address=make('span','Hosting: '+settings.host_address+' · Friends choose Join Network Game and enter this address.');
  if(settings.proxy_ports){const ports=settings.proxy_ports;box.append(make('span','For public connections, point the HTTPS proxy at local HTTP port '+ports.http+' and /ws at port '+ports.ws+'.'));}
  address.id='host-address';box.append(address);
 }
 if(settings.can_manage_server){
  const fresh=make('button','New game');fresh.type='button';fresh.className='ed-btn';fresh.id='new-game-in-play';
  fresh.onclick=()=>{
   if(window.ExpansePixelStudio?.canLeave()===false)return;
   if(!window.expanseCharacterLoaded){location.href='/mode.html#new-game';return;}
   if(!confirm('Save your current game and open New game?'))return;
   if(typeof ws==='undefined'||ws?.readyState!==1){status.textContent='Reconnect to save your current game.';return;}
   fresh.disabled=true;window.expanseStartingNewGame=true;
   ws.send(JSON.stringify({command:'save_exit'}));
  };
  box.append(fresh,quitting);
  {
  const discard=make('button','Quit Without Saving');discard.className='ed-btn';discard.type='button';box.append(discard);
  discard.onclick=async()=>{if(!confirm('Quit without saving this session? Changes since the last explicit Save will be discarded when the host stops. Unsaved creator edits are discarded.'))return;try{window.expanseLeaving=true;const result=await fetch('/api/application/discard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({control_token:settings.control_token})}).then(r=>r.json());if(result.error)throw Error(result.error);status.textContent='Closing without saving…';}catch(e){window.expanseLeaving=false;status.textContent=e.message;}};
  }
  quitting.onclick=async()=>{
   if(!confirm('Save and quit Expanse completely? The server will stop and connected players will be disconnected after their characters are saved.'))return;
   if(window.ExpansePixelStudio?.canLeave()===false)return;
   quitting.disabled=true;status.textContent='Saving and shutting down…';window.expanseLeaving=true;
   try{
    const reply=await fetch('/api/application/quit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({control_token:settings.control_token})}).then(r=>r.json());
    if(reply.error)throw Error(reply.error);
    document.body.replaceChildren();const panel=make('main','');panel.style.cssText='padding:40px;max-width:700px;margin:auto;font-family:monospace';
    panel.append(make('h1','Expanse saved and shutting down'),make('p','The application is stopping. The Expanse window will close automatically.'),make('p','To start again, run:'),make('pre','bash "$HOME/Dev-Site/run-expanse.sh"'));
    document.body.append(panel);
   }catch(e){window.expanseLeaving=false;quitting.disabled=false;status.textContent='Quit cancelled: '+e.message;}
  };
 }
 if(settings.build){const version=make('small','Build '+settings.build);version.id='expanse-build';version.title='Use this build label when reporting a problem.';box.append(version);}
 box.append(status);
 if(isStart)document.body.append(box);else document.querySelector('header')?.append(box);
})();
