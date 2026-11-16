/* Local workspace preferences only: no game commands or editor permissions. */
(()=>{
 const workspaces=new Map();
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e;};
 function workspace(parent,entries,key){
  const storage='expanse.layout.v1.'+key,ids=entries.map(e=>e[0]),optional=entries.filter(e=>e[3]?.optional).map(e=>e[0]);
  const initial=()=>({ids:[...ids],order:[...ids],widths:ids.map(()=>1),floating:{},hidden:Object.fromEntries(optional.map(id=>[id,true]))});
  let state=initial(),editing=false,gesture=null;
  const windowModes=new Map(),revealed=new Set();let maximized=null; // Session-only; never rewrite saved layout geometry.
  // Older saves have only the original three panels. Keep their order, widths
  // and floating bounds; new optional panels do not consume space until shown.
  try{
   const s=JSON.parse(localStorage.getItem(storage));
   if(s&&Array.isArray(s.order)&&new Set(s.order).size===s.order.length&&s.order.every(id=>ids.includes(id))&&ids.filter(id=>!optional.includes(id)).every(id=>s.order.includes(id))){
    state.order=[...s.order,...ids.filter(id=>!s.order.includes(id))];
    const savedIds=Array.isArray(s.ids)?s.ids:ids.filter(id=>s.order.includes(id));
    for(const id of ids){
     const f=s.floating?.[id];
     if(f&&['x','y','w','h'].every(k=>Number.isFinite(f[k])))state.floating[id]={x:Math.max(0,Math.min(.8,f.x)),y:Math.max(0,Math.min(.8,f.y)),w:Math.max(.2,Math.min(1,f.w)),h:Math.max(.2,Math.min(1,f.h))};
     const width=s.widths?.[savedIds.indexOf(id)];
     if(Number.isFinite(width)&&width>0)state.widths[ids.indexOf(id)]=Math.min(10,Math.max(.1,width));
     if(optional.includes(id)&&typeof s.hidden?.[id]==='boolean')state.hidden[id]=s.hidden[id];
    }
   }
  }catch{}
  const root=make('section','dock-workspace');root.dataset.workspace=key;
  const toolbar=make('div','dock-toolbar'),toggle=make('button','ed-btn','Edit Layout'),reset=make('button','ed-btn','Reset Layout'),hint=make('span','dock-hint','Layout locked');toggle.type=reset.type='button';toggle.setAttribute('aria-pressed','false');hint.setAttribute('role','status');toolbar.append(toggle,reset,hint);
  const targets=make('div','dock-targets'),visibility=new Map();
  for(const id of optional){const title=entries.find(e=>e[0]===id)[1],button=make('button','ed-btn dock-visibility');button.type='button';button.dataset.togglePanel=id;button.setAttribute('aria-controls','dock-'+key+'-'+id);button.onclick=()=>{if(windowModes.has(id)){windowModes.delete(id);hidePanel(id,false);}else hidePanel(id,!panelHidden(id));if(!panelHidden(id))activeTab=id;render();save();};toolbar.insertBefore(button,hint);visibility.set(id,button);}
  const display=window.ExpanseDisplay;
  const panelHidden=id=>!revealed.has(id)&&(key==='game'&&id==='character' ? !display.character() : !!state.hidden[id]);
  function hidePanel(id,hidden){
   revealed.delete(id);
   state.hidden[id]=hidden;
   if(key==='game'&&id==='character')display.choose('character',hidden?'hide':'show');
  }
  let activeTab=ids[0], lastDisplay='';
  const tabBar=make('nav','dock-tabs');
  tabBar.setAttribute('aria-label',key==='game'?'Game panels':'Creator panels');
  const panelsButton=make('button','ed-btn','Panels');panelsButton.type='button';panelsButton.dataset.openPanels=key;panelsButton.setAttribute('aria-label','Show, reopen or restore panels');toolbar.insertBefore(panelsButton,hint);
  const phoneBar=make('div','dock-phone-actions');phoneBar.hidden=true;phoneBar.setAttribute('role','toolbar');phoneBar.setAttribute('aria-label',key==='game'?'Game actions and panels':'Creator panels');
  const tray=make('div','window-panel-tray');tray.setAttribute('aria-label','Restore closed or minimized panels');toolbar.append(tray);
  const canvas=make('div','dock-canvas'),rail=make('div','dock-rail');canvas.append(rail);root.append(toolbar,tabBar,phoneBar,targets,canvas);parent.append(root);
  const panes=new Map();let top=10;
  const picker=make('dialog','panel-picker'),pickerTitle=make('h2','',key==='game'?'Game panels':'Creator panels'),pickerRows=make('div','panel-picker-rows'),showAll=make('button','ed-btn','Show all panels'),pickerClose=make('button','ed-btn','Close');
  picker.id='panels-'+key;showAll.id=picker.id+'-show-all';pickerClose.id=picker.id+'-close';pickerTitle.id=picker.id+'-title';picker.setAttribute('aria-labelledby',pickerTitle.id);showAll.type=pickerClose.type='button';
  picker.append(pickerTitle,make('p','','Restore a panel without resetting its saved size or position.'),pickerRows,showAll,pickerClose);document.body.append(picker);let pickerFocus=null;
  function pickerRender(){
   const focused=document.activeElement?.dataset?.pickerPanel;pickerRows.replaceChildren();
   for(const id of ids){const row=make('div','panel-picker-row'),status=panelHidden(id)?'Hidden':windowModes.get(id)==='closed'?'Closed':windowModes.has(id)?'Minimized':'Visible',b=make('button','ed-btn',status==='Visible'?'Focus':'Show');b.type='button';b.dataset.pickerPanel=id;b.setAttribute('aria-label',(status==='Visible'?'Focus ':'Show ')+panes.get(id).title);row.append(make('strong','',panes.get(id).title),make('span','',status),b);b.onclick=()=>{restorePanel(id);picker.close();focusPanel(id);};
    if(status==='Visible'){const hide=make('button','ed-btn','Hide');hide.type='button';hide.setAttribute('aria-label','Hide '+panes.get(id).title);hide.onclick=()=>{windowChange(id,'minimized');pickerRows.querySelector('[data-picker-panel="'+id+'"]')?.focus();};row.append(hide);}
    pickerRows.append(row);}
   if(focused)pickerRows.querySelector('[data-picker-panel="'+focused+'"]')?.focus();
  }
  if(key==='game')window.addEventListener('expanse:show-terrain',()=>restorePanel('map'));
  function focusPanel(id){(root.dataset.arrangement==='tabs'?tabBar.querySelector('[data-dock-tab="'+id+'"]'):panes.get(id).windowButtons[0])?.focus({preventScroll:true});}
  function restorePanel(id){const changed=panelHidden(id);if(changed)hidePanel(id,false);activeTab=id;windowModes.delete(id);maximized=null;render();if(changed)save();}
  // A guide can reveal one live panel without replacing the player's saved
  // size, docking order, visibility preference or display settings.
  function revealPanel(id){if(!ids.includes(id))return null;revealed.add(id);activeTab=id;windowModes.delete(id);maximized=null;render();return panes.get(id).panel;}
  function restoreAll(){let changed=false;for(const id of ids){if(panelHidden(id)){changed=true;hidePanel(id,false);}}windowModes.clear();maximized=null;render();if(changed)save();}
  function openPicker(){if(picker.open){pickerClose.focus();return;}if(document.querySelector('dialog:modal'))return;pickerFocus=document.activeElement;pickerRender();picker.showModal();pickerClose.focus();}
  function closePicker(){picker.close();if(pickerFocus?.isConnected)pickerFocus.focus();}
  panelsButton.onclick=openPicker;pickerClose.onclick=closePicker;picker.addEventListener('cancel',e=>{e.preventDefault();closePicker();});showAll.onclick=()=>{restoreAll();pickerRender();showAll.focus();};
  workspaces.set(key,{open:openPicker,restoreAll,reveal:revealPanel});
  function save(){try{localStorage.setItem(storage,JSON.stringify(state));}catch{hint.textContent='Layout works, but preferences could not be saved.';}}
  function floatRect(id){if(maximized===id)return;const f=state.floating[id],w=canvas.clientWidth,h=canvas.clientHeight;if(!f||!w||!h||root.dataset.arrangement==='tabs')return;const p=panes.get(id).panel;const pw=Math.min(w,Math.max(Math.min(240,w),f.w*w)),ph=Math.min(h,Math.max(Math.min(180,h),f.h*h));const x=Math.max(0,Math.min(w-pw,f.x*w)),y=Math.max(0,Math.min(h-ph,f.y*h));Object.assign(p.style,{left:x+'px',top:y+'px',width:pw+'px',height:ph+'px'});}
  function visibleOrder(){return state.order.filter(id=>!panelHidden(id)&&!windowModes.has(id));}
  function windowChange(id,mode){if(mode==='restore'){windowModes.delete(id);maximized=null;}else windowModes.set(id,mode);if(maximized===id)maximized=null;render();const target=mode==='restore'?panes.get(id).windowButtons[0]:tray.querySelector('[data-restore-panel="'+id+'"]');target?.focus();}
  function maximize(id){activeTab=id;maximized=maximized===id?null:id;render();panes.get(id).windowButtons[1].focus();}
  function dock(id,slot){delete state.floating[id];state.order=state.order.filter(x=>x!==id);const before=visibleOrder()[Math.max(0,slot)];state.order.splice(before?state.order.indexOf(before):state.order.length,0,id);render();save();}
  function floating(id){if(!state.floating[id])state.floating[id]={x:.1,y:.1,w:.6,h:.75};render();save();}
  function render(){
   const editingField=document.activeElement,keepFocus=root.contains(editingField)&&editingField?.matches?.('input,textarea');
   const selection=keepFocus&&typeof editingField.selectionStart==='number'?[editingField.selectionStart,editingField.selectionEnd,editingField.selectionDirection]:null;
   tray.replaceChildren();for(const [id,mode] of windowModes){const b=make('button','ed-btn',(mode==='minimized'?'Restore ':'Reopen ')+panes.get(id).title);b.type='button';b.dataset.restorePanel=id;b.onclick=()=>windowChange(id,'restore');tray.append(b);}
   rail.replaceChildren();const visible=visibleOrder(),docked=visible.filter(id=>!state.floating[id]);
   const tabbed=display.tabs(),phone=display.phone?.()===true;
   root.dataset.arrangement=tabbed?'tabs':'columns';
   root.dataset.phone=String(phone);phoneBar.hidden=!phone;
   if(phone){if(panelsButton.parentElement!==phoneBar)phoneBar.append(panelsButton);if(reset.parentElement!==picker)picker.insertBefore(reset,showAll);}
   else{if(panelsButton.parentElement!==toolbar)toolbar.insertBefore(panelsButton,hint);if(reset.parentElement!==toolbar)toolbar.insertBefore(reset,hint);}
   toggle.disabled=tabbed;
   if(tabbed){editing=false;if(maximized)maximized=null;}
   if(!visible.includes(activeTab))activeTab=visible[0];
   tabBar.hidden=!tabbed;tabBar.replaceChildren();
   if(tabbed)for(const id of visible){
    const title=panes.get(id).title,short=key==='game'?{conversation:'Talk',map:'Map',location:'Nearby',character:'You'}:{library:'Library',map:'Map',inspector:'Details'};
    const label=phone?(short[id]||title):title,b=make('button','ed-btn',label);
    b.type='button';b.dataset.dockTab=id;
    b.title=title;b.setAttribute('aria-label',label===title?title:label+' — '+title);
    b.setAttribute('aria-pressed',String(id===activeTab));
    b.setAttribute('aria-controls',panes.get(id).panel.id);
    b.onclick=()=>{
     activeTab=id;
     render();
     tabBar.querySelector('[data-dock-tab="'+id+'"]')?.focus({preventScroll:true});
     if(key==='game'&&id==='map'&&!display.phone?.()&&window.matchMedia('(max-width:850px),(max-height:530px)').matches){
      requestAnimationFrame(()=>panes.get(id).panel.querySelector('.atlas-viewport')?.scrollIntoView({block:'center'}));
     }
    };
    tabBar.append(b);
   }
   targets.replaceChildren();for(let i=0;i<visible.length;i++){const t=make('div','dock-target','Dock '+(visible.length===3?['left','middle','right'][i]:i+1));t.dataset.slot=i;targets.append(t);}
   for(const [id,button] of visibility){const showing=!panelHidden(id)&&!windowModes.has(id);button.textContent=(showing?'Hide ':'Show ')+panes.get(id).title;button.setAttribute('aria-pressed',String(showing));button.setAttribute('aria-expanded',String(showing));}
   for(const id of state.order){const item=panes.get(id),p=item.panel;const f=!!state.floating[id];p.hidden=panelHidden(id)||windowModes.has(id)||(tabbed&&id!==activeTab);p.classList.toggle('is-floating',f);p.removeAttribute('style');item.float.textContent=f?'Dock':'Float';item.grip.hidden=!f;
    item.controls.forEach(b=>b.disabled=!editing||maximized===id);item.windowButtons[1].textContent=maximized===id?'▣':'□';item.windowButtons[1].setAttribute('aria-label',(maximized===id?'Restore ':'Maximize ')+item.title);item.windowButtons[1].title=item.windowButtons[1].getAttribute('aria-label');p.classList.toggle('window-maximized',maximized===id);p.dataset.locked=String(!editing);
    if(p.hidden){canvas.append(p);continue;}
    if(tabbed){rail.append(p);p.style.flex="1";item.grip.hidden=true;continue;}
    if(maximized===id){canvas.append(p);p.style.cssText='position:absolute;inset:0;width:100%;height:100%;z-index:1000';item.grip.hidden=true;continue;}
    if(f){canvas.append(p);p.style.zIndex=++top;floatRect(id);}else{p.style.flex=state.widths[ids.indexOf(id)]+' 1 0';rail.append(p);const next=docked[docked.indexOf(id)+1];if(next){const splitter=make('div','dock-splitter');splitter.tabIndex=editing?0:-1;splitter.setAttribute('role','separator');splitter.setAttribute('aria-label','Resize '+item.title+' and adjacent panel');splitter.setAttribute('aria-orientation','vertical');splitter.setAttribute('aria-valuenow',String(Math.round(state.widths[ids.indexOf(id)]*100)));splitter.onpointerdown=e=>start(e,id,'split',next);splitter.onkeydown=e=>{if(!editing||!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const a=ids.indexOf(id),b=ids.indexOf(next),sum=state.widths[a]+state.widths[b],delta=e.key==='ArrowRight'?.1:-.1;state.widths[a]=Math.max(.15,Math.min(sum-.15,state.widths[a]+delta));state.widths[b]=sum-state.widths[a];render();save();};rail.append(splitter);}}}
   if(picker.open)pickerRender();
   root.classList.toggle('layout-editing',editing);toggle.textContent=editing?'Lock Layout':'Edit Layout';toggle.setAttribute('aria-pressed',String(editing));hint.textContent=editing?'Drag title bars; drop on a docking target. Drag dividers or a floating panel’s corner to resize.':'Layout locked';
   if(keepFocus&&editingField.isConnected&&!editingField.closest('[hidden]')){if(document.activeElement!==editingField)editingField.focus({preventScroll:true});if(selection)try{editingField.setSelectionRange(...selection);}catch{}}
  }
  function start(e,id,kind,next){if(!editing||e.button!==0||gesture||maximized===id)return;if(kind==='move'&&e.target.closest('button'))return;e.preventDefault();e.stopPropagation();const before=JSON.stringify(state),p=panes.get(id).panel,r=p.getBoundingClientRect(),c=canvas.getBoundingClientRect();
   if(kind==='move'&&!state.floating[id]){state.floating[id]={x:(r.left-c.left)/c.width,y:(r.top-c.top)/c.height,w:r.width/c.width,h:r.height/c.height};render();}
   gesture={id,kind,next,x:e.clientX,y:e.clientY,rect:r,canvas:c,before,weights:[...state.widths],pointer:e.pointerId};p.style.zIndex=++top;if(e.isTrusted)e.currentTarget.setPointerCapture?.(e.pointerId);document.body.classList.add('layout-dragging');
  }
  function move(e){if(!gesture||e.pointerId!==gesture.pointer)return;const g=gesture,dx=e.clientX-g.x,dy=e.clientY-g.y;if(g.kind==='split'){const a=ids.indexOf(g.id),b=ids.indexOf(g.next),pa=panes.get(g.id).panel,pb=panes.get(g.next).panel,total=pa.getBoundingClientRect().width+pb.getBoundingClientRect().width,sum=g.weights[a]+g.weights[b];const ratio=Math.max(.15,Math.min(.85,(g.rect.width+dx)/total));state.widths[a]=sum*ratio;state.widths[b]=sum-state.widths[a];pa.style.flex=state.widths[a]+' 1 0';pb.style.flex=state.widths[b]+' 1 0';return;}
   const f=state.floating[g.id];if(g.kind==='move'){f.x=(g.rect.left-g.canvas.left+dx)/g.canvas.width;f.y=(g.rect.top-g.canvas.top+dy)/g.canvas.height;}else{f.w=(g.rect.width+dx)/g.canvas.width;f.h=(g.rect.height+dy)/g.canvas.height;}floatRect(g.id);
   targets.querySelectorAll('.dock-target').forEach(t=>{const r=t.getBoundingClientRect();t.classList.toggle('drop-ready',g.kind==='move'&&e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom);});
  }
  function end(e){if(!gesture||e.pointerId!==gesture.pointer)return;const g=gesture;gesture=null;document.body.classList.remove('layout-dragging');const target=targets.querySelector('.drop-ready');if(e.type==='pointercancel'){state=JSON.parse(g.before);render();}else if(target&&g.kind==='move'){dock(g.id,Number(target.dataset.slot));}else{const p=panes.get(g.id).panel;if(state.floating[g.id])state.floating[g.id]={x:p.offsetLeft/canvas.clientWidth,y:p.offsetTop/canvas.clientHeight,w:p.offsetWidth/canvas.clientWidth,h:p.offsetHeight/canvas.clientHeight};render();save();}targets.querySelectorAll('.drop-ready').forEach(t=>t.classList.remove('drop-ready'));}
  for(const [id,title,content] of entries){const panel=make('section','dock-panel'),header=make('div','dock-titlebar'),label=make('strong','',title),controls=[];panel.dataset.panel=id;panel.id='dock-'+key+'-'+id;panel.setAttribute('aria-label',title+' panel');
   const action=(text,fn)=>{const b=make('button','dock-control',text);b.type='button';b.onclick=fn;controls.push(b);return b;};
   const left=action('←',()=>dock(id,Math.max(0,visibleOrder().indexOf(id)-1))),right=action('→',()=>dock(id,Math.min(visibleOrder().length-1,visibleOrder().indexOf(id)+1))),float=action('Float',()=>state.floating[id]?dock(id,visibleOrder().indexOf(id)):floating(id));left.setAttribute('aria-label','Dock '+title+' farther left');right.setAttribute('aria-label','Dock '+title+' farther right');
   const windowButtons=[];for(const [symbol,verb,fn] of [['−','Minimize',()=>windowChange(id,'minimized')],['□','Maximize',()=>maximize(id)],['×','Close',()=>windowChange(id,'closed')]]){const b=make('button','expanse-window-button',symbol);b.type='button';b.setAttribute('aria-label',verb+' '+title);b.title=verb+' '+title;b.onclick=fn;windowButtons.push(b);}
   header.append(label,left,right,float,...windowButtons);if(optional.includes(id)){const hide=make('button','dock-control dock-hide','Hide');hide.type='button';hide.setAttribute('aria-label','Hide '+title);hide.onclick=()=>{hidePanel(id,true);render();save();visibility.get(id).focus();};header.append(hide);}header.onpointerdown=e=>start(e,id,'move');const body=make('div','dock-content');body.append(content);if(content.tagName==='DETAILS')content.open=true;
   const grip=action('↘',()=>{});grip.className='dock-resize';grip.title='Resize panel';grip.setAttribute('aria-label','Resize '+title+'; use arrow keys');grip.onpointerdown=e=>start(e,id,'resize');grip.onkeydown=e=>{
    if(!editing||!state.floating[id]||!e.key.startsWith('Arrow'))return;e.preventDefault();
    const f=state.floating[id],w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;
    const bounded=(value,min)=>Math.max(min,Math.min(1,value)),minW=Math.min(240/w,1),minH=Math.min(180/h,1);
    // Start from the visible bounds so reversing at a limit responds immediately.
    f.w=bounded(bounded(f.w,minW)+(e.key==='ArrowRight'?.03:e.key==='ArrowLeft'?-.03:0),minW);
    f.h=bounded(bounded(f.h,minH)+(e.key==='ArrowDown'?.03:e.key==='ArrowUp'?-.03:0),minH);
    floatRect(id);save();
   };
   panel.append(header,body,grip);panes.set(id,{panel,title,controls,float,grip,windowButtons});}
  document.addEventListener('pointermove',move);document.addEventListener('pointerup',end);document.addEventListener('pointercancel',end);
  toggle.onclick=()=>{editing=!editing;render();};reset.onclick=()=>{state=initial();editing=false;windowModes.clear();revealed.clear();maximized=null;if(key==='game')display.choose('character','auto');render();save();};new ResizeObserver(()=>{for(const id of ids)floatRect(id);}).observe(canvas);
  function adapt(){
   const mode=display.tabs()+'|'+(key==='game'&&display.character())+'|'+(display.phone?.()===true);
   if(mode===lastDisplay)return;
   lastDisplay=mode;
   if(gesture){end({pointerId:gesture.pointer,type:'pointercancel'});}
   render();
  }
  window.addEventListener('expanse:display',adapt);adapt();
 }
 const game=document.getElementById('tab-game');workspace(game,[['conversation','Conversation',document.querySelector('.conversation')],['map','Terrain Map',document.getElementById('player-map-panel')],['location','Location & Inventory',document.getElementById('location-panel')],['character','Character',document.getElementById('character-frame'),{optional:true}]],'game');
 const editor=document.getElementById('ed-grid');editor.classList.add('dock-managed');workspace(editor,[['library','Creator Library',document.querySelector('.creator-library')],['map','World Map',document.getElementById('designer-map-panel')],['inspector','Creator Inspector',document.querySelector('.creator-inspector')]],'editor');
 const active=()=>document.getElementById('tab-editor')?.classList.contains('active')?'editor':'game';
 window.ExpansePanels={open:()=>workspaces.get(active())?.open(),restoreAll:()=>workspaces.get(active())?.restoreAll(),reveal:id=>workspaces.get('game')?.reveal(id)};
 document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.shiftKey&&e.key.toLowerCase()==='p'){e.preventDefault();e.stopPropagation();window.ExpansePanels.open();}},true);
})();
