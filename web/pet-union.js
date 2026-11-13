(() => {
  const element = (tag,text) => Object.assign(document.createElement(tag),{textContent:text || ''});
  function button(parent,label,click) {
    const b=element('button',label);
    b.type='button'; b.className='ed-btn'; b.onclick=click; parent.append(b);
    return b;
  }
  function command(parent,label,cmd){
    return button(parent,label,()=>{
      if(typeof act==='function')act(cmd,label);
      else if(window.expanseAtlasSend?.(cmd))append('user','> '+label);
    });
  }
  function walk(id){
    if(window.PhonePopups){
      const dialog=document.getElementById('map-tools');
      if(PhonePopups.visible(dialog))PhonePopups.finish(dialog);
      if(typeof page==='function')page('terrain');
    }
    window.ExpansePlayerControls?.walkTo(id);
  }
  const petChoice=new Map();
  window.addEventListener('expanse:build-room-content',({detail:{packet,content,keyed}})=>{
    const u=packet.companion_union;
    if(!u)return;
    const box=element('details'), summary=element('summary',u.title);
    box.open=u.here;
    box.append(keyed(summary,'union summary'));
    box.append(element('p',u.active+' / '+u.slots+' active · '+u.pets.length+' / '+u.capacity+' registered'));
    if(!u.here){
      box.append(element('p','The charter desk, stable and healer are at '+u.yard_name+'.'));
      button(box,'Walk to the Union',()=>walk(u.hall));
    }else{
      if(u.at_desk!==false)command(box,'Consult the charter desk','union desk');
      else button(box,'Visit the charter desk',()=>walk(u.hall));
      const q=u.quests[0];
      if(q&&u.at_desk!==false){
        box.append(element('p',q.name));
        command(box,(q.status==='active'?'Turn in ':'Accept ')+q.name,(q.status==='active'?'complete ':'accept ')+q.name);
      }
      const groups=new Map(), select=element('select');
      select.setAttribute('aria-label','Choose an animal');
      for(const animal of u.stock){
        if(!groups.has(animal.temperament)){
          const g=element('optgroup');g.label=animal.temperament;groups.set(animal.temperament,g);select.append(g);
        }
        groups.get(animal.temperament).append(new Option(animal.name+' · '+animal.skill,animal.name));
      }
      const key=packet.character.id, desc=element('p');
      select.value=petChoice.get(key)||u.stock[0].name;
      const describe=()=>{const animal=u.stock.find(x=>x.name===select.value);petChoice.set(key,animal.name);desc.textContent=animal.temperament+' · '+[animal,...(animal.other_skills||[])].map(s=>s.skill+' — '+s.description).join(' ');};
      select.onchange=describe;describe();
      box.append(element('h4','Animal register'),select,desc);
      command(box,'Study the field guide','union study');
      const adopt=button(box,'Adopt selected animal',()=>{
        const cmd='union adopt '+select.value,label='Adopt '+select.value;
        if(typeof act==='function')act(cmd,label);else if(window.expanseAtlasSend?.(cmd))append('user','> '+label);
      });
      adopt.disabled=!u.licenced||u.pets.length>=u.capacity;
    }
    for(const pet of u.pets){
      const row=element('div');row.append(element('h4',pet.name+' · '+pet.status));
      const action=(label,verb)=>command(row,label,'union '+verb+' '+pet.id);
      if(u.here){
        if(pet.status==='Deceased')action('Resurrect','revive');
        else{
          action('Present to keeper','present');
          action('Heal','heal');
          if(pet.status==='Active')action('Stable','stable');
          else if(u.active<u.slots)action('Call from stable','recall');
        }
      }
      if(pet.status==='Active'){
        for(const skill of pet.skills||[]){
          const verb=skill.trained?'use':'train';
          if(skill.trained||u.here)command(row,(skill.trained?'Use ':'Train ')+skill.name,'union '+verb+' '+pet.id+' | '+skill.name);
        }
      }
      box.append(row);
    }
    content.prepend(keyed(box,'companion union',packet.location.id));
  });
  const tools=document.getElementById('map-tools');
  if(tools){
    const label=element('label','Walk to a known place'), search=element('input'), select=element('select');
    search.type='search';search.placeholder='Find a place';search.setAttribute('aria-label','Find a known destination');
    select.setAttribute('aria-label','Walking destination');
    const group=element('div'); group.className='map-launchers';
    group.append(label,search,select);
    const go=button(group,'Start walking',()=>{if(select.value)walk(select.value);});
    function fill(){
      const term=search.value.trim().toLocaleLowerCase(),old=select.value;
      const rows=(window.latestMap?.walking_destinations||[]).filter(r=>r.id!==window.latestMap?.location?.id&&r.name.toLocaleLowerCase().includes(term)).sort((a,b)=>a.name.localeCompare(b.name)).slice(0,100);
      select.replaceChildren(...rows.map(r=>new Option(r.name,r.id)));
      if(rows.some(r=>r.id===old))select.value=old;
      go.disabled=!select.value;
    }
    search.oninput=fill;
    tools.append(group);
    // PhonePopups temporarily moves the dialog's children to the active popup.
    window.addEventListener('expanse:phone-view',()=>{if(PhonePower.popupVisible('map-tools'))fill();});
  }
})();
