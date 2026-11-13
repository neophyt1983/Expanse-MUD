/* A local, server-quoted trade dialog. Identity IDs stay in protocol fields only. */
(()=>{
 const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const dialog=make('dialog');dialog.id='npc-trade';dialog.setAttribute('aria-labelledby','npc-trade-title');
 const title=make('h2','Trade');title.id='npc-trade-title';const close=make('button','Close');close.type='button';close.className='ed-btn';
 const header=make('header');header.append(title,close);const note=make('p'),status=make('p');status.setAttribute('role','status');status.id='npc-trade-status';
 const barterSection=make('section');barterSection.id='npc-trade-barter';barterSection.hidden=true;
 const tabs=make('div');tabs.className='npc-trade-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Trade direction');
 const body=make('div');body.id='npc-trade-items';body.setAttribute('role','tabpanel');
 const search=make('input');search.type='search';search.placeholder='Find an item';search.setAttribute('aria-label','Filter trade items by name');
 const refresh=make('button','Refresh prices');refresh.type='button';refresh.className='ed-btn';
 const state={target:null,room:null,packet:null,tab:'buy',serial:0,pending:false,focus:null,session:null,openRequest:null};
 let lastActivity=0;
 function active(){if(!state.session||Date.now()-lastActivity<5000)return;lastActivity=Date.now();send('tradeactive '+state.session);}
 dialog.addEventListener('pointerdown',active);dialog.addEventListener('keydown',active);dialog.addEventListener('input',active);
 const buttons={};for(const key of ['buy','sell']){const b=make('button',key==='buy'?'Buy':'Sell');b.type='button';b.className='ed-btn';b.setAttribute('role','tab');b.id='npc-trade-'+key;b.setAttribute('aria-controls',body.id);b.onclick=()=>{state.tab=key;draw();};b.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();buttons[key==='buy'?'sell':'buy'].click();buttons[state.tab].focus();}};buttons[key]=b;tabs.append(b);}
 dialog.append(header,note,tabs,search,refresh,status,body,barterSection);document.body.append(dialog);
 function send(command){if(!window.expanseCharacterLoaded||!ws||ws.readyState!==WebSocket.OPEN){status.textContent='Connect and load your character first.';return false;}ws.send(JSON.stringify({command}));return true;}
 function request(opening=false){if(!dialog.open||!state.target)return;state.pending=true;draw();const id=++state.serial;if(opening)state.openRequest=id;if(!send((opening?'tradeopen ':'tradeview ')+state.target+' '+id+(!opening&&state.session?' '+state.session:''))){state.pending=false;draw();}}
 function draw(){
  const focused=document.activeElement?.closest?.('[data-trade-key]');
  const focusKey=focused&&body.contains(focused)?focused.dataset.tradeKey:null;
  function restoreRowFocus(){if(!focusKey)return;const card=[...body.children].find(e=>e.dataset.tradeKey===focusKey);if(!card){buttons[state.tab].focus();return;}const action=card.querySelector('button');(action&&!action.disabled?action:card).focus();}
  for(const key of ['buy','sell']){buttons[key].setAttribute('aria-selected',String(key===state.tab));buttons[key].tabIndex=key===state.tab?0:-1;}
  body.setAttribute('aria-labelledby',buttons[state.tab].id);refresh.disabled=state.pending;body.replaceChildren();
  if(state.pending){status.textContent='Checking current prices and availability…';}
  else if(state.packet){status.textContent='You have '+state.packet.gold+' gold. '+(state.tab==='buy'?'Buy one item at a time.':'Sell one item at a time. Equipped items must be unequipped first.');}
  const allRows=state.packet?.[state.tab]||[];
  barterSection.replaceChildren();barterSection.hidden=!state.packet?.barter?.length;
  if(!barterSection.hidden){
   barterSection.append(make('h3','Barter-only possessions (not gold-sale stock)'));
   for(const item of state.packet.barter)barterSection.append(make('p',item.name+' · barter value '+item.value+' (not a purchase price)'));
   const talk=make('button','Discuss barter in Talk');talk.type='button';talk.className='ed-btn';talk.disabled=state.pending||typeof window.openNpcSocial!=='function';talk.onclick=()=>{const id=state.target;dismiss();window.openNpcSocial?.(id);};barterSection.append(talk);
  }
  const rows=allRows.filter(x=>x.name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()));
  if(!rows.length){body.append(make('p',state.pending?'Loading…':search.value?'No items match this filter. Clear the search to see the full list.':state.tab==='buy'?(state.packet?.buy_empty||'This NPC has no goods listed for sale for gold.'):'You have no carried items to list.'));restoreRowFocus();return;}
  for(const row of rows){
   const card=make('article');card.tabIndex=-1;card.dataset.tradeKey=JSON.stringify([state.tab,row.id,row.channel]);card.className='npc-trade-row'+(!row.enabled?' unavailable':'');
   const name=make('strong',row.name),details=make('p',(row.price===null?'No offer':row.price+' gold')+' · '+(row.quantity===null?'Unlimited':row.quantity+' '+(state.tab==='buy'?'available':'carried'))+(row.detail?' · '+row.detail:''));
   const reason=make('p',row.reason||'Available');reason.className='npc-trade-reason';
   const act=make('button',(state.tab==='buy'?'Buy ':'Sell ')+row.name);act.type='button';act.className='ed-btn';act.disabled=state.pending||!row.enabled;act.title=row.reason||((state.tab==='buy'?'Buy':'Sell')+' one for '+row.price+' gold');
   act.onclick=()=>{if(state.pending||!row.enabled)return;const action=state.tab;state.pending=true;draw();if(send('tradeitem '+[action,state.target,row.id,row.channel,row.price].join(' '))){append('user','> '+(action==='buy'?'Buy ':'Sell ')+row.name+' · '+row.price+' gold');request();}else{state.pending=false;draw();}};
   card.append(name,details,reason,act);body.append(card);
  }
  restoreRowFocus();
 }
 function dismiss(){if(ws?.readyState===WebSocket.OPEN){if(state.session)ws.send(JSON.stringify({command:'tradeclose '+state.session}));else if(state.openRequest!==null)ws.send(JSON.stringify({command:'tradecancel '+state.openRequest}));}state.session=null;state.openRequest=null;if(dialog.open)dialog.close();state.target=null;state.packet=null;state.pending=false;state.serial++;const old=state.focus;state.focus=null;if(old?.isConnected)old.focus();}
 close.onclick=dismiss;dialog.addEventListener('cancel',e=>{e.preventDefault();dismiss();});search.oninput=draw;refresh.onclick=request;
 function open(id,name){if(dialog.open)dismiss();if(!dialog.open)state.focus=document.activeElement;state.target=id;state.room=window.latestMap?.location?.id||null;state.packet=null;state.tab='buy';search.value='';title.textContent='Trade'+(name?' with '+name:'');note.textContent='Checking this nearby trader…';if(!dialog.open)dialog.showModal();close.focus();request(true);}
 function receive(msg){
  if(msg.type==='trade_view'){
   if(!dialog.open||msg.trader!==state.target||msg.request_id!==state.serial)return true;
   state.pending=false;if(msg.error){const reason=msg.error;dismiss();append('system','Trade unavailable: '+reason);return true;}
   const first=!state.packet;state.packet=msg;if(msg.trade_session!==state.session)lastActivity=0;state.session=msg.trade_session||state.session;if(first&&!msg.buy?.length&&msg.sell?.some(r=>r.price!==null))state.tab='sell';state.room=msg.room;title.textContent='Trade with '+msg.name;note.textContent=msg.note+' Location: '+msg.location;draw();return true;
  }
  if(['character_required','saved_exit'].includes(msg.type))dismiss();
  return false;
 }
 function update(m){if(!dialog.open)return;if(m.location?.id!==state.room||(m.location.npcs||[]).every(n=>n.id!==state.target)||m.location.npcs?.find(n=>n.id===state.target)?.trade_available===false){dismiss();append('system','Trade closed because you or the trader moved, the trader went off duty, or there are no eligible offers.');return;}if(!state.pending)request();}
 window.ExpanseTrade={open,receive,update,disconnect:dismiss};
})();
