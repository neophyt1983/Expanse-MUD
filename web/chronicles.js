/* The server scopes every page to the connected character. */
(()=>{'use strict';
 const el=(tag,text)=>{const node=document.createElement(tag);if(text)node.textContent=text;return node;};
 const panel=el('dialog');panel.id='chronicle-reader';panel.className='style-dialog';
 const head=el('header'),title=el('h2','World chronicles'),exit=el('button','Close');head.append(title,exit);
 title.id='chronicle-title';panel.setAttribute('aria-labelledby',title.id);
 const controls=el('div'),section=el('select'),query=el('input'),full=el('input'),label=el('label');
 for(const [id,name] of [['geology','Geology · Deep time'],['civilization','Civilization · Medium time'],['individual','Individuals · Recent time'],['natural','Creature Compendium'],['monstorium','Monstorium'],['knowledge','Frontiers of knowledge'],['sources','Research bibliography']])section.add(new Option(name,id));
 section.setAttribute('aria-label','History');query.type='search';query.maxLength=120;
 query.placeholder='Find a name or event';query.setAttribute('aria-label','Search history');
 full.type='checkbox';label.append(full,document.createTextNode(' Host view'));label.hidden=true;
 controls.className='chronicle-controls';controls.append(section,query,label);
 const info=el('p'),list=el('ol'),pager=el('div'),back=el('button','Previous'),next=el('button','Next'),count=el('span');
 list.className='chronicle-entries';list.tabIndex=0;list.setAttribute('aria-label','Chronicle entries');info.className='chronicle-info';pager.className='chronicle-pager';pager.append(back,count,next);
 panel.append(head,controls,info,list,pager);document.body.append(panel);
 let page=1,sequence=0,timer;
 function request(){
  clearTimeout(timer);if(!panel.open)return;
  if(typeof ws==='undefined'||ws?.readyState!==1){info.textContent='Enter the world with a character to read its histories.';return;}
  ws.send(JSON.stringify({command:'ui chronicles '+JSON.stringify({section:section.value,query:query.value,page,full:full.checked}),request_id:'chronicle-'+(++sequence)}));
 }
 function resetPage(){page=1;request();}
 section.onchange=()=>{query.value='';resetPage();};full.onchange=resetPage;
 query.oninput=()=>{clearTimeout(timer);sequence++;page=1;timer=setTimeout(request,160);};
 back.onclick=()=>{page--;request();};next.onclick=()=>{page++;request();};
 function close(){clearTimeout(timer);sequence++;if(panel.open)panel.close();}
 exit.onclick=close;
 function open(){window.ExpanseWindowControls?.clear(panel);if(!panel.open){query.value='';page=1;full.checked=false;label.hidden=true;list.replaceChildren();panel.showModal();}request();}
 function receive(msg){
  if(!String(msg.request_id||'').startsWith('chronicle-'))return false;
  if(!panel.open||msg.request_id!=='chronicle-'+sequence)return true;
  list.replaceChildren();
  if(msg.type!=='chronicle_page'){info.textContent=msg.text||'The chronicle could not be read.';return true;}
  for(const option of section.options){option.hidden=Array.isArray(msg.editions) && !msg.editions.includes(option.value);}
  page=msg.page;label.hidden=!msg.director;info.textContent=msg.origin+' · '+msg.title;
  if(!msg.entries.length)info.textContent+=section.value==='individual'&&!query.value?' · Meet a resident to discover their history.':' · No matching records.';
  for(const row of msg.entries){const li=el('li'),when=el('small',[row.date,row.name].filter(Boolean).join(' · '));li.append(when,el('div',row.text));if(row.url&&/^https:\/\//.test(row.url)){const ref=el('a','Open research source');ref.href=row.url;ref.target='_blank';ref.rel='noopener noreferrer';li.append(ref);}li.style.marginBottom='.7em';list.append(li);}
  list.scrollTop=0;count.textContent=' '+page+' / '+msg.pages+' ';back.disabled=page<=1;next.disabled=page>=msg.pages;
  return true;
 }
 function restore(){if(!panel.open)panel.showModal();request();}
 window.ExpanseChronicles={open,restore,close,receive};
})();
