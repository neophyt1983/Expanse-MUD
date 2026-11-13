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
  const advancement=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='Experience and leveling';advancement.append(legend);const advancementInputs={};
  const defaults={enabled:true,level_cap:20,threshold_step:100,discovery_xp:2,quest_xp:50,social_xp:20,craft_xp:12,gather_xp:8,combat_xp:20,social_partners:5,repeat_percent:50,repeat_floor_percent:25,repeat_cooldown_minutes:5,repeat_daily_xp:200};
  for(const [key,value] of Object.entries({...defaults,...current.progression})){const label=document.createElement('label'),input=document.createElement('input');label.style.display='block';label.textContent=key.replaceAll('_',' ')+' ';input.type=key==='enabled'?'checkbox':'number';if(key==='enabled')input.checked=value;else{input.value=value;input.min=['level_cap','threshold_step'].includes(key)?1:0;input.max=key==='level_cap'?100:key==='social_partners'?20:['repeat_percent','repeat_floor_percent'].includes(key)?100:10000;input.step=1;}label.append(input);advancement.append(label);advancementInputs[key]=input;}
  const explanation=document.createElement('p');explanation.textContent='First accomplishments give full XP. Repeat successful crafting, gathering, hostile combat and repeatable quests earn diminishing practice XP, with a per-activity cooldown and a daily budget. Waiting alone gives no XP. Discoveries remain once-only; social lessons count a limited number of partners. Existing growth stays earned. Threshold step × current level is the XP needed for the next level.';advancement.append(explanation);
  save.onclick=async()=>{const r=await apiPost(gpath('world-rules'),{start_minute:startAtDawn.checked?null:Number(startHour.value)*60+Number(startMinute.value),progression:Object.fromEntries(Object.entries(advancementInputs).map(([key,input])=>[key,key==='enabled'?input.checked:Number(input.value)])),player_death:mode.value,max_players:Number(cap.value),pvp:pvp.checked,sunrise_minute:Number(dawnHour.value)*60+Number(dawnMinute.value)});setStatus(r.error||r.text,r.error?'warn':'');if(!r.error)dialog.remove();};close.onclick=()=>dialog.remove();dialog.append(document.createTextNode('Choose player mortality and maximum player count. Existing permanent deaths stay recorded. Apply after saving. '),mode,cap,document.createTextNode(' Allow player combat '),pvp,document.createTextNode(' Calendar: 25 hours/day, 9 days/week, 26 days/month, 8 months/year. Dawn: '),dawnHour,dawnMinute,startLabel,startHour,startMinute,startNote,advancement,save,close);document.body.append(dialog);dialog.showModal();
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
 const choices={progress_scope:['lifetime','accepted'],consumption:['producer','herbivore','omnivore','carnivore'],food_origin:['','plant','animal'],name_mode:['manual','faction'],interaction_effect:['create','damage','heal','repair'],target_kind:['item','npc','self'],scope:['character','world'],station:['hand','forge','kitchen','enchanting','loom','workbench','alchemy','scriptorium','husbandry','construction','shipyard'],kind:['crafting','cooking'],effect:['damage','heal','group_heal','ward','tame','escape','enchant','disenchant'],disposition:['friendly','neutral','hostile'],companion_kind:['pet','familiar']};
 function el(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
 function picker(type,val){const s=el('select');s.append(new Option('Choose…',''));for(const o of ed.entriesCache[type]||[])s.append(new Option(o.name||o.id,o.id));if(val&&!Array.from(s.options).some(o=>o.value===val))s.append(new Option(val,val));s.value=val||'';return s;}
 function jsonField(key,val){const box=el('div'),hint=el('small','Advanced structured field: valid JSON is required. Changes apply only after Save field.'),ta=el('textarea');ta.dataset.creatorJson=key;ta.dataset.creatorType=ed.type;ta.dataset.creatorWorld=ed.gameSlug;ta.dataset.creatorEntry=String(ed.entryId);ta.dataset.creatorVersion=String(ed.selectionVersion||0);ta.rows=6;ta.value=JSON.stringify(val??{},null,2);const b=el('button','Save field');b.type='button';b.className='ed-btn';b.onclick=()=>{if(ta.dataset.creatorWorld!==ed.gameSlug||ta.dataset.creatorType!==ed.type||ta.dataset.creatorEntry!==String(ed.entryId)||ta.dataset.creatorVersion!==String(ed.selectionVersion||0)){setStatus('Selection changed. Reopen this JSON field before staging it.','warn');return;}try{const v=JSON.parse(ta.value);saveField(key,v);}catch(e){setStatus('Invalid JSON: '+e.message,'warn');}};box.append(hint,ta,b);return box;}
 buildFieldWidget=function(key,kind,val,objId){
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
  if(key==='ability_rules'){const box=jsonField(key,val);box.prepend(el('p','Optional ability family rules. Empty {} preserves legacy behavior. family: mage, class, or race; classes/races: eligible IDs; minimum_level: 1–100; cooldown_minutes: 0–15000; weapon_required: true/false; ward_hits: 1–20; ignore_defense: true/false; components: item ID → quantity. Non-mage abilities must have cost_mp 0. See ABILITY-FRAMEWORK.txt for examples.'));return box;}
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
