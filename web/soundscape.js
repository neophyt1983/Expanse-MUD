/* Original scores for Expanse. Notes are MIDI pitches, zero sustains silence. */
(()=>{
 'use strict';
 const venues={home:'House',tavern:'Tavern or inn',civic:'Government building',school:'School'};
 const live=document.createElement('div');live.className='location-announcement';live.setAttribute('role','status');live.setAttribute('aria-live','polite');live.setAttribute('aria-atomic','true');document.body.append(live);
 let cueKey='',transpose=0,mood='neutral',area='';
 let lastPlace='';const heardEvents=new Set();
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
 function active(){return !!room&&!document.hidden&&document.getElementById('tab-game')?.classList.contains('active');}
 function sync(){
   window.ExpanseWorldAudio?.mix(active()&&gesture?songFile:null,transpose,gain('music'),active()?gain('effects'):0);
 }
 function arm(){gesture=true;sync();}
 document.addEventListener('pointerdown',arm,{passive:true});document.addEventListener('keydown',arm);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stopSpeech();sync();});
 for(const id of ['play','tab-game']){const el=document.getElementById(id);if(el)new MutationObserver(sync).observe(el,{attributes:true,attributeFilter:['hidden','style','class']});}
 window.addEventListener('pagehide',()=>{room=null;stopSpeech();sync();});
 window.addEventListener('expanse:player-map',({detail:p})=>{
   if(!p?.location||!p.character)return;
   const prior=room,oldSession=session;
   room=p.location.id;session=p.character.id;
   const cue=p.music_cue||{track:p.soundtrack||'lantern',mood:'neutral',transpose:0,area:''};
   songFile=cue.file;arrival=cue.arrival;
   const signature=JSON.stringify([cue.track,cue.mood,cue.transpose,cue.area,session]);
   if(signature!==cueKey){
     cueKey=signature;track=cue.track;mood=cue.mood;transpose=Number(cue.transpose)||0;area=cue.area;
     const label=document.querySelector('.audio-settings .now-playing');
     if(label)label.textContent=track==='silence'?'Silent area':(area?area+' · '+mood+' · ':'')+(cue.title||'');
   }
   if(oldSession!==session)heardEvents.clear();
   const arrived=prior!==room||oldSession!==session;
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
   sync();if(active()&&gesture&&prior&&prior!==room&&oldSession===session&&gain('effects'))window.ExpanseWorldAudio.cue(arrival);
 });
 function controls(host){
   if(!host||host.querySelector('.audio-settings'))return;
   const group=document.createElement('fieldset');group.className='audio-settings';const legend=document.createElement('legend');legend.textContent='Sound';const playing=document.createElement('p');playing.className='now-playing';group.append(legend,playing);
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
})();
