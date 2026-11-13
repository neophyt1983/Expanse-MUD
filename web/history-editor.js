/* Creator-only fresh-world history tools. No automatic source/live-world writes. */
(()=>{
'use strict';
const toolbar=document.getElementById('ed-save')?.parentElement;if(!toolbar)return;
const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
const button=text=>{const b=node('button',text);b.type='button';b.className='ed-btn';return b;};
const open=button('World history');open.id='ed-history';toolbar.append(open);
let dialog=null,busy=false;
const previous=updateToolbar;
function permission(){open.hidden=!config.editor_enabled;open.disabled=busy||!!dialog||!ed.gameSlug;if(dialog&&(!config.editor_enabled||dialog.dataset.world!==ed.gameSlug))dialog.close();}
updateToolbar=function(){previous();permission();};permission();
open.onclick=async()=>{
 if(busy||dialog||!config.editor_enabled||!ed.gameSlug)return;
 const slug=ed.gameSlug,path='games/'+encodeURIComponent(slug)+'/history';busy=true;permission();
 try{
  const current=await apiGet(path);if(current.error)throw Error(current.error);
  if(slug!==ed.gameSlug||!config.editor_enabled)return;
  const d=node('dialog');dialog=d;d.dataset.world=slug;d.id='history-dialog';d.setAttribute('aria-label','New world history');
  d.style.cssText='width:min(900px,94vw);max-height:90vh;overflow:auto;background:#161c24;color:#e2e8ed;padding:22px;border:1px solid #607c72';
  d.append(node('h2','World history · '+slug),node('p','Generate into a separate NEW world. The source and current game are never rewritten. Supported population/shortcut manifests and image/Pixel Studio assets are preserved; unsupported template entries stop generation instead of being omitted. This prototype models bounded annual development and faction history, not full ancestry or geological simulation.'));
  const target=node('input');target.id='history-target';target.value=(slug.toLowerCase().replace(/[^a-z0-9_]/g,'_').replace(/^[^a-z]+/,'world_').slice(0,24)||'world')+'_history';target.maxLength=32;
  const label=node('label','New world name ');label.append(target);d.append(label);
  const input=node('textarea');input.id='history-config';input.rows=16;input.spellcheck=false;input.value=JSON.stringify(current.config,null,2);input.style.cssText='display:block;width:100%;box-sizing:border-box;background:#0d1218;color:#def1e9;font:13px monospace;margin-top:12px';
  d.append(node('p','Editable components: history_plan (seed, dated geology/civil events); selection (NPC IDs and available learning/work); faction_pairs (bounds, locks and optional war); rules (individual numerical settings). Begin with explicit IDs from the reference list below.'),input);
  const rules=node('details');rules.append(node('summary','Rule settings and ranges'),node('pre',JSON.stringify(current.rules,null,2)));d.append(rules);
  const refs=node('details');refs.append(node('summary','Available NPC, faction and room IDs'),node('pre',JSON.stringify(current.references,null,2)));d.append(refs);
  const help=node('details');help.append(node('summary','Configuration examples and limits'),node('pre',JSON.stringify({selection:[{source_id:'your_npc',work_available:true,education_available:true,annual_income:20,annual_expenses:10,accident_probability:0,generated_fields:[]}],faction_pairs:[{a:'faction_a',b:'faction_b',initial_score:50,minimum:0,maximum:100,locked:false,allow_war:false,generated_relation:false}],rules:{skill_gain_per_work_year:2},live_diplomacy:{enabled:false,seed:17,interval_minutes:312000,pairs:[{a:'faction_a',b:'faction_b',initial_score:50,minimum:25,maximum:100,change:3,locked:false}]}},null,2)),node('p','Selection must reference sentient NPCs with explicit ages. generated_fields explicitly permits replacing authored gold, health, life_profile or birth_epoch; otherwise existing choices win. generated_relation permits replacing an authored faction relationship, still within its limits. live_diplomacy is off by default. When enabled in the new world it evolves goodwill through cooperation and disputes, respects locks/bounds, and persists across saves. It does not run wars, armies or conquest. No setting generates troops, reproduction or new terrain.'));
  d.append(help);
  if(current.chronicles){
   const archive=current.chronicles,part=node('select'),find=node('input'),list=node('ol'),group=node('details'),more=node('button','More entries');
   group.append(node('summary','Read world chronicles'));part.setAttribute('aria-label','History to read');
   for(const [id,label] of [['geology','Geology · Deep time'],['civilization','Civilization · Medium time'],['individual','Individuals · Recent time'],...Object.keys(archive.volumes||{}).map(k=>[k,({natural:'Natural history and peoples',monstorium:'Monstorium',knowledge:'Frontiers of knowledge',sources:'Research bibliography'})[k]||k])])part.add(new Option(label,id));
   find.type='search';find.placeholder='Filter entries';find.setAttribute('aria-label','Filter history');
   const names=new Map(current.references.npc.map(n=>[n.id,n.name]));let limit=20;
   function draw(){list.replaceChildren();
    const rows=part.value==='individual'?Object.entries(archive.people).flatMap(([id,es])=>es.map(e=>({...e,person:names.get(id)||'Resident'}))):(archive.volumes?.[part.value]||archive.events.filter(e=>e.domain===part.value));
    const filtered=rows.filter(e=>[e.person,e.heading,e.name,e.text].join(' ').toLowerCase().includes(find.value.toLowerCase()));
    for(const e of filtered.slice(0,limit)){const years=Math.floor((archive.present-e.at)/312000);list.append(node('li',[e.date||(years>0?years.toLocaleString()+' world years before the start':'At the start'),e.name||e.heading||e.person,e.text].filter(Boolean).join(' · ')));}
    if(!filtered.length)list.append(node('li','No matching records.'));more.hidden=filtered.length<=limit;
   }
   part.onchange=find.oninput=()=>{limit=20;draw();};more.type='button';more.onclick=()=>{limit+=20;draw();};group.ontoggle=()=>{if(group.open)draw();};
   group.append(part,find,list,more);d.append(group);
  }
  const output=node('pre');output.id='history-output';output.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto';
  const inspect=node('select');inspect.id='history-inspect';inspect.setAttribute('aria-label','Inspect historical component');
  let artifact=current.history,token=null,working=false;
  function showHistory(){inspect.replaceChildren();for(const [value,text] of [['overview','Summary and limits'],['events','Timeline'],['factions','Faction state'],['template','Preserved template files (SHA256)'],...Object.keys(artifact?.actors||{}).map(id=>['actor:'+id,id])]){const o=node('option',text);o.value=value;inspect.append(o);}render();}
  function render(){if(!artifact){output.textContent='No saved generated history in this world.';return;}const key=inspect.value;output.textContent=JSON.stringify(key==='overview'?{status:artifact.status,steps:artifact.steps,limitations:artifact.limitations}:key.startsWith('actor:')?artifact.actors[key.slice(6)]:artifact[key],null,2);}
  inspect.onchange=render;showHistory();
  const status=node('p','Preview is read-only. Publish becomes available after a successful preview.');status.id='history-status';status.style.whiteSpace='pre-line';status.setAttribute('role','status');
  const preview=button('Preview'),publish=button('Create new world'),close=button('Close');preview.id='history-preview';publish.id='history-publish';close.id='history-close';publish.disabled=true;
  const invalidate=()=>{token=null;publish.disabled=true;status.textContent='Settings changed. Preview again.';};input.oninput=invalidate;target.oninput=invalidate;
  async function run(action){if(working)return;working=true;preview.disabled=publish.disabled=true;
   try{const result=await apiPost(path,{action,config:JSON.parse(input.value),target:target.value,preview_token:token});if(result.error)throw Error(result.error);status.textContent=result.text+(result.warnings?.length?'\n'+result.warnings.join('\n'):'');if(action==='preview'){token=result.preview_token;artifact=result.history;showHistory();}else{token=null;setStatus(result.text);}}
   catch(e){token=null;status.textContent=e.message;}finally{working=false;preview.disabled=false;publish.disabled=!token;}
  }
  preview.onclick=()=>run('preview');publish.onclick=()=>run('publish');close.onclick=()=>d.close();
  d.append(status,preview,publish,close,node('h3','Inspect history'),inspect,output);d.onclose=()=>{d.remove();dialog=null;permission();};document.body.append(d);d.showModal();
 }catch(e){setStatus(e.message,'warn');}finally{busy=false;permission();}
};
})();
