/* Save acknowledgement precedes socket close and optional playtest feedback. */
(()=>{
 'use strict';
 const make=(tag,text)=>{const node=document.createElement(tag);if(text)node.textContent=text;return node;};
 const button=(text,fn)=>{const node=make('button',text);node.type='button';node.className='ed-btn';node.onclick=fn;return node;};
 const state={enabled:false,bound:false,current:null,pending:null,saved:null,busy:false,checking:false,dirty:false,lastBeat:0,timer:null,configured:false,sessionVersion:0};
 let hooks={send:packet=>{if(typeof ws==='undefined'||ws?.readyState!==WebSocket.OPEN)return false;ws.send(JSON.stringify(packet));return true;},
   close:()=>{if(typeof ws!=='undefined')ws?.close();},leave:()=>{location.href=window.expanseStartingNewGame?'/mode.html#new-game':'/mode.html';},
   reconnect:()=>{if(typeof retryConnection==='function')retryConnection();},contextURL:url=>url};
 const notice=make('aside');notice.id='playtest-notice';notice.hidden=true;notice.setAttribute('aria-label','Playtest collection');
 const noticeText=make('p'),noticeActions=make('div');notice.append(noticeText,noticeActions);
 const recover=button('Feedback on last saved session',()=>openFeedback(state.saved));recover.hidden=true;
 const checkSave=button('Check save status',()=>recoverSave());checkSave.hidden=true;
 const reconnect=button('Reconnect to keep playing',()=>{state.pending=null;checkSave.hidden=reconnect.hidden=true;lockQuit(false);window.expanseLeaving=false;hooks.reconnect();});reconnect.hidden=true;
 noticeActions.append(recover,checkSave,reconnect);
 (document.getElementById('tab-game')||document.body).prepend(notice);
 const dialog=make('dialog');dialog.id='playtest-feedback';dialog.setAttribute('aria-labelledby','playtest-feedback-title');
 const title=make('h2','Game saved — session feedback');title.id='playtest-feedback-title';
 const intro=make('p','Your character and world are saved. The session has ended. These optional answers help improve Expanse. Please avoid passwords or other private information.');
 const form=make('form'),fields={},ratings={};
 for(const [key,label,ends] of [
   ['enjoyment','How much did you enjoy this session?','1 = not enjoyable · 5 = very enjoyable'],
   ['clarity','How clear was it what to do?','1 = confusing · 5 = very clear'],
   ['difficulty','How difficult did this session feel?','1 = too easy · 3 = about right · 5 = too hard']]){
   const group=make('label'),caption=make('span',label),select=make('select'),help=make('small',ends);
   select.name=key;select.id='playtest-'+key;group.htmlFor=select.id;select.append(new Option('No rating',''));
   for(let i=1;i<=5;i++)select.append(new Option(String(i),String(i)));
   group.append(caption,select,help);ratings[key]=select;form.append(group);
 }
 for(const [key,label,placeholder] of [
   ['liked','What did you like?','An encounter, character, place or feature…'],
   ['disliked','What was frustrating or difficult to use?','Describe where you got stuck or what felt unclear…'],
   ['avoided_places','Which places did you avoid or feel cautious about?','Use place names if you remember them; “none” is useful too.'],
   ['avoided_why','Why did you avoid those places?','Danger, navigation, lack of interest, performance, or another reason…'],
   ['next_goal','What would you like to try next?','Your next goal, or a feature you would like to explore…']]){
   const labelNode=make('label'),area=make('textarea');area.name=key;area.id='playtest-'+key;area.maxLength=1600;area.rows=3;area.placeholder=placeholder;
   labelNode.htmlFor=area.id;labelNode.append(make('span',label),area);fields[key]=area;form.append(labelNode);
 }
 const status=make('p');status.id='playtest-feedback-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const actions=make('div');actions.className='playtest-feedback-actions';
 const submit=make('button','Send feedback & leave');submit.type='submit';submit.className='ed-btn primary';
 const skip=button('Skip feedback & leave',()=>sendFeedback(true));
 const leaveNow=button('Leave now — game is saved',()=>hooks.leave());leaveNow.hidden=true;
 actions.append(submit,skip,leaveNow);form.append(status,actions);dialog.append(title,intro,form);document.body.append(dialog);
 dialog.addEventListener('cancel',event=>{event.preventDefault();sendFeedback(true);});
 form.onsubmit=event=>{event.preventDefault();sendFeedback(false);};
 function setStatus(text){window.expanseSaveStatus?.(text);if(state.pending){notice.hidden=false;noticeText.textContent=text;}}
 function lockQuit(locked){for(const node of document.querySelectorAll('[data-playtest-save-quit]'))node.disabled=locked;}
 async function api(path,body){
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
   try{
     const result=await fetch(hooks.contextURL('/api/playtest/'+path),{credentials:'same-origin',cache:'no-store',signal:controller.signal,
       ...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
     let data;try{data=await result.json();}catch{throw Error('The playtest service did not respond.');}
     if(!result.ok||data.error)throw Error(data.error||'Could not reach the playtest service.');
     return data;
   }finally{clearTimeout(timer);}
 }
 async function refresh(){
   const version=state.sessionVersion;
   try{
     const data=await api('status');state.enabled=data.enabled===true;state.configured=true;if(version===state.sessionVersion)state.current=data.current_session;
     if(!state.pending){notice.hidden=!state.enabled&&!data.collection_degraded;noticeText.textContent=data.notice||'';}
     if(!state.saved&&data.pending_feedback?.length)state.saved=data.pending_feedback[0].session_id;
     recover.hidden=!!state.current||!state.saved;
     return data;
   }catch{return null;}
 }
 function bind(options={}){
   hooks={...hooks,...options};state.bound=true;
   if(!state.configured)refresh();
 }
 function saveAndQuit(){
   if(state.pending)return true;
   if(window.ExpansePixelStudio?.canLeave()===false)return false;
   window.ExpansePlayerControls?.stopWalking();
   const request_id='playtest-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
   state.pending={request_id,disconnected:false};lockQuit(true);
   checkSave.hidden=reconnect.hidden=true;
   if(!hooks.send({command:'save_exit',request_id})){
     state.pending=null;lockQuit(false);window.expanseSaveStatus?.('Connect to the game before saving.');return false;
   }
   setStatus('Saving your character and world… Keep this page open.');
   clearTimeout(state.timer);state.timer=setTimeout(()=>recoverSave(),12000);
   return true;
 }
 function completed(sessionId){
   clearTimeout(state.timer);state.pending=null;state.current=null;state.saved=sessionId||null;state.sessionVersion++;
   checkSave.hidden=reconnect.hidden=true;lockQuit(false);
   window.expanseLeaving=true;window.expanseCharacterLoaded=false;
   hooks.close();
   window.ExpansePlayerControls?.disconnect();window.ExpanseDamage?.clear();
   document.getElementById('character-creation')?.classList.remove('show');
   window.expanseSaveStatus?.('Saved successfully. Session ended.');
   if(sessionId){state.enabled=true;openFeedback(sessionId);}else hooks.leave();
 }
 function receive(message){
   if(message.event==='character_entered'){
     state.sessionVersion++;
     state.current=message.playtest?.session_id||null;
     recover.hidden=true;if(dialog.open)dialog.close();
     if(message.playtest?.notice){state.enabled=message.playtest.enabled!==false;notice.hidden=false;noticeText.textContent=message.playtest.notice;}
     state.dirty=true;
     return false;
   }
   if(message.type==='error'&&(message.save_failed||/^Save failed/i.test(message.text||''))){
     if(state.pending&&(!message.request_id||message.request_id===state.pending.request_id)){
       clearTimeout(state.timer);state.pending=null;lockQuit(false);checkSave.hidden=reconnect.hidden=true;
       window.expanseLeaving=false;
       window.expanseSaveStatus?.('Save failed. Your session is still open; fix the problem and try Save & quit again.');
       if(state.enabled)refresh();
     }
     return false;
   }
   if(message.type==='saved_exit'){
     if(message.checkpoint_saved===true)completed(message.playtest?.questionnaire?message.playtest.session_id:null);
     else{state.pending=null;clearTimeout(state.timer);window.expanseLeaving=true;hooks.close();hooks.leave();}
     return true;
   }
   return false;
 }
 async function recoverSave(){
   if(!state.pending||state.checking)return;
   state.checking=true;checkSave.disabled=true;
   const request=state.pending;
   try{
     const data=await api('status');
     if(state.pending!==request)return;
     const match=data.pending_feedback?.find(item=>item.request_id===request.request_id);
     if(match){completed(match.session_id);return;}
     checkSave.hidden=false;reconnect.hidden=!request.disconnected;
     setStatus(request.disconnected?'Connection lost before a save acknowledgement. No second save was sent. Check again, or reconnect to inspect your saved games.':'The save has not been acknowledged yet. Keep this page open, or check save status again.');
   }catch{
     if(state.pending!==request)return;
     checkSave.hidden=false;reconnect.hidden=!request.disconnected;
     setStatus('Could not confirm the save. No second save was sent. Check status again when the connection is available.');
   }finally{state.checking=false;checkSave.disabled=false;}
 }
 function disconnected(){
   if(state.pending){state.pending.disconnected=true;recoverSave();return true;}
   state.current=null;state.sessionVersion++;
   return false;
 }
 function openFeedback(sessionId){
   if(!sessionId||state.current)return;
   if(dialog.dataset.session!==sessionId){form.reset();status.textContent='';dialog.dataset.session=sessionId;}
   state.saved=sessionId;recover.hidden=true;
   if(!dialog.open)dialog.showModal();
   title.tabIndex=-1;title.focus();
 }
 async function sendFeedback(skipped){
   if(state.busy||!state.saved)return;
   state.busy=true;submit.disabled=skip.disabled=true;leaveNow.hidden=true;status.textContent=skipped?'Skipping feedback…':'Sending feedback…';
   const body={session_id:state.saved,skipped};
   if(!skipped){
     body.ratings={};for(const [key,input] of Object.entries(ratings))if(input.value)body.ratings[key]=Number(input.value);
     for(const [key,input] of Object.entries(fields))body[key]=input.value;
   }
   try{await api('feedback',body);state.saved=null;dialog.close();hooks.leave();}
   catch(error){status.textContent='Your game is already saved. '+error.message+' Your answers are still here; retry, skip, or leave now.';leaveNow.hidden=false;}
   finally{state.busy=false;submit.disabled=skip.disabled=false;}
 }
 function noteActivity(){state.dirty=true;}
 for(const kind of ['pointerdown','keydown','wheel','touchstart'])document.addEventListener(kind,noteActivity,{passive:true,capture:true});
 async function heartbeat(){
   if(!state.enabled||!state.current||state.pending||document.visibilityState==='prerender')return;
   const now=Date.now();if(now-state.lastBeat<5000)return;state.lastBeat=now;
   const active=state.dirty&&document.visibilityState==='visible';state.dirty=false;
   try{await api('activity',{visible:document.visibilityState==='visible',active});}catch{/* Analytics never blocks play. */}
 }
 document.addEventListener('visibilitychange',heartbeat);
 setInterval(heartbeat,15000);
 window.ExpansePlaytest={bind,receive,saveAndQuit,disconnected,refresh};
 // Standalone/local hosts may not expose telemetry. Save & quit still works and
 // follows their existing acknowledgement; the collection notice stays hidden.
 if(typeof config!=='undefined'&&config.render_web)refresh();
})();
