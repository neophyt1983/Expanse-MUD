/* Local comfort controls. Server commands and the server clock remain authoritative. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id),make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const defaults={north:'Numpad8',northeast:'Numpad9',east:'Numpad6',southeast:'Numpad3',south:'Numpad2',southwest:'Numpad1',west:'Numpad4',northwest:'Numpad7',up:'NumpadSubtract',down:'NumpadAdd',look:'Numpad5'};
 const labels={north:'North',northeast:'Northeast',east:'East',southeast:'Southeast',south:'South',southwest:'Southwest',west:'West',northwest:'Northwest',up:'Up a level',down:'Down a level',look:'Look'};
 const storage='expanse.controls.v1';let bindings={...defaults},history=[],index=0,draft='',capture=null,lastFocus=null;
 const valid=code=>/^(Key[A-Z]|Digit[0-9]|Numpad[0-9]|Numpad(Add|Subtract|Multiply|Divide|Decimal)|Arrow(Up|Down|Left|Right)|Home|End|PageUp|PageDown)$/.test(code);
 try{const saved=JSON.parse(localStorage.getItem(storage)||'null');if(saved&&typeof saved==='object'){const used=new Set();for(const action of Object.keys(defaults)){const code=saved[action];if((code===''||valid(code))&&!used.has(code)){bindings[action]=code;if(code)used.add(code);}else bindings[action]='';}}}catch{}
 function persist(){try{localStorage.setItem(storage,JSON.stringify(bindings));settingsStatus.textContent='Bindings saved on this device.';}catch{settingsStatus.textContent='Bindings work this session; this browser could not save them.';}}
 function remember(cmd){if(cmd&&!/^(clear|cls)$/i.test(cmd)&&history.at(-1)!==cmd){history.push(cmd);if(history.length>100)history.shift();}index=history.length;draft='';}
 function submit(cmd){
  if(/^(news|newspaper)(?:\s+editions)?$/i.test(cmd)&&window.ExpanseGazette){window.ExpanseGazette.open(/\s+editions$/i.test(cmd));return true;}
  if(/^(journal|quests)$/i.test(cmd)&&window.ExpansePlayerLists){window.ExpansePlayerLists.open('quests');return true;}
  if(!/^(clear|cls)$/i.test(cmd))return false;$('log').replaceChildren();window.ExpanseTranscript?.jumpToLatest();index=history.length;draft='';return true;
 }
 const controls=make('div');controls.id='player-controls';
 const focus=make('button','Use movement keys'),settings=make('button','Keyboard layout and movement bindings');focus.type=settings.type='button';focus.className=settings.className='ed-btn';focus.id='movement-key-focus';settings.id='player-keybindings';
 focus.title='Focus movement controls. Keypad or your bindings move; click the command box to type.';
 const hint=make('small','Movement keys work outside text fields. Up/Down in the command box recalls commands. clear or cls clears this conversation only.');
 const movementStatus=make('small');movementStatus.id='movement-status';movementStatus.setAttribute('role','status');
 let pendingMove=null,sequence=0,walk=null,stepTimer=null;
 const stopWalk=make('button','Stop walking');stopWalk.type='button';stopWalk.hidden=true;stopWalk.className='ed-btn';
 function cancelWalk(message=''){clearTimeout(stepTimer);queuedDestination=null;if(walk)window.dispatchEvent(new CustomEvent('expanse:walking',{detail:false}));walk=null;stopWalk.hidden=true;if(message)movementStatus.textContent=message;}
 stopWalk.onclick=()=>cancelWalk('Walking stopped.');
 document.addEventListener('keydown',e=>{if(walk&&e.key==='Escape'){cancelWalk('Walking stopped.');}});
 let queuedDestination=null, ackTimer=null;

 let held=null, repeatTimer=null;
 function stopHold(){clearTimeout(repeatTimer);held=null;}
 function holdAllowed(){
  if(document.hidden||document.querySelector('dialog[open]:not(#quest-compass)')||!ws||ws.readyState!==1)return false;
  const focus=document.activeElement;
  if(focus?.isContentEditable||focus?.closest?.('input,textarea,select,[role="textbox"]'))return false;
  return !!$('tab-game')?.classList.contains('active') && !$('app')?.inert;
 }
 function startHold(direction,key){
  if(!holdAllowed())return false;
  stopHold();cancelWalk();
  if(!move('go '+direction))return false;
  held={direction,key,id:pendingMove.id,socket:ws,started:performance.now(),first:true};
  return true;
 }
 function confirmedHold(message){
  if(!held||held.id!==message.movement_id)return;
  if(!message.step_taken||!holdAllowed()){stopHold();return;}
  const intent=held,delay=Math.max(0,(intent.first?350:140)-(performance.now()-intent.started));
  intent.first=false;
  repeatTimer=setTimeout(()=>{
   if(intent!==held||ws!==intent.socket||!holdAllowed()||!move('go '+intent.direction)){stopHold();return;}
   intent.id=pendingMove.id;intent.started=performance.now();
  },delay);
 }
 document.addEventListener('keyup',e=>{if(held?.key===e.code)stopHold();});
 window.addEventListener('blur',stopHold);
 document.addEventListener('visibilitychange',stopHold);
 window.addEventListener('expanse:character-reset',stopHold);
 document.addEventListener('focusin',()=>{if(held&&!holdAllowed())stopHold();});
 
 function walkTo(destination){
   stopHold();
   if(typeof ws==='undefined'||ws?.readyState!==1||!destination)return;
   if(window.latestMap?.location?.id===destination){if(walk)cancelWalk('Walking stopped.');return;}
   cancelWalk();
   if(pendingMove){
     queuedDestination={destination,options:arguments[1],socket:ws};
     movementStatus.textContent='Changing destination…';
     stopWalk.hidden=false;return;
   }
   const id='route-'+(++sequence);walk={id,socket:ws,steps:[],index:0};stopWalk.hidden=false;window.dispatchEvent(new CustomEvent('expanse:walking',{detail:true}));movementStatus.textContent='Finding a route…';
   ws.send(JSON.stringify({command:'walk to tile',request_id:id,destination,...window.ExpanseCountryView?.walkOptions(destination)}));
 }
 function nextStep(){
   if(!walk||walk.socket!==ws||ws.readyState!==1){cancelWalk();return;}
   const edge=walk.steps[walk.index];if(!edge){cancelWalk('Arrived.');return;}
   if(!move('go '+edge[1],edge))cancelWalk('Walking stopped.');
 }

 function resetMovement(){stopHold();clearTimeout(ackTimer);pendingMove=null;cancelWalk();movementStatus.textContent='';}
 // Do not buffer inputs behind a slow simulation step. A key/click means one
 // immediate step; a rejected typed command remains in the input field.
 function move(command,edge=null){
  if(!edge&&walk)cancelWalk();
  if(!edge&&command.startsWith('go ')&&window.latestMap?.visual?.exits?.some(e=>e.direction==='approach '+command.slice(3)))command='go approach '+command.slice(3);
  if(typeof command!=='string'||command.length>4096){append('error','Commands must be at most 4096 characters.');return false;}
  if(!ws||ws.readyState!==WebSocket.OPEN){append('error','Not connected.');return false;}
  if(pendingMove){movementStatus.textContent='Waiting for your previous step. No extra moves are queued.';return false;}
  const id='move-'+(++sequence);
  if(edge)walk.sentAt=performance.now();
  pendingMove={id,socket:ws,route:edge?walk.id:null};movementStatus.textContent='Moving…';
  clearTimeout(ackTimer);
  ackTimer=setTimeout(()=>{
   if(pendingMove?.id!==id)return;
   stopHold();pendingMove=null;cancelWalk('The last step has not been confirmed. Tap a destination to plan again.');
  },15000);
  try{ws.send(JSON.stringify({command,movement_id:id,...(edge?{walk_edge:edge}:{})}));}
  catch{resetMovement();append('error','Movement could not be sent.');return false;}
  return true;
 }
 function receive(message){
  if(message.type==='walk_plan'){
   if(walk?.id===message.request_id&&walk.socket===ws){
    if(message.error){cancelWalk(message.error);append('response',message.error);}
    else{walk.steps=message.steps||[];nextStep();}
   }return true;
  }
  if(['character_required','saved_exit'].includes(message.type)||message.event==='character_entered'){resetMovement();return;}
  if(pendingMove&&pendingMove.socket===ws&&message.movement_id===pendingMove.id){
   clearTimeout(ackTimer);const route=pendingMove.route;pendingMove=null;movementStatus.textContent='';
   confirmedHold(message);
   if(queuedDestination){
     const target=queuedDestination;queuedDestination=null;
     const options=target.options?.extent?{extent:target.options.extent,center:window.latestMap?.location?.id}:undefined;
     if(target.socket===ws)walkTo(target.destination,options);
     return;
   }
   if(route&&route===walk?.id){
    if(!message.walk_arrived){cancelWalk('Walking stopped.');return;}
    walk.index++;
    if(walk.index===walk.steps.length)cancelWalk('Arrived.');
    else{movementStatus.textContent='Walking · '+(walk.steps.length-walk.index)+' steps left';stepTimer=setTimeout(nextStep,Math.max(0,95-(performance.now()-walk.sentAt)));}
   }
  }
 }
 controls.append(focus,settings,hint);
 $('input-form')?.append(movementStatus,stopWalk);$('input')?.setAttribute('aria-label','Game command');
 focus.hidden=!$('tab-game');
 function focusMovement(){
  const game=$('tab-game');if(!game)return;
  if($('game-settings')?.open)$('game-settings').close();
  game.tabIndex=-1;game.focus();
 }
 focus.onclick=focusMovement;
 const dial=make('div');dial.id='player-sundial';dial.setAttribute('role','img');dial.setAttribute('aria-label','World clock unavailable');dial.hidden=true;
 $('character-strip')?.append(dial);
 const dialog=make('dialog');dialog.id='player-keybindings-dialog';dialog.setAttribute('aria-labelledby','player-keybindings-heading');
 const title=make('h2','Movement keybindings');title.id='player-keybindings-heading';const help=make('p','Choose a binding, then press a key. Escape cancels capture. Bindings use physical key positions, with or without Num Lock. They do not run while typing, in dialogs, the editor or the full-window atlas.');
 const list=make('div'),settingsStatus=make('p'),reset=make('button','Reset defaults'),close=make('button','Close');settingsStatus.setAttribute('role','status');reset.type=close.type='button';reset.className=close.className='ed-btn';close.id='player-keybindings-close';dialog.append(title,help,list,settingsStatus,reset,close);document.body.append(dialog);
 function drawBindings(){list.replaceChildren();for(const action of Object.keys(defaults)){const row=make('div'),label=make('span',labels[action]),bind=make('button',bindings[action]||'Unbound'),clear=make('button','Unbind');row.className='keybinding-row';bind.type=clear.type='button';bind.dataset.binding=action;bind.setAttribute('aria-label','Set '+labels[action]+' binding, currently '+(bindings[action]||'unbound'));bind.onclick=()=>{capture=action;settingsStatus.textContent='Press a key for '+labels[action]+'. Escape cancels.';};clear.onclick=()=>{capture=null;bindings[action]='';persist();drawBindings();list.querySelector(`[data-binding="${action}"]`).focus();};row.append(label,bind,clear);list.append(row);}}
 settings.onclick=()=>{
  const parent=$('game-settings');if(parent?.open)parent.close();
  capture=null;lastFocus=settings;drawBindings();settingsStatus.textContent='';dialog.showModal();close.focus();};
 function dismiss(){capture=null;dialog.close();
  if(lastFocus===settings&&settings.closest('#game-settings'))window.ExpanseSettings?.open();
  if(lastFocus?.isConnected)lastFocus.focus();
 }
 close.onclick=dismiss;dialog.addEventListener('cancel',e=>{e.preventDefault();if(capture){capture=null;settingsStatus.textContent='Binding capture canceled.';}else dismiss();});
 reset.onclick=()=>{capture=null;bindings={...defaults};persist();drawBindings();};
 $('input')?.addEventListener('keydown',e=>{
  if(e.isComposing||e.ctrlKey||e.altKey||e.metaKey||e.shiftKey)return;
  if(e.key==='ArrowUp'||e.key==='ArrowDown'){
   e.preventDefault();if(e.repeat||!history.length)return;
   if(index===history.length)draft=e.target.value;
   index=Math.max(0,Math.min(history.length,index+(e.key==='ArrowUp'?-1:1)));
   e.target.value=index===history.length?draft:history[index];e.target.setSelectionRange(e.target.value.length,e.target.value.length);
  }
 });
 document.addEventListener('keydown',e=>{
  if(capture){
   if(e.isComposing||e.repeat)return;
   e.preventDefault();e.stopPropagation();
   if(e.key==='Escape'){capture=null;settingsStatus.textContent='Binding capture canceled.';return;}
   if(e.ctrlKey||e.altKey||e.metaKey||e.shiftKey||!valid(e.code)){settingsStatus.textContent='Choose a letter, number, arrow, keypad, Home/End or Page key without modifiers.';return;}
   const action=capture;capture=null;
   for(const a of Object.keys(bindings))if(bindings[a]===e.code)bindings[a]='';
   bindings[action]=e.code;persist();drawBindings();list.querySelector(`[data-binding="${action}"]`).focus();return;
  }
  if(e.defaultPrevented||e.repeat||e.isComposing||e.ctrlKey||e.altKey||e.metaKey||e.shiftKey)return;
  if(!$('tab-game')?.classList.contains('active')||$('app')?.inert||document.querySelector('dialog[open]:not(#quest-compass)')||$('character-creation')?.classList.contains('show'))return;
  if(e.target.isContentEditable||e.target.closest?.('input,textarea,select,[contenteditable=""],[contenteditable="true"],[role="textbox"]'))return;
  const action=Object.keys(bindings).find(a=>bindings[a]&&bindings[a]===e.code);if(!action)return;
  e.preventDefault();
  if(!ws||ws.readyState!==WebSocket.OPEN){append('error','Not connected.');return;}
  const command=action==='look'?'look':'go '+action;if(action==='look')ws.send(JSON.stringify({command}));else if(!startHold(action,e.code))return;append('user','> '+command);remember(command);
 });
 function weatherView(m){
  const weather=m.weather;
  if(!weather||typeof weather.weather!=='string'||!weather.weather.trim())return null;
  const state=weather.weather.trim(),daylight=m.calendar?.daylight??weather.daylight;
  const known={clear:[daylight?'☀':'☾',daylight?'Sunny':'Clear sky'],sunny:[daylight?'☀':'☾',daylight?'Sunny':'Clear sky'],'partly cloudy':['◒','Partly cloudy'],overcast:['☁','Overcast'],rain:['☂','Rain'],snow:['❄','Snow'],wind:['≋','Wind'],thunderstorm:['ϟ','Thunderstorm'],'severe thunderstorm':['ϟ','Severe thunderstorm'],tornado:['↺','Tornado'],'dust storm':['≋','Dust storm'],'rough seas':['≈','Rough seas'],sheltered:['⌂','Sheltered']};
  const [symbol,label]=known[state]||['◇',state],parts=[label];
  if(Number.isFinite(weather.temperature_c))parts.push(weather.temperature_c+' °C');
  if(Number.isFinite(weather.wind_kph)&&weather.wind_kph>=0){
   const direction=typeof weather.wind_direction==='string'&&weather.wind_kph>0?' ('+weather.wind_direction.trim()+')':'';
   parts.push('Wind '+weather.wind_kph+' km/h'+direction);
  }
  if(weather.precipitation==='snow'&&state!=='snow')parts.push('Snow');
  const compact=parts.join(' · ');
  if(Number.isFinite(weather.weather_intensity)&&weather.weather_intensity>=0&&weather.weather_intensity<=1&&state!=='sheltered')parts.push('Strength '+Math.round(weather.weather_intensity*100)+'%');
  if(Number.isFinite(weather.rain_mm_h)&&weather.rain_mm_h>0)parts.push('Rain '+weather.rain_mm_h+' mm/h');
  const warning=typeof weather.weather_warning==='string'?weather.weather_warning.trim():'';
  if(weather.weather_phase==='warning')parts.push('Warning phase');
  if(warning)parts.push(warning);
  return {symbol,compact:compact+((warning||weather.weather_phase==='warning')?' · Weather warning':''),description:parts.join(' · '),warning:!!warning||weather.weather_phase==='warning',region:typeof weather.weather_region==='string'?weather.weather_region.trim():''};
 }
 const mapWeather=make('div');mapWeather.id='map-weather-controls';
 const weatherLabel=make('label'),weatherToggle=make('input'),weatherBadge=make('span');
 weatherToggle.id='map-weather-toggle';weatherToggle.type='checkbox';weatherToggle.checked=true;
 weatherBadge.id='map-local-weather';weatherBadge.setAttribute('role','img');weatherToggle.setAttribute('aria-controls',weatherBadge.id);
 try{weatherToggle.checked=localStorage.getItem('expanse.map.weather.v1')!=='hidden';}catch{}
 weatherLabel.append(weatherToggle,document.createTextNode('Weather'));mapWeather.append(weatherLabel,weatherBadge);
 let currentWeather=null;
 function drawMapWeather(){
  (document.querySelector('#player-visual-map .atlas-position-header')||document.querySelector('#player-visual-map .atlas-heading'))?.append(mapWeather);
  weatherBadge.hidden=!weatherToggle.checked||!currentWeather;
  weatherBadge.replaceChildren();weatherBadge.classList.toggle('local-weather-warning',!!currentWeather?.warning);
  if(!currentWeather)return;
  const icon=make('span',currentWeather.symbol);icon.setAttribute('aria-hidden','true');
  weatherBadge.append(icon,make('span',currentWeather.compact));weatherBadge.setAttribute('aria-label','Current location: '+currentWeather.description);weatherBadge.title=currentWeather.description+'\nCurrent location only, not weather across the explored map.'+(currentWeather.region?' Region: '+currentWeather.region+'.':'')+' Intensity is the current event strength, not a forecast probability.';
 }
 weatherToggle.onchange=()=>{try{localStorage.setItem('expanse.map.weather.v1',weatherToggle.checked?'shown':'hidden');}catch{}drawMapWeather();};
 drawMapWeather();
 function renderClock(m){
  currentWeather=weatherView(m);drawMapWeather();
  $('character-strip')?.append(dial);
  const c=m.calendar;const minutes=c?.minutes_per_day,daylight=c?.daylight_minutes,sunrise=c?.sunrise_minute;
  if(!c||!Number.isFinite(minutes)||minutes<=0||!Number.isFinite(daylight)||!Number.isFinite(sunrise)||!Number.isFinite(c.hour)||!Number.isFinite(c.minute)){dial.hidden=true;return;}
  dial.hidden=false;dial.replaceChildren();const clock=c.hour*60+c.minute,phase=((clock%minutes)+minutes)%minutes,angle=phase/minutes*360;
  const face=make('span');face.className='sundial-face';face.style.background=`conic-gradient(from ${sunrise/minutes*360}deg, #e4c968 0deg ${daylight/minutes*360}deg, #263a64 ${daylight/minutes*360}deg 360deg)`;
  const hand=make('span');hand.className='sundial-hand';hand.style.transform=`rotate(${angle}deg)`;face.append(hand);
  const time=String(c.hour).padStart(2,'0')+':'+String(c.minute).padStart(2,'0'),description=time+' · '+(c.daylight?'Daylight':'Night');
  const text=make('span',description);dial.append(face,text);
  let weatherDescription='';
  if(currentWeather){
   weatherDescription=currentWeather.description;
   const local=make('span');local.className='sundial-weather'+(currentWeather.warning?' local-weather-warning':'');
   const icon=make('span',currentWeather.symbol);icon.className='sundial-weather-icon';icon.setAttribute('aria-hidden','true');
   local.append(icon,make('span',weatherDescription));dial.append(local);
  }
  dial.setAttribute('aria-label','Expanse world clock '+description+'. '+minutes/60+' hours per day.'+(weatherDescription?' Local conditions: '+weatherDescription+'.':''));
  dial.title=(m.calendar_text||description)+'\nGold is daylight; blue is night. The clock uses server time.'+(weatherDescription?'\nLocal conditions: '+weatherDescription:'');
 }
 const previous=window.renderRoomPanel;window.renderRoomPanel=m=>{previous?.(m);renderClock(m);};
 if(window.latestMap)renderClock(window.latestMap);
 window.ExpansePlayerControls={controls,focusMovement,usesMovementKey:code=>!!code&&Object.values(bindings).includes(code),submit,remember,move,walkTo,stopWalking:()=>cancelWalk("Walking stopped."),receive,disconnect:resetMovement,minimizeBindings:()=>{if(capture)return false;dialog.close();return true;},restoreBindings:()=>{dialog.showModal();close.focus();}};
})();
