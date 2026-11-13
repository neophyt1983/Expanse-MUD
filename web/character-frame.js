/* A read-only player portrait, independent of the Terrain Map panel. */
(()=>{
 'use strict';
 const make=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
 const label=value=>String(value).replaceAll('_',' ');
 const slotNames={body:'Underlayer',armor:'Outer armor / coat',head:'Head',hands:'Hands',legs:'Legs',feet:'Feet',weapon:'Weapon',offhand:'Offhand',charm:'Charm',appearance_tunic:'Tunic / dress',appearance_cloak:'Cloak',appearance_hat:'Hat'};
 const slotOrder=['body','appearance_tunic','armor','appearance_cloak','head','appearance_hat','hands','legs','feet','weapon','offhand','charm'];
 const frame=make('section','character-frame');frame.id='character-frame';frame.setAttribute('aria-label','Your character appearance and equipment');
 const empty=make('p','character-empty','Create or resume a character to see yourself here.'),content=make('div','character-content');content.hidden=true;
 const heading=make('div','character-heading'),name=make('h2','character-name'),identity=make('div','character-identity');heading.append(make('div','character-eyebrow','YOUR CHARACTER'),name,identity);
 const portrait=make('div','character-portrait'),canvas=make('canvas','character-doll');canvas.width=canvas.height=192;canvas.setAttribute('role','img');portrait.append(canvas);
 const camp=make('p','character-camp-status');camp.hidden=true;camp.setAttribute('role','status');
 const equipment=make('section','character-equipment'),gear=make('dl','character-facts');equipment.append(make('h3','','Equipped'),gear);
 const appearance=make('section','character-appearance'),features=make('dl','character-facts');appearance.append(make('h3','','Characteristics'),features);
 const note=make('p','character-note','Your miniature follows your equipped items and recorded characteristics.');
 content.append(heading,portrait,camp,equipment,appearance,note);frame.append(empty,content);document.getElementById('tab-game').append(frame);
 let latest=null;
 function fact(list,key,value){const description=make('dd','',value);list.append(make('dt','',label(key)),description);return description;}
 function render(packet){
  latest=packet||null;
  const actors=packet?.visual?.version===1?packet.visual.actors||[]:[],character=packet?.character;
  const actor=actors.find(a=>a.kind==='self'||a.self||a.id===character?.id);
  const renderer=window.ExpanseActorRenderer;
  if(!actor||!renderer){content.hidden=true;empty.hidden=false;empty.textContent=character?'Character appearance is unavailable for this host.':'Create or resume a character to see yourself here.';return;}
  content.hidden=false;empty.hidden=true;name.textContent=character?.name||actor.name||'Your character';
  identity.textContent=[character?.race_name||character?.race||actor.race,character?.class_name||character?.char_class||actor.char_class].filter(Boolean).join(' · ');
  const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);c.imageSmoothingEnabled=false;renderer.drawActor(c,actor,96,96,160,false);
  canvas.setAttribute('aria-label',name.textContent+' in currently equipped items');
  gear.replaceChildren();features.replaceChildren();const doll=actor.paperdoll?.version===1?actor.paperdoll:null;
  if(doll){
   for(const item of [...(doll.equipment||[])].sort((a,b)=>slotOrder.indexOf(a.slot)-slotOrder.indexOf(b.slot))){
    const row=fact(gear,slotNames[item.slot]||item.slot,item.name||'Unnamed item');
    const construction=[item.shape,item.material,item.pattern,item.color].filter(Boolean).map(label).join(' · ');
    if(construction){row.title=construction;row.setAttribute('aria-label',(item.name||'Unnamed item')+': '+construction);}
   }
   if(!gear.children.length)gear.append(make('p','character-muted','Nothing equipped.'));
   for(const [key,value] of Object.entries(doll.characteristics||{}))if(value!==null&&value!==undefined&&value!=='')fact(features,key,typeof value==='boolean'?(value?'Yes':'No'):label(value));
   if(!features.children.length)features.append(make('p','character-muted','No characteristics recorded.'));
   note.textContent='Your miniature follows your equipped items and recorded characteristics.';
  }else{
   gear.append(make('p','character-muted','Equipment details unavailable for this host.'));features.append(make('p','character-muted','Characteristics unavailable for this host.'));
   note.textContent='This host supplies a legacy miniature. Detailed equipment is not available.';
  }
  camp.hidden=!actor.actions?.tent;camp.textContent=actor.actions?.tent?(actor.actions.campfire?'Your tent is pitched here. Campfire lit.':'Your tent is pitched here. Fire unlit.'):'';
 }
 window.ExpanseCharacter={render};
 window.addEventListener('expanse:player-map',event=>render(event.detail));
 window.addEventListener('expanse:actor-renderer-ready',()=>render(window.ExpanseActorRenderer?.latestPacket||window.latestMap||latest));
 render(window.ExpanseActorRenderer?.latestPacket||window.latestMap);
})();
