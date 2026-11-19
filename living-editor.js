/* Living-world forms use the existing Save / Validate / Apply workflow. */
(()=>{
 const enable=document.createElement('button');enable.type='button';enable.className='ed-btn';enable.textContent='Enable living rules';enable.title='Enable the expanded engine for the selected world';enable.onclick=async()=>{if(!ed.gameSlug){setStatus('Select a world first.','warn');return;}const res=await apiPost(gpath('living-enable'),{});setStatus(res.error||res.text,res.error?'warn':'');};document.getElementById('ed-save').parentElement.append(enable);
 const rules=document.createElement('button');rules.type='button';rules.className='ed-btn';rules.textContent='World rules';rules.onclick=async()=>{
  const current=await apiGet(gpath('world-rules'));if(current.error){setStatus(current.error,'warn');return;}
  const dialog=document.createElement('dialog'),mode=document.createElement('select'),cap=document.createElement('input'),pvp=document.createElement('input'),dawnHour=document.createElement('select'),dawnMinute=document.createElement('select'),save=document.createElement('button'),close=document.createElement('button');
  for(let h=0;h<25;h++)dawnHour.append(new Option(String(h).padStart(2,'0'),h));for(let m=0;m<60;m++)dawnMinute.append(new Option(String(m).padStart(2,'0'),m));dawnHour.value=Math.floor(current.sunrise_minute/60);dawnMinute.value=current.sunrise_minute%60;pvp.type='checkbox';pvp.checked=current.pvp;pvp.title='Allow player-versus-player combat outside sanctuaries';mode.append(new Option('Revival with consequences','revival'),new Option('Permanent character death','permanent'));cap.type='number';cap.min=1;cap.max=128;cap.value=current.max_players;mode.value=current.player_death;cap.title='Maximum connected players';save.textContent='Save world rules';close.textContent='Cancel';
  const startLabel=document.createElement('label'),startAtDawn=document.createElement('input'),startHour=document.createElement('select'),startMinute=document.createElement('select'),startNote=document.createElement('p');
  startAtDawn.type='checkbox';startAtDawn.id='world-start-at-dawn';startAtDawn.checked=current.start_at_dawn!==false;startLabel.append(startAtDawn,document.createTextNode(' Start new worlds at dawn'));
  startHour.id='world-start-hour';startMinute.id='world-start-minute';startHour.setAttribute('aria-label','New-world start hour');startMinute.setAttribute('aria-label','New-world start minute');
  for(let h=0;h<25;h++)startHour.append(new Option(String(h).padStart(2,'0'),h));for(let m=0;m<60;m++)startMinute.append(new Option(String(m).padStart(2,'0'),m));
  const initial=Number.isInteger(current.start_minute)?current.start_minute:current.sunrise_minute;startHour.value=Math.floor(initial/60);startMinute.value=initial%60;
  const syncStart=()=>{startHour.disabled=startMinute.disabled=startAtDawn.checked;if(startAtDawn.checked){startHour.value=dawnHour.value;startMinute.value=dawnMinute.value;}};startAtDawn.onchange=syncStart;dawnHour.addEventListener('change',syncStart);dawnMinute.addEventListener('change',syncStart);syncStart();
  startNote.textContent='New-world start time applies only to a fresh adventure/world in Single Player or Host mode. It does not reset an existing world, saved character, or running session. Hours run from 00 to 24.';
  const travel=document.createElement('fieldset'),travelLegend=document.createElement('legend'),travelLabel=document.createElement('label'),travelSpeed=document.createElement('input'),travelHelp=document.createElement('p');
  travelLegend.textContent='Travel pace';travelLabel.textContent='Speed multiplier ';travelSpeed.type='number';travelSpeed.id='world-travel-speed';travelSpeed.min='.25';travelSpeed.max='4';travelSpeed.step='.25';travelSpeed.value=current.travel_speed_multiplier??1;travelLabel.append(travelSpeed);travelHelp.textContent='1 is normal travel speed; 2 makes travel between locations twice as fast. Terrain and weather still affect travel. Save this setting in the world, then Apply or export the game file.';travel.append(travelLegend,travelLabel,travelHelp);
  const advancement=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='Experience and leveling';advancement.append(legend);const advancementInputs={};
  const defaults={enabled:true,level_cap:20,threshold_step:100,discovery_xp:2,quest_xp:50,social_xp:20,craft_xp:12,gather_xp:8,combat_xp:20,social_partners:5,repeat_percent:50,repeat_floor_percent:25,repeat_cooldown_minutes:5,repeat_daily_xp:200};
  for(const [key,value] of Object.entries({...defaults,...current.progression})){const label=document.createElement('label'),input=document.createElement('input');label.style.display='block';label.textContent=key.replaceAll('_',' ')+' ';input.type=key==='enabled'?'checkbox':'number';if(key==='enabled')input.checked=value;else{input.value=value;input.min=['level_cap','threshold_step'].includes(key)?1:0;input.max=key==='level_cap'?100:key==='social_partners'?20:['repeat_percent','repeat_floor_percent'].includes(key)?100:10000;input.step=1;}label.append(input);advancement.append(label);advancementInputs[key]=input;}
  const explanation=document.createElement('p');explanation.textContent='First accomplishments give full XP. Repeat successful crafting, gathering, hostile combat and repeatable quests earn diminishing practice XP, with a per-activity cooldown and a daily budget. Waiting alone gives no XP. Discoveries remain once-only; social lessons count a limited number of partners. Existing growth stays earned. Threshold step × current level is the XP needed for the next level.';advancement.append(explanation);
  save.onclick=async()=>{const r=await apiPost(gpath('world-rules'),{travel_speed_multiplier:Number(travelSpeed.value),start_minute:startAtDawn.checked?null:Number(startHour.value)*60+Number(startMinute.value),progression:Object.fromEntries(Object.entries(advancementInputs).map(([key,input])=>[key,key==='enabled'?input.checked:Number(input.value)])),player_death:mode.value,max_players:Number(cap.value),pvp:pvp.checked,sunrise_minute:Number(dawnHour.value)*60+Number(dawnMinute.value)});setStatus(r.error||r.text,r.error?'warn':'');if(!r.error)dialog.remove();};close.onclick=()=>dialog.remove();dialog.append(document.createTextNode('Choose player mortality and maximum player count. Existing permanent deaths stay recorded. Apply after saving. '),mode,cap,document.createTextNode(' Allow player combat '),pvp,document.createTextNode(' Calendar: 25 hours/day, 9 days/week, 26 days/month, 8 months/year. Dawn: '),dawnHour,dawnMinute,startLabel,startHour,startMinute,startNote,travel,advancement,save,close);document.body.append(dialog);dialog.showModal();
 };document.getElementById('ed-save').parentElement.append(rules);
 const civic=document.createElement('button');civic.type='button';civic.className='ed-btn';civic.textContent='Enable civic rules';civic.onclick=async()=>{const result=await apiPost(gpath('civic-enable'),{});setStatus(result.error||result.text,result.error?'warn':'');};document.getElementById('ed-save').parentElement.append(civic);
 const originalRender=renderFields,originalWidget=buildFieldWidget;
 renderFields=function(obj){
   obj={...(window.LIVING_DEFAULTS[ed.type]||{}),...obj};
   ED_FIELD_ORDER[ed.type]=[...new Set([...(ED_FIELD_ORDER[ed.type]||[]),...Object.keys(obj)])];
   originalRender(obj);
 };
 const refs={training_classes:'class',teaches_abilities:'ability',required_abilities:'ability',prey_species:'species',diet:'item',requires_resources:'resource',patrol_route:'room',talk_to:'npc',resources:'resource',encounters:'encounter',members:'npc',drops:'item',reward_items:'item',starting_equipment:'item',starting_abilities:'ability',visit_rooms:'room',prerequisites:'quest',exclusive_with:'quest'};
 const singles={sex:'sex',species:'species',requires_ammo:'item',location:'room',offer_room:'room',turn_in_room:'room',tool:'item',tame_item:'item',harvest_source:'npc',learn_ability:'ability',prepared_ability:'ability',class:'class',race:'race'};
 const counts={requires_species:'species',renewable_products:'item',remains:'item',components:'item',ingredients:'item',outputs:'item',yields:'item',required_items:'item',harvest:'item',kills:'npc',reputation:'group'};
 const choices={progress_scope:['lifetime','accepted'],consumption:['producer','herbivore','omnivore','carnivore'],food_origin:['','plant','animal'],name_mode:['manual','faction'],interaction_effect:['create','damage','heal','repair'],target_kind:['item','npc','self'],scope:['character','world'],station:['hand','forge','kitchen','enchanting','loom','workbench','alchemy','scriptorium','husbandry','construction','shipyard'],kind:['crafting','cooking'],effect:['damage','heal','ally_heal','group_heal','ward','cleanse','guarded_strike','focus','sunder','repair','mana_conversion','raise_dead','summon','resurrection','teleport','light','ally_ward','relief','weather_guard','tame','escape','enchant','disenchant'],disposition:['friendly','neutral','hostile'],companion_kind:['pet','familiar']};
 function el(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
 function picker(type,val){const s=el('select');s.append(new Option('Choose…',''));for(const o of ed.entriesCache[type]||[])s.append(new Option(o.name||o.id,o.id));if(val&&!Array.from(s.options).some(o=>o.value===val))s.append(new Option(val,val));s.value=val||'';return s;}
 function jsonField(key,val){const box=el('div'),hint=el('small','Advanced structured field: valid JSON is required. Changes apply only after Save field.'),ta=el('textarea');ta.dataset.creatorJson=key;ta.dataset.creatorType=ed.type;ta.dataset.creatorWorld=ed.gameSlug;ta.dataset.creatorEntry=String(ed.entryId);ta.dataset.creatorVersion=String(ed.selectionVersion||0);ta.rows=6;ta.value=JSON.stringify(val??{},null,2);const b=el('button','Save field');b.type='button';b.className='ed-btn';b.onclick=()=>{if(ta.dataset.creatorWorld!==ed.gameSlug||ta.dataset.creatorType!==ed.type||ta.dataset.creatorEntry!==String(ed.entryId)||ta.dataset.creatorVersion!==String(ed.selectionVersion||0)){setStatus('Selection changed. Reopen this JSON field before staging it.','warn');return;}try{const v=JSON.parse(ta.value);saveField(key,v);}catch(e){setStatus('Invalid JSON: '+e.message,'warn');}};box.append(hint,ta,b);return box;}
 function abilityRulesField(val){
  const box=jsonField('ability_rules',val);box.prepend(el('p','Optional ability family rules. Empty {} preserves legacy behavior. family: mage, class, or race; classes/races: eligible IDs; minimum_level: 1–100; cooldown_minutes: 0–15000; weapon_required: true/false; ward_hits: 1–20; ignore_defense: true/false; components: item ID → quantity. Non-mage abilities must have cost_mp 0. The full JSON field preserves all other rules.'));
  if(val&&(!val||typeof val!=='object'||Array.isArray(val))){return box;}
  const draft=structuredClone(val||{}),object=v=>v&&typeof v==='object'&&!Array.isArray(v);
  if(['summon','resurrection','teleport','utility'].some(key=>draft[key]!==undefined&&(!object(draft[key])||draft[key].version!==1))
   ||(draft.utility?.conditions!==undefined&&!object(draft.utility.conditions))){box.prepend(el('p','Repair unsupported spell settings in the full JSON field before using structured controls. Validate checks the complete ability.'));return box;}
  const selection={world:ed.gameSlug,type:ed.type,id:String(ed.entryId),version:String(ed.selectionVersion||0)};
  const advanced=el('details');advanced.append(el('summary','Spell mechanics controls'));box.append(advanced);
  advanced.append(el('p','Enable only the settings matching this ability’s effect. Raising an undead creature uses raise_dead; restoring the same fallen person uses resurrection. Summoning needs a real NPC template. Teleport destinations must be authored rooms the traveler has already visited.'));
  function field(parent,label,node,name){const row=el('label',label);row.style.display='block';row.style.margin='8px 0';node.style.maxWidth='100%';node.style.boxSizing='border-box';node.dataset.spellRule=name;node.setAttribute('aria-label',label);row.append(node);parent.append(row);return node;}
  function number(parent,label,name,value,min,max){const n=el('input');n.type='number';n.min=min;n.max=max;n.step=1;n.value=value;return field(parent,label+' ',n,name);}
  function boolean(parent,label,name,value){const n=el('input');n.type='checkbox';n.checked=value===true;return field(parent,label+' ',n,name);}
  function searchPicker(parent,label,type,value,name){
   const search=el('input');search.type='search';search.placeholder='Find by name or ID';search.dataset.spellSearch=name;field(parent,'Find '+type+' ',search,name+'_search');
   const select=field(parent,label,el('select'),name);let selected=value||'';
   const draw=()=>{selected=select.value||selected;const query=search.value.trim().toLocaleLowerCase(),rows=ed.entriesCache[type]||[];
    const found=rows.filter(row=>!query||String(row.id+' '+(row.name||'')).toLocaleLowerCase().includes(query)).slice(0,50);
    select.replaceChildren(new Option('Choose…',''));if(selected&&!found.some(row=>row.id===selected)){const row=rows.find(row=>row.id===selected);select.append(new Option(row?.name||selected,selected));}
    for(const row of found)select.append(new Option(row.name||row.id,row.id));select.value=selected;
   };
   select.onchange=()=>{selected=select.value;};search.oninput=draw;draw();parent.append(el('small',' Up to 50 matches. Type part of a name or ID to narrow the list.'));return select;
  }
  function section(name,label){const outer=el('fieldset');outer.style.minWidth='0';outer.append(el('legend',label));advanced.append(outer);const enabled=boolean(outer,'Use these settings',name+'_enabled',draft[name]!==undefined),fields=el('fieldset');fields.style.minWidth='0';outer.append(fields);enabled.onchange=()=>{fields.disabled=!enabled.checked;};enabled.onchange();return {enabled,fields};}
  const family=field(advanced,'Ability family ',el('select'),'family');for(const name of ['mage','class','race'])family.append(new Option(name,name));family.value=draft.family||'class';
  const allies=boolean(advanced,'Allow ally_heal to target other living players here','ally_players',draft.ally_players);
  const summon=section('summon','Finite summoned or raised creatures'),sc=draft.summon||{};
  const template=searchPicker(summon.fields,'NPC template (summon only; leave blank for raise_dead) ','npc',sc.npc||'','summon_npc');
  const summonDuration=number(summon.fields,'Lifetime in game minutes','summon_duration',sc.duration_minutes??30,1,1440);
  const summonCap=number(summon.fields,'Maximum active creatures','summon_max_active',sc.max_active??1,1,8);
  const summonLevel=number(summon.fields,'Maximum target/template level','summon_max_level',sc.max_level??5,1,100);
  const resurrection=section('resurrection','Restore a fallen person'),rc=draft.resurrection||{};
  const players=boolean(resurrection.fields,'Allow fallen players','resurrection_players',rc.players);
  const companions=boolean(resurrection.fields,'Allow owned fallen companions','resurrection_companions',rc.companions);
  const health=number(resurrection.fields,'Health restored, percent','resurrection_health',rc.health_percent??25,1,100);
  const recovery=number(resurrection.fields,'Recovery in game minutes','resurrection_recovery',rc.recovery_minutes??60,1,1440);
  const injury=number(resurrection.fields,'Injury on revival','resurrection_injury',rc.injury??20,0,100);
  const teleport=section('teleport','Travel to a visited waypoint'),tc=draft.teleport||{};
  const destinations=field(teleport.fields,'Destination room IDs (one per line) ',el('textarea'),'teleport_destinations');destinations.rows=5;destinations.style.display='block';destinations.style.width='100%';destinations.value=Array.isArray(tc.destinations)?tc.destinations.join('\n'):'';
  const destination=searchPicker(teleport.fields,'Add an existing room ','room','','teleport_add');
  const add=el('button','Append selected room');add.type='button';add.onclick=()=>{if(!destination.value)return;const values=destinations.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);if(!values.includes(destination.value)){destinations.value=[...values,destination.value].join('\n');destinations.dispatchEvent(new Event('input',{bubbles:true}));}};teleport.fields.append(add,el('small',' Only these rooms can be offered, and the traveler must have visited them. require_visited is always true; access and travel restrictions are checked again by the server.'));
  const utility=section('utility','Light, protection and relief'),uc=draft.utility||{};
  const utilityEffect=field(utility.fields,'Utility settings for effect ',el('select'),'utility_effect');
  for(const [id,label] of [['light','light — temporary illumination'],['ally_ward','ally_ward — limited protective hits'],['relief','relief — reduce named conditions'],['weather_guard','weather_guard — reduce weather exposure']])utilityEffect.append(new Option(label,id));
  utilityEffect.value=uc.conditions!==undefined?'relief':uc.hits!==undefined?'ally_ward':uc.reduction_percent!==undefined?'weather_guard':'light';
  utility.fields.append(el('small',' Match this choice to the ability’s effect field. Saving these settings does not change the effect. Self is always eligible; other recipients must be present and permitted by the server.'));
  const utilityPlayers=boolean(utility.fields,'Allow other players here','utility_players',uc.players),utilityCompanions=boolean(utility.fields,'Allow owned companions here','utility_companions',uc.companions);
  const durationFields=el('div'),wardFields=el('div'),reliefFields=el('div'),weatherFields=el('div');utility.fields.append(durationFields,wardFields,reliefFields,weatherFields);
  const utilityDuration=number(durationFields,'Duration in game minutes','utility_duration',uc.duration_minutes??30,1,1440);
  const utilityHits=number(wardFields,'Protected incoming hits','utility_hits',uc.hits??5,1,64);wardFields.append(el('small',' Set the ability’s power field from 1 to 100 for the protection strength.'));
  const conditionInputs={};for(const [name,label] of [['injury','Injury'],['disease','Disease'],['intoxication','Intoxication']]){const input=number(reliefFields,label+' reduction (blank omits)','utility_'+name,uc.conditions?.[name]??'',1,100);conditionInputs[name]=input;}
  reliefFields.append(el('small',' Include at least one reduction from 1 to 100. Blank conditions are not affected.'));
  const weatherReduction=number(weatherFields,'Weather exposure reduction, percent','utility_reduction',uc.reduction_percent??25,1,75);
  utilityEffect.onchange=()=>{durationFields.hidden=!['light','weather_guard'].includes(utilityEffect.value);wardFields.hidden=utilityEffect.value!=='ally_ward';reliefFields.hidden=utilityEffect.value!=='relief';weatherFields.hidden=utilityEffect.value!=='weather_guard';};utilityEffect.onchange();
  const save=el('button','Save spell settings');save.type='button';save.className='ed-btn';save.dataset.saveSpellRules='true';
  save.onclick=()=>{
   if(selection.world!==ed.gameSlug||selection.type!==ed.type||selection.id!==String(ed.entryId)||selection.version!==String(ed.selectionVersion||0)){setStatus('Selection changed. Reopen ability rules before saving them.','warn');return;}
   const value=structuredClone(draft);
   try{
    const whole=(input,min,max)=>{const n=Number(input.value);if(input.value===''||!Number.isInteger(n)||n<min||n>max)throw Error(input.getAttribute('aria-label')+'must be a whole number from '+min+' to '+max+'.');return n;};
    if(!['mage','class','race'].includes(family.value))throw Error('Choose a supported ability family.');
    if(Object.hasOwn(value,'family')||summon.enabled.checked||resurrection.enabled.checked||teleport.enabled.checked||utility.enabled.checked||allies.checked)value.family=family.value;
    if(Object.hasOwn(value,'ally_players')||allies.checked)value.ally_players=allies.checked;
    if(summon.enabled.checked){
     value.summon={...sc,version:1,duration_minutes:whole(summonDuration,1,1440),max_active:whole(summonCap,1,8),max_level:whole(summonLevel,1,100)};
     if(template.value){if(!(ed.entriesCache.npc||[]).some(row=>row.id===template.value))throw Error('Choose an existing NPC template.');value.summon.npc=template.value;}else delete value.summon.npc;
    }else delete value.summon;
    if(resurrection.enabled.checked){
     if(!players.checked&&!companions.checked)throw Error('Allow at least one eligible resurrection target category.');
     value.resurrection={...rc,version:1,players:players.checked,companions:companions.checked,health_percent:whole(health,1,100),recovery_minutes:whole(recovery,1,1440),injury:whole(injury,0,100)};
    }else delete value.resurrection;
    if(teleport.enabled.checked){
     const ids=destinations.value.split(/\r?\n/).map(id=>id.trim()).filter(Boolean);
     if(ids.length<1||ids.length>128||new Set(ids).size!==ids.length||ids.some(id=>!(ed.entriesCache.room||[]).some(row=>row.id===id)))throw Error('Choose 1–128 unique existing destination rooms.');
     value.teleport={...tc,version:1,destinations:ids,require_visited:true};
    }else delete value.teleport;
    if(utility.enabled.checked){
     const cfg={...uc,version:1,players:utilityPlayers.checked,companions:utilityCompanions.checked};
     for(const key of ['duration_minutes','hits','conditions','reduction_percent'])delete cfg[key];
     if(utilityEffect.value==='light'||utilityEffect.value==='weather_guard')cfg.duration_minutes=whole(utilityDuration,1,1440);
     if(utilityEffect.value==='ally_ward')cfg.hits=whole(utilityHits,1,64);
     else if(utilityEffect.value==='relief'){
      cfg.conditions={...(uc.conditions||{})};let count=0;
      for(const [name,input] of Object.entries(conditionInputs)){if(input.value==='')delete cfg.conditions[name];else{cfg.conditions[name]=whole(input,1,100);count++;}}
      if(!count)throw Error('Include at least one condition reduction from 1 to 100.');
     }else if(utilityEffect.value==='weather_guard')cfg.reduction_percent=whole(weatherReduction,1,75);
     else if(utilityEffect.value!=='light')throw Error('Choose a supported utility effect.');
     value.utility=cfg;
    }else delete value.utility;
    saveField('ability_rules',value);
   }catch(error){setStatus('Cannot stage spell settings: '+error.message,'warn');}
  };
  advanced.append(el('p','Save spell settings stages these controls while retaining family eligibility, components, costs and additional JSON fields. Use the full JSON field above for other ability rules. Validate checks that the settings and effect agree.'),save);return box;
 }
 function presentationField(key,val){
  const styles={glow:'Glow around the recipient',ground_rise:'Crawl up from the ground',portal_rise:'Emerge through a ground portal',projectile:'Travel from caster to recipient',ward:'Protective shield',burst:'Brief radial burst',fade:'Departure or arrival ring'};
  const object=val&&typeof val==='object'&&!Array.isArray(val);
  if(val&&(!object||(val.version!==undefined&&val.version!==1)
   ||(val.style!==undefined&&!Object.hasOwn(styles,val.style))
   ||(val.colors!==undefined&&(!Array.isArray(val.colors)||val.colors.some(c=>typeof c!=='string'))))){
   const raw=jsonField(key,val);raw.prepend(el('p','This presentation needs advanced editing. The original fields are preserved. Supported presentations use version 1 and the bounded settings described in the Creator guide; Validate must pass before export or play.'));return raw;
  }
  const draft=structuredClone(val||{}),selection={world:ed.gameSlug,type:ed.type,id:String(ed.entryId),version:String(ed.selectionVersion||0)};
  const box=el('div'),section=el('fieldset');section.style.minWidth='0';box.append(section);section.append(el('legend','Visible magic'));
  section.append(el('p','Presentation describes a successful server-confirmed action. It does not grant an ability, heal, move, revive or summon anyone. Ground and portal emergence reveal the actual creature created by the corresponding mechanic.'));
  const enabled=el('input');enabled.type='checkbox';enabled.checked=Object.keys(draft).length>0;enabled.dataset.presentationField='enabled';
  const include=el('label',' Use this presentation');include.prepend(enabled);section.append(include);
  const fields=el('fieldset');fields.style.minWidth='0';section.append(fields);
  function field(label,node,name){const row=el('label',label);row.style.display='block';row.style.margin='8px 0';node.style.display='block';node.style.width='100%';node.style.boxSizing='border-box';node.style.minWidth='0';node.dataset.presentationField=name;node.setAttribute('aria-label',label);row.append(node);fields.append(row);return node;}
  const style=field('Visual style',el('select'),'style');for(const [id,label] of Object.entries(styles))style.append(new Option(label,id));style.value=draft.style||'glow';
  const colors=field('One to three colors (#RRGGBB, one per line)',el('textarea'),'colors');colors.rows=3;colors.value=(draft.colors||['#B1E4E8']).join('\n');
  function number(label,name,value,min,max,step){const input=field(label,el('input'),name);input.type='number';input.min=min;input.max=max;input.step=step;input.value=value;return input;}
  const duration=number('Duration in milliseconds (300–5000)','duration_ms',draft.duration_ms??1800,300,5000,1);
  const scale=number('Size relative to the actor (0.5–2)','scale',draft.scale??1,.5,2,.1);
  const particles=number('Particles (0–24)','particles',draft.particles??12,0,24,1);
  enabled.onchange=()=>{fields.disabled=!enabled.checked;};enabled.onchange();
  fields.append(el('small','Reduced-motion mode keeps the actor fully visible and uses a brief static indicator. Effects end quickly and do not replay after leaving the game.'));
  const commit=el('button','Save presentation');commit.type='button';commit.className='ed-btn';commit.dataset.savePresentation=key;
  commit.onclick=()=>{
   if(selection.world!==ed.gameSlug||selection.type!==ed.type||selection.id!==String(ed.entryId)||selection.version!==String(ed.selectionVersion||0)){setStatus('Selection changed. Reopen this presentation before saving it.','warn');return;}
   if(!enabled.checked){saveField(key,{});return;}
   const palette=colors.value.split(/\r?\n/).map(c=>c.trim()).filter(Boolean);
   if(!Object.hasOwn(styles,style.value)||palette.length<1||palette.length>3||palette.some(c=>!/^#[0-9a-f]{6}$/i.test(c))){setStatus('Choose a supported style and one to three colors in #RRGGBB format.','warn');return;}
   const values={duration_ms:Number(duration.value),scale:Number(scale.value),particles:Number(particles.value)};
   if(!duration.value||!scale.value||!particles.value||!Number.isInteger(values.duration_ms)||values.duration_ms<300||values.duration_ms>5000
    ||!Number.isFinite(values.scale)||values.scale<.5||values.scale>2||!Number.isInteger(values.particles)||values.particles<0||values.particles>24){setStatus('Use a duration of 300–5000 whole milliseconds, size 0.5–2 and 0–24 whole particles.','warn');return;}
   saveField(key,{...draft,version:1,style:style.value,colors:palette,...values});
  };
  section.append(el('p','Save presentation stages this field only. Save draft, Validate and export the complete .expanse file to publish the authored settings. Additional custom fields are preserved.'),commit);return box;
 }
 function npcSpellcastingField(val){
  const key='spellcasting',object=val&&typeof val==='object'&&!Array.isArray(val),box=jsonField(key,val);
  if(val!==undefined&&(!object||(val.version!==undefined&&val.version!==1)
   ||(val.abilities!==undefined&&(!Array.isArray(val.abilities)||val.abilities.some(id=>typeof id!=='string'))))){box.querySelector('textarea').value=JSON.stringify(val,null,2);box.prepend(el('p','Unsupported NPC spellcasting metadata is preserved in the full JSON field. Repair it, then Validate before export.'));return box;}
  const draft=structuredClone(val||{}),selection={world:ed.gameSlug,type:ed.type,id:String(ed.entryId),version:String(ed.selectionVersion||0)};
  const current=()=>selection.world===ed.gameSlug&&selection.type===ed.type&&selection.id===String(ed.entryId)&&selection.version===String(ed.selectionVersion||0);
  const outer=el('fieldset');outer.style.minWidth='0';outer.append(el('legend','NPC combat spellcasting'));box.prepend(outer);
  outer.append(el('p','This policy grants a chosen NPC a finite combat spell repertoire. Casting discipline and level do not change their primary class, profession, identity, equipment or physical statistics. Ordinary spell costs, components, recovery and target rules still apply.'));
  const enabled=el('input');enabled.type='checkbox';enabled.checked=Object.keys(draft).length>0;enabled.dataset.npcSpellcastingField='enabled';const enabledLabel=el('label',' Use this NPC casting policy');enabledLabel.prepend(enabled);outer.append(enabledLabel);
  const fields=el('fieldset');fields.style.minWidth='0';outer.append(fields);
  function field(label,node,name){const row=el('label',label);row.style.display='block';row.style.margin='8px 0';node.style.display='block';node.style.width='100%';node.style.boxSizing='border-box';node.style.minWidth='0';node.dataset.npcSpellcastingField=name;node.setAttribute('aria-label',label);row.append(node);fields.append(row);return node;}
  function number(label,name,value,min,max){const node=field(label,el('input'),name);node.type='number';node.step=1;node.min=min;node.max=max;node.value=value;return node;}
  const discipline=field('Casting discipline',picker('class',draft.class),'class');
  const level=number('Casting level (1–100)','level',draft.level??1,1,100);
  const abilities=field('Spell IDs, one per line (1–8 unique spells)',el('textarea'),'abilities');abilities.rows=5;abilities.value=(draft.abilities||[]).join('\n');
  const search=field('Find a combat spell',el('input'),'search');search.type='search';search.placeholder='Name or ID';
  const choice=field('Add a configured spell',el('select'),'add');
  const supported=new Set(['damage','heal','ally_heal','ward','ally_ward']);
  function draw(){const selected=choice.value||'',query=search.value.trim().toLocaleLowerCase();const rows=(ed.entriesCache.ability||[]).filter(a=>a.ability_rules?.family==='mage'&&supported.has(a.effect)&&(!query||String(a.id+' '+(a.name||'')).toLocaleLowerCase().includes(query))).slice(0,50);choice.replaceChildren(new Option('Choose…',''));if(selected&&!rows.some(a=>a.id===selected))choice.append(new Option(selected,selected));for(const a of rows)choice.append(new Option(a.name||a.id,a.id));choice.value=selected;}
  search.oninput=draw;draw();fields.append(el('small',' Up to 50 matches. Only configured mage damage, heal, ally_heal, ward and ally_ward effects are supported. Class, explicit NPC race and level eligibility are checked against the current draft when saved.'));
  const add=el('button','Append selected spell');add.type='button';add.onclick=()=>{if(!choice.value)return;const ids=abilities.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);if(ids.includes(choice.value))return;if(ids.length>=8){setStatus('An NPC casting policy can contain at most eight spells.','warn');return;}abilities.value=[...ids,choice.value].join('\n');};fields.append(add);
  const maxMana=number('Maximum mana (1–500)','max_mana',draft.max_mana??24,1,500);
  const startingMana=number('Starting mana (0 to maximum mana)','starting_mana',draft.starting_mana??24,0,500);
  const regen=number('Mana recovered per game minute (0–10)','regen_per_minute',draft.regen_per_minute??1,0,10);
  const delay=number('Delay before mana recovery, game minutes (1–1440)','regen_delay_minutes',draft.regen_delay_minutes??10,1,1440);
  const interval=number('Minimum interval between casts, game minutes (1–60)','cast_interval_minutes',draft.cast_interval_minutes??2,1,60);
  const heal=number('Heal below health percent (1–99)','heal_below_percent',draft.heal_below_percent??40,1,99);
  enabled.onchange=()=>{fields.disabled=!enabled.checked;};enabled.onchange();
  outer.append(el('p','The NPC casts only during an authorized combat turn. Healing applies to itself or actual friendly NPC responders in the same fight; this policy does not supply passive healing or teach players spells. Empty {} disables it.'));
  const save=el('button','Save NPC spellcasting');save.type='button';save.className='ed-btn';save.dataset.saveNpcSpellcasting='true';let pending=false;
  save.onclick=async()=>{
   if(pending)return;
   if(!current()){setStatus('Selection changed. Reopen this NPC before saving its spellcasting policy.','warn');return;}
   if(!enabled.checked){saveField(key,{});return;}
   try{
    const whole=(node,min,max)=>{const n=Number(node.value);if(node.value===''||!Number.isInteger(n)||n<min||n>max)throw Error(node.getAttribute('aria-label')+' must be a whole number from '+min+' to '+max+'.');return n;};
    const maximum=whole(maxMana,1,500),ids=abilities.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    if(!discipline.value)throw Error('Choose an existing casting discipline.');
    if(ids.length<1||ids.length>8||new Set(ids).size!==ids.length)throw Error('Choose one to eight unique configured spell IDs.');
    const value={...draft,version:1,class:discipline.value,level:whole(level,1,100),abilities:ids,max_mana:maximum,starting_mana:whole(startingMana,0,maximum),regen_per_minute:whole(regen,0,10),regen_delay_minutes:whole(delay,1,1440),cast_interval_minutes:whole(interval,1,60),heal_below_percent:whole(heal,1,99)};
    pending=true;save.disabled=true;
    const [npc,spellList,classList]=await Promise.all([apiGet(gpath('show/npc/'+encodeURIComponent(selection.id))),apiGet(gpath('entries/ability')),apiGet(gpath('entries/class'))]);
    if(!current())throw Error('Selection changed. Reopen this NPC before saving its spellcasting policy.');
    if(npc?.error||spellList?.error||classList?.error||npc?.id!==selection.id||!Array.isArray(spellList?.entries)||!Array.isArray(classList?.entries))throw Error('Could not read the current NPC and spell definitions. Reopen this field and try again.');
    if(!classList.entries.some(c=>c.id===value.class))throw Error('Choose an existing casting discipline.');
    for(const id of ids){
     const a=spellList.entries.find(a=>a.id===id),rules=a?.ability_rules;
     if(!a||!rules||rules.family!=='mage'||!supported.has(a.effect))throw Error('Spell '+id+' must be a configured mage damage, heal, ally_heal, ward or ally_ward ability.');
     if(!Array.isArray(rules.classes)||!rules.classes.includes(value.class))throw Error((a.name||id)+' does not allow this casting discipline.');
     if(rules.races!==undefined&&(!Array.isArray(rules.races)||(rules.races.length&&!rules.races.includes(npc.race))))throw Error((a.name||id)+' does not allow this NPC’s explicit race.');
     const minimum=rules.minimum_level??1;if(!Number.isInteger(minimum)||minimum<1||minimum>value.level)throw Error((a.name||id)+' requires a higher or valid casting level.');
    }
    await saveField(key,value);
   }catch(error){setStatus('Cannot stage NPC spellcasting: '+error.message,'warn');}
   finally{pending=false;save.disabled=false;}
  };
  outer.append(save,el('p','This stages only the spellcasting field. Save the draft, Validate, then export or Apply through the normal Creator workflow.'));return box;
 }
 function singingField(key,val){
  const object=x=>!!x&&typeof x==='object'&&!Array.isArray(x),strings=x=>Array.isArray(x)&&x.every(v=>typeof v==='string');
  const type=ed.type,source=val??{},kind=key==='song'?'song':key==='instrument'?'instrument':type;
  let supported=object(source)&&(source.version===undefined||source.version===1);
  for(const name of ['tradition','style','voice','tag'])if(source?.[name]!==undefined&&typeof source[name]!=='string')supported=false;
  for(const name of ['songs','preferred_instruments','contexts','festivals'])if(source?.[name]!==undefined&&!strings(source[name]))supported=false;
  if(Array.isArray(source?.contexts)&&source.contexts.some(context=>!['work','leisure','performance','festival'].includes(context)))supported=false;
  if(source?.respond!==undefined&&typeof source.respond!=='boolean')supported=false;
  if(source?.interval_minutes!==undefined&&(!Number.isInteger(source.interval_minutes)||source.interval_minutes<1||source.interval_minutes>1500))supported=false;
  if(source?.voices!==undefined&&(!Array.isArray(source.voices)||source.voices.some(v=>!object(v)||typeof v.id!=='string'||typeof v.label!=='string'||(v.transpose!==undefined&&!Number.isInteger(v.transpose)))))supported=false;
  if(source?.form!==undefined&&!['solo','call_response','relay'].includes(source.form))supported=false;
  if(source?.verses!==undefined&&(!Array.isArray(source.verses)||source.verses.some(v=>!object(v)||typeof v.call!=='string'||(v.response!==undefined&&typeof v.response!=='string')||(v.relay!==undefined&&!strings(v.relay)))))supported=false;
  if(Array.isArray(source?.verses)&&source.verses.some(v=>object(v)&&(((source.form||'solo')==='solo'&&(v.response!==undefined||v.relay!==undefined))||(source.form==='call_response'&&v.relay!==undefined)||(source.form==='relay'&&(v.response!==undefined||(Array.isArray(v.relay)&&v.relay.length>3))))))supported=false;
  if(source?.score!==undefined&&!object(source.score))supported=false;
  if(!supported){const raw=jsonField(key,val);raw.prepend(el('p','This singing record needs advanced editing. Its original JSON is preserved. Supported singing, song and instrument fields are described in the Creator guide; Validate checks their meanings and references.'));return raw;}
  const draft=structuredClone(source),context={world:ed.gameSlug,type:ed.type,id:String(ed.entryId),version:String(ed.selectionVersion||0)};
  const box=el('div'),section=el('fieldset'),fields=el('fieldset');box.className='singing-editor';section.style.minWidth=fields.style.minWidth='0';box.append(section);
  const title=kind==='song'?'Songbook':kind==='instrument'?'Musical instrument':kind==='race'?'Singing tradition and voices':'Individual singing';section.append(el('legend',title));
  const enabled=el('input');enabled.type='checkbox';enabled.checked=Object.keys(draft).length>0;enabled.dataset.musicField='enabled';
  const enabledLabel=el('label',' Include '+title.toLowerCase());enabledLabel.prepend(enabled);section.append(enabledLabel,fields);
  const changed=()=>section.dispatchEvent(new Event('input',{bubbles:true}));
  const button=(parent,label,action)=>{const b=el('button',label);b.type='button';b.className='ed-btn';b.onclick=action;parent.append(b);return b;};
  function field(parent,label,name,value='',tag='input'){
   const row=el('label',label),input=el(tag);row.style.display='block';row.style.margin='8px 0';input.style.display='block';input.style.width='100%';input.style.boxSizing='border-box';input.style.minWidth='0';
   if(tag==='input')input.type='text';if(tag==='textarea')input.rows=3;input.value=value;input.dataset.musicField=name;input.setAttribute('aria-label',label);row.append(input);parent.append(row);return input;
  }
  function numberField(parent,label,name,value,min,max){const input=field(parent,label,name,value??'');input.type='number';input.min=min;input.max=max;input.step=1;return input;}
  const lines=input=>input.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  function set(value,name,next,empty=''){if(Object.hasOwn(value,name)||JSON.stringify(next)!==JSON.stringify(empty))value[name]=next;}
  function songList(){
   const input=field(fields,'Known songbook item IDs (one per line)','songs',(draft.songs||[]).join('\n'),'textarea');
   const select=picker('item','');select.dataset.musicField='add_song';select.setAttribute('aria-label','Existing songbook item');select.style.maxWidth='100%';fields.append(select);
   button(fields,'Append selected songbook',()=>{if(!select.value)return;const ids=lines(input);if(ids.includes(select.value)){setStatus('That item is already in this repertoire.','warn');return;}input.value=[...ids,select.value].join('\n');input.dispatchEvent(new Event('input',{bubbles:true}));});
   fields.append(el('small','Choose a readable item with its own song field. Any race may learn another songbook by reading it. Validate checks these IDs.'));return input;
  }
  let collect;
  if(kind==='race'){
   fields.append(el('p','Author this tradition here. Each person receives a stable individual voice from this pool, independent of sex or gender. Leaving the pool empty does not borrow another tradition.'));
   const tradition=field(fields,'Tradition ID (optional)','tradition',draft.tradition||''),style=field(fields,'Performance style','style',draft.style||'','textarea'),songs=songList();
   const instruments=field(fields,'Preferred instrument tags (one per line)','preferred_instruments',(draft.preferred_instruments||[]).join('\n'),'textarea');
   const voiceHost=el('div');fields.append(voiceHost);const voices=(draft.voices||[]).map(v=>({...v}));let voiceRows=[];
   function drawVoices(){voiceHost.replaceChildren();voiceRows=voices.map((voice,index)=>{
    const row=el('fieldset');row.style.minWidth='0';row.dataset.musicVoice=String(index);row.append(el('legend','Voice '+(index+1)));voiceHost.append(row);
    const id=field(row,'Stable voice ID','voice_id',voice.id),label=field(row,'Voice label','voice_label',voice.label),transpose=numberField(row,'Semitone transposition (−36 to 36)','transpose',voice.transpose??0,-36,36);
    id.oninput=()=>{voice.id=id.value;};label.oninput=()=>{voice.label=label.value;};transpose.oninput=()=>{voice.transpose=transpose.value===''?null:Number(transpose.value);};
    button(row,'Remove voice',()=>{voices.splice(index,1);drawVoices();changed();});return {voice,id,label,transpose};
   });}
   drawVoices();button(fields,'Add voice',()=>{voices.push({id:'',label:'',transpose:0});drawVoices();changed();});
   fields.append(el('small','Transpose shifts the authored voice notes by semitones. Validate checks every song against every available voice; the engine never clamps an out-of-range melody.'));
   collect=value=>{
    const pool=voiceRows.map(({voice,id,label,transpose})=>{const result={...voice,id:id.value,label:label.value};set(result,'transpose',Number(transpose.value),0);return result;});
    if(pool.some((v,i)=>!v.id.trim()||!v.label.trim()||voiceRows[i].transpose.value===''||!Number.isInteger(v.transpose??0)||(v.transpose??0)<-36||(v.transpose??0)>36)||new Set(pool.map(v=>v.id)).size!==pool.length)throw Error('Use unique voice IDs, nonempty labels and integer transpositions from −36 to 36.');
    set(value,'tradition',tradition.value);set(value,'style',style.value);set(value,'songs',lines(songs),[]);set(value,'preferred_instruments',lines(instruments),[]);set(value,'voices',pool,[]);
   };
  }else if(kind==='npc'){
   fields.append(el('p','Repertoire adds to this person’s race songs. Only selected contexts allow spontaneous singing. Responses and relays require an actual local, awake, cooperative NPC who knows the song. Other players never answer automatically.'));
   const voice=field(fields,'Voice ID from this person’s race pool (optional)','voice',draft.voice||''),songs=songList(),interval=numberField(fields,'Minutes between spontaneous performances (blank uses world setting)','interval_minutes',draft.interval_minutes,1,1500);
   const festivals=field(fields,'Festival IDs (one per line; must exist in metadata.singing.festivals)','festivals',(draft.festivals||[]).join('\n'),'textarea');
   const contexts={};for(const name of ['work','leisure','performance','festival']){const label=el('label',' Sing during '+name),input=el('input');input.type='checkbox';input.checked=(draft.contexts||[]).includes(name);input.dataset.musicContext=name;label.prepend(input);label.style.display='block';fields.append(label);contexts[name]=input;}
   const respond=el('input');respond.type='checkbox';respond.checked=draft.respond===true;respond.dataset.musicField='respond';const responseLabel=el('label',' Willing to answer or pass along a known song');responseLabel.prepend(respond);fields.append(responseLabel);
   collect=value=>{
    if(interval.value!==''&&(!Number.isInteger(Number(interval.value))||Number(interval.value)<1||Number(interval.value)>1500))throw Error('The singing interval must be a whole number from 1 to 1500 minutes, or blank.');
    const selected=(draft.contexts||[]).filter(name=>contexts[name].checked);for(const name of Object.keys(contexts))if(contexts[name].checked&&!selected.includes(name))selected.push(name);
    set(value,'voice',voice.value);set(value,'songs',lines(songs),[]);set(value,'contexts',selected,[]);set(value,'festivals',lines(festivals),[]);set(value,'respond',respond.checked,false);if(interval.value!=='')value.interval_minutes=Number(interval.value);else delete value.interval_minutes;
   };
  }else if(kind==='instrument'){
   fields.append(el('p','This tag identifies a real playable instrument. Accompaniment is available only when an actual participant carries an item with the score’s matching tag. Singing never creates or replenishes items.'));
   const tag=field(fields,'Instrument tag','tag',draft.tag||'');
   fields.append(el('small','Use normal item descriptions, recipes, ingredients and workshop stock to author construction and trade. Set producers’ recipes, work location and finite supplies separately.'));
   collect=value=>{if(!tag.value.trim())throw Error('Enter the instrument tag used by accompaniment tracks.');value.tag=tag.value;};
  }else{
   fields.append(el('p','Use this field on an ordinary readable item. Its name, read_text, publication and physical location remain separate. One authored verse is performed at a time; no lyrics or musical style are generated by the engine.'));
   const tradition=field(fields,'Tradition ID (optional)','tradition',draft.tradition||''),style=field(fields,'Performance style','style',draft.style||'','textarea'),form=field(fields,'Song form','form','','select');
   for(const [id,label] of [['solo','Solo'],['call_response','Call and response'],['relay','Relay between actual singers']])form.append(new Option(label,id));form.value=draft.form||'solo';
   const verses=(draft.verses||[]).map(v=>structuredClone(v)),verseHost=el('div');fields.append(verseHost);let verseRows=[];
   function drawVerses(){verseHost.replaceChildren();verseRows=verses.map((verse,index)=>{
    const row=el('fieldset');row.style.minWidth='0';row.dataset.musicVerse=String(index);row.append(el('legend','Verse '+(index+1)));verseHost.append(row);
    const call=field(row,'Lead line (up to 240 characters)','call',verse.call||'','textarea');call.maxLength=240;call.oninput=()=>{verse.call=call.value;};let response=null,relay=null;
    if(form.value==='call_response'){response=field(row,'Answering line (up to 240 characters)','response',verse.response||'','textarea');response.maxLength=240;response.oninput=()=>{verse.response=response.value;};}
    if(form.value==='relay'){relay=[];for(let next=0;next<3;next++){const line=field(row,'Relay singer '+(next+2)+' line (up to 240 characters; later singers optional)','relay_'+(next+1),verse.relay?.[next]||'','textarea');line.maxLength=240;line.oninput=()=>{verse.relay=relay.map(input=>input.value);while(verse.relay.at(-1)==='')verse.relay.pop();};relay.push(line);}}
    for(const [label,delta] of [['Move verse up',-1],['Move verse down',1]]){const move=button(row,label,()=>{const next=index+delta;if(next<0||next>=verses.length)return;[verses[index],verses[next]]=[verses[next],verses[index]];drawVerses();changed();});move.disabled=index+delta<0||index+delta>=verses.length;}
    button(row,'Remove verse',()=>{verses.splice(index,1);drawVerses();changed();});return {verse,call,response,relay};
   });}
   drawVerses();form.onchange=()=>{drawVerses();changed();};button(fields,'Add verse',()=>{if(verses.length>=16){setStatus('A song supports at most 16 verses.','warn');return;}verses.push({call:''});drawVerses();changed();});
   fields.append(el('small','Changing the form removes incompatible response or relay lines only when you Save songbook. Each relay successor needs a different willing local NPC; absent singers and their tracks are omitted.'));
   const score=field(fields,'Optional synthesized score (JSON; blank means text only)','score',draft.score===undefined?'':JSON.stringify(draft.score,null,2),'textarea');score.rows=12;score.spellcheck=false;
   fields.append(el('small','Score version 1: tempo 40–240; at most 8 tracks, 128 notes and 20 seconds including releases. Notes are [MIDI pitch, start beats, duration beats, velocity]. Voice tracks use periodic harmonics; accompaniment requires an instrument tag and periodic or noise timbre. Relay tracks also specify participant 1–3. See the Creator guide for gain and envelope ranges. These are musical tones; lyrics remain in Conversation.'));
   collect=value=>{
    if(verseRows.length<1||verseRows.length>16)throw Error('A song needs 1–16 authored verses.');
    const result=verseRows.map(({verse,call,response,relay})=>{
     const entry={...verse,call:call.value};if(!entry.call.trim()||entry.call.length>240)throw Error('Every verse needs a lead line of 1–240 characters.');
     if(form.value==='call_response'){entry.response=response.value;delete entry.relay;if(!entry.response.trim()||entry.response.length>240)throw Error('Every call-and-response verse needs an answering line of 1–240 characters.');}
     else if(form.value==='relay'){entry.relay=relay.map(input=>input.value);while(entry.relay.at(-1)==='')entry.relay.pop();delete entry.response;if(entry.relay.length<1||entry.relay.length>3||entry.relay.some(line=>!line.trim()||line.length>240))throw Error('Every relay verse needs 1–3 consecutive successor lines of 1–240 characters each.');}
     else{delete entry.response;delete entry.relay;}return entry;
    });
    set(value,'tradition',tradition.value);set(value,'style',style.value);set(value,'form',form.value,'solo');value.verses=result;
    if(score.value.trim()){const parsed=JSON.parse(score.value);if(!object(parsed))throw Error('The score must be a JSON object.');value.score=parsed;}else delete value.score;
   };
  }
  function toggle(){fields.disabled=!enabled.checked;}enabled.onchange=toggle;toggle();
  section.append(el('p','Save this field stages the selected record only. Then Save draft, Validate and export the complete .expanse file. Unknown fields are preserved; complete records and metadata.singing remain editable in World files.'));
  const commit=button(section,'Save '+title.toLowerCase(),()=>{
   if(context.world!==ed.gameSlug||context.type!==ed.type||context.id!==String(ed.entryId)||context.version!==String(ed.selectionVersion||0)){setStatus('Selection changed. Reopen this singing field before saving it.','warn');return;}
   if(!enabled.checked){saveField(key,{});return;}
   try{const value=structuredClone(draft);collect(value);if(value.songs&&new Set(value.songs).size!==value.songs.length)throw Error('Choose each songbook only once.');saveField(key,value);}catch(error){setStatus('Cannot stage '+key+': '+error.message,'warn');}
  });commit.dataset.saveMusicField=key;return box;
 }
 function questChainField(key,val){
  const object=val&&typeof val==='object'&&!Array.isArray(val);
  if(val&&(!object||(val.version!==undefined&&val.version!==1)||(val.stages!==undefined&&(!Array.isArray(val.stages)||val.stages.some(id=>typeof id!=='string'))))){
   const raw=jsonField(key,val);raw.prepend(el('p','This chain needs advanced editing. Its original fields are preserved below. Supported chains use version 1, an ordered stages list, a final quest ID, a zero-based index and a destination room.'));return raw;
  }
  const draft=structuredClone(val||{}),context={world:ed.gameSlug,type:ed.type,id:String(ed.entryId),version:String(ed.selectionVersion||0)};
  // Keep the fieldset inside its field wrapper so Inspector search and pending
  // edit tracking continue to associate every control with quest_chain.
  const box=el('div'),section=el('fieldset');box.className='quest-chain-editor';section.style.minWidth='0';box.append(section);
  section.append(el('legend','Quest stages'));
  section.append(el('p','Give each destination its own quest. Use the same ordered stage IDs on every quest in the chain, and put the preceding stage in each later quest’s prerequisites.'));
  const enabled=el('input');enabled.type='checkbox';enabled.checked=Object.keys(draft).length>0;enabled.dataset.questChainField='enabled';
  const include=el('label',' Use a quest chain');include.prepend(enabled);section.append(include);
  const fields=el('fieldset');fields.style.minWidth='0';section.append(fields);
  function field(label,input,key){const row=el('label',label);row.style.display='block';row.style.margin='8px 0';input.style.display='block';input.style.width='100%';input.style.boxSizing='border-box';input.style.minWidth='0';input.dataset.questChainField=key;input.setAttribute('aria-label',label);row.append(input);fields.append(row);return input;}
  const chain=field('Final quest / chain ID',picker('quest',draft.id||context.id),'id');
  const stages=field('Stage quest IDs in travel order (one per line)',el('textarea'),'stages');stages.rows=5;stages.value=(draft.stages||[]).join('\n');
  const addChoice=field('Add an existing quest to the end',picker('quest',''),'add');
  const add=el('button','Append selected stage');add.type='button';add.className='ed-btn';fields.append(add);
  const place=el('p');place.dataset.questChainStatus='true';place.setAttribute('role','status');fields.append(place);
  const destination=field('This stage’s destination',picker('room',draft.destination),'destination');
  const source=field('Continuation book (optional)',picker('item',draft.source_item),'source_item');
  fields.append(el('small','Use the same destination in turn_in_room. A continuation book belongs at the preceding destination: make it anchored and readable, and include this quest in its knowledge.quests.'));
  const ordered=()=>stages.value.split(/\r?\n/).map(id=>id.trim()).filter(Boolean);
  function summary(){
   fields.disabled=!enabled.checked;
   const ids=ordered(),index=ids.indexOf(context.id);
   place.textContent=index<0?'Include the selected quest '+context.id+' in the stage list.':'This quest is stage '+(index+1)+' of '+ids.length+'. The stored index is '+index+'.';
  }
  stages.oninput=summary;
  add.onclick=()=>{
   const ids=ordered();if(!addChoice.value)return;
   if(ids.includes(addChoice.value)){setStatus('That quest is already in the stage list.','warn');return;}
   if(ids.length>=64){setStatus('A chain supports at most 64 stages.','warn');return;}
   stages.value=[...ids,addChoice.value].join('\n');stages.dispatchEvent(new Event('input',{bubbles:true}));
  };
  enabled.onchange=()=>{if(enabled.checked&&!ordered().length)stages.value=context.id;summary();};summary();
  const commit=el('button','Save quest chain');commit.type='button';commit.className='ed-btn';commit.dataset.saveQuestChain='true';
  commit.onclick=()=>{
   if(context.world!==ed.gameSlug||context.type!==ed.type||context.id!==String(ed.entryId)||context.version!==String(ed.selectionVersion||0)){setStatus('Selection changed. Reopen the quest chain before saving it.','warn');return;}
   if(!enabled.checked){saveField(key,{});return;}
   const ids=ordered(),index=ids.indexOf(context.id);
   if(ids.length<2||ids.length>64||new Set(ids).size!==ids.length||index<0){setStatus('Use 2–64 unique stage quest IDs and include the selected quest exactly once.','warn');return;}
   if(!chain.value||ids.at(-1)!==chain.value){setStatus('The final quest / chain ID must be the last quest in the ordered stage list.','warn');return;}
   if(!destination.value){setStatus('Choose this stage’s destination, then use the same room in turn_in_room.','warn');return;}
   const value={...draft,version:1,id:chain.value,stages:ids,index,destination:destination.value};
   if(source.value)value.source_item=source.value;else if(draft.source_item!=='')delete value.source_item;
   saveField(key,value);
  };
  section.append(el('p','For a split quest, set reward_gold and reward_xp on every stage to the original amount divided by the number of stages, rounded up; zero remains zero. Keep item rewards and other completion effects on the final stage.'));
  section.append(el('small','Save quest chain stages only this field. Create or update the other quest records and their prerequisites separately, then Save draft, Validate and export the complete .expanse file.'),commit);return box;
 }
 function interfaceTourField(key,val){
  if(val&&(typeof val!=='object'||Array.isArray(val)||(val.version&&val.version!==1)||(val.alternative_quest!==undefined&&typeof val.alternative_quest!=='string')||(Array.isArray(val.steps)&&val.steps.some(step=>!step||typeof step!=='object'||Array.isArray(step)))))return jsonField(key,val);
  const draft=structuredClone(val||{}),context={world:ed.gameSlug,type:ed.type,id:String(ed.entryId),version:String(ed.selectionVersion||0)};
  const targets={conversation:'Conversation',command:'Command input',actions:'Actions menu',quests:'Quests',map:'Terrain map',compass:'Quest compass',location:'Location and nearby people',books:'Bookshelves',inventory:'Inventory',status:'Character status',condition:'Condition',save:'Save',save_quit:'Save & quit',panels:'Panels and restoring windows',help:'Help'};
  const box=el('fieldset');box.className='interface-tour-editor';box.append(el('legend','Interface lesson'));
  box.append(el('p','Author up to 24 short steps that point to real controls. Next acknowledges a step; Show me reveals a control. A lesson never moves the character or activates Save. Newly accepted quests require the lesson before turn-in; already accepted or completed quests can replay it.'));
  const enabled=el('input');enabled.type='checkbox';enabled.checked=Array.isArray(draft.steps)&&draft.steps.length>0;
  const enabledLabel=el('label','Include an interface lesson ');enabledLabel.prepend(enabled);box.append(enabledLabel);
  const fields=el('fieldset');fields.className='interface-tour-fields';box.append(fields);
  const title=el('input');title.type='text';title.maxLength=120;title.value=draft.title||'';title.setAttribute('aria-label','Interface lesson title');
  const titleLabel=el('label','Lesson title');titleLabel.append(title);fields.append(titleLabel);
  const completion=el('textarea');completion.rows=3;completion.maxLength=1200;completion.value=draft.completion_text||'';completion.setAttribute('aria-label','Interface lesson completion guidance');
  const completionLabel=el('label','After the lesson — next quest guidance');completionLabel.append(completion);fields.append(completionLabel);
  fields.append(el('small','Leave completion guidance blank to use the quest description. The actual quest objectives and rewards remain separate.'));
  const alternative=picker('quest',draft.alternative_quest),alternativeLabel=el('label','Alternative starting quest (optional)');alternative.dataset.tourField='alternative_quest';alternative.setAttribute('aria-label','Alternative starting quest');alternativeLabel.append(alternative);fields.append(alternativeLabel);
  fields.append(el('small','Choose one ordinary quest that can replace this lesson quest. Its explicit XP, gold and item rewards must match exactly. Choosing it only accepts work; it never grants a reward. Effect, reputation and flag rewards are not supported for these pairs. Keep shared later quests separate; Validate checks the route and its references.'));
  const rows=el('div');rows.className='tour-editor-steps';fields.append(rows);
  let steps=Array.isArray(draft.steps)?draft.steps.map(step=>({...step})):[];
  const add=el('button','Add step');add.type='button';add.className='ed-btn';fields.append(add);
  function field(parent,label,key,value,tag='input'){
   const wrapper=el('label',label),input=el(tag);input.value=value||'';input.dataset.tourField=key;input.setAttribute('aria-label',label);
   if(tag==='textarea'){input.rows=4;input.maxLength=1200;}else{input.type='text';input.maxLength=key==='id'?64:120;}
   wrapper.append(input);parent.append(wrapper);return input;
  }
  function draw(){
   rows.replaceChildren();fields.disabled=!enabled.checked;add.disabled=steps.length>=24;
   steps.forEach((step,index)=>{
    const row=el('section');row.className='tour-editor-step';row.dataset.tourStep=String(index);row.append(el('h4','Step '+(index+1)));
    for(const [label,name,tag] of [['Stable step ID','id','input'],['Step title','title','input'],['Short explanation','text','textarea']]){const input=field(row,label,name,step[name],tag);input.oninput=()=>{step[name]=input.value;};}
    const targetLabel=el('label','Highlight control'),target=el('select');target.dataset.tourField='target';target.setAttribute('aria-label','Highlight control');
    for(const [id,label] of Object.entries(targets))target.append(new Option(label,id));
    if(step.target&&!Object.hasOwn(targets,step.target))target.append(new Option('Unknown: '+step.target,step.target));target.value=step.target||'conversation';step.target=target.value;target.onchange=()=>{step.target=target.value;};targetLabel.append(target);row.append(targetLabel);
    const controls=el('div');controls.className='tour-editor-buttons';
    for(const [label,delta] of [['Move up',-1],['Move down',1]]){const b=el('button',label);b.type='button';b.disabled=index+delta<0||index+delta>=steps.length;b.onclick=()=>{const other=index+delta;if(other<0||other>=steps.length)return;[steps[index],steps[other]]=[steps[other],steps[index]];draw();rows.children[other]?.querySelector('input')?.focus();};controls.append(b);}
    const remove=el('button','Remove step');remove.type='button';remove.onclick=()=>{steps.splice(index,1);draw();add.focus();};controls.append(remove);row.append(controls);rows.append(row);
   });
  }
  function appendStep(){if(steps.length>=24)return;let n=steps.length+1;while(steps.some(step=>step.id==='step_'+n))n++;steps.push({id:'step_'+n,target:'conversation',title:'',text:''});draw();rows.lastElementChild?.querySelector('input')?.focus();}
  add.onclick=appendStep;enabled.onchange=()=>{if(enabled.checked&&!steps.length)appendStep();else draw();};draw();
  const commit=el('button','Save interface lesson');commit.type='button';commit.className='ed-btn';commit.dataset.saveInterfaceTour='true';
  commit.onclick=()=>{
   if(context.world!==ed.gameSlug||context.type!==ed.type||context.id!==String(ed.entryId)||context.version!==String(ed.selectionVersion||0)){setStatus('Selection changed. Reopen the interface lesson before saving it.','warn');return;}
   if(!enabled.checked){saveField(key,{});return;}
   if(!title.value.trim()||title.value.trim().length>120||steps.length<1||steps.length>24){setStatus('Use a lesson title of 1–120 characters and 1–24 steps.','warn');return;}
   const ids=new Set();
   for(const [index,step] of steps.entries()){
    if(typeof step.id!=='string'||!/^[-_a-zA-Z0-9]{1,64}$/.test(step.id)||ids.has(step.id)){setStatus('Step '+(index+1)+' needs a unique ID using 1–64 letters, digits, underscores or hyphens.','warn');return;}ids.add(step.id);
    if(!Object.hasOwn(targets,step.target)||typeof step.title!=='string'||!step.title.trim()||step.title.trim().length>120||typeof step.text!=='string'||!step.text.trim()||step.text.trim().length>1200){setStatus('Step '+(index+1)+' needs a supported control, a short title (up to 120 characters), and text (up to 1200 characters).','warn');return;}
   }
   if(completion.value.trim().length>1200){setStatus('Completion guidance is limited to 1200 characters.','warn');return;}
   if(alternative.value===context.id){setStatus('Choose a different ordinary quest as the alternative.','warn');return;}
   const value={...draft,version:1,title:title.value.trim(),steps:steps.map(step=>({...step,title:step.title.trim(),text:step.text.trim()}))};
   if(completion.value.trim())value.completion_text=completion.value.trim();else delete value.completion_text;
   if(alternative.value)value.alternative_quest=alternative.value;else delete value.alternative_quest;
   saveField(key,value);
  };
  box.append(el('p','Save interface lesson stages only this field on the selected quest. Validate and export the complete world through the usual Creator workflow.'),commit);return box;
 }
 buildFieldWidget=function(key,kind,val,objId){
  if(key==='spellcasting'&&ed.type==='npc')return npcSpellcastingField(val);
  if((key==='presentation'&&ed.type==='ability')||(key==='summon_presentation'&&ed.type==='npc'))return presentationField(key,val);
  if((key==='singing'&&['race','npc'].includes(ed.type))||(['song','instrument'].includes(key)&&ed.type==='item'))return singingField(key,val);
  if(key==='quest_chain'&&ed.type==='quest')return questChainField(key,val);
  if(key==='quest_split_migration'&&ed.type==='quest'){
   const box=el('div'),details=el('details');details.append(el('summary','Original quest preserved for existing saves'));
   details.append(el('p','Keep this record on the final quest when converting a published quest. Its original snapshot preserves progress and rewards for characters who already accepted or completed the older quest. Editing or removing that snapshot can change how their saves are interpreted.'));
   details.append(el('p','An unsplit quest uses an empty object. A migration record has version 1, a revision, and original containing the complete quest before it was split. Preserve any resolved_reward_xp, resolved_reward_gold and additional metadata already present.'));
   details.append(jsonField(key,val));box.append(details);return box;
  }
  if(key==='interface_tour'&&ed.type==='quest')return interfaceTourField(key,val);
  if(key==='combat_level'&&ed.type==='npc'){const box=el('div'),n=el('input');n.type='number';n.min=1;n.max=100;n.step=1;n.value=val??1;n.onchange=()=>{if(n.checkValidity())saveField(key,Number(n.value));else n.reportValidity();};box.append(n,el('small',' Authored base threat level for loot tiers. Earned levels above 1 are added; this field does not change combat statistics.'));return box;}
  if(key==='loot_table'&&ed.type==='npc'){const box=jsonField(key,val);box.prepend(el('p','Optional combat loot. Empty {} preserves fixed drops. Use version: 1 and nonoverlapping tiers with min_level/max_level (1–100), chance (0–1), gold {min,max}, and items [{item,weight,min,max}]. A successful chance gives that money and one weighted item stack together. Optional bonus [{item,chance,min,max}] rolls independently; rare bonuses never fill a failed common roll. Quantities are positive integers. Validate checks references and ranges. Players, owned companions and zoo exhibits receive no supplemental bundle.'));return box;}
  if(key==='escort'&&ed.type==='quest'){
   const box=el('fieldset');box.append(el('legend','Travel together'));
   const mode=el('select');for(const [v,label] of [['','No escort'],['follow','Follow a guide'],['lead','Lead a companion']])mode.add(new Option(label,v));
   mode.value=val?.mode||'';const npc=picker('npc',val?.npc),dest=picker('room',val?.destination);
   for(const [text,input] of [['Objective',mode],['Companion',npc],['Destination',dest]]){const label=el('label',text+' ');label.append(input);box.append(label);}
   const commit=el('button','Save escort');commit.type='button';commit.onclick=()=>saveField(key,mode.value?{mode:mode.value,npc:npc.value,destination:dest.value}:{});box.append(commit);return box;
  }
  if(key==='waterway'&&ed.type==='room'){
   const box=el('fieldset');box.append(el('legend','Waterway'));
   const type=el('select'),name=el('input'),outlet=el('input'),flow=el('select');
   for(const kind of ['','dry','stream','tributary','river','lake','ocean','canal','wetland'])type.add(new Option(kind||'Automatic',kind));
   for(const d of ['','still','north','east','south','west'])flow.add(new Option(d||'Use the local drainage',d));
   type.value=val?.kind||'';name.value=val?.name||'';outlet.value=val?.outlet||'';flow.value=val?.flow||'';
   for(const [caption,field] of [['Kind',type],['Waterway name',name],['Flows into',outlet],['Direction',flow]]){
    const label=el('label',caption+' ');label.append(field);box.append(label);
   }
   const commit=el('button','Save waterway');commit.type='button';commit.onclick=()=>{
    const row={...val,kind:type.value,name:name.value.trim(),outlet:outlet.value.trim(),flow:flow.value};
    saveField(key,type.value?row:{});
   };box.append(commit);return box;
  }
  if(key==='route_surface'&&ed.type==='room'){
   const box=el('div'),surface=el('select'),axis=el('select');surface.setAttribute('aria-label','Route tile surface');axis.setAttribute('aria-label','Route surface orientation');
   for(const [v,n] of [['','No route surface'],['road','Maintained road'],['trail','Trodden trail']])surface.append(new Option(n,v));
   for(const [v,n] of [['east_west','East–west'],['north_south','North–south'],['crossroads','Crossroads']])axis.append(new Option(n,v));
   surface.value=val?.kind||'';axis.value=val?.axis||'east_west';axis.disabled=!surface.value;
   const save=()=>{axis.disabled=!surface.value;saveField(key,surface.value?{kind:surface.value,axis:axis.value}:{});};surface.onchange=axis.onchange=save;
   box.append(surface,axis,el('small',' Tile artwork only. Add or edit actual exits separately; this never creates a route.'));return box;
  }
  if(key==='ability_rules')return abilityRulesField(val);
  if(['life_stages','population_health','population_profile'].includes(key))return jsonField(key,val);
  if(['gift_preferences','companion_care','relationship_quest'].includes(key)){
   const box=el('div'),data=structuredClone(val||{});
   const itemFields=['wanted_items','disliked_items','treat_items','toy_items'];
   const emotionKeys=['happy','excited','in_love','amusement','sleepy','serious','irritated','angry','insulted','insulting'];
   const save=()=>saveField(key,data);
   if(key==='gift_preferences'){
    const details=el('details'),summary=el('summary','Speech bubbles');details.append(summary,el('small','One to three words per emotion. Leave blank for the usual phrase.'));
    for(const emotion of emotionKeys){
     const label=el('label',emotion.replaceAll('_',' ')+' '),input=el('input');
     input.value=data.speech_lines?.[emotion]||'';input.maxLength=30;label.style.display='block';
     input.onchange=()=>{const text=input.value.trim();if(text&&text.split(/\s+/).length>3){setStatus('Use up to three words.','warn');return;}data.speech_lines??={};if(text)data.speech_lines[emotion]=text;else delete data.speech_lines[emotion];save();};
     label.append(input);details.append(label);
    }
    box.append(details);
    const everyday=el('details');everyday.append(el('summary','Everyday conversation'));
    for(const [key,label] of Object.entries({hurt:'Injured',danger:'In danger',temper:'Frustrated',rest:'Tired',home:'At home',work:'At work',family:'With family',hunger:'Hungry',paid:'Paid today'})){
     const field=el('label',label+' '),input=el('input');input.value=data.everyday_lines?.[key]||'';input.maxLength=30;
     field.style.display='block';field.append(input);everyday.append(field);
     input.onchange=()=>{const words=input.value.trim();if(words&&words.split(/\s+/).length>3){setStatus('Use up to three words.','warn');return;}
      data.everyday_lines??={};if(words)data.everyday_lines[key]=words;else delete data.everyday_lines[key];save();};
    }
    box.append(everyday);
   }
   for(const [field,value] of Object.entries(data)){
    if(field==='speech_lines'||field==='everyday_lines')continue;
    const row=el('div');row.append(el('strong',field.replaceAll('_',' ')+' '));box.append(row);
    if(itemFields.includes(field)||field==='emotions'){
     const draw=()=>{row.replaceChildren(el('strong',field.replaceAll('_',' ')+' '));data[field].forEach((id,i)=>{const select=itemFields.includes(field)?picker('item',id):el('select');if(field==='emotions'){for(const v of emotionKeys)select.append(new Option(v,v));select.value=id;}select.onchange=()=>{data[field][i]=select.value;save();};const remove=el('button','Remove');remove.type='button';remove.onclick=()=>{data[field].splice(i,1);save();draw();};row.append(select,remove);});const add=el('button','Add');add.type='button';add.onclick=()=>{data[field].push(field==='emotions'?'happy':(ed.entriesCache.item||[])[0]?.id||'');save();draw();};row.append(add);};draw();
    }else if(field==='goals'){
     for(const emotion of [...emotionKeys,'gift_wanted']){const input=el('input');input.type='number';input.min=0;input.step=1;input.value=value[emotion]||0;input.title=emotion;input.style.width='65px';input.onchange=()=>{if(!input.checkValidity())return;const n=Number(input.value);if(n)data.goals[emotion]=n;else delete data.goals[emotion];save();};row.append(el('span',emotion+' '),input);}
    }else{const input=el('input');input.type=typeof value==='boolean'?'checkbox':typeof value==='number'?'number':'text';if(input.type==='checkbox')input.checked=value;else input.value=Array.isArray(value)?value.join(', '):value;if(input.type==='number'){input.step=1;input.min=field.includes('trust')?-100:1;}input.onchange=()=>{if(!input.checkValidity())return;data[field]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):Array.isArray(value)?input.value.split(',').map(x=>x.trim()).filter(Boolean):input.value;save();};row.append(input);}
   }return box;
  }
  if(['social_profile','coupling_rules','laws','traffic','climate','name_pool'].includes(key)){
   const box=el('div'),data=structuredClone(val||{});
   if(key==='social_profile'){
    data.business_meeting_days ??= 3;
    data.business_partner_limit ??= 1;
    data.age_in_world ??= true;data.elder_lifespan_years ??= 25;data.grown_family_percent ??= 50;
    box.append(el('small','Residents age on the world clock. Elder lifespan sets the years beyond elder age. Zero disables natural death. Grown family percent sets the chance a newborn seeks a family as an adult.'));
    box.append(el('small','Automatic business partnerships require meetings on distinct working days. The partner limit counts active partners. Set it to zero to disable automatic partnerships.'));
   }
   box.append(el('small',key==='social_profile'?'Romance requires adult sentient participants. Animals breed only within their species and season.':'These rules apply to both participants. Player acceptance is always required.'));
   for(const [field,value] of Object.entries(data)){
    const row=el('label');row.style.cssText='display:block;margin:6px 0';row.append(el('span',field.replaceAll('_',' ')+' '));
    const input=el('input');input.type=typeof value==='boolean'?'checkbox':typeof value==='number'?'number':'text';
    if(input.type==='checkbox')input.checked=value;else input.value=Array.isArray(value)?value.join(', '):value;
    if(input.type==='number'){if(!['born_minute','age_epoch_minute'].includes(field))input.min=field==='latitude'?-90:field==='elevation_m'?-1000:field==='business_meeting_days'?1:0;input.step=field==='latitude'?.1:['accident_chance','traffic_reduction'].includes(field)?.01:['age_years','age_epoch_years'].includes(field)?'any':1;if(field==='latitude')input.max=90;if(['accident_chance','traffic_reduction'].includes(field))input.max=1;}
    input.onchange=()=>{if(!input.checkValidity()){setStatus('Invalid '+field.replaceAll('_',' ')+': '+input.validationMessage,'warn');input.reportValidity();return;}data[field]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):Array.isArray(value)?input.value.split(',').map(v=>v.trim()).filter(Boolean):input.value;saveField(key,data);};
    if(Array.isArray(value))input.title='Comma-separated values';row.append(input);box.append(row);
   }return box;
  }
  if(key==='category'&&ed.type==='species'){const select=el('select');for(const category of ['bird','fish','mammal','insect','plant','arachnid','crustacean','reptile','mollusk'])select.append(new Option(category,category));if(val&&!Array.from(select.options).some(o=>o.value===val))select.append(new Option(val+' (unsupported authored value)',val));select.value=val;select.onchange=()=>saveField(key,select.value);return select;}
  if(key==='profession'){const s=el('select');for(const v of ['','producer','guard','teacher','merchant','citizen'])s.append(new Option(v||'Unassigned',v));s.value=val||'';s.onchange=()=>saveField(key,s.value);return s;}
  if(singles[key])return renderIdPicker(key,val,singles[key]);
  if(choices[key]){const s=el('select');for(const v of choices[key])s.append(new Option(v,v));s.value=val||choices[key][0];s.onchange=()=>saveField(key,s.value);return s;}
  if(typeof val==='boolean'){const c=el('input');c.type='checkbox';c.checked=val;c.onchange=()=>saveField(key,c.checked);return c;}
  if(refs[key]){
   const box=el('div'),values=[...(val||[])];
   const draw=()=>{box.replaceChildren();values.forEach((id,i)=>{const row=el('div'),p=picker(refs[key],id),b=el('button','Remove');p.onchange=()=>{values[i]=p.value;saveField(key,values.filter(Boolean));};b.type='button';b.onclick=()=>{values.splice(i,1);saveField(key,values);draw();};row.append(p,b);box.append(row);});const add=el('button','Add selection');add.type='button';add.onclick=()=>{values.push('');draw();};box.append(add);};draw();return box;
  }
  if(key==='diplomacy'){
   const box=el('div'),rows=structuredClone(val||{});
   for(const group of ed.entriesCache.group||[]){const row=el('div');row.append(el('span',group.name+' '));const rule=rows[group.id]||{minimum:0,base:50,maximum:100};for(const field of ['minimum','base','maximum']){const input=el('input');input.type='number';input.min=0;input.max=100;input.value=rule[field];input.title=field;input.style.width='70px';input.onchange=()=>{rule[field]=Number(input.value);rows[group.id]=rule;saveField(key,rows);};row.append(el('small',field+' '),input);}box.append(row);}return box;
  }
  if(key==='workshop'){
   const box=el('div');box.append(el('small','Production: recipe IDs, finite stock, treasury, shift interval, repair availability. All references are validated on Save / Apply.'));
   const enabled=el('input');enabled.type='checkbox';enabled.checked=!!val?.recipes;enabled.onchange=()=>saveField(key,enabled.checked?{name:'Workshop',recipes:[],initial_stock:{},capital:500,interval:30,repair:true,stock_limit:40}:{});box.append(el('span','Enable workshop '),enabled);
   if(val?.recipes){const recs=el('div');for(const recipe of ed.entriesCache.recipe||[]){const label=el('label'),c=el('input');c.type='checkbox';c.checked=val.recipes.includes(recipe.id);c.onchange=()=>{val.recipes=c.checked?[...val.recipes,recipe.id]:val.recipes.filter(x=>x!==recipe.id);saveField(key,val);};label.append(c,el('span',recipe.name));recs.append(label,el('br'));}recs.style.cssText='max-height:180px;overflow:auto';box.append(recs);for(const field of ['capital','interval','stock_limit']){const input=el('input');input.type='number';input.min=field==='capital'?0:1;input.value=val[field]??30;input.onchange=()=>{val[field]=Number(input.value);saveField(key,val);};box.append(el('small',field),input);}box.append(jsonField(key,val));}return box;
  }
  if(key==='relations'){
   const rows=Object.entries(val||{}),box=el('div');
   const save=()=>saveField(key,Object.fromEntries(rows.filter(r=>r[0])));
   const draw=()=>{box.replaceChildren();rows.forEach((r,i)=>{const row=el('div'),group=picker('group',r[0]),relation=el('select'),remove=el('button','Remove');for(const v of ['allied','tolerated','neutral','hostile'])relation.append(new Option(v,v));relation.value=r[1];group.onchange=()=>{r[0]=group.value;save();};relation.onchange=()=>{r[1]=relation.value;save();};remove.type='button';remove.onclick=()=>{rows.splice(i,1);save();draw();};row.append(group,relation,remove);box.append(row);});const add=el('button','Add relationship');add.type='button';add.onclick=()=>{rows.push(['','neutral']);draw();};box.append(add);};draw();return box;
  }
  if(counts[key]){
   const box=el('div'),rows=Object.entries(val||{});
   const save=()=>{const result={};for(const [id,n] of rows){if(!id)continue;if(id in result){setStatus('Choose each entry only once.','warn');return;}result[id]=n;}saveField(key,result);};
   const draw=()=>{box.replaceChildren();rows.forEach((pair,i)=>{const row=el('div'),p=picker(counts[key],pair[0]),n=el('input'),b=el('button','Remove');n.type='number';n.step='1';n.value=pair[1];if(key!=='reputation')n.min='1';p.onchange=()=>{pair[0]=p.value;save();};n.onchange=()=>{if(n.checkValidity()){pair[1]=Number(n.value);save();}};b.type='button';b.onclick=()=>{rows.splice(i,1);save();draw();};row.append(p,n,b);box.append(row);});const add=el('button','Add quantity');add.type='button';add.onclick=()=>{rows.push(['',1]);draw();};box.append(add);};draw();return box;
  }
  if(key==='schedule'){
   const rows=structuredClone(val||[]),box=el('div');
   const save=()=>saveField(key,rows.filter(r=>r.room));
   const draw=()=>{box.replaceChildren();rows.forEach((r,i)=>{const row=el('div'),hour=el('input'),minute=el('input'),days=el('input'),room=picker('room',r.room),activity=el('input'),b=el('button','Remove');hour.type='number';hour.min=0;hour.max=24;hour.step=1;hour.value=r.hour;hour.title='Hour (0–24)';minute.type='number';minute.min=0;minute.max=59;minute.value=r.minute||0;minute.title='Minute (0–59)';minute.onchange=()=>{if(minute.checkValidity()){r.minute=Number(minute.value);save();}};days.value=(r.weekdays||[]).join(',');days.placeholder='Days 1–9 (blank: daily)';days.onchange=()=>{const values=days.value.split(',').map(x=>x.trim()).filter(Boolean).map(Number);if(values.some(v=>!Number.isInteger(v)||v<1||v>9)){setStatus('Weekdays must be 1–9.','warn');return;}r.weekdays=values;save();};activity.value=r.activity||'';activity.placeholder='Activity';hour.onchange=()=>{if(hour.checkValidity()){r.hour=Number(hour.value);save();}};room.onchange=()=>{r.room=room.value;save();};activity.onchange=()=>{r.activity=activity.value;save();};b.type='button';b.onclick=()=>{rows.splice(i,1);save();draw();};row.append(hour,minute,days,room,activity,b);box.append(row);});const add=el('button','Add daily activity');add.type='button';add.onclick=()=>{rows.push({hour:8,room:'',activity:'working'});draw();};box.append(add);};draw();return box;
  }
  // Old widgets remain in charge of stock, exits, spawners and descriptions.
  const legacy=['spawners','exits','variants','greetings','stock','items_room','rooms','hostile_to','roster'];
  if(val&&typeof val==='object'&&!legacy.includes(kind)&&!legacy.includes(key)){
    if(!Array.isArray(val)||val.some(x=>x&&typeof x==='object'))return jsonField(key,val);
  }
  if(['chance','raw_risk','disease_chance','aggression_chance'].includes(key)){const n=el('input');n.type='number';n.min=0;n.max=1;n.step='.05';n.value=val||0;n.onchange=()=>{if(n.checkValidity())saveField(key,Number(n.value));};return n;}
  return originalWidget(key,kind,val,objId);
 };
})();
