(() => {
  'use strict';
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const dialog=el('dialog');dialog.id='local-quests';dialog.setAttribute('aria-label','Local quests');
  dialog.style.cssText='max-width:min(38rem,94vw);max-height:85dvh;overflow:auto;color:inherit;background:var(--panel,#182a30)';
  const title=el('h2','Local quests'),body=el('div'),status=el('p');status.setAttribute('role','status');
  const nav=el('div'),close=el('button','Close'),hide=el('button','Hide');
  const makeButton=(name,fn)=>{const b=el('button',name);b.type='button';b.onclick=fn;return b;};
  const phone=window.PhonePopups;let sequence=0,current='',catalog,form,posting,nonce=null,approvedPay=null;
  const open=()=>{if(phone)phone.open(dialog);else if(!dialog.open)dialog.showModal();request('list');};
  close.onclick=()=>{dialog.close();body.replaceChildren();};hide.onclick=()=>dialog.close();
  if(!phone)nav.append(hide,close);
  const refresh=makeButton('View requests',()=>request('list')),create=makeButton('Create a quest',()=>request('catalog'));
  nav.prepend(refresh,create);dialog.append(title,nav,status,body);document.body.append(dialog);
  const entry=makeButton('Local quests',open);entry.className='action-btn';
  const parent=phone?document.querySelector('#story .quick-actions'):(document.getElementById('conversation-menu')||document.querySelector('.quick-actions'));
  if(parent?.getAttribute('role')==='menu')entry.setAttribute('role','menuitem');
  parent?.append(entry);
  function request(action,data={}){
    if(typeof ws==='undefined'||ws?.readyState!==1){status.textContent='Enter the game to use local quests.';return;}
    current='local-'+(++sequence);status.textContent='Checking…';
    ws.send(JSON.stringify({command:'local quests',action,request_id:current,...data}));
  }
  function choose(label,options,multi=false){
    const field=el('label',label+' '),select=el('select');select.multiple=multi;
    for(const [value,text] of options){const o=el('option',text);o.value=value;select.append(o);}
    field.append(select);field.style.display='block';field.style.margin='.65em 0';body.append(field);return select;
  }
  function showForm(c,kind=Object.keys(c.tasks)[0]){
    catalog=c;nonce=null;body.replaceChildren();
    const task=choose('Task',Object.entries(c.tasks));task.value=kind;task.onchange=()=>showForm(c,task.value);
    const target=choose('Target',c[kind],['herd','watch'].includes(kind));
    if(target.options.length)target.options[0].selected=true;
    const amount=el('input');amount.type='number';amount.min='1';amount.max=kind==='watch'?'120':'12';amount.value=kind==='watch'?'20':'1';
    if(!['find','herd'].includes(kind)){const l=el('label',kind==='watch'?'Game minutes to supervise ':'Quantity ');l.append(amount);body.append(l);}
    const dest=kind==='herd'?choose('Herd destination',c.places):null;
    const channel=choose('Offer',c.board?[['board','Post on the local noticeboard'],['ask','Ask in person']]:[['ask','Ask in person']]);
    const whom=choose('Who to ask',[['','Anyone I meet'],...c.nearby]);
    function reset(){nonce=null;posting.disabled=true;whom.parentElement.style.display=channel.value==='ask'?'block':'none';status.textContent='';}
    form=()=>({kind,targets:[...target.selectedOptions].map(o=>o.value),qty:Number(amount.value),dest:dest?.value||null,mode:channel.value,to:channel.value==='ask'?(whom.value||null):null});
    const quote=makeButton('Check route and reward',()=>request('quote',form()));
    posting=makeButton('Offer quest',()=>{if(nonce===JSON.stringify(form())){posting.disabled=true;request('post',{...form(),expected_pay:approvedPay});}});
    body.append(quote,posting);[target,amount,dest,channel,whom].filter(Boolean).forEach(n=>n.oninput=reset);reset();
    if(!c[kind].length)status.textContent='You haven’t learned of any targets for this task yet.';
  }
  function list(m){
    body.replaceChildren();body.append(el('p',m.gold+' gold available'+(m.receipt?' · '+m.receipt:'')));
    if(m.summary)body.append(el('p',m.summary));
    if(m.recent?.length){const activity=el('details');activity.append(el('summary','Recent local quest activity'));for(const row of m.recent)activity.append(el('p',typeof row==='string'?row:row.text||row.note||''));body.append(activity);}
    if(!m.rows.length)body.append(el('p','No local offers or personal requests here. Visit a tavern, or ask someone in person.'));
    for(const j of m.rows){
      const section=el('section');section.style.cssText='border-top:1px solid #657775;padding:.8em 0';body.append(section);
      section.append(el('strong',j.title),el('p',j.issuer+' · '+j.pay+' gold · '+j.status+' · '+j.where),el('p',j.note));
      const action=(name,verb)=>section.append(makeButton(name,()=>request(verb,{job:j.id})));
      if(j.assigned){
        section.append(el('p',j.step+' at '+j.room+(j.remaining===undefined?'':' · '+j.remaining+' minutes remaining')));
        if(j.here)action(j.step,'work');action('Return assignment','return');
      }else if(j.mine&&j.status!=='active'){
        if(j.status==='returned')action('Offer again','repost');
        const sel=el('select');sel.setAttribute('aria-label','Choose a person here');
        for(const [id,name] of m.nearby||[]){const o=el('option',name);o.value=id;sel.append(o);}
        if(sel.length){section.append(sel,makeButton('Ask this person',()=>request('offer',{job:j.id,to:sel.value})));}
        action('Withdraw and refund','withdraw');
      }else if(!j.mine&&j.status==='open'){action('Accept','accept');if(j.personal)action('Decline','decline');}
      if(j.history?.length>1){const more=el('details');more.append(el('summary','Request history'));for(const n of j.history)more.append(el('p',n));section.append(more);}
    }
  }
  window.ExpanseLocalQuests={open,receive(m){
    if(m.type!=='local_quests')return false;if(current!==m.request_id)return true;
    if(m.error){status.textContent=m.error;if(posting&&form)posting.disabled=true;return true;}
    status.textContent='';
    if(m.catalog)showForm(m.catalog);
    else if(m.pay!==undefined){nonce=JSON.stringify(form());approvedPay=m.pay;posting.disabled=m.pay>m.funds;status.textContent=m.pay+' gold (you have '+m.funds+') · about '+m.minutes+' game minutes · '+m.route.join(' → ');}
    else list(m);
    return true;
  }};
})();
