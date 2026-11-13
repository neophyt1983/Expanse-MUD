/* Explicit fresh worlds, separate from creating another character in a saved world. */
(()=>{'use strict';
 const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const button=(text,fn)=>{const b=make('button',text);b.type='button';b.className='ed-btn';b.onclick=fn;return b;};
 const dialog=make('dialog');dialog.id='adventures';dialog.setAttribute('aria-labelledby','adventure-title');dialog.style.cssText='background:#141821;color:#d8dce4;border:1px solid #7fd1a4;border-radius:8px;width:min(700px,92vw);max-height:88vh;overflow:auto;padding:24px';
 const title=make('h2','New game');title.id='adventure-title';
 const description=make('p','New adventures begin at dawn. Choose Save during play to keep your progress.');
 const status=make('p');status.setAttribute('role','status');status.id='adventure-status';
 const form=make('form');form.id='adventure-form';const name=make('input');name.id='adventure-name';name.required=true;name.maxLength=80;name.autocomplete='off';
 const template=make('select');template.id='adventure-template';const mode=make('select');mode.id='adventure-mode';for(const [id,label]of[['single','Single player'],['host','Host a separate network adventure']]){const o=make('option',label);o.value=id;mode.append(o);}
 function field(label,input){const l=make('label',label+' ');l.style.display='block';l.style.margin='14px 0';l.append(input);return l;}
 const create=make('button','Start new game');create.id='adventure-create';create.type='submit';create.className='ed-btn';form.append(field('Game name',name),field('World',template),field('Play mode',mode),create);
 const existing=make('div');existing.id='adventure-existing';const close=button('Close',()=>dialog.close());close.id='adventure-close';
 const legacy=button('Continue the original world',()=>openLegacy());legacy.id='adventure-legacy';
 const otherGames=make('details');otherGames.append(make('summary','Other adventures'),existing,legacy);
 dialog.append(title,description,form,otherGames,close,status);document.body.append(dialog);
 let pending=false,config={},data={},requestId=null,requestKey=null;
 function enter(url){sessionStorage.removeItem("expanse.pending-save");sessionStorage.removeItem("expanse.active");location.href=url;}
 async function request(path,body){for(;;){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,control_token:config.control_token})}:undefined);const d=await r.json();if(r.status===202&&d.starting){status.textContent='Loading the world…';await new Promise(done=>setTimeout(done,750));continue;}if(!r.ok||d.error)throw Error(d.error||'Could not complete this action');return d;}}
 function busy(on){pending=on;for(const el of dialog.querySelectorAll('button,input,select'))el.disabled=on||((el===create||el===legacy)&&!template.options.length);}
 async function permission(){config=await request('/api/config');if(!config.can_manage_server)throw Error('Only this computer’s owner can create or switch adventures. Guests use Join.');if(config.connected_players)throw Error('Every player must return to Start (save first to keep progress) before switching adventures. Their current world has not been changed.');if(config.game_status==='ready'||config.game_status==='starting'){return confirm('Stop the currently running '+(config.mode==='host'?'hosted world':'world')+' without saving before opening another adventure? Unsaved progress will be discarded. Previously chosen saves are kept.');}return true;}
 async function open(id){if(pending)return;busy(true);try{if(!await permission())return;const r=await request('/api/adventures/open',{id,confirm_switch:true});enter(r.redirect);}catch(e){status.textContent=e.message;}finally{busy(false);}}
 async function openLegacy(){if(pending)return;busy(true);try{if(!await permission())return;const r=await request('/api/adventures/open',{id:'legacy',template:template.value==='official_expanse'?'default':template.value,mode:mode.value,confirm_switch:true});enter(r.redirect);}catch(e){status.textContent=e.message;}finally{busy(false);}}
 form.onsubmit=async e=>{e.preventDefault();if(pending)return;busy(true);status.textContent='Preparing a separate adventure…';try{if(!await permission()){status.textContent='Cancelled. No adventure was created.';return;}
  const key=JSON.stringify([name.value.trim(),template.value,mode.value]);if(key!==requestKey){requestKey=key;requestId=crypto.randomUUID().replaceAll('-','');}
  const r=await request('/api/adventures/create',{name:name.value.trim(),template:template.value,mode:mode.value,request_id:requestId});status.textContent='Adventure created. Opening…';
  const opened=await request('/api/adventures/open',{id:r.adventure.id,confirm_switch:true});enter(opened.redirect);
 }catch(e){status.textContent=e.message+' If opening failed, the separate adventure remains under Continue adventure.';await load(false).catch(()=>{});}finally{busy(false);}};
 async function load(clear=true){config=await request('/api/config');data=await request('/api/adventures');const selected=template.value;template.replaceChildren();for(const row of data.templates){const o=make('option',row.name);o.value=row.id;template.append(o);}if([...template.options].some(o=>o.value===selected))template.value=selected;else if([...template.options].some(o=>o.value==='expanse'))template.value='expanse';else if([...template.options].some(o=>o.value===config.running_game))template.value=config.running_game;
  existing.replaceChildren();for(const row of data.adventures){const div=make('p');div.append(make('span',row.name+(row.saved===false?' (unsaved session)':'')+' · '+(row.mode==='host'?'Hosted':'Single player')+' · '+row.created_at+' '),button('Continue',()=>open(row.id)));existing.append(div);}if(!data.adventures.length)existing.append(make('p','No saved adventures yet.'));create.disabled=!template.options.length;legacy.disabled=!template.options.length;if(clear)status.textContent=template.options.length?'':'Choose Import world on the start screen to add a .expanse file.';
 }
 window.openAdventureMenu=async function(playMode, requestedWorld){
  dialog.showModal();status.textContent='Reading adventures…';busy(true);
  try{await load();if(playMode){mode.value=playMode;const wanted=requestedWorld||localStorage.getItem('expanse.lastImportedWorld')||'expanse';if([...template.options].some(o=>o.value===wanted))template.value=wanted;}if(!name.value){const base='Adventure';let n=1;const names=new Set(data.adventures.map(a=>a.name));while(names.has(base+' '+n))n++;name.value=base+' '+n;}name.select();}
  catch(e){status.textContent=e.message;}finally{busy(false);name.focus();}
 };
 if(location.hash==='#new-game'){
  history.replaceState(null,'',location.pathname+location.search);
  window.openAdventureMenu('single');
 }
 dialog.addEventListener('cancel',e=>{if(pending)e.preventDefault();});
})();
