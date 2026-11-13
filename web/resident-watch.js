(()=>{
 const el=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
 const btn=(label,fn)=>{const b=el('button',label);b.type='button';b.className='ed-btn';b.onclick=fn;return b;};
 const panel=el('dialog');panel.id='resident-watch';panel.className='resident-window';panel.setAttribute('aria-label','Resident watch');
 const heading=el('h2','Resident watch'),chooser=el('select');chooser.setAttribute('aria-label','Choose a resident');
 const summary=el('p'),status=el('p');status.setAttribute('role','status');const events=el('ol'),portrait=el('canvas');portrait.width=portrait.height=82;portrait.setAttribute('aria-hidden','true');
 const head=el('div');head.className='resident-summary';head.append(portrait,summary);
 let seq=0,timer=null,last='',target=null,cursor=null,previous=[],offset=0,tracked=null;
 const figure=el('figure');figure.className='watch-scene';figure.hidden=true;
 const caption=el('figcaption'),map=el('canvas'),description=el('p'),company=el('p');map.setAttribute('role','img');
 const weatherView=el('div');weatherView.className='watch-weather-view';weatherView.append(map);
 figure.append(caption,weatherView,description,company);let scene=null;
 function showScene(value,name){
   scene=value||null;figure.hidden=!scene;
   window.ExpanseSky?.update(weatherView,scene?.weather,scene?.tiles?.find(t=>t.current)?.effects);
   if(!scene)return;
   caption.textContent=[scene.name,scene.context,'Level '+scene.floor].filter((v,i,a)=>a.indexOf(v)===i).join(' · ');
   description.textContent=scene.description;description.hidden=!scene.description;
   const companions=scene.others.join(', ')+(scene.other_count>scene.others.length?' and '+(scene.other_count-scene.others.length)+' more':'');
   company.textContent=[scene.heading_to?'Heading to '+scene.heading_to:'',companions?'With '+companions:''].filter(Boolean).join(' · ');
   company.hidden=!company.textContent;map.setAttribute('aria-label',name+' at '+caption.textContent);
   window.ExpanseMap?.drawWatchScene(map,scene);
 }
 new ResizeObserver(()=>{if(scene&&panel.open)window.ExpanseMap?.drawWatchScene(map,scene);}).observe(map);
 function request(action='view',id=target){if(!panel.open)return;if(typeof ws==='undefined'||ws?.readyState!==1){status.textContent='Reconnect to see this resident.';return;}
   ws.send(JSON.stringify({command:'resident watch',request_id:'watch-'+(++seq),action,resident:id,before:cursor,follow_camera:true}));
 }
 function resetPage(){cursor=null;previous=[];last='';}
 function open(id=null){
   showScene(null);if(!panel.open)panel.showModal();window.ExpanseWindowControls?.clear(panel);target=id;resetPage();clearTimeout(timer);request(id?'start':'view',id);
 }
 function close(){clearTimeout(timer);seq++;if(panel.open)panel.close();}
 const follow=btn('Watch',()=>{const id=chooser.value;if(!id)return;resetPage();target=id;request('start',id);});
 const stop=btn('Stop watching',()=>{resetPage();request('stop',null);});
 const earlier=btn('Earlier',()=>{if(offset){previous.push(cursor);cursor=offset;request();}});
 const later=btn('Later',()=>{cursor=previous.pop()??null;request();});
 const latest=btn('Latest',()=>{resetPage();request();});
 const nav=el('div');nav.className='watch-tools';nav.append(earlier,later,latest);
 const tools=el('div');tools.className='watch-tools';tools.append(chooser,follow,stop);
 panel.append(heading,tools,figure,head,status,events,nav,btn('Close',close));document.body.append(panel);
 panel.addEventListener('close',()=>{clearTimeout(timer);scene=null;if(!panel.open&&typeof ws!=='undefined'&&ws?.readyState===1)ws.send(JSON.stringify({command:'resident watch',action:'close'}));});
 chooser.onchange=()=>{showScene(null);target=chooser.value||null;resetPage();request();};
 function receive(m){
   if(m.type!=='resident_watch')return false;
   if(!panel.open||m.request_id!=='watch-'+seq)return true;
   clearTimeout(timer);
   if(m.error){showScene(null);status.textContent=m.error;return true;}
   showScene(m.scene,m.name);
   tracked=m.selected;target=m.resident||target||tracked;const options=JSON.stringify(m.choices);
   if(chooser.dataset.last!==options){chooser.dataset.last=options;chooser.replaceChildren(new Option('Choose a resident…',''));
     for(const [id,name] of m.choices)chooser.append(new Option(name,id));}
   chooser.value=target||'';follow.disabled=!chooser.value||chooser.value===tracked||m.ended;stop.hidden=!tracked;
   offset=m.before||0;earlier.disabled=!offset;later.disabled=latest.disabled=cursor===null;nav.hidden=!m.resident;
   if(!m.state){summary.textContent='';portrait.hidden=true;status.textContent=m.choices.length?'Choose a resident and press Watch.':'Meet a resident to begin watching.';events.replaceChildren();last='';}
   else{
     const s=m.state;summary.textContent=[m.name,s.alive?(m.absent?'Away':s.activity):'Deceased',s.place,s.occupation,
       s.stage==='animal'?'':s.stage+' · age '+s.age,s.home?'Home · '+s.home:'',Number.isFinite(s.sanity)?'Sanity '+s.sanity+'/100':'',...(s.expedition_memories||[]).map(text=>m.name+' '+text+'.')].filter(Boolean).join('\n');
     status.textContent=m.ended?'Life record complete.':tracked===target?'Watching live.':'Recorded observations.';
     const draw=portrait.getContext('2d');draw.clearRect(0,0,82,82);portrait.hidden=!!m.scene||!m.portrait;
     if(m.portrait&&window.ExpanseActorRenderer){draw.imageSmoothingEnabled=false;window.ExpanseActorRenderer.drawActor(draw,m.portrait,41,41,82,false);}
     const key=JSON.stringify([m.resident,m.events]);if(last!==key){last=key;const at=events.scrollTop;events.replaceChildren();
       for(const [at,place,line] of m.events){const li=el('li');li.append(el('small',[at,place].filter(Boolean).join(' · ')),el('div',line));events.append(li);}events.scrollTop=at;}
   }
   if(panel.open&&cursor===null&&(!m.resident||(!m.ended&&tracked===target)))timer=setTimeout(()=>request(),2500);
   return true;
 }
 window.ExpanseResidentWatch={open,close,restore:()=>open(),receive};
})();
