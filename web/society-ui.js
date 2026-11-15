(()=>{
 const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const send=command=>{if(ws&&ws.readyState===1)ws.send(JSON.stringify({command}));else append('error','Connect first.');};
 const button=(text,fn)=>{const b=make('button',text);b.className='ed-btn';b.type='button';b.onclick=fn;return b;};
 const panel=make('details'),summary=make('summary','Chat, exchange and workshops');panel.className='society-panel';panel.append(summary);
 const channel=make('select');for(const [id,name] of [['say','Room'],['chat','World'],['faction','My faction']])channel.append(new Option(name,id));
 const message=make('input');message.placeholder='Message';message.maxLength=2000;panel.append(channel,message,button('Send',()=>{send(channel.value+' '+message.value);message.value='';}),button('Faction standing',()=>send('standing')),button('Workshop',()=>send('workshop')));
 const recipient=make('select'),item=make('select'),quantity=make('input'),gold=make('input');quantity.type=gold.type='number';quantity.min=1;quantity.value=1;gold.min=0;gold.value=0;
 quantity.title='Quantity';gold.title='Total price in gold (0 for gift)';recipient.title='Nearby player';item.title='Carried item';
 const requested=make('input'),requestedQty=make('input');requested.placeholder='Requested item ID (optional)';requestedQty.type='number';requestedQty.min=1;requestedQty.value=1;requestedQty.title='Requested quantity';
 panel.append(make('p','Exchange: same faction or above 50% mutual friendliness. The recipient must accept.'),recipient,item,quantity,gold,requested,requestedQty,button('Offer exchange',()=>send(`offer ${recipient.value} ${item.value} ${quantity.value} ${gold.value}`+(requested.value.trim()?` ${requested.value.trim()} ${requestedQty.value}`:''))));
 const notices=make('div');panel.append(notices);document.getElementById('session-actions').after(panel);
 const host=make('details');host.className='society-panel';host.hidden=true;host.append(make('summary','Host controls'));
 const center=make('select'),map=make('pre'),players=make('div'),person=make('input'),announcement=make('input');person.placeholder='Player ID or exact name';announcement.placeholder='Message to every player';
 host.append(center,button('View full map',()=>send('hostmap '+center.value)),button('List players',()=>send('players')),person,button('Promote creator',()=>send('promote '+person.value)),button('Revoke creator',()=>send('demote '+person.value)),announcement,button('Announce to everyone',()=>send('announce '+announcement.value)),map,players);document.getElementById('session-actions').after(host);
 const social=make('fieldset');social.append(make('legend','Relationships and family'));
 const partner=make('select'),bond=make('select');for(const kind of ['friend','business','companion','lover','married','parenthood'])bond.append(new Option(kind,kind));
 social.append(partner,bond,button('Propose',()=>send(`relationship propose ${bond.value} ${partner.value}`)),button('End relationship',()=>send(`relationship end ${bond.value} ${partner.value}`)));
 for(const field of ['romance_enabled','family_enabled','fertile']){const label=make('label'),input=make('input');input.type='checkbox';input.dataset.preference=field;input.onchange=()=>send(`relationship preferences ${field} ${input.checked?'on':'off'}`);label.append(input,make('span',field.replaceAll('_',' ')));social.append(label);}
 const role=make('select');for(const value of ['none','carrier','contributor'])role.append(new Option('Reproductive role: '+value,value));role.onchange=()=>send('relationship preferences reproductive_role '+role.value);social.append(role);
 const proposals=make('div'),bonds=make('div');social.append(proposals,bonds);panel.append(social);
 const npcSocial=make('fieldset');npcSocial.id='npc-social';npcSocial.append(make('legend','NPC social interactions'));
 const npcChoice=make('select'),emotion=make('select'),gift=make('select'),trust=make('p'),questList=make('div');
 const resident=make('section');resident.id='npc-population-profile';resident.hidden=true;resident.setAttribute('aria-live','polite');
 npcChoice.title='Nearby NPC';emotion.title='Social emotion';gift.title='Gift from inventory';
 const validNpc=()=>socialMap?.social?.npcs?.some(n=>n.id===npcChoice.value);
 function npcAction(command){if(!validNpc()){showNpc();return;}send(command);}
 const expressButton=button('Express emotion',()=>npcAction(`social emote ${emotion.value} to ${npcChoice.value}`));
 const giftButton=button('Offer NPC gift',()=>{if(!gift.value){showNpc();return;}npcAction(`social gift ${gift.value} to ${npcChoice.value}`);});
 const dialogueButton=button('Quest dialogue / services',()=>npcAction('dialogue '+npcChoice.value));
 const wakeButton=button('Wake NPC',()=>npcAction('wake '+npcChoice.value));wakeButton.title='Deliberately wake this person. They may resent the interruption.';
 const questions=make('fieldset');questions.append(make('legend','Conversation topics and directions'));
 const subject=make('input'),addressee=make('input');subject.placeholder='Name or place';subject.maxLength=120;
 subject.setAttribute('aria-label','Person or place to ask about');addressee.placeholder='Person to tell';addressee.maxLength=120;
 addressee.setAttribute('aria-label','Person to give directions to');
 function ask(action){npcAction('social '+action+' '+subject.value.trim()+(action==='relay'?' for '+addressee.value.trim():'')+' to '+npcChoice.value);}
 const about=button('Ask about someone',()=>ask('about')),route=button('Ask directions',()=>ask('directions')),relay=button('Pass directions on',()=>ask('relay'));
 const tell=button('Tell about someone',()=>ask('tell')),giveRoute=button('Give directions',()=>ask('showroute'));
 const stories=make('select');stories.setAttribute('aria-label','Dispatch to share');
 const shareNews=button('Share headline',()=>npcAction('social headline '+stories.value+' to '+npcChoice.value));
 stories.hidden=shareNews.hidden=true;
 window.addEventListener('expanse:edition-read',event=>{
   stories.replaceChildren(...event.detail.map(row=>new Option(row.title,row.ref)));
   stories.hidden=shareNews.hidden=!stories.options.length;
 });
 questions.append(button('Relationships and feelings',()=>ask('people')),button('Your work',()=>ask('work')),button('Current activities',()=>ask('activities')),button('Future plans',()=>ask('plans')),button('Creatures and monsters',()=>ask('creatures')),button('Discuss the news',()=>ask('localnews')),button('Share a memory',()=>ask('memories')),subject,about,tell,route,giveRoute,addressee,relay,stories,shareNews);
 const sellChoice=make('select'),takeChoice=make('select');sellChoice.title='Items this NPC wants';takeChoice.title='NPC possessions available for barter';
 const sellButton=button('Sell to NPC',()=>{if(sellChoice.value)npcAction(`sell ${sellChoice.value} to ${npcChoice.value}`);});
 const barterButton=button('Barter with NPC',()=>{if(sellChoice.value&&takeChoice.value)npcAction(`barter ${sellChoice.value} for ${takeChoice.value} with ${npcChoice.value}`);});
 npcSocial.append(npcChoice,wakeButton,emotion,expressButton,gift,giftButton,dialogueButton,questions,trust,resident,sellChoice,sellButton,takeChoice,barterButton,questList);const npcPanel=make('details');npcPanel.className='society-panel';npcPanel.append(make('summary','NPC gifts, emotions and relationship quests'),npcSocial);panel.after(npcPanel);
 const pets=make('fieldset');pets.id='companion-controls';pets.append(make('legend','Pets and familiars'));
 const pet=make('select'),foe=make('select'),treat=make('select'),toy=make('select'),petInfo=make('p');pet.title='Your companion';foe.title='Attack target';treat.title='Suitable carried treat';toy.title='Suitable carried toy';pets.append(pet,foe,button('Attack target',()=>send(`companion attack ${pet.value} at ${foe.value}`)));
 for(const order of ['defend','peaceful','stay','follow','dismiss','recall'])pets.append(button(order[0].toUpperCase()+order.slice(1),()=>send(`companion ${order} ${pet.value}`)));
 pets.append(treat,button('Give treat',()=>send(`companion treat ${pet.value} with ${treat.value}`)),toy,button('Give toy',()=>send(`companion toy ${pet.value} with ${toy.value}`)),button('Play together',()=>send(`companion play ${pet.value} with ${toy.value}`)),petInfo);const petPanel=make('details');petPanel.className='society-panel';petPanel.append(make('summary','Pets and familiars'),pets);npcPanel.after(petPanel);
 const tameChoices=make('select'),tameInfo=make('p');tameChoices.title='Nearby tameable creature';
 const tameButton=button('Tame creature',()=>{const row=socialMap?.taming?.find(r=>r.id===tameChoices.value);if(row&&!row.blocked)send('tame '+row.id);});
 pets.prepend(tameChoices,tameButton,tameInfo);
 function showTaming(){const row=socialMap?.taming?.find(r=>r.id===tameChoices.value);tameButton.disabled=!row||!!row.blocked;tameInfo.textContent=row?row.name+' needs '+row.food+'. '+(row.blocked||'Ready to tame.'): 'No tameable creature here. Companion field notes explain how to begin.';}
 tameChoices.onchange=showTaming;
 const panelStack=make('div');panelStack.id='society-panels';document.getElementById('session-actions').after(panelStack);panelStack.append(host,panel,npcPanel,petPanel);
 let socialMap=null,missingNpc=false;
 function npcOptions(rows){const old=npcChoice.value;npcChoice.replaceChildren(new Option(rows.length?'Choose a nearby NPC':'No living social NPC nearby',''));for(const row of rows)npcChoice.append(new Option(row.name,row.id));if(rows.some(n=>n.id===old))npcChoice.value=old;else if(old)missingNpc=true;npcChoice.disabled=!rows.length;}

 function options(select,rows){const old=select.value;select.replaceChildren();for(const row of rows)select.append(new Option(row.name,row.id));if(rows.some(r=>r.id===old))select.value=old;}
 function showNpc(){const n=socialMap?.social?.npcs?.find(n=>n.id===npcChoice.value);showResident(n?.population);questions.disabled=!n||n.awake===false;options(emotion,Object.entries(socialMap?.social?.emotions||{}).filter(([id])=>id!=='in_love'||n?.adult!==false).map(([id,emoji])=>({id,name:emoji+' '+id.replaceAll('_',' ')})));options(sellChoice,(n?.commerce?.buying||[]).map(i=>({...i,name:i.name+' — '+i.price+' gold'+(i.reason?' · '+i.reason:'')+(i.affordable?'':' (cannot afford)')})));options(takeChoice,(n?.commerce?.offering||[]).map(i=>({...i,name:i.name+' — value '+i.value})));const canTrade=!!n&&(socialMap?.location?.npcs||[]).some(x=>x.id===n.id&&x.trade_available===true);for(const control of [sellChoice,sellButton,takeChoice,barterButton])control.hidden=!canTrade;sellButton.disabled=!canTrade||!sellChoice.value;barterButton.disabled=!canTrade||!sellChoice.value||!takeChoice.value;wakeButton.disabled=!n||n.awake!==false;expressButton.disabled=!n||n.awake===false||!emotion.value;giftButton.disabled=!n||n.awake===false||!gift.value;dialogueButton.disabled=!n||n.awake===false;gift.disabled=!gift.options.length;trust.textContent=n?(n.awake===false?'Sleeping. Choose Wake NPC to disturb them; they may resent it. ':'Awake. ')+'Personal trust: '+n.trust+'. Interests: '+(n.likes||'No gift interests specified')+'. '+(n.needs||'')+' Gifts do not change faction reputation.'+(!gift.value?' You have no unequipped items to offer.':''):(missingNpc?'The selected NPC is no longer available here. Choose another nearby NPC.':(socialMap?.social?.npcs?.length?'Choose a nearby NPC, then choose a gift.':'No living NPC here can receive social gifts. Find a person and choose Talk.'));questList.replaceChildren();for(const q of n?.quests||[]){const row=make('p',q.name+' — '+q.status+'. '+q.description+' '+Object.entries(q.goals).map(([k,v])=>k.replaceAll('_',' ')+': '+q.progress[k]+'/'+v).join('; ')+(q.blocked?' — '+q.blocked:''));const b=button(q.status==='active'?'Complete quest':'Accept quest',()=>send(`social ${q.status==='active'?'complete':'accept'} ${q.id} with ${n.id}`));b.disabled=!!q.blocked||q.status==='complete';row.append(b);questList.append(row);}}
 function showResident(profile){
  resident.replaceChildren();resident.hidden=!profile;if(!profile)return;
  resident.append(make('h4','Resident profile'));
  const pretty=value=>typeof value==='string'?value.replaceAll('_',' '):String(value);
  const row=(label,value)=>{if(value!==undefined&&value!==null&&value!=='')resident.append(make('p',label+': '+pretty(value)));};
  if(typeof profile.age_years==='number'&&Number.isFinite(profile.age_years))row('Age',Math.floor(profile.age_years)+' local Expanse years');
  row('Life stage',profile.life_stage);row('Household type',profile.household_type);row('Household role',profile.household_role);row('Marital history / status',profile.marital_status);row('Care needs',typeof profile.care_need==='boolean'?(profile.care_need?'Support needed':'No additional need recorded'):profile.care_need);if(profile.care_provision_unavailable===true)row('Care provision','Currently unavailable');
  const education=profile.education;
  if(education){row('Current enrollment',education.enrollment);row('Attainment record',education.attainment);row('Literacy',education.literacy);if(Array.isArray(education.skills))row('Skills',education.skills.length?education.skills.map(pretty).join(', '):'No skills recorded');row('Learning provision',education.provision);resident.append(make('small','Enrollment describes current learning, not a completed qualification.'));}
  const health=profile.health;
  if(health?.fictional===true){
   resident.append(make('h5','Fictional chronic profile'));
   const conditions=Array.isArray(health.conditions)?health.conditions:[];
   if(!conditions.length)resident.append(make('p','No chronic conditions recorded in this fictional profile.'));
   for(const condition of conditions){row('Condition',condition.label);for(const note of condition.support_notes||[])row('Support preference',note);}
   for(const note of health.support_notes||[])row('Support preference',note);
   resident.append(make('small','Descriptive author choices, separate from acute injury or disease. They do not determine capability, disability or retirement.'));
  }
 }
 function relationshipChoices(){
  const person=socialMap?.social?.npcs?.find(n=>n.id===partner.value);
  for(const option of bond.options){const restricted=person?.adult===false&&['lover','married','parenthood'].includes(option.value);option.disabled=restricted;option.hidden=restricted;}
  if(bond.selectedOptions[0]?.disabled)bond.value='friend';
 }
 partner.onchange=relationshipChoices;
 function showPet(){const c=socialMap?.companions?.find(c=>c.id===pet.value);const inv=socialMap?.character?.inventory||[];const unique=inv.filter((x,i)=>inv.findIndex(y=>y.id===x.id)===i);options(treat,unique.filter(i=>c?.treats.includes(i.id)));options(toy,[...unique.filter(i=>c?.toys.includes(i.id)),...(c?.held_toys||[]).filter(i=>!unique.some(x=>x.id===i.id))]);petInfo.textContent=c?`${c.name}: ${c.order}, ${c.mode}; location: ${c.location}; happiness ${c.happiness}/100. Dismissal preserves ownership. Recall brings your living companion back.`:'Tame a suitable creature to gain a companion.';}
 window.openNpcSocial=id=>{
  if(!(socialMap?.social?.npcs||[]).some(n=>n.id===id)){append('error','That NPC is no longer nearby or does not use social conversation.');return;}
  send('social begin '+id);npcChoice.value=id;missingNpc=false;showNpc();if(window.ExpansePlayWindows)window.ExpansePlayWindows.open(npcPanel);else{npcPanel.open=true;npcPanel.scrollIntoView({block:'nearest'});}(wakeButton.disabled?emotion:wakeButton).focus();
 };
 npcChoice.onchange=()=>{missingNpc=false;showNpc();if(validNpc())send('social begin '+npcChoice.value);};gift.onchange=showNpc;emotion.onchange=showNpc;pet.onchange=showPet;
 const previous=window.renderRoomPanel;window.renderRoomPanel=m=>{
  previous(m);socialMap=m;npcSocial.hidden=!m.social;pets.hidden=!m.social;
  npcOptions(m.social?.npcs||[]);options(emotion,Object.entries(m.social?.emotions||{}).map(([id,emoji])=>({id,name:emoji+' '+id.replaceAll('_',' ')})));options(gift,(m.character.inventory||[]).filter((x,i,a)=>!x.equipped&&a.findIndex(y=>y.id===x.id)===i));showNpc();
  options(tameChoices,m.taming||[]);showTaming();
  options(pet,m.companions||[]);options(foe,[...(m.location.npcs||[]),...(m.location.players||[])].filter(x=>x.id!==m.character.id));showPet();
  recipient.replaceChildren();for(const p of m.location.players||[])if(p.id!==m.character.id)recipient.append(new Option(p.name,p.id));
  const selected=partner.value;partner.replaceChildren();for(const person of [...(m.location.players||[]),...(m.location.npcs||[])])if(person.id!==m.character.id)partner.append(new Option(person.name,person.id));if(selected)partner.value=selected;relationshipChoices();
  const info=m.relationships||{};social.hidden=!m.relationships;proposals.replaceChildren();bonds.replaceChildren();
  for(const proposal of info.proposals||[]){const row=make('p',proposal.sender+' proposes '+proposal.kind+' ');row.append(button('Accept',()=>send('relationship accept '+proposal.id)),button('Decline',()=>send('relationship decline '+proposal.id)));proposals.append(row);}
  for(const rel of info.bonds||[])bonds.append(make('p',rel.names.join(' & ')+': '+rel.kinds.join(', ')+(rel.deceased?.length?' — deceased family member':'')+'; trust '+rel.trust));
  for(const input of social.querySelectorAll('[data-preference]'))input.checked=!!info.profile?.[input.dataset.preference];role.value=info.profile?.reproductive_role||'none';
  const old=item.value;item.replaceChildren();for(const i of m.character.inventory||[])if(!Array.from(item.options).some(o=>o.value===i.id))item.append(new Option(i.name,i.id));if(old)item.value=old;
 };
 window.societyMessage=msg=>{
  if(msg.type==='host_ready'){host.hidden=false;return true;}
  if(msg.type==='host_map'){
   const old=center.value;center.replaceChildren();for(const r of msg.map.rooms)center.append(new Option(r.name,r.id));center.value=msg.map.center||old;map.textContent=msg.map.text;
   players.replaceChildren(...msg.players.map(p=>make('p',p.name+' — '+p.location_name+' ['+p.id+']')));return true;
  }
  if(msg.type==='permissions'){fetchConfig().then(()=>{if(!config.editor_enabled)document.querySelector('[data-tab="game"]').click();});append('system',msg.text);return true;}
  if(msg.type==='trade_offer'){const row=make('div',msg.text);row.append(button('Accept',()=>{send('accept_offer '+msg.id);row.remove();}),button('Decline',()=>{send('decline_offer '+msg.id);row.remove();}));notices.append(row);return true;}
  return false;
 };
})();
