/* Read-only, character-owned skills and learned knowledge from the host. */
(()=>{'use strict';
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 let latest=null,owner='',dialog=null,body=null,signature='';
 const visible=()=>dialog&&(window.PhonePopups?.visible?PhonePopups.visible(dialog):dialog.open);
 function close(){if(visible()){if(window.PhonePopups)window.PhonePopups.finish(dialog);else dialog.close();}}
 function reset(){close();latest=null;owner='';signature='';body?.replaceChildren();}
 function fill(){
  if(!body)return;const view=latest?.character?.skills;body.replaceChildren();
  if(!view){body.append(node('p','Enter the world to see your character’s skills.'));return;}
  body.append(node('p','Task levels are separate from your overall character level. Real attempts earn practice; each higher level takes longer.'));
  const list=node('div');list.className='skills-list';
  for(const row of view.skills||[]){
   const item=node('section');item.className='skill-row';
   item.append(node('strong',row.name),node('span',row.level+'/100 · '+row.proficiency));
   if(row.next_practice!==null){
    const label=node('small','Practice toward next level: '+row.practice+' / '+row.next_practice);
    const bar=node('progress');bar.max=row.next_practice;bar.value=row.practice;bar.setAttribute('aria-label',row.name+' practice toward next level');item.append(label,bar);
   }else item.append(node('small','Maximum skill level reached.'));
   list.append(item);
  }
  body.append(list,node('p','Knowing a recipe or technique tells you what to attempt. Your task level describes how practised you are.'));
  for(const [key,label] of [['recipes','Known recipes'],['techniques','Learned techniques'],['books','Reading journal']]){
   const rows=view.knowledge?.[key]||[],section=node('details'),summary=node('summary',label+' ('+rows.length+')');section.append(summary);
   if(rows.length){const ul=node('ul');for(const row of rows)ul.append(node('li',row.name));section.append(ul);}
   else section.append(node('p','None recorded yet.'));body.append(section);
  }
 }
 function open(){
  if(!dialog){dialog=node('dialog');dialog.id='player-skills';dialog.className='style-dialog';dialog.setAttribute('aria-label','Skills & knowledge');
   const heading=node('h2','Skills & knowledge');body=node('div');body.className='skills-body';
   const done=node('button','Close');done.type='button';done.className='ed-btn';done.onclick=close;
   dialog.append(heading,body,done);document.body.append(dialog);}
  fill();if(!visible()){if(window.PhonePopups)window.PhonePopups.open(dialog);else dialog.showModal();}
 }
 window.addEventListener('expanse:build-room-content',({detail:{packet}})=>{
  const next=JSON.stringify([packet.visual?.travel_world||'',packet.character?.id||'']);
  if(next!==owner){reset();owner=next;}latest=packet;
  const value=JSON.stringify(packet.character?.skills||null);if(value!==signature){signature=value;if(visible())fill();}
 });
 window.addEventListener('expanse:character-reset',reset);
 window.ExpanseSkills={open,reset};
})();
