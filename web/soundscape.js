/* World-authored audio and bounded synthesized performances share Sound settings. */
(()=>{
 'use strict';
 const venues={home:'House',tavern:'Tavern or inn',civic:'Government building',school:'School'};
 const live=document.createElement('div');live.className='location-announcement';live.setAttribute('role','status');live.setAttribute('aria-live','polite');live.setAttribute('aria-atomic','true');document.body.append(live);
 let cueKey='',transpose=0,mood='neutral',area='';
 let lastPlace='',mediaWorld='',playingPerformance=null;const heardEvents=new Set(),heardPerformances=new Set();
 const singingButtons=[];
 const festivalBanner=document.createElement('div');festivalBanner.id='expanse-festival-banner';
 festivalBanner.hidden=true;festivalBanner.setAttribute('role','status');
 festivalBanner.style.cssText='border:1px solid #778f72;background:#172922;color:#e3f2de;padding:8px 12px;margin:6px 0;border-radius:6px;font-size:.92em;max-height:96px;overflow-y:auto;';
 document.getElementById('player-map-panel')?.append(festivalBanner);
 function showFestival(singing){
   const event=singing?.festival;
   festivalBanner.hidden=!event;
   if(!event){festivalBanner.textContent='';return;}
   const names=(Array.isArray(event.performers)?event.performers:[]).slice(0,12).map(p=>
     p.name+(p.instruments?.length?' — '+p.instruments.join(', '):''));
   const description=event.name+(event.description?' · '+event.description:'')+
       (names.length?' · Musicians here: '+names.join('; '):' · The performers have not arrived.');
   if(festivalBanner.textContent!==description)festivalBanner.textContent=description;
 }
 function singingAvailable(value){for(const button of singingButtons){button.hidden=!value;button.disabled=!value;}}
 let ctx,master,music,musicVolume,fx,timer,at=0,step=0,track='silence',room=null,session=null,gesture=false;
 let prefs={music:32,effects:40,announcements:75,mute_music:false,mute_effects:false,mute_announcements:false,muted:false,speak:false,publicSpeech:false};
 function restore(raw){try{const s=JSON.parse(raw||'{}');for(const k of ['music','effects','announcements'])if(Number.isFinite(s[k]))prefs[k]=Math.max(0,Math.min(100,s[k]));prefs.muted=s.muted===true;prefs.speak=s.speak===true;prefs.publicSpeech=s.publicSpeech===true;for(const k of ['music','effects','announcements'])prefs['mute_'+k]=s['mute_'+k]===true;}catch{}}
 try{restore(localStorage.getItem('expanse-audio'));}catch{}
 function gain(k){return prefs.muted||prefs['mute_'+k]?0:prefs[k]/100;}
 function stopSpeech(){
   if(window.ExpanseVoice)window.ExpanseVoice.stop();
   else window.speechSynthesis?.cancel();
 }
 function speak(text){
   if(!text||document.hidden||(window.ExpanseNativeAudio&&!window.ExpanseVoice)||gain('announcements')===0)return;
   if(window.ExpanseVoice){window.ExpanseVoice.speak(text,gain('announcements'));return;}
   if(window.speechSynthesis&&window.SpeechSynthesisUtterance){
     const utterance=new SpeechSynthesisUtterance(text);utterance.volume=gain('announcements');speechSynthesis.cancel();speechSynthesis.speak(utterance);
   }
 }
 function apply(){
   const announce=gain('announcements')>0;live.setAttribute('aria-live',announce&&!prefs.speak?'polite':'off');
   if(!announce)stopSpeech();
   sync();
 }
 let songFile=null,arrival=null;
 function active(){const tab=document.getElementById('tab-game'),play=document.getElementById('play');return !!room&&!document.hidden&&!!tab?.classList.contains('active')&&!tab.hidden&&tab.style.display!=='none'&&!play?.hidden&&play?.style.display!=='none';}
 function sync(){
   const audible=active()&&gesture;
   if(!audible||!gain('music'))playingPerformance=null;
   window.ExpanseWorldAudio?.mix(audible?songFile:null,transpose,audible?gain('music'):0,active()?gain('effects'):0);
 }
 function stopPerformance(){playingPerformance=null;window.ExpanseWorldAudio?.stopPerformance();}
 function disconnect(){room=null;session=null;songFile=null;arrival=null;cueKey='';lastPlace='';live.textContent='';singingAvailable(false);showFestival(null);stopSpeech();stopPerformance();sync();}
 function performances(packet){
   singingAvailable(!!packet.singing&&typeof packet.singing==='object'&&!Array.isArray(packet.singing));
   showFestival(packet.singing);
   let latest=null;const present=new Map();
   for(const event of Array.isArray(packet.singing?.events)?packet.singing.events.slice(-128):[]){
     if(!event||typeof event.id!=='string'||!event.id||event.room_id!==room||!Number.isFinite(event.age_seconds)||event.age_seconds<0||event.age_seconds>=20)continue;
     const key=JSON.stringify([mediaWorld,session,event.id]);
     const signature=JSON.stringify([event.score,event.performers]);present.set(key,signature);
     if(heardPerformances.has(key))continue;
     // Consume even when muted, hidden or awaiting a gesture: changing a sound
     // preference must not replay an old map snapshot or build an audio queue.
     heardPerformances.add(key);if(heardPerformances.size>256)heardPerformances.delete(heardPerformances.values().next().value);
     if(event.rendering==='synthesized'&&event.score&&(!latest||event.age_seconds<latest.event.age_seconds))latest={event,key,signature};
   }
   if(playingPerformance&&present.get(playingPerformance.key)!==playingPerformance.signature)stopPerformance();
   if(latest&&active()&&gesture&&gain('music')){
     playingPerformance=latest;
     Promise.resolve(window.ExpanseWorldAudio?.perform(latest.event)).then(played=>{if(!played&&playingPerformance===latest)playingPerformance=null;}).catch(()=>{if(playingPerformance===latest)stopPerformance();});
   }
 }
 function arm(){gesture=true;sync();}
 document.addEventListener('pointerdown',arm,{passive:true});document.addEventListener('keydown',arm);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stopSpeech();sync();});
 for(const id of ['play','tab-game']){const el=document.getElementById(id);if(el)new MutationObserver(sync).observe(el,{attributes:true,attributeFilter:['hidden','style','class']});}
 window.addEventListener('pagehide',disconnect);
 window.addEventListener('expanse:world-assets',disconnect);
 window.addEventListener('expanse:player-map',({detail:p})=>{
   if(!p?.location||!p.character){disconnect();return;}
   const prior=room,oldSession=session,oldWorld=mediaWorld;
   room=p.location.id;session=p.character.id;mediaWorld=p.media_world||'';
   if(prior!==room||oldSession!==session||oldWorld!==mediaWorld)stopPerformance();
   const cue=p.music_cue||{track:p.soundtrack||'lantern',mood:'neutral',transpose:0,area:''};
   songFile=cue.file;arrival=cue.arrival;
   const signature=JSON.stringify([cue.track,cue.mood,cue.transpose,cue.area,session]);
   if(signature!==cueKey){
     cueKey=signature;track=cue.track;mood=cue.mood;transpose=Number(cue.transpose)||0;area=cue.area;
     const label=document.querySelector('.audio-settings .now-playing');
     if(label)label.textContent=track==='silence'?'Silent area':(area?area+' · '+mood+' · ':'')+(cue.title||'');
   }
   if(oldSession!==session||oldWorld!==mediaWorld)heardEvents.clear();
   const arrived=prior!==room||oldSession!==session||oldWorld!==mediaWorld;
   lastPlace=[p.location.name,venues[cue.venue],area&&area!==p.location.name?area:''].filter(Boolean).join('. ');
   const notices=[];
   for(const event of p.location.services||[]){
     if(!event.command?.startsWith('attend ')||heardEvents.has(event.id))continue;
     heardEvents.add(event.id);if(heardEvents.size>128)heardEvents.delete(heardEvents.values().next().value);
     notices.push(event.label+' is in session at '+p.location.name+'.');
   }
   if(arrived||notices.length){
     const visual=[arrived?lastPlace:'',...notices].filter(Boolean);
     const spoken=[arrived&&prefs.speak?lastPlace:'',...(prefs.publicSpeech?notices:[])].filter(Boolean);
     const reader=[arrived&&!prefs.speak?lastPlace:'',...(!prefs.publicSpeech?notices:[])].filter(Boolean);
     live.setAttribute('aria-live',gain('announcements')&&reader.length?'polite':'off');
     live.textContent=(reader.length?reader:visual).join(' ');
     if(spoken.length)speak(spoken.join(' '));
   }
   sync();performances(p);if(active()&&gesture&&prior&&prior!==room&&oldSession===session&&oldWorld===mediaWorld&&gain('effects'))window.ExpanseWorldAudio.cue(arrival);
 });
 function controls(host){
   if(!host||host.querySelector('.audio-settings'))return;
   const group=document.createElement('fieldset');group.className='audio-settings';const legend=document.createElement('legend');legend.textContent='Sound';const playing=document.createElement('p');playing.className='now-playing';group.append(legend,playing);
   const singing=document.createElement('p');singing.className='singing-audio-help';singing.textContent='Music includes short synthesized singing and instrument cues. Sung words appear in Conversation; the sounds are musical tones, not recorded voices.';group.append(singing);
   function save(){try{const raw=JSON.stringify(prefs);localStorage.setItem('expanse-audio',raw);window.ExpanseVoice?.remember?.(raw);}catch{}apply();sync();}
   for(const [k,name] of [['music','Music'],['effects','Sound effects'],['announcements','Announcements']]){
     const l=document.createElement('label'),input=document.createElement('input'),out=document.createElement('output');
     l.style.display='block';input.type='range';input.min=0;input.max=100;input.value=prefs[k];input.setAttribute('aria-label',name+' volume');out.textContent=prefs[k]+'%';
     input.oninput=()=>{prefs[k]=Number(input.value);out.textContent=input.value+'%';save();};l.append(name+' ',input,' ',out);
     const quiet=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.checked=prefs['mute_'+k];box.setAttribute('aria-label','Mute '+name.toLowerCase());
     box.onchange=()=>{prefs['mute_'+k]=box.checked;save();};quiet.append(box,' Mute '+name.toLowerCase());
     const row=document.createElement('div');row.append(l,quiet);group.append(row);
   }
   const l=document.createElement('label'),mute=document.createElement('input');mute.type='checkbox';mute.checked=prefs.muted;mute.onchange=()=>{prefs.muted=mute.checked;save();};l.append(mute,' Mute all sound');group.append(l);
   if(window.ExpanseNativeAudio||window.ExpanseVoice||window.speechSynthesis){
     const label=document.createElement('label'),names=document.createElement('input');label.style.display='block';names.type='checkbox';names.checked=prefs.speak;
     names.onchange=()=>{prefs.speak=names.checked;save();if(names.checked)speak(lastPlace);else stopSpeech();};
     label.append(names,' Speak place names on arrival');group.append(label);
     const notices=document.createElement('label'),events=document.createElement('input');notices.style.display='block';events.type='checkbox';events.checked=prefs.publicSpeech;
     events.onchange=()=>{prefs.publicSpeech=events.checked;save();if(!events.checked)stopSpeech();};
     notices.append(events,' Speak local event announcements');group.append(notices);
   }
   host.append(group);
 }
 const host=document.getElementById('game-settings')||document.getElementById('settings');
 function loadDevice(){
   if(window.ExpanseNativeAudio&&window.ExpanseVoice?.saved)restore(window.ExpanseVoice.saved);
   host?.querySelector('.audio-settings')?.remove();controls(host);apply();sync();
 }
 window.addEventListener('expanse:device-audio',loadDevice);loadDevice();
 const actions=document.getElementById('conversation-menu')||document.querySelector('.quick-actions');
 for(const [label,command] of [['Songs','songs'],['Sing','sing']]){
   if(!actions||actions.querySelector('[data-action="'+command+'"]'))continue;
   const button=document.createElement('button');button.type='button';button.className='ed-btn';button.textContent=label;button.dataset.action=command;button.hidden=button.disabled=true;if(actions.id==='conversation-menu')button.setAttribute('role','menuitem');singingButtons.push(button);
   button.onclick=()=>{if(button.hidden||button.disabled)return;if(typeof ws==='undefined'||!ws||ws.readyState!==WebSocket.OPEN){append('error','Connect to the game first.');return;}ws.send(JSON.stringify({command}));append('user','> '+label);};actions.append(button);
 }
 window.ExpanseSoundscape={disconnect};
})();
