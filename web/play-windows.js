/* Keep tools available without taking height away from the map or transcript. */
(()=>{
 const bar=document.getElementById('society-panels');
 const game=document.getElementById('tab-game');
 if(!bar||!game||!window.ExpanseWindowControls)return;
 const windows=new Map(),named=new Map();
 function frame(id,title,entry){
  const dialog=document.createElement('dialog');dialog.id=id;dialog.className='play-tool-window';
  const h=document.createElement('h2');h.id=id+'-title';h.textContent=title;dialog.setAttribute('aria-labelledby',h.id);dialog.append(h);
  const open=()=>{if(entry.hidden)return;window.ExpanseWindowControls.clear(dialog);if(!dialog.open)dialog.showModal();};
  const close=()=>{if(dialog.open)dialog.close();if(entry.isConnected&&!entry.hidden)tools.focus();};
  window.ExpanseWindowControls.register(id,{minimize(){if(dialog.open)dialog.close();return true;},restore:open});
  dialog.oncancel=e=>{e.preventDefault();close();};
  entry.onclick=open;entry.setAttribute('aria-controls',id);entry.setAttribute('aria-haspopup','dialog');
  document.body.append(dialog);windows.set(dialog,close);return {dialog,open,close};
 }
 // Session tools share one button. A native popover stays inside the window
 // even when the dock below it has a short scrolling viewport.
 const tools=document.createElement('button');
 tools.id='play-tools';tools.className='ed-btn';tools.type='button';tools.textContent='Tools ▾';
 tools.setAttribute('aria-controls',bar.id);tools.setAttribute('aria-expanded','false');
 bar.popover='auto';
 document.getElementById('session-actions').append(tools);
 function placeTools(){
  const bounds=tools.getBoundingClientRect();
  bar.style.left=Math.max(4,Math.min(innerWidth-bar.offsetWidth-4,bounds.left))+'px';
  bar.style.top=Math.max(4,Math.min(innerHeight-bar.offsetHeight-4,bounds.bottom+2))+'px';
 }
 tools.onclick=()=>{if(bar.matches(':popover-open'))bar.hidePopover();else{bar.showPopover();placeTools();bar.querySelector('button:not([hidden])')?.focus();}};
 bar.addEventListener('toggle',()=>tools.setAttribute('aria-expanded',String(bar.matches(':popover-open'))));
 window.addEventListener('resize',()=>{if(bar.matches(':popover-open'))placeTools();});
 const panels=[...bar.querySelectorAll(':scope > details'),...game.querySelectorAll(':scope > details.society-panel')];
 for(const [i,panel] of panels.entries()){
  const title=panel.querySelector('summary').textContent,entry=document.createElement('button');
  entry.type='button';entry.className='ed-btn';entry.textContent=title;entry.hidden=panel.hidden;bar.append(entry);
  const win=frame('game-tool-'+i,title,entry);named.set(panel,win);
  entry.onclick=()=>{bar.hidePopover();win.open();};
  win.dialog.append(panel);panel.open=true;
  new MutationObserver(()=>{entry.hidden=panel.hidden;if(entry.hidden){window.ExpanseWindowControls.clear(win.dialog);win.close();}}).observe(panel,{attributes:true,attributeFilter:['hidden']});
 }
 const quick=document.querySelector('.quick-actions');
 if(quick){
  const menu=document.createElement('div');menu.className='conversation-menu';menu.id='conversation-menu';menu.popover='auto';menu.setAttribute('role','menu');menu.setAttribute('aria-label','Conversation commands');
  const actions=[...quick.querySelectorAll('button')];for(const action of actions){action.setAttribute('role','menuitem');menu.append(action);}
  const entry=document.createElement('button');entry.id='conversation-commands';entry.type='button';entry.textContent='Commands ▾';entry.setAttribute('aria-haspopup','menu');entry.setAttribute('aria-controls',menu.id);entry.setAttribute('aria-expanded','false');
  quick.append(entry,menu);
  document.querySelector('#dock-game-conversation .dock-titlebar strong')?.after(quick);
  function place(){
   const rect=entry.getBoundingClientRect(),width=menu.offsetWidth,height=menu.offsetHeight;
   menu.style.left=Math.max(6,Math.min(innerWidth-width-6,rect.left))+'px';
   menu.style.top=Math.max(6,Math.min(innerHeight-height-6,rect.bottom+3))+'px';
  }
  const enabled=()=>actions.filter(b=>!b.hidden&&!b.disabled&&b.getClientRects().length);
  function open(){if(menu.matches(':popover-open'))return;menu.showPopover();place();enabled()[0]?.focus();}
  function close(){if(menu.matches(':popover-open')){menu.hidePopover();entry.focus();}}
  entry.onclick=()=>menu.matches(':popover-open')?close():open();
  entry.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();open();}};
  menu.addEventListener('toggle',()=>entry.setAttribute('aria-expanded',String(menu.matches(':popover-open'))));
  menu.onkeydown=e=>{
   if(e.key==='Escape'){e.preventDefault();close();return;}
   const items=enabled(),at=items.indexOf(document.activeElement);
   if(!items.length)return;
   const next={ArrowDown:(at+1)%items.length,ArrowUp:(at+items.length-1)%items.length,Home:0,End:items.length-1}[e.key];
   if(next!==undefined){e.preventDefault();items[next].focus();}
  };
  // Close the menu before existing list and command handlers choose their return focus.
  document.addEventListener('click',e=>{if(menu.contains(e.target)&&e.target.closest('button'))close();},true);
  window.addEventListener('resize',()=>{if(menu.matches(':popover-open'))place();});
 }
 window.ExpansePlayWindows={open(panel){named.get(panel)?.open();},disconnect(){for(const [win,close] of windows){window.ExpanseWindowControls.clear(win);if(win.open)close();}}};
})();
