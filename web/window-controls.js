/* Common window chrome. Dialog minimization requires an explicit lifecycle adapter. */
(()=>{'use strict';
 const shelf=document.createElement('nav');shelf.className='expanse-window-shelf';shelf.setAttribute('aria-label','Minimized windows');document.body.append(shelf);
 const minimized=new Map(),adapters=new Map();
 const scale=()=>Math.max(.1,Number.parseFloat(getComputedStyle(document.documentElement).zoom)||1);
 function viewport(){return {width:window.visualViewport?.width||innerWidth,height:window.visualViewport?.height||innerHeight,scale:scale()};}
 function syncViewport(){
  const view=viewport();
  document.documentElement.style.setProperty('--expanse-viewport-width',view.width/view.scale+'px');
  document.documentElement.style.setProperty('--expanse-viewport-height',view.height/view.scale+'px');
 }
 function placePopover(menu,anchor){
  const view=viewport(),rect=anchor.getBoundingClientRect(),width=view.width/view.scale,height=view.height/view.scale;
  menu.style.left=Math.max(6,Math.min(width-menu.offsetWidth-6,rect.left/view.scale))+'px';
  menu.style.top=Math.max(6,Math.min(height-menu.offsetHeight-6,rect.bottom/view.scale+3))+'px';
 }
 syncViewport();
 window.addEventListener('expanse:display',syncViewport);
 window.visualViewport?.addEventListener('resize',syncViewport);
 function button(symbol,label,fn){const b=document.createElement('button');b.type='button';b.className='expanse-window-button';b.textContent=symbol;b.title=label;b.setAttribute('aria-label',label);b.onclick=fn;return b;}
 function clear(el){minimized.get(el)?.remove();minimized.delete(el);}
 function restore(el,adapter){if(document.querySelector('dialog:modal'))return;clear(el);adapter.restore();}
 function minimize(el,adapter,label){if(!adapter||adapter.minimize()===false){const status=el.querySelector('.window-chrome-status');if(status)status.textContent='Finish the current action before minimizing.';return;}clear(el);const b=document.createElement('button');b.type='button';b.className='ed-btn';b.textContent='Restore '+label;b.onclick=()=>restore(el,adapter);shelf.append(b);minimized.set(el,b);b.focus();}
 function place(el,x,y){
  const box=el.getBoundingClientRect(),{width,height,scale:zoom}=viewport();
  if(!box.width||!box.height)return;
  el.style.setProperty('--window-x',Math.max(0,Math.min(width-box.width,x))/zoom+'px');
  el.style.setProperty('--window-y',Math.max(0,Math.min(height-box.height,y))/zoom+'px');
  el.dataset.windowMoved='true';
 }
 function fit(el){
  if(!el.dataset.windowMoved||el.classList.contains('expanse-dialog-maximized'))return;
  const box=el.getBoundingClientRect();place(el,box.left,box.top);
 }
 function movable(el,bar,allowed=()=>!el.classList.contains('expanse-dialog-maximized')){
  let drag=null;
  bar.tabIndex=0;bar.title='Drag to move. Arrow keys move the window; Home centers it.';
  bar.classList.add('move-window-handle');
  bar.addEventListener('pointerdown',e=>{
   if(e.button!==0||drag||!allowed()||e.target.closest('button,input,select,a'))return;
   const box=el.getBoundingClientRect();
   drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:box.left,top:box.top};
   bar.focus({preventScroll:true});bar.setPointerCapture(e.pointerId);e.preventDefault();
  });
  bar.addEventListener('pointermove',e=>{
   if(!drag||drag.id!==e.pointerId||!allowed())return;
   const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
   if(Math.hypot(dx,dy)>3)place(el,drag.left+dx,drag.top+dy);
  });
  bar.addEventListener('pointercancel',e=>{if(drag?.id===e.pointerId){place(el,drag.left,drag.top);drag=null;}});
  bar.addEventListener('lostpointercapture',()=>{drag=null;});
  bar.addEventListener('keydown',e=>{
   if(e.target!==bar||!allowed())return;
   if(e.key==='Home'){e.preventDefault();e.stopPropagation();delete el.dataset.windowMoved;return;}
   const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
   if(!delta)return;
   e.preventDefault();e.stopPropagation();const box=el.getBoundingClientRect(),n=e.shiftKey?40:12;
   place(el,box.left+n*delta[0],box.top+n*delta[1]);
  });
  new ResizeObserver(()=>{if(allowed())fit(el);}).observe(el);
 }
 const atlas=document.getElementById('world-atlas');
 if(atlas)movable(atlas,atlas.querySelector('header'),()=>atlas.classList.contains('atlas-window-restored'));
 window.addEventListener('resize',()=>{syncViewport();document.querySelectorAll('[data-window-moved]').forEach(fit);});
 function decorate(el){if(el.id==='world-atlas')return;if(el.dataset.windowChrome&&el.querySelector(':scope > .expanse-window-bar'))return;el.dataset.windowChrome='true';
  const title=el.querySelector('h1,h2,h3')?.textContent||'Window';
  const existingClose=[...el.querySelectorAll('button')].find(b=>/^close(?:\b|$)/i.test(b.textContent.trim()))||[...el.querySelectorAll('button')].find(b=>/^cancel$/i.test(b.textContent.trim()));
  const bar=document.createElement('div');bar.className='expanse-window-bar';const label=document.createElement('strong');label.textContent=title;bar.append(label);
  const adapter=adapters.get(el.id);
  const min=button('−','Minimize '+title,()=>minimize(el,adapter,title));
  if(!adapter){min.disabled=true;min.title='This active dialog must be closed or completed before returning to play.';min.setAttribute('aria-label','Minimize unavailable: '+title+' must be closed or completed.');}
  const max=button('□','Maximize '+title,()=>{const active=el.classList.toggle('expanse-dialog-maximized');max.textContent=active?'▣':'□';max.title=(active?'Restore ':'Maximize ')+title;max.setAttribute('aria-label',max.title);});
  const close=button('×','Close '+title,()=>{clear(el);if(existingClose)existingClose.click();else{const event=new Event('cancel',{cancelable:true});if(el.dispatchEvent(event))el.close();}});
  const status=document.createElement('small');status.className='window-chrome-status';status.setAttribute('role','status');bar.append(status,min,max,close);el.prepend(bar);movable(el,bar);
 }
 adapters.set('resident-watch',{minimize:()=>{window.ExpanseResidentWatch.close();return true;},restore:()=>window.ExpanseResidentWatch.restore()});
 adapters.set('quest-offers',{minimize:()=>{document.getElementById('quest-offers').close();return true;},restore:()=>window.ExpanseSourceQuests.open()});
 adapters.set('save-browser',{minimize:()=>document.getElementById('save-browser').close(),restore:()=>document.getElementById('open-save-browser').click()});
 adapters.set('chronicle-reader',{minimize:()=>{window.ExpanseChronicles.close();return true;},restore:()=>window.ExpanseChronicles.restore()});
 adapters.set('press-reader',{minimize:()=>{window.ExpanseGazette.close();return true;},restore:()=>window.ExpanseGazette.open()});
 adapters.set('quest-compass',{minimize:()=>window.ExpansePlayerLists.minimizeCompass(),restore:()=>window.ExpansePlayerLists.openCompass()});
 adapters.set('context-actions',{minimize:()=>window.ExpanseContextActions.minimize(),restore:()=>window.ExpanseContextActions.restore()});
 adapters.set('player-lists',{minimize:()=>window.ExpansePlayerLists.minimize(),restore:()=>window.ExpansePlayerLists.restore()});
 adapters.set('player-keybindings-dialog',{minimize:()=>window.ExpansePlayerControls.minimizeBindings(),restore:()=>window.ExpansePlayerControls.restoreBindings()});
 adapters.set('player-calendar',{minimize:()=>window.ExpanseCalendar.minimize(),restore:()=>window.ExpanseCalendar.restore()});
 document.querySelectorAll('dialog').forEach(decorate);
 new MutationObserver(records=>{for(const record of records){if(record.type==='attributes'){if(record.target.open)clear(record.target);continue;}const owner=record.target.closest?.('dialog');if(owner)decorate(owner);for(const node of record.addedNodes){if(node.nodeType!==1)continue;if(node.matches('dialog'))decorate(node);node.querySelectorAll('dialog').forEach(decorate);}for(const node of record.removedNodes){if(minimized.has(node))clear(node);}}}).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['open']});
 window.ExpanseWindowControls={disconnect:()=>{for(const el of [...minimized.keys()])clear(el);},decorate,register:(id,adapter)=>adapters.set(id,adapter),clear,button,shelf,minimize,viewport,placePopover};
})();
