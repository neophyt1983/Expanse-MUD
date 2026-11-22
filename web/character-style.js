(()=>{'use strict';
const by=id=>document.getElementById(id);
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const title=s=>s.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
let gameData,createState={},liveState={},liveOptions,liveActor;
function form(host,opts,state,actor){
 host.replaceChildren();
 const preview=el('canvas');preview.className='style-portrait';preview.width=preview.height=96;preview.setAttribute('aria-label','Character preview');host.append(preview);
 const grid=el('div');grid.className='appearance-grid';host.append(grid);
 function draw(){
  const traits=Object.fromEntries(Object.entries(opts.traits).map(([k,v])=>[k,state[k]||v[0]]));
  const doll={...actor?.paperdoll,version:1,family:opts.family,characteristics:{...actor?.paperdoll?.characteristics,...traits},accent:opts.accents.find(a=>a.name===state.accent)};
  const c=preview.getContext('2d');c.clearRect(0,0,96,96);c.imageSmoothingEnabled=false;
  window.ExpanseActorRenderer?.playerActor(c,{paperdoll:doll},48,48,96,false);
 }
 for(const [key,values] of Object.entries({...opts.traits,accent:['Plain',...opts.accents.map(a=>a.name)]})){
  const label=el('label',key==='accent'?'Appearance detail':title(key)),sel=el('select');sel.dataset.trait=key;
  values.forEach(v=>sel.add(new Option(title(v),v)));if(values.includes(state[key]))sel.value=state[key];else state[key]=sel.value;
  sel.onchange=()=>{state[key]=sel.value;draw();};label.append(sel);grid.append(label);
 }
 draw();host._draw=draw;
}
function creation(data){
 gameData=data;const change=()=>{
  const race=gameData.races.find(r=>r.id===by('cc-race').value),cls=gameData.classes.find(c=>c.id===by('cc-class').value);
  const box=by('cc-style-fields');if(!race||(!cls&&gameData.classless_start!==true)){box.replaceChildren();createState={};return;}
  form(box,{family:race.family,traits:race.traits||{},accents:cls?.accents||[]},createState);
 };
 createState={};by('cc-race').onchange=change;by('cc-class').onchange=change;change();
}
const dialog=el('dialog');dialog.className='style-dialog';dialog.setAttribute('aria-label','Character appearance');
const bar=el('header'),apply=el('button','Apply appearance'),close=el('button','Close'),body=el('div'),note=el('p');
bar.append(el('h2','Character appearance'),close);dialog.append(bar,body,apply,note);document.body.append(dialog);
close.onclick=()=>dialog.close();apply.onclick=()=>{if(!window.expanseAtlasSend?.('ui appearance '+JSON.stringify(liveState)))note.textContent='Reconnect to your character.';};
function open(){if(window.expanseAtlasSend?.('ui appearance'))return;note.textContent='Load a character to change appearance.';if(!dialog.open)dialog.showModal();}
function receive(msg){
 if(msg.type!=='character_appearance')return false;
 liveState={...msg.selection};liveOptions=msg.options;
 liveActor=window.latestMap?.visual?.actors?.find(a=>a.kind==='self');
 if(!msg.applied){form(body,liveOptions,liveState,liveActor);note.textContent='Use Save in the game to keep these choices.';if(!dialog.open)dialog.showModal();}
 else{note.textContent='Appearance applied.';dialog.close();}
 return true;
}
const openButton=el('button','Customize appearance');openButton.className='ed-btn';openButton.onclick=open;document.querySelector('.character-appearance')?.prepend(openButton);
window.addEventListener('expanse:sprite-ready',()=>{by('cc-style-fields')?._draw?.();if(dialog.open)body._draw?.();});
function editor(fields,obj,type){
 if(!['item','race','npc','class'].includes(type))return;
 if(type==='item'&&(obj.type==='weapon'||['weapon','offhand','mainhand'].includes(obj.slot))){
  const label=el('label','Fighting stance'),select=el('select');select.add(new Option('From equipped weapon',''));
  for(const [id,name] of Object.entries(window.ExpanseCombatArt?.labels||{}))select.add(new Option(name,id));
  select.value=obj.fighting_stance||'';select.onchange=()=>saveField('fighting_stance',select.value);label.append(select);fields.append(label);
 }
 if(type==='item'&&(obj.type==='book'||obj.publication||obj.newspaper)){
  const shelf=el('fieldset');shelf.append(el('legend','Publication'));fields.append(shelf);
  const meta={...obj.publication};
  for(const key of ['author','genre']){
   const label=el('label',title(key)),input=el('input');input.value=meta[key]||'';input.maxLength=100;
   input.onchange=()=>{meta[key]=input.value.trim();if(meta.genre&&meta.author)saveField('publication',meta);};label.append(input);shelf.append(label);
  }
  const label=el('label','Lesson taught by this book'),sel=el('select');sel.multiple=true;sel.size=4;
  for(const a of ed.entriesCache.ability||[]){const opt=new Option(a.name||a.id,a.id);opt.selected=(obj.study_abilities||[]).includes(a.id);sel.add(opt);}
  sel.onchange=async()=>{const ids=[...sel.selectedOptions].map(o=>o.value);await saveField('study_abilities',ids);await saveField('teaches_abilities',ids);};label.append(sel);shelf.append(label);
  const pub=el('label','Newspaper edition'),name=el('input');name.value=obj.press_edition||'';name.placeholder='Country, city or town';name.maxLength=90;
  name.onchange=async()=>{const val=name.value.trim();await saveField('press_edition',val);await saveField('newspaper',!!val);};pub.append(name);shelf.append(pub);
  return;
 }
 const box=el('fieldset');box.append(el('legend','Appearance'));fields.append(box);
 const trigger=el('button',type==='class'?'Edit class details':'Edit artwork and appearance');trigger.type='button';trigger.className='ed-btn';box.append(trigger);
 trigger.onclick=async()=>{
  trigger.disabled=true;const ctx=window.expansePixelContext();
  try{
   const p=await window.expansePixelRequest({action:'starter',target_type:type==='class'?'classes':ctx.type,target_id:ctx.id,rig:'humanoid:average:average'});
   if(!box.isConnected)return;
   if(type!=='class'){
    const studio=el('button','Open Pixel Art Studio');studio.className='ed-btn';studio.onclick=()=>window.ExpansePixelStudio.open();box.append(studio);
   }
   if(type==='race'){
    const traits={...p.traits};
    for(const [k,allowed] of Object.entries(p.palettes)){
     const group=el('details'),sum=el('summary',title(k));group.append(sum);
     for(const value of allowed){
      const label=el('label'),input=el('input');input.type='checkbox';input.checked=traits[k].includes(value);
      input.onchange=()=>{const chosen=[...group.querySelectorAll('input:checked')].map(n=>n.value);if(!chosen.length){input.checked=true;return;}traits[k]=chosen;saveField('appearance_choices',traits);};
      input.value=value;label.append(input,document.createTextNode(title(value)));group.append(label);
     }box.append(group);
    }
   }
   if(type==='class'){
    const accents=p.accents.map(x=>({...x}));const list=el('div');box.append(list);
    const render=()=>{list.replaceChildren();accents.forEach((a,i)=>{
     const row=el('div'),name=el('input'),mark=el('select'),color=el('select'),remove=el('button','Remove');
     name.value=a.name;name.maxLength=60;name.setAttribute('aria-label','Detail name');
     for(const v of ['collar','cuffs','sash'])mark.add(new Option(title(v),v));for(const v of p.colors)color.add(new Option(title(v),v));
     mark.value=a.mark;color.value=a.color;name.onchange=()=>{if(name.value.trim()){a.name=name.value.trim();saveField('appearance_styles',accents);}};
     mark.onchange=()=>{a.mark=mark.value;saveField('appearance_styles',accents);};color.onchange=()=>{a.color=color.value;saveField('appearance_styles',accents);};
     remove.onclick=()=>{accents.splice(i,1);saveField('appearance_styles',accents);render();};row.append(name,mark,color,remove);list.append(row);
    });};render();const add=el('button','Add class detail');add.onclick=()=>{accents.push({name:'Guild detail '+(accents.length+1),color:'green',mark:'collar'});saveField('appearance_styles',accents);render();};box.append(add);
   }
   if(type==='npc'&&p.actor.paperdoll){
    const info={...obj.portrait};
    for(const [key,choices] of Object.entries({uniform:p.uniforms,cut:['neutral','feminine','masculine'],color:p.colors})){
     const label=el('label',title(key)),sel=el('select');sel.add(new Option('From character',''));choices.forEach(v=>sel.add(new Option(title(v),v)));sel.value=info[key]||'';
     sel.onchange=()=>{if(sel.value)info[key]=sel.value;else delete info[key];saveField('portrait',info);};label.append(sel);box.append(label);
    }
   }
   trigger.remove();
  }catch(e){trigger.disabled=false;setStatus(e.message,'warn');}
 };
}
window.ExpanseStyles={creation,selection:()=>({...createState}),open,receive,editor};
})();
