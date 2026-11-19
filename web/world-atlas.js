/* Read-only, server-scoped whole-room atlas. No concept artwork or hidden data. */
(()=>{'use strict';
 const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
 const state={open:false,scope:null,packet:null,version:0,focus:null,mode:'layout',floor:0,scale:28,cx:0,cy:0,follow:true,selected:null,positions:[],frame:0,drag:null,creator:null,inert:[]};
 const root=make('dialog');root.id='world-atlas';if(root.open)root.close();root.hidden=true;root.setAttribute('role','dialog');root.setAttribute('aria-modal','true');root.setAttribute('aria-labelledby','world-atlas-title');
 root.addEventListener('cancel',e=>{e.preventDefault();closeAtlas();});
 const header=make('header'),title=make('h2','','Explored room atlas');title.id='world-atlas-title';
 const close=make('button','','Close atlas');close.id='world-atlas-close';close.title='Close atlas (Escape)';header.append(title,close);
 const minimizeWindow=make('button','expanse-window-button','−'),resizeWindow=make('button','expanse-window-button','▣');minimizeWindow.type=resizeWindow.type='button';minimizeWindow.setAttribute('aria-label','Minimize atlas');minimizeWindow.title='Minimize atlas';resizeWindow.setAttribute('aria-label','Restore atlas window');resizeWindow.title='Restore atlas window';close.classList.add('expanse-window-button');close.textContent='×';close.setAttribute('aria-label','Close atlas');header.insertBefore(minimizeWindow,close);header.insertBefore(resizeWindow,close);
 function restoreAtlas(){state.minimized=false;window.ExpanseWindowControls?.clear(root);state.inert.forEach(([el])=>el.inert=true);root.hidden=false;if(!root.open)root.showModal();close.focus();schedule();}
 function minimizeAtlas(){hideTip();if(!state.open)return false;state.minimized=true;state.drag=null;if(root.open)root.close();root.hidden=true;state.inert.forEach(([el,value])=>el.inert=value);return true;}
 minimizeWindow.onclick=()=>window.ExpanseWindowControls?.minimize(root,{minimize:minimizeAtlas,restore:restoreAtlas},'Atlas');
 resizeWindow.onclick=()=>{const restored=root.classList.toggle('atlas-window-restored');resizeWindow.textContent=restored?'□':'▣';resizeWindow.title=restored?'Maximize atlas':'Restore atlas window';resizeWindow.setAttribute('aria-label',resizeWindow.title);schedule();};
 const toolbar=make('div','wa-tools');
 const mode=make('select');mode.id='world-atlas-mode';mode.setAttribute('aria-label','Coordinate view');mode.append(new Option('Room layout','layout'),new Option('Authored world anchors','world'),new Option('Planet globe','globe'));
 const floor=make('select');floor.id='world-atlas-floor';floor.setAttribute('aria-label','Atlas floor');const floorLabel=make('label','','Floor');floorLabel.append(floor);
 const center=make('button','','Follow player');center.id='world-atlas-center';
 const fit=make('button','','Fit explored');fit.id='world-atlas-fit';
 const minus=make('button','','−');minus.setAttribute('aria-label','Zoom out');minus.id='world-atlas-minus';const plus=make('button','','+');plus.setAttribute('aria-label','Zoom in');plus.id='world-atlas-plus';
 const refresh=make('button','','Refresh');refresh.id='world-atlas-refresh';
 const search=make('input','wa-search');search.type='search';search.placeholder='Find a known room';search.setAttribute('aria-label','Search atlas rooms');search.id='world-atlas-search';
 const found=make('select','wa-found');found.setAttribute('aria-label','Matching atlas rooms');found.id='world-atlas-found';
 toolbar.append(mode,floorLabel,center,fit,minus,plus,refresh,search,found);
 const returnButton=make('button','','Back');returnButton.type='button';returnButton.id='atlas-back';returnButton.hidden=true;toolbar.prepend(returnButton);
 const stopTrip=make('button','','Stop walking');stopTrip.type='button';stopTrip.hidden=true;toolbar.append(stopTrip);
 stopTrip.onclick=()=>window.ExpansePlayerControls?.stopWalking();
 window.addEventListener('expanse:walking',e=>{stopTrip.hidden=!e.detail;});
 returnButton.onclick=()=>closeAtlas(true,true);let returnPage=null;
 const layer=document.createElement('select');layer.id='globe-layer';layer.setAttribute('aria-label','Globe map layer');
 for(const [value,name] of [['terrain','Terrain'],['height','Elevation'],['water','Waterways'],['political','Political borders'],['rock','Geology'],['weather','Weather']])layer.append(new Option(name,value));
 layer.hidden=true;toolbar.append(layer);
 const era=document.createElement('select');era.id='political-date';era.setAttribute('aria-label','Political border history');era.hidden=true;toolbar.append(era);
 let sky={},weatherMinute=null,survey=new Map(),politics=null,owners={},chartTimer=null,chartWorld=null,chartSeq=0;
 function chartKey(r){const p=r?.planet;if(!p)return null;const x=Math.floor(((p.lon+180)%360+360)%360/7.5),y=Math.max(0,Math.min(23,Math.floor((90-p.lat)/7.5)));return 'planet_'+x+'_'+y;}
 function territory(r){return politics?.countries?.[owners[chartKey(r)]];}
 function worldDate(minute){const d=Math.floor(minute/1500);return 'Y'+(Math.floor(d/208)+1)+' M'+(Math.floor(d%208/26)+1)+' D'+(d%26+1)+' · '+String(Math.floor(minute%1500/60)).padStart(2,'0')+':'+String(minute%60).padStart(2,'0');}
 function selectEdition(){
  owners={...politics?.owners};const events=politics?.events||[],v=era.value;
  if(v&&v!=='live')for(let i=events.length-1;i>=0;i--){const e=events[i];if(e.minute<=Number(v))break;if(e.old)owners[e.cell]=e.old;else delete owners[e.cell];}
 }
 era.onchange=()=>{selectEdition();refreshPanel();schedule();};
 function chartRequest(){
  clearTimeout(chartTimer);
  if(!state.open||state.mode!=='globe'||typeof ws==='undefined'||ws?.readyState!==1)return;
  const world=state.scope==='complete'?state.creator?.slug:config.running_game;
  if(world&&world!==config.running_game)return;
  if(chartWorld!==config.running_game){survey=new Map();politics=null;sky={};weatherMinute=null;chartWorld=config.running_game;}
  ws.send(JSON.stringify({command:'public chart',request_id:'chart-'+(++chartSeq),revision:politics?.revision??-1,surface:!survey.size,weather:layer.value==='weather',weather_minute:weatherMinute}));
  chartTimer=setTimeout(chartRequest,5000);
 }
 function receiveChart(value){
  if(!state.open||state.mode!=='globe'||value.world!==chartWorld||value.request_id!=='chart-'+chartSeq)return;
  if(value.sky){sky=value.sky;weatherMinute=value.weather_minute;}
  if(value.surface)survey=new Map(value.surface.map(r=>[r.id,r]));
  if(value.owners){
   const selected=era.value;politics=value;era.replaceChildren(new Option('Live borders','live'));
   for(const e of [...value.events].reverse())era.add(new Option(worldDate(e.minute),String(e.minute)));
   if([...era.options].some(o=>o.value===selected))era.value=selected;selectEdition();
  }
  if(value.surface||value.owners||value.sky){refreshPanel();schedule();}
 }

 function weatherAt(room){
  const live=window.latestMap;
  return room.id===live?.location?.id?live.weather:sky[chartKey(room)]||null;
 }
 const weatherColors={clear:'#a19763',sunny:'#c4ac63',rain:'#3979a1',snow:'#dae6e6',overcast:'#788994','partly cloudy':'#8fa49f',wind:'#5f9a89',thunderstorm:'#746790','severe thunderstorm':'#88536d',tornado:'#8b414c','dust storm':'#ae8561','rough seas':'#35577d',sheltered:'#726f65'};
 const weatherKey=make('details','wa-weather-key'),weatherLabel=make('summary','','Weather map key');
 weatherKey.hidden=true;weatherKey.append(weatherLabel);
 for(const [name,color] of Object.entries({...weatherColors,'No observation':'#49565c'})){
   const chip=make('span','',name);chip.style.cssText='display:inline-flex;align-items:center;gap:.3em;margin:.25em .55em';
   const dot=make('i');dot.style.cssText='background:'+color+';width:1em;height:1em;border:1px solid #cad3da';
   chip.prepend(dot);weatherKey.append(chip);
 }
 toolbar.append(weatherKey);
 function layerColor(room){
  const empty='#49565c';
  switch(layer.value){
   case 'political':return room.terrain==='ocean'?'#305570':territory(room)?.color||'#7c8178';
   case 'height':return !Number.isFinite(room.elevation_m)?empty:room.elevation_m<0?'#456b90':room.elevation_m<100?'#568a7a':room.elevation_m<500?'#b5b375':room.elevation_m<1500?'#af8359':'#f3e7db';
   case 'water':{
    const base=({ocean:'#315d86',water:'#588fb0',lake:'#528fb7',wetland:'#72897c',coast:'#b0a985',shore:'#b0a985'})[room.water?.kind];
    return base||(room.elevation_m>800?'#a7a49a':room.elevation_m>250?'#858c7b':'#697e70');
   }
   case 'rock':return ({volcano:'#d67965',cooled_lava:'#ad8072',lava_field:'#c47c65',collision_range:'#ac97b8',eroded_range:'#c3a281',alluvial:'#c6b987',lava_tube:'#927e9c',kimberlite_pipe:'#8ea89c',lamproite_pipe:'#8ea89c'})[room.geology?.landform]||empty;
   case 'weather':return weatherColors[weatherAt(room)?.weather]||empty;
  }
  return null;
 }
 function layerCaption(room){
  if(room.learnedOnly)return 'Only the name and position are known.';
  switch(layer.value){
   case 'political':return room.terrain==='ocean'?'Open water':territory(room)?.name||'Unclaimed land';
   case 'height':return Number.isFinite(room.elevation_m)?room.elevation_m+' m elevation':'No recorded elevation.';
   case 'water':return room.water?[room.water.name,room.water.kind,room.water.outlet?'Flows to '+room.water.outlet:'',room.water.downstream&&knownIndex.get(room.water.downstream)?'Downstream · '+knownIndex.get(room.water.downstream).name:'',room.water.requires_boat?'Boat required':''].filter(Boolean).join(' · '):'No recorded water feature.';
   case 'rock':return room.geology?[room.geology.landform.replaceAll('_',' '),room.geology.rock,room.geology.notes].filter(Boolean).join(' · '):'No recorded geology.';
   case 'weather':{const w=weatherAt(room);return w?[w.weather,w.temperature_c!=null?w.temperature_c+' °C':'',w.wind_kph!=null?'Wind '+w.wind_kph+' km/h':'',w.weather_warning].filter(Boolean).join(' · '):'No current weather observation here.';}
   default:return '';
  }
 }
 const basin=make('button','','Fit watershed');basin.type='button';basin.id='globe-fit-basin';basin.hidden=true;toolbar.append(basin);
 function fitWatershed(){
  const anchor=knownIndex.get(state.selected)||survey.get(state.selected)||current();if(!anchor?.planet)return;
  const rooms=globeRows().filter(r=>r.water&&!r.learnedOnly&&r.planet);
  const candidates=rooms.filter(r=>r.atlas_region&&r.atlas_region===anchor.atlas_region);
  if(candidates.length){window.ExpanseGlobe.fitBasin(candidates,main.clientWidth,main.clientHeight);state.follow=false;schedule();}
  else {window.ExpanseGlobe.closeUp(anchor.planet,main.clientWidth,main.clientHeight);schedule();}
 }
 basin.onclick=fitWatershed;
 function showLayers(){weatherKey.hidden=state.mode!=='globe'||layer.value!=='weather';era.hidden=state.mode!=='globe'||layer.value!=='political';chartRequest();basin.hidden=state.mode!=='globe'||layer.value!=='water';layer.hidden=state.mode!=='globe';layer.querySelector('[value=weather]').disabled=false;}
 layer.onchange=()=>{showLayers();refreshPanel();if(layer.value==='water'&&state.scope==='complete'&&knownIndex.get(state.selected)?.planet?.survey)fitWatershed();schedule();};
 window.addEventListener('expanse:player-map',()=>{if(state.open&&state.mode==='globe'&&layer.value==='weather'){refreshPanel();schedule();}});
 const scaleStatus=make('output','wa-scale');scaleStatus.id='world-atlas-scale';scaleStatus.setAttribute('aria-label','Room atlas scale');toolbar.append(scaleStatus);
 const summary=make('div','wa-summary');summary.id='world-atlas-summary';summary.setAttribute('role','status');
 const main=make('div','wa-main'),canvas=make('canvas');canvas.id='world-atlas-canvas';canvas.tabIndex=0;canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Room atlas. Arrow keys pan, plus and minus zoom. Search and select a room for its details.');
 const tip=make('div','wa-tooltip');tip.id='world-atlas-tooltip';tip.hidden=true;tip.setAttribute('role','tooltip');canvas.setAttribute('aria-describedby',tip.id);found.setAttribute('aria-describedby',tip.id);
 const empty=make('div','wa-empty','Waiting for your explored map…');main.append(canvas,empty,tip);
 const inspect=make('div','wa-inspect');inspect.id='world-atlas-inspect';inspect.setAttribute('aria-live','polite');
 const spread=make('div','wa-spread'),sidebar=make('aside','wa-place-panel');sidebar.hidden=true;
 spread.append(main,sidebar);
 const terrainKey=make('div','wa-terrain-legend');terrainKey.setAttribute('aria-label','Room terrain colors');
 const key=make('div','wa-key');key.append(make('span','wa-dot'),document.createTextNode('Current location · Drag or arrow keys to pan · Wheel or +/− to zoom · Dotted outlines mark places seen in passing. Diamonds mark places you learned about.'));
 root.append(header,toolbar,summary,spread,inspect,terrainKey,key);document.body.append(root);
 let knownPins=[],pendingFocus=null,knownIndex=new Map(),bookmarks=[],selectedPin=null,pinRequest=null,serial=0;
 const pinMessage=make('p','wa-pin-status');pinMessage.setAttribute('role','status');
 const put=(node,text,fn)=>{const b=make('button','',text);b.type='button';b.onclick=fn;node.append(b);return b;};
 function requestPins(payload){
  if(state.scope!=='explored'||typeof ws==='undefined'||!ws||ws.readyState!==1)return;
  const request='globe-pins-'+(++serial);pinRequest=request;
  ws.send(JSON.stringify({command:'ui globe-pins '+JSON.stringify(payload),request_id:request}));
 }
 function showFloor(room){mode.value='layout';mode.onchange();if(room)chosen(room,true);}
 function globeRows(){const rows=known().filter(r=>state.scope==='complete'||r.visited||r.learnedOnly||r.id===state.packet?.center);
  if(!survey.size)return rows;const knownCells=new Set(rows.filter(r=>r.planet?.cell).map(r=>r.id));return [...rows,...[...survey.values()].filter(r=>!knownCells.has(r.id))];}
 function refreshPanel(){
  sidebar.hidden=state.mode!=='globe';if(sidebar.hidden)return;
  const room=knownIndex.get(state.selected)||survey.get(state.selected)||current();
  sidebar.replaceChildren();
  if(!room){sidebar.append(make('p','','Waiting for the current room…'));return;}
  const isHere=state.scope==='explored'&&room.id===state.packet.center;
  sidebar.append(make('small','wa-kicker',isHere?'YOUR LOCATION':'SELECTED LOCATION'),make('h3','',room.name));
  const caption=layerCaption(room);if(layer.value==='water')sidebar.append(make('p','wa-key','Thin green-blue lines are streams. Wider blue lines are rivers. Arrows show downstream.'));if(caption)sidebar.append(make('p','wa-layer-caption',caption));
  const placement=room.planet;
  sidebar.append(make('p','',room.learnedOnly?'Learned from a person, item or quest.':isHere?'Your character is here.':room.publicChart?'Public surface survey':state.scope==='complete'?'Host view':'Visited'));
  const art=room.learnedOnly?null:(window.ExpanseMap?.customArt?.(room.pixel_art)||window.ExpanseMap?.getTerrainTile?.(room.terrain,room.id,room.route_surface));
  if(art){const swatch=make('canvas','wa-terrain-swatch');swatch.width=72;swatch.height=72;swatch.setAttribute('aria-label',room.terrain+' tile from the local map');const c=swatch.getContext('2d');c.imageSmoothingEnabled=false;c.drawImage(art,0,0,72,72);sidebar.append(swatch);}
  if(placement){sidebar.append(make('p','wa-coords',placement.lat+'° latitude · '+placement.lon+'° longitude'+(Number.isFinite(room.elevation_m)?' · '+room.elevation_m+' m elevation':'')));put(sidebar,'Center selected place',()=>{window.ExpanseGlobe.closeUp(placement,main.clientWidth,main.clientHeight);schedule();});}
  else sidebar.append(make('p','','No globe coordinates recorded. Use the room map to inspect this location.'));
  put(sidebar,'Room / floor detail',()=>showFloor(room));
  if(layer.value==='political'&&politics){
   const counts={};for(const gid of Object.values(owners))counts[gid]=(counts[gid]||0)+1;
   const key=make('details','wa-countries');key.append(make('summary','','Countries and territories'));
   for(const [gid,n] of Object.entries(counts).sort((a,b)=>b[1]-a[1])){const row=make('p','',politics.countries[gid].name+' · '+n);row.style.borderInlineStart='8px solid '+politics.countries[gid].color;row.style.paddingInlineStart='8px';key.append(row);}sidebar.append(key);
   const event=era.value==='live'?politics.events.at(-1):politics.events.find(e=>String(e.minute)===era.value);
   if(event)sidebar.append(make('p','',worldDate(event.minute)+' · '+event.text));
  }
  const options=known().filter(r=>r.id!==room.id);
  if(state.scope==='explored'&&options.length){
   sidebar.append(make('h4','','Known places'));
   const sorted=options.sort((a,b)=>Number(b.learnedOnly===true)-Number(a.learnedOnly===true)||a.name.localeCompare(b.name));
   for(const item of sorted.slice(0,8))put(sidebar,item.name+(item.learnedOnly?' · learned':''),()=>chosen(item,true));
  }
  if(state.scope==='complete'){
   const people=globeRows().filter(r=>r.host_players?.length);
   if(people.length){sidebar.append(make('h4','','Connected players'));for(const r of people)for(const name of r.host_players)put(sidebar,name+' · '+r.name,()=>chosen(r,true));}
  }else{
   sidebar.append(make('h4','','My destinations'));
   for(const b of bookmarks)put(sidebar,(b.id===selectedPin?'◆ ':'')+b.name,()=>chosen(knownIndex.get(b.room_id)||b.location,true));
   sidebar.append(pinMessage);
  }
 }
 function bookmarkEditor(room){
  if(state.scope!=='explored'||room.learnedOnly||(!room.visited&&room.id!==state.packet?.center))return;
  const existing=bookmarks.find(b=>b.room_id===room.id),form=make('form','wa-pin-form'),label=make('label','','Pin name '),name=make('input');name.maxLength=80;name.value=existing?.name||room.name;label.append(name);form.append(label);
  const add=make('button','',existing?'Rename pin':'Pin this place');add.type='submit';form.append(add);
  form.onsubmit=e=>{e.preventDefault();if(!name.value.trim())return;requestPins(existing?{action:'rename',id:existing.id,name:name.value}:{action:'create',room_id:room.id,name:name.value});};
  if(existing){put(form,selectedPin===existing.id?'Stop following pin':'Follow pin',()=>requestPins(selectedPin===existing.id?{action:'clear'}:{action:'select',id:existing.id}));
    put(form,'Remove pin',()=>requestPins({action:'remove',id:existing.id}));}
  inspect.append(form);
 }

 const namedRoom=r=>r.publicChart||state.scope==='complete'||r.current||r.id===state.packet?.center||r.visited===true||r.visibility==='visited'||r.learnedOnly;
 function hideTip(){if(hoverFrame)cancelAnimationFrame(hoverFrame);hoverFrame=0;hoverPoint=null;tip.hidden=true;tip.textContent='';tip.dataset.markerKey='';}
 tip.onpointerdown=e=>{const init={bubbles:true,pointerId:e.pointerId,pointerType:e.pointerType,isPrimary:e.isPrimary,button:e.button,buttons:e.buttons,clientX:e.clientX,clientY:e.clientY};hideTip();canvas.dispatchEvent(new PointerEvent('pointerdown',init));};
 function shortTipText(value,limit){const chars=Array.from(String(value||'').replace(/\s+/g,' ').trim());return chars.length>limit?chars.slice(0,limit-1).join('')+'…':chars.join('');}
 function showTip(p){
  const rows=(p?.rooms||[]).map(r=>knownIndex.get(r.id)||(r.publicChart?r:null)).filter(r=>r&&namedRoom(r));
  if(!rows.length){hideTip();return;}
  const room=rows.find(r=>r.id===state.selected)||rows.find(r=>r.id===state.packet?.center)||rows[0],name=shortTipText(room.name,52),parts=[];
  if(room.learnedOnly)parts.push('Learned location');
  if(rows.length>1)parts.push('+'+(rows.length-1)+' other place'+(rows.length===2?'':'s'));
  else if(!room.learnedOnly)parts.push(room.id===state.packet?.center?(state.scope==='complete'?'Selected room':'You are here'):room.publicChart?'Public survey':shortTipText(String(room.terrain||'').replaceAll('_',' '),18));
  const meta=parts.join(' · '),text=name+'\n'+meta,key=rows.map(r=>r.id).join('|');
  if(!tip.hidden&&tip.dataset.markerKey===key&&tip.textContent===text)return;
  tip.dataset.markerKey=key;tip.replaceChildren(make('strong','wa-tooltip-title',name),document.createTextNode('\n'),make('span','wa-tooltip-meta',meta));tip.hidden=false;
  tip.style.left=Math.max(4,Math.min(main.clientWidth-tip.offsetWidth-4,p.x+14))+'px';
  tip.style.top=Math.max(4,Math.min(main.clientHeight-tip.offsetHeight-4,p.y+14))+'px';
 }
 let hoverFrame=0,hoverPoint=null;function queueHover(e){hoverPoint={clientX:e.clientX,clientY:e.clientY};if(!hoverFrame)hoverFrame=requestAnimationFrame(()=>{hoverFrame=0;if(state.open&&!state.drag)showTip(hit(hoverPoint));});}
 function pointerPoint(e){const b=canvas.getBoundingClientRect();return {x:(e.clientX-b.left)*canvas.clientWidth/Math.max(1,b.width),y:(e.clientY-b.top)*canvas.clientHeight/Math.max(1,b.height)};}
 function hit(e){const {x,y}=pointerPoint(e);if(state.mode==='globe')return window.ExpanseGlobe.hit(x,y);return [...state.positions].reverse().find(p=>p.bounds?(x>=p.bounds.left&&x<p.bounds.right&&y>=p.bounds.top&&y<p.bounds.bottom):(x>=p.x-p.radius&&x<p.x+p.radius&&y>=p.y-p.radius&&y<p.y+p.radius));}
 function focusTip(){const room=known().find(r=>r.id===(document.activeElement===found?found.value:state.selected||state.packet?.center));if(!room||!namedRoom(room)){hideTip();return;}showTip(state.positions.find(p=>p.rooms.some(r=>r.id===room.id))||{rooms:[room],x:8,y:8});}

 const known=()=>{const rows=state.packet?.rooms||[];if(state.scope==='complete')return rows;
  const merged=new Map(rows.map(r=>[r.id,r]));for(const r of knownPins){const prev=merged.get(r.id);if(!prev||(state.mode==='globe'&&!prev.visited&&!prev.current))merged.set(r.id,r);}
  return [...merged.values()];};
 const nearby=r=>r.visibility==='visible'&&r.visited===false;
 const finite=n=>typeof n==='number'&&Number.isFinite(n);
 function point(room){if(state.mode==='world'){const w=room.tile_position||room.coordinates?.world;return w&&finite(w.x)&&finite(w.y)?{x:w.x,y:-w.y}:null;}return finite(room.x)&&finite(room.y)?{x:room.x,y:room.y}:null;}
 const visible=()=>known().filter(r=>r.z===state.floor&&point(r));
 const current=()=>state.packet?.rooms.find(r=>r.id===state.packet.center);
 function schedule(){if(state.minimized)return;if(!state.frame)state.frame=requestAnimationFrame(()=>{state.frame=0;draw();});}
 function chosen(room,pan=false){if(!room)return;state.selected=room.id;if(state.scope==='complete'){state.packet.center=room.id;if(state.creator)state.creator.room=room.id;updateSummary();}if(pan){if(state.mode==='layout'&&state.scale<12)state.scale=readingScale();if(state.mode==='globe')window.ExpanseGlobe.center(room.planet);if(Number.isInteger(room.z)){state.floor=room.z;floor.value=String(room.z);}state.follow=false;const p=point(room);if(p){state.cx=p.x;state.cy=p.y;}}details(room);schedule();}
 function details(room){refreshPanel();if(inspect.contains(document.activeElement)&&document.activeElement.matches('.wa-pin-form input')&&inspect.dataset.room===room?.id)return;
  inspect.dataset.room=room?.id||'';inspect.replaceChildren();if(!room){inspect.append(make('p','','Select a known room. This view does not move your character.'));return;}
  const tile=room.tile_position;
  if(tile)inspect.append(make('p','wa-coords','Tile X '+tile.x+' m · Y '+tile.y+' m · Z '+tile.z+' m'),make('p','wa-coords','Latitude '+tile.lat.toFixed(8)+'° · Longitude '+tile.lon.toFixed(8)+'° · Altitude '+tile.alt+' m'));
  const p=room.coordinates?.world;inspect.append(make('p','',room.name+(state.scope==='complete'?' ['+room.id+']':'')+(room.id===state.packet?.center?(state.scope==='complete'?' · Selected host room':' · You are here'):'')),make('p','',(finite(room.x)&&finite(room.y)?'Room layout X '+room.x+', Y '+room.y+', level '+room.z:'Room layout position not placed')+' · '+(room.learnedOnly?'Learned location · terrain not explored':String(room.terrain||'unspecified').replaceAll('_',' ')+(room.facility_landmark?' · '+room.facility_landmark.label:'')+(nearby(room)?' · Seen in passing':''))),make('p','',tile?'':p?'World X '+p.x+', Y '+p.y+(p.units==='m'?' m':' world units')+(p.region?' · '+p.region:''):state.mode==='globe'?'':'World position not placed.'));
  if(state.mode==='globe'){
   const pos=room.planet;
   inspect.append(make('p','',pos?(pos.regional?'Regional marker · ':pos.survey?'Survey placement · ':'')+'Latitude '+pos.lat+'° · Longitude '+pos.lon+'°':'No planetary position recorded for this room.'));
   if(room.host_players?.length)inspect.append(make('p','','Players here: '+room.host_players.join(', ')));
   if(state.scope==='explored'&&namedRoom(room)&&room.id!==state.packet.center){const walk=make('button','','Walk to '+room.name);walk.type='button';walk.onclick=()=>{closeAtlas(false);window.ExpansePlayerControls?.walkTo(room.id);};inspect.append(walk);const route=make('button','','Route to '+room.name);route.type='button';route.onclick=()=>{if(send('waypoint '+room.id))closeAtlas();};inspect.append(route);}
   bookmarkEditor(room);
   const others=globeRows().filter(r=>r.id!==room.id&&pos&&r.planet?.lon===pos.lon&&r.planet?.lat===pos.lat);
   if(others.length){const pick=make('select');pick.setAttribute('aria-label','Places at this position');pick.append(new Option('Other places at this position',''));for(const r of others)pick.append(new Option(r.name,r.id));pick.onchange=()=>chosen(knownIndex.get(pick.value));inspect.append(pick);}return;
  }
  const at=point(room);if(at){const same=visible().filter(r=>{const p=point(r);return p.x===at.x&&p.y===at.y;});if(same.length>1){inspect.append(make('p','',same.length+' known rooms use this map square. Select a room to see its tile coordinates.'));const stack=make('div','wa-stack');for(const r of same){const b=make('button','',r.name);b.onclick=()=>chosen(r);stack.append(b);}inspect.append(stack);}}
 }
 function updateSearch(){const q=search.value.trim().toLocaleLowerCase();found.replaceChildren(new Option('Select a known room…',''));const rows=(state.mode==='globe'?globeRows():known()).filter(r=>!q||(r.name+' '+r.id).toLocaleLowerCase().includes(q));for(const r of rows.slice(0,200))found.append(new Option(r.name+(Number.isInteger(r.z)?' · level '+r.z:' · position not placed'),r.id));if(state.selected&&Array.from(found.options).some(option=>option.value===state.selected))found.value=state.selected;found.title=rows.length>200?'Showing first 200 matches. Narrow your search.':rows.length+' known rooms';found.disabled=!rows.length;}
 function updateSummary(){if(!state.packet)return;
  terrainKey.hidden=state.mode!=='layout';
  if(!terrainKey.hidden){
   const present=new Set(visible().filter(r=>!r.learnedOnly).map(r=>r.terrain)),fragment=document.createDocumentFragment();
   for(const [k,label] of [['plains','Plains'],['forest','Forest'],['rainforest','Rainforest'],['mountain','Mountains'],['desert','Desert'],['wetland','Wetlands'],['river','River'],['lake','Lake'],['coast','Coast'],['ocean','Ocean'],['road','Road']]){
    if(!present.has(k))continue;
    const item=make('span','',label),swatch=make('i');swatch.style.background=colors[k];item.prepend(swatch);fragment.append(item);
   }
   if(state.scope==='explored' && state.floor===0 && groundRows.has(0)){
    const item=make('span','','Outside the public survey'), swatch=make('i');
    swatch.style.background='repeating-linear-gradient(135deg,#172a33 0 3px,#47616b 3px 4px)';
    item.prepend(swatch);fragment.append(item);
   }
   terrainKey.replaceChildren(fragment);
  }if(state.mode==='globe'){summary.textContent=(state.scope==='complete'?'Complete host globe':'Explored globe')+' · '+globeRows().filter(r=>r.planet).length+' placed rooms · Drag to rotate.'+(state.scope==='explored'?' The globe shows the public surface survey. Detailed rooms appear as you explore.':'');return;}const rows=state.packet.rooms,placed=rows.filter(r=>r.coordinates?.world).length;summary.textContent=(state.scope==='complete'?'Host: all rooms':'Visited rooms and remembered surroundings')+' · '+(state.scope==='complete'?rows.length+' rooms':rows.filter(r=>!nearby(r)).length+' visited/current rooms · '+rows.filter(nearby).length+' seen in passing')+(state.scope==='explored'&&knownPins.length?' · '+knownPins.filter(p=>!rows.some(r=>r.id===p.id)).length+' learned markers':'')+' · '+(rows.length-placed)+' without world placement. '+(state.mode==='layout'?'Tiles are rooms. × counts rooms at the same position. Terrain follows the public survey.':(current()?.tile_position?'Survey grid in metres. +X east, +Y north, +Z up.':'World anchors: +X east, +Y north.'))+(state.mode==='world'&&current()&&!point(current())?' '+(state.scope==='complete'?'The selected room':'Your current room')+' has no authored world position.':'')+(current()?' '+(state.scope==='complete'?'Selected: ':'You are at ')+current().name+' (level '+current().z+').':'');}
 function fitRooms(){if(state.mode==='globe'){window.ExpanseGlobe.fit();schedule();return;}const rows=visible();if(!rows.length){schedule();return;}const pts=rows.map(point),xs=pts.map(p=>p.x),ys=pts.map(p=>p.y),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);state.cx=(xmin+xmax)/2;state.cy=(ymin+ymax)/2;state.scale=Math.max(.000001,Math.min(64,(main.clientWidth-80)/Math.max(2,xmax-xmin+2),(main.clientHeight-80)/Math.max(2,ymax-ymin+2)));state.follow=false;schedule();}
 function readingScale(){
  return 24*(window.ExpanseDisplay?.tileZoom(main.clientWidth,main.clientHeight)||1);
 }
 function recenter(readable=false){const r=current();if(!r)return;if(readable&&state.mode==='layout')state.scale=readingScale();if(state.mode==='globe'){if(readable&&state.scope==='explored')window.ExpanseGlobe.closeUp(r.planet,main.clientWidth,main.clientHeight);else window.ExpanseGlobe.center(r.planet);}state.floor=r.z;floor.value=String(r.z);state.follow=true;state.selected=r.id;const p=point(r);if(p){state.cx=p.x;state.cy=p.y;}details(r);schedule();}
 function zoom(factor){if(state.mode==='globe'){window.ExpanseGlobe.zoom(factor);schedule();return;}state.scale=Math.min(128,Math.max(.000001,state.scale*factor));schedule();}
 const colors={plains:'#8da65f',forest:'#447f62',rainforest:'#377d70',mountain:'#a6a7a2',desert:'#c6ac75',wetland:'#6b9e9e',coast:'#bcb991',ocean:'#527f9d',water:'#527f9d',river:'#527f9d',lake:'#527f9d',valley:'#a0b27c',cave:'#8a8296',floor:'#9a8a75',interior:'#9a8a75',road:'#baaa83',snow:'#e5eeee',building:'#ad997e',unknown:'#607174'};
 const groundRows=new Map();
 const unsurveyedTile=document.createElement('canvas');
 unsurveyedTile.width=unsurveyedTile.height=16;
 const hatch=unsurveyedTile.getContext('2d');
 hatch.fillStyle='#172a33';hatch.fillRect(0,0,16,16);
 hatch.strokeStyle='#34505b';hatch.beginPath();
 hatch.moveTo(0,16);hatch.lineTo(16,0);hatch.stroke();
 function drawGround(c,w,h){
  if(state.mode!=='layout'||state.scope!=='explored')return;
  const scale=state.scale, floor=groundRows.get(state.floor);
  if(!floor)return;
  const left=state.cx-w/(2*scale), top=state.cy-h/(2*scale), right=left+w/scale;
  c.save();c.imageSmoothingEnabled=false;
  if(state.floor===0){
   c.fillStyle=c.createPattern(unsurveyedTile,'repeat');c.fillRect(0,0,w,h);
  }
  for(const [y,runs] of floor){
   if(y<top-.5||y>top+h/scale+.5)continue;
   const py=Math.round((y-top-.5)*scale),bottom=Math.round((y-top+.5)*scale);
   for(const [x,count,terrain] of runs){
    if(x+count<left-.5||x>right+.5)continue;
    const px=Math.round((x-left-.5)*scale),end=Math.round((x+count-left-.5)*scale);
    c.fillStyle=colors[terrain]||colors.unknown;
    c.fillRect(px,py,Math.max(1,end-px),Math.max(1,bottom-py));
    if(scale<12||!window.ExpanseMap?.getTerrainTile)continue;
    for(let i=Math.max(x,Math.ceil(left-.5));i<Math.min(x+count,right+.5);i++){
     const a=Math.round((i-left-.5)*scale),b=Math.round((i-left+.5)*scale);
     const tile=window.ExpanseMap.getTerrainTile(terrain,'survey-'+(i&3)+'-'+(y&3));
     if(tile)c.drawImage(tile,a,py,b-a,bottom-py);
    }
   }
  }
  c.restore();
 }
 function draw(){if(!state.open)return;const w=main.clientWidth,h=main.clientHeight,dpr=window.devicePixelRatio||1;canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.fillStyle='#101f27';c.fillRect(0,0,w,h);state.positions=[];
  scaleStatus.hidden=state.mode!=='layout';if(!scaleStatus.hidden)scaleStatus.textContent=state.scale<1?'Overview':Math.round(state.scale)+' px per room';
  if(state.mode==='globe'&&state.packet){const placed=globeRows().some(r=>r.planet);empty.hidden=placed;if(!placed)empty.textContent='No known place in this world has globe coordinates yet. Choose Room / floor detail.';state.positions=window.ExpanseGlobe.draw(c,w,h,globeRows(),state.packet.center,state.selected,colors,state.scope,bookmarks,layer.value==='terrain'?null:layerColor,layer.value==='water');return;}
  drawGround(c,w,h);c.fillStyle='#aac1c8';c.font='12px system-ui';c.fillText('N ↑',18,24);
  if(!state.packet){empty.hidden=false;return;}const rows=visible();empty.hidden=!!rows.length;empty.textContent=state.mode==='world'?'No authored world anchors on this floor. Use Room layout to see known rooms. No geographic positions have been guessed.':'No known rooms on this floor.';
  const groups=new Map();for(const r of rows){const p=point(r),id=p.x+','+p.y;if(!groups.has(id))groups.set(id,{p,rooms:[]});groups.get(id).rooms.push(r);}
  const size=state.mode==='world'?12:state.scale;
  for(const {p,rooms} of groups.values()){const px=w/2+(p.x-state.cx)*state.scale,py=h/2+(p.y-state.cy)*state.scale;const edge=n=>state.mode==='layout'?Math.round(n*dpr)/dpr:n,left=edge(px-size/2),right=edge(px+size/2),top=edge(py-size/2),bottom=edge(py+size/2),x=(left+right)/2,y=(top+bottom)/2;if(x< -(state.mode==='world'?40:size)||x>w+(state.mode==='world'?40:size)||y< -(state.mode==='world'?40:size)||y>h+(state.mode==='world'?40:size))continue;const r=rooms.find(room=>!room.learnedOnly)||rooms[0];if(r.learnedOnly){c.strokeStyle='#a6d9ee';c.lineWidth=2;c.beginPath();c.moveTo(x,y-7);c.lineTo(x+7,y);c.lineTo(x,y+7);c.lineTo(x-7,y);c.closePath();c.stroke();}else{c.fillStyle=colors[r.terrain]||colors.unknown;c.fillRect(left,top,Math.max(1,right-left),Math.max(1,bottom-top));if(size>=12&&window.ExpanseMap?.getTerrainTile){c.save();if(state.mode==='layout'){c.beginPath();c.rect(left,top,right-left,bottom-top);c.clip();}c.imageSmoothingEnabled=false;c.drawImage(window.ExpanseMap.customArt?.(r.pixel_art)||window.ExpanseMap.getTerrainTile(r.terrain,r.id,r.route_surface),state.mode==='world'?Math.round(left):left,state.mode==='world'?Math.round(top):top,state.mode==='world'?Math.round(size):right-left,state.mode==='world'?Math.round(size):bottom-top);window.ExpanseMap.drawFacility?.(c,r,Math.round(x-size/2),Math.round(y-size/2),Math.round(size));c.restore();}}
   if(!r.learnedOnly&&nearby(r)){c.save();c.strokeStyle='#b2d8bf';c.lineWidth=1;c.setLineDash([2,2]);if(state.mode==='world')c.strokeRect(x-size/2-1,y-size/2-1,size+2,size+2);else c.strokeRect(left+.5,top+.5,Math.max(0,right-left-1),Math.max(0,bottom-top-1));c.restore();}
   if(rooms.some(r=>r.id===state.selected)){c.strokeStyle='#f1dc98';c.lineWidth=2;if(state.mode==='world')c.strokeRect(x-size/2-3,y-size/2-3,size+6,size+6);else c.strokeRect(left+1,top+1,Math.max(0,right-left-2),Math.max(0,bottom-top-2));}
   if(rooms.length>1&&size>=24){c.fillStyle='#fff';c.strokeStyle='#071b24';c.lineWidth=3;c.font='bold 11px system-ui';const t=rooms.length>99?'×99+':'×'+rooms.length;c.strokeText(t,x+6,y-6);c.fillText(t,x+6,y-6);}
   state.positions.push({x,y,rooms,radius:Math.max(8,size/2+4),bounds:state.mode==='layout'?{left,right,top,bottom}:null});
  }
  if(state.mode==='layout'&&size<22)drawRegions(c,rows,w,h);
  const target=state.scope==='explored'&&state.selected!==state.packet.center
   ?state.positions.find(pos=>pos.rooms.some(room=>room.id===state.selected)):null;

  const r=current(),p=r&&r.z===state.floor?point(r):null;if(p){const x=w/2+(p.x-state.cx)*state.scale,y=h/2+(p.y-state.cy)*state.scale;if(x>=0&&x<=w&&y>=0&&y<=h){c.beginPath();c.arc(x,y,(state.mode==='layout'?Math.max(2,Math.min(8,size/2-2)):Math.max(8,size/2+4)),0,Math.PI*2);c.strokeStyle='#f6df8c';c.lineWidth=3;c.stroke();c.beginPath();c.moveTo(x,y-6);c.lineTo(x-5,y+5);c.lineTo(x+5,y+5);c.closePath();c.fillStyle='#fff5bb';c.fill();c.fillStyle='#fff5bb';c.font='bold 12px system-ui';const label=(state.scope==='complete'?'Selected · ':'You · ')+r.name;
   const width=Math.min(w-12,c.measureText(label).width+12),left=Math.max(4,Math.min(w-width-4,x-width/2)),top=Math.max(4,Math.min(h-25,y-Math.max(12,size/2)-24));
   c.fillStyle='#102027';c.fillRect(left,top,width,20);c.fillStyle='#ffedae';c.fillText(label,left+6,top+14,width-12);}}
  if(target){
   const room=target.rooms.find(room=>room.id===state.selected);
   const {x,y}=target;
   c.save();
   c.strokeStyle='#081b23';c.lineWidth=5;
   const radius=Math.max(7,Math.min(15,size/2));
   c.beginPath();c.moveTo(x,y-radius);c.lineTo(x+radius,y);c.lineTo(x,y+radius);c.lineTo(x-radius,y);c.closePath();c.stroke();
   c.strokeStyle='#71efff';c.lineWidth=3;c.stroke();
   const label='Selected · '+room.name;
   c.font='bold 12px system-ui';
   const width=Math.min(w-12,c.measureText(label).width+12);
   const left=Math.max(4,Math.min(w-width-4,x-width/2));
   const top=Math.max(4,Math.min(h-24,y+radius+5));
   c.fillStyle='#09272f';c.fillRect(left,top,width,20);
   c.fillStyle='#a8f6ff';c.fillText(label,left+6,top+14,width-12);
   c.restore();
  }
 }
 function drawRegions(c,rooms,w,h){
  const regions=new Map();
  for(const r of rooms){
   if(!r.atlas_region||!namedRoom(r)||r.learnedOnly)continue;
   const group=regions.get(r.atlas_region)||{n:0,x:0,y:0};
   group.n++;group.x+=r.x;group.y+=r.y;regions.set(r.atlas_region,group);
  }
  const placed=[];
  c.font='bold 13px system-ui';
  for(const [label,group] of [...regions].sort((a,b)=>b[1].n-a[1].n)){
   if(group.n<4)continue;
   const x=w/2+(group.x/group.n-state.cx)*state.scale,y=h/2+(group.y/group.n-state.cy)*state.scale;
   const width=c.measureText(label).width+12,left=x-width/2,top=y-22;
   if(left<4||top<4||left+width>w-4||top+20>h-4||placed.some(p=>left<p.right+3&&left+width>p.left-3&&top<p.top+23&&top+20>p.top-3))continue;
   c.fillStyle='#14232de8';c.fillRect(left,top,width,20);c.fillStyle='#e2e8df';c.fillText(label,left+6,top+14);placed.push({left,right:left+width,top});
  }
 }
 function packet(value){window.ExpanseMap?.loadPixelAssets(value?.pixel_assets);hideTip();if(!value||!Array.isArray(value.rooms))return;const first=!state.packet,old=state.packet?.center;state.packet=value;knownIndex=new Map(known().map(r=>[r.id,r]));const floors=[...new Set(known().map(r=>r.z).filter(Number.isInteger))].sort((a,b)=>a-b);floor.replaceChildren(...floors.map(z=>new Option(String(z),z)));if(first||!floors.includes(state.floor))state.floor=current()?.z??floors[0]??0;floor.value=String(state.floor);updateSearch();updateSummary();if(first){state.selected=value.center;if(state.mode==='layout')state.scale=readingScale();else fitRooms();state.follow=true;}if(state.follow&&(first||old!==value.center))recenter(first&&state.mode==='globe');else{const selected=known().find(r=>r.id===state.selected);if(!selected)state.selected=null;details(selected||null);}if(pendingFocus){const target=known().find(r=>r.id===pendingFocus);if(target){state.scale=Math.max(state.scale,28);chosen(target,true);pendingFocus=null;}}schedule();}
 function start(scope){basin.hidden=true;layer.hidden=true;layer.value='terrain';if(state.open&&state.scope===scope)return false;if(state.open)closeAtlas(false);groundRows.clear();state.open=true;state.scope=scope;state.packet=null;knownIndex.clear();state.selected=null;sidebar.hidden=true;pinRequest=null;pinMessage.textContent='';state.version++;state.focus=document.activeElement;state.follow=true;window.ExpanseGlobe?.reset();floor.disabled=false;state.mode='layout';mode.value='layout';state.scale=28;search.value='';found.replaceChildren();floor.replaceChildren();summary.textContent='Loading atlas…';empty.textContent='Loading atlas…';empty.hidden=false;inspect.replaceChildren();state.inert=[...document.body.children].filter(el=>el!==root&&el.tagName!=='SCRIPT'&&el.tagName!=='LINK').map(el=>[el,el.inert]);state.inert.forEach(([el])=>el.inert=true);root.hidden=false;if(!root.open)root.showModal();title.textContent=scope==='complete'?'Complete host atlas':'Explored room atlas';center.textContent=scope==='complete'?'Recenter selected':'Follow player';fit.textContent=scope==='complete'?'Fit all rooms':'Fit explored';key.lastChild.textContent=(scope==='complete'?'Selected host room':'Your current location')+' · Drag or arrow keys to pan · Wheel or +/− to zoom · Dotted outlines mark places seen in passing. Diamonds mark places you learned about.';close.focus();schedule();return true;}
 function send(command){return window.expanseAtlasSend?.(command)===true;}
 function openPlayer(){if(state.open&&state.scope==='explored'){if(state.minimized)restoreAtlas();return;}if(!start('explored'))return;if(!send('atlas open')){empty.textContent='Connect and load a character before opening your explored atlas.';summary.textContent='No live player map is available.';}}
 async function loadCreator(){const version=state.version,creator=state.creator;if(!creator)return;summary.textContent='Loading complete host atlas…';try{const value=await window.expanseAtlasCreator(creator);if(!state.open||state.scope!=='complete'||state.version!==version)return;if(value.error){state.packet=null;knownIndex.clear();empty.hidden=false;empty.textContent=value.error;summary.textContent='Complete maps require local host access.';schedule();return;}packet(value);}catch(e){if(state.open&&state.version===version){empty.hidden=false;empty.textContent='Could not load atlas: '+e.message;summary.textContent='No complete map loaded.';}}}
 function openCreator(creator){if(!creator?.slug)return;if(state.open&&state.scope==='complete'&&state.creator?.slug===creator.slug){if(state.minimized)restoreAtlas();return;}start('complete');state.creator=creator;loadCreator();}
 function closeAtlas(restore=true,back=false){clearTimeout(chartTimer);chartSeq++;era.hidden=true;hideTip();knownIndex.clear();window.ExpanseWindowControls?.clear(root);state.minimized=false;if(!state.open)return;if(state.scope==='explored')send('atlas close');state.version++;state.open=false;state.scope=null;state.packet=null;state.creator=null;state.positions=[];state.drag=null;pendingFocus=null;if(root.open)root.close();root.hidden=true;state.inert.forEach(([el,value])=>el.inert=value);state.inert=[];inspect.replaceChildren();found.replaceChildren();floor.replaceChildren();search.value='';summary.textContent='';canvas.width=1;canvas.height=1;const origin=returnPage;returnPage=null;returnButton.hidden=true;if(restore&&origin&&back)origin.restore();else if(restore&&origin)origin.dismiss();else if(restore&&state.focus?.isConnected)state.focus.focus();state.focus=null;}
 function disconnect(){closeAtlas(false);knownPins=[];bookmarks=[];selectedPin=null;pinRequest=null;pendingFocus=null;}
 function setKnownPins(pins){const next=(Array.isArray(pins)?pins:[]).filter(p=>p&&typeof p.id==='string').map(p=>({...p,learnedOnly:true}));if(JSON.stringify(next)===JSON.stringify(knownPins))return;knownPins=next;if(state.open&&state.scope==='explored'&&state.packet)packet({...state.packet});}
 function focusKnown(pin,origin=null){if(!pin?.id)return;const retained=knownPins.filter(p=>p.id!==pin.id);if(!state.packet?.rooms.some(r=>r.id===pin.id))retained.push(pin);setKnownPins(retained);openPlayer();returnPage=origin;returnButton.hidden=!origin;if(origin)returnButton.textContent='Back to '+origin.label;pendingFocus=pin.id;if(state.packet){const target=known().find(r=>r.id===pin.id);if(target){state.scale=Math.max(state.scale,28);chosen(target,true);pendingFocus=null;}}}

 function receive(value){if(value?.type==='public_chart'){receiveChart(value);return true;}
  if(value?.type==='globe_pins'||(value?.type==='error'&&value.request_id?.startsWith?.('globe-pins-'))){
   if(value.request_id!==pinRequest||!state.open||state.scope!=='explored')return true;
   pinRequest=null;
   if(value.type==='error'){pinMessage.textContent=value.text;return true;}
   bookmarks=value.travel_pins||[];selectedPin=value.selected_travel_pin||null;pinMessage.textContent=value.travel_guidance?'Following '+value.travel_guidance.name:'';
   setKnownPins(value.learned||[]);
   if(state.packet){knownIndex=new Map(known().map(r=>[r.id,r]));inspect.dataset.room='';details(knownIndex.get(state.selected)||survey.get(state.selected)||current());schedule();}
   window.ExpansePlayerLists?.requestNavigation?.();return true;
  }
  if(value?.type==='error'&&state.open&&state.scope==='explored'&&!state.packet){summary.textContent='Could not open explored atlas.';empty.textContent=value.text||'No live player map is available.';return false;}
  if(!['world_atlas','world_atlas_position','world_atlas_update'].includes(value?.type))return false;
  if(!state.open||state.scope!=='explored'||value.scope!=='explored')return true;
  if(value.type==='world_atlas')groundRows.clear();
  for(const [z,y,runs] of value.terrain_rows||[]){
   if(!groundRows.has(z))groundRows.set(z,new Map());
   groundRows.get(z).set(y,runs);
  }
  if(value.type==='world_atlas')packet(value);
  else if(state.packet&&value.type==='world_atlas_position'){
   if(!state.packet.rooms.some(r=>r.id===value.center))return true;
   const changed=state.packet.center!==value.center;state.packet.center=value.center;updateSummary();
   if(changed&&state.follow)recenter();else details(known().find(r=>r.id===state.selected));schedule();
  }else if(state.packet&&Array.isArray(value.rooms)){
   const rows=new Map(state.packet.rooms.map(r=>[r.id,r]));for(const id of Array.isArray(value.removed)?value.removed:[])rows.delete(id);for(const r of value.rooms)rows.set(r.id,r);
   packet({...state.packet,...value,type:'world_atlas',rooms:[...rows.values()]});
  }
  return true;
 }
 close.onclick=()=>closeAtlas();fit.onclick=fitRooms;center.onclick=()=>recenter(true);minus.onclick=()=>zoom(1/1.5);plus.onclick=()=>zoom(1.5);refresh.onclick=()=>{if(state.scope==='complete')loadCreator();else if(!send('atlas refresh')){summary.textContent='Connection unavailable. Close and reopen after reconnecting.';}};
 mode.onchange=()=>{state.mode=mode.value;showLayers();fit.textContent=state.mode==='globe'?'Whole planet':state.scope==='complete'?'Fit all rooms':'Fit explored';sidebar.hidden=state.mode!=='globe';knownIndex=new Map(known().map(r=>[r.id,r]));updateSearch();if(state.mode==='globe'&&state.scope==='explored')requestPins({action:'list'});floor.disabled=state.mode==='globe';title.textContent=state.scope==='complete'?(state.mode==='globe'?'Complete host globe':'Complete host atlas'):(state.mode==='globe'?'Explored globe':'Explored room atlas');key.lastChild.textContent=state.mode==='globe'?'Drag the surface to rotate · Click a place to center it · Wheel or +/− to zoom.':'Drag or use arrow keys to pan · × counts rooms sharing a position · Fit shows the overview.';updateSummary();if(state.mode==='layout'||(state.mode==='globe'&&state.scope==='explored'))recenter(true);else{fitRooms();recenter();}};floor.onchange=()=>{state.floor=Number(floor.value);state.follow=false;state.selected=null;details(null);updateSummary();fitRooms();};search.oninput=updateSearch;found.onchange=()=>{chosen(known().find(r=>r.id===found.value),true);focusTip();};found.onfocus=focusTip;found.onblur=hideTip;canvas.onfocus=focusTip;canvas.onblur=hideTip;canvas.onpointerleave=e=>{if(e.pointerType!=='touch'&&e.relatedTarget!==tip&&!tip.contains(e.relatedTarget))hideTip();};tip.onpointerleave=e=>{if(e.pointerType!=='touch'&&e.relatedTarget!==canvas)hideTip();};
 canvas.onpointerdown=e=>{
  if(e.button!==0||state.drag)return;
  canvas.focus();const point=pointerPoint(e),pressed=hit(e);
  const anchor=state.mode==='globe'?window.ExpanseGlobe.grabPoint(point.x,point.y):null;
  state.drag={id:e.pointerId,x:e.clientX,y:e.clientY,point,cx:state.cx,cy:state.cy,moved:false,anchor,hit:pressed&&{...pressed,rooms:[...pressed.rooms]},version:state.version,mode:state.mode,floor:state.floor};
  canvas.setPointerCapture(e.pointerId);
 };
 canvas.onpointermove=e=>{
  const d=state.drag;if(!d){queueHover(e);return;}if(d.id!==e.pointerId)return;
  hideTip();const dx=e.clientX-d.x,dy=e.clientY-d.y;
  d.moved=d.moved||Math.hypot(dx,dy)>5;if(!d.moved)return;
  const point=pointerPoint(e);
  if(state.mode==='globe'){
   if(!window.ExpanseGlobe.dragTo(d.anchor,point.x,point.y))return;
  }else{state.cx=d.cx-(point.x-d.point.x)/state.scale;state.cy=d.cy-(point.y-d.point.y)/state.scale;}
  state.follow=false;schedule();
 };
 canvas.onpointerup=e=>{
  const d=state.drag;if(!d||d.id!==e.pointerId)return;
  state.drag=null;
  if(d.moved||Math.hypot(e.clientX-d.x,e.clientY-d.y)>5||d.version!==state.version||d.mode!==state.mode||d.floor!==state.floor)return;
  // The map can follow a confirmed step during a press. Select the original
  // marker, never whichever different room has slid under the release point.
  const p=d.hit;if(!p)return;
  chosen(p.rooms.find(r=>r.id===state.packet.center)||p.rooms[0],state.mode==='globe'||(state.mode==='layout'&&state.scale<12));
  if(state.scope==='explored'&&state.mode==='layout'&&!e.shiftKey&&p.rooms.length===1){
   window.ExpansePlayerControls?.walkTo(p.rooms[0].id);
  }
  if(state.mode!=='globe')showTip(p);
 };
 canvas.onpointercancel=()=>{state.drag=null;hideTip();};canvas.onwheel=e=>{e.preventDefault();state.drag=null;hideTip();zoom(e.deltaY<0?1.2:1/1.2);};
 canvas.onkeydown=e=>{hideTip();if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();state.follow=false;if(state.mode==='globe'){window.ExpanseGlobe.rotate(({ArrowLeft:-12,ArrowRight:12}[e.key]||0),({ArrowUp:12,ArrowDown:-12}[e.key]||0));schedule();return;}state.cx+=({'ArrowLeft':-1,'ArrowRight':1}[e.key]||0)*60/state.scale;state.cy+=({'ArrowUp':-1,'ArrowDown':1}[e.key]||0)*60/state.scale;schedule();}else if(['+','=','-'].includes(e.key)){e.preventDefault();zoom(e.key==='-'?1/1.5:1.5);}};
 root.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();closeAtlas();}else if(e.key==='Tab'){const els=[...root.querySelectorAll('button,input,select,canvas')].filter(el=>!el.disabled&&el.getClientRects().length);const first=els[0],last=els.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
 window.addEventListener('expanse:sprite-ready',()=>{if(state.open)schedule();});
 new ResizeObserver(schedule).observe(main);window.addEventListener('resize',schedule);
 function openGlobe(creator){if(creator)openCreator(creator);else openPlayer();mode.value='globe';mode.onchange();}
 window.ExpanseWorldAtlas={openGlobe,setKnownPins,focusKnown,openPlayer,openCreator,close:closeAtlas,disconnect,receive,worldChanged:()=>disconnect()};
})();
