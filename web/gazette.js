/* Read the edition published for the selected place and in-game day. */
(()=>{
  'use strict';
  const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const dialog=el('dialog'), head=el('header'), heading=el('h2','Newspaper'), exit=el('button','Close');
  dialog.id='press-reader';dialog.className='style-dialog';heading.id='press-title';
  dialog.setAttribute('aria-labelledby',heading.id);head.append(heading,exit);
  const controls=el('div'),locality=el('select'),when=el('select'),view=el('select'),refresh=el('button','Refresh');
  controls.className='press-controls';
  locality.setAttribute('aria-label','Newspaper edition');
  when.setAttribute('aria-label','Publication day');when.add(new Option('Today',''));when.add(new Option('Yesterday','yesterday'));
  view.setAttribute('aria-label','Newspaper view');view.add(new Option('Front page',''));view.add(new Option('All dispatches','/all'));
  controls.append(locality,when,view,refresh);
  const status=el('p'),paper=el('article');
  status.setAttribute('role','status');paper.setAttribute('aria-label','Selected edition');paper.tabIndex=0;
  dialog.append(head,controls,status,paper);document.body.append(dialog);

  let sequence=0,timer,loaded=false;
  function stop(){clearTimeout(timer);sequence++;paper.removeAttribute('aria-busy');}
  function update(){
    stop();
    if(!dialog.open)return;
    const request='paper-'+sequence;
    if(typeof ws==='undefined'||ws?.readyState!==1){status.textContent='Connect with a character to read the newspaper.';return;}
    const command=['ui gazette',locality.value,when.value,view.value].filter(Boolean).join(' ');
    status.textContent='Checking '+(locality.value||'the local edition')+'…';
    paper.setAttribute('aria-busy','true');
    timer=setTimeout(()=>{
      if(request!=='paper-'+sequence)return;
      paper.removeAttribute('aria-busy');
      status.textContent='No reply from the press desk yet. Choose Refresh to try again.';
    },8000);
    ws.send(JSON.stringify({command,request_id:request}));
  }
  function open(chooseEdition=false){
    window.ExpanseWindowControls?.clear(dialog);
    if(!dialog.open)dialog.showModal();
    update();
    if(chooseEdition)locality.focus({preventScroll:true});
  }
  function close(){stop();if(dialog.open)dialog.close();}
  function disconnect(){close();loaded=false;locality.replaceChildren();paper.replaceChildren();when.selectedIndex=view.selectedIndex=0;}
  function receive(msg){
    if(!String(msg.request_id||'').startsWith('paper-'))return false;
    if(!dialog.open||msg.request_id!=='paper-'+sequence)return true;
    clearTimeout(timer);paper.removeAttribute('aria-busy');
    if(msg.type!=='press_edition'){status.textContent=msg.text||'This edition could not be read.';return true;}
    const old=locality.value;
    const options=document.createDocumentFragment();
    for(const [kind,title] of [['country','Countries'],['city','Cities'],['town','Towns']]){
      const group=el('optgroup');group.label=title;
      for(const row of msg.editions.filter(r=>r.kind===kind))group.append(new Option(row.name,row.name));
      if(group.childElementCount)options.append(group);
    }
    locality.replaceChildren(options);
    const selection=old||msg.local;
    if(selection && [...locality.options].some(o=>o.value===selection))locality.value=selection;
    if(!old&&!msg.local&&locality.value){update();return true;}
    const blocks=msg.text.split('\n\n').map(s=>s.trim()).filter(Boolean);
    const body=document.createDocumentFragment();
    for(const [i,block] of blocks.entries()){
      const node=el(i===0?'h3':'p',block);body.append(node);
      const pin=msg.venues?.[block];
      if(pin){
        const link=el('button','Show '+pin.name+' on map');link.type='button';node.append(el('br'),link);
        link.onclick=()=>{
          const page={label:'newspaper',dismiss(){},restore(){if(!dialog.open)dialog.showModal();link.focus({preventScroll:true});}};
          if(window.PhonePopups)PhonePopups.navigate(()=>window.ExpanseWorldAtlas.focusKnown(pin,page));
          else{dialog.close();window.ExpanseWorldAtlas.focusKnown(pin,page);}
        };
      }
    }
    const changed=paper.textContent!==body.textContent;
    if(changed){paper.replaceChildren(body);paper.scrollTop=0;}
    status.textContent=(loaded&&!changed?'Up to date':'Edition loaded')+' · '+(locality.value||'Local paper')+' · '+when.selectedOptions[0].text+' · '+view.selectedOptions[0].text;
    window.dispatchEvent(new CustomEvent('expanse:edition-read',{detail:msg.stories||[]}));
    loaded=true;return true;
  }
  exit.onclick=close;dialog.addEventListener('close',()=>{if(!dialog.open)stop();});
  refresh.onclick=update;locality.onchange=when.onchange=view.onchange=update;
  window.ExpanseGazette={open,receive,close,disconnect};
})();
