/* Each conversation has one way back to its current offers. */
(()=>{'use strict';
 const panel=document.createElement('dialog');panel.id='quest-offers';panel.className='resident-window';panel.setAttribute('aria-label','Quest offers');
 const title=document.createElement('h2');title.textContent='Quest offers';const list=document.createElement('div');list.className='offer-list';
 const close=document.createElement('button');close.type='button';close.className='ed-btn';close.textContent='Close';close.onclick=()=>panel.close();
 panel.append(title,list,close);document.body.append(panel);
 let room=null,entry=null;
 function clear(){for(const b of list.children)b.disabled=true;if(entry)entry.remove();entry=null;if(panel.open)panel.close();window.ExpanseWindowControls?.clear(panel);}
 function locationChanged(id){if(room!==null&&id!==room)clear();room=id;}
 function open(){if(entry&&!panel.open){window.ExpanseWindowControls?.clear(panel);panel.showModal();}}
 function show(rows,automatic=true){
   if(!Array.isArray(rows)||!rows.length)return;
   const choices=rows.filter(r=>typeof r.id==='string'&&typeof r.name==='string');
   if(!choices.length)return;clear();list.replaceChildren();
   for(const row of choices){
     const b=document.createElement('button');b.type='button';b.className='ed-btn';b.dataset.sourceQuest=row.id;b.textContent='Accept '+row.name;
     b.onclick=()=>{if(typeof ws==='undefined'||!ws||ws.readyState!==1)return;b.disabled=true;
       ws.send(JSON.stringify({command:'accept '+row.id}));if([...list.children].every(b=>b.disabled)){if(entry)entry.disabled=true;panel.close();}
     };list.append(b);
   }
   const log=document.getElementById('log');entry=document.createElement('button');entry.type='button';entry.className='ed-btn';
   entry.textContent='View quest offers ('+choices.length+')';entry.onclick=open;log.append(entry);log.scrollTop=log.scrollHeight;
   if(automatic&&!document.querySelector('dialog:modal'))open();
 }
 window.ExpanseSourceQuests={show,clear,open,locationChanged};
})();
