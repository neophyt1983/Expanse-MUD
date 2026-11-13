/* Offline, opt-in JSON field assistance. Never sends a request or saves a draft.
   Keys: shipped LIVING_DEFAULTS; life stages: engine/life_stages.DEFAULT_PROFILE.
   Terrain enum: engine/climate.TERRAINS. References: explicit field contracts only. */
(()=>{'use strict';
const life={fictional:true,infancy_end_years:3,school_start_years:6,adolescence_start_years:13,adulthood_years:18,work_start_years:18,elder_years:65};
const terrain=['plains','forest','rainforest','desert','mountain','valley','wetland','coast','ocean','settlement','cave'];
const refs={'npc.social_profile.species':'species','room.laws.authority':'group','room.laws.arrest_room':'room','room.workshop.recipes.0':'recipe'};
const own=(o,k)=>o!=null&&Object.prototype.hasOwnProperty.call(o,k);
function schema(type,field){return type==='species'&&field==='life_stages'?life:window.LIVING_DEFAULTS?.[type]?.[field];}
// A bounded prefix parser tracks JSON position, not a regexp over ordinary prose.
function context(text,pos){if(text.length>100000||pos<0||pos>text.length)return null;let i=0,stack=[],root='value';
 const frame=()=>stack[stack.length-1],state=()=>frame()?.state||root;
 const path=()=>{const f=frame();return !f?[]:f.kind==='array'?[...f.path,0]:[...f.path,f.key];};
 const complete=()=>{if(frame())frame().state='after';else root='after';};
 while(i<pos){if(/\s/.test(text[i])){i++;continue;}const c=text[i],s=state(),f=frame();
  if(c==='"') {if(!['key','value','first'].includes(s))return null;const start=i++;let escaped=false,closed=false;
   while(i<pos){const x=text[i++];if(escaped){escaped=false;continue;}if(x==='\\'){escaped=true;continue;}if(x==='"'){closed=true;break;}}
   if(!closed){let prefix;try{prefix=JSON.parse(text.slice(start,pos)+'"');}catch{return null;}let end=pos,escape=false;while(end<text.length){const x=text[end++];if(escape){escape=false;continue;}if(x==='\\'){escape=true;continue;}if(x==='"')break;if(x==='\n'||x==='\r'){end=pos;break;}}if(end===text.length&&text[end-1]!=='"')end=pos;return {key:s==='key'||s==='first'&&f?.kind==='object',path:f?.path||[],valuePath:path(),prefix,start,end};}
   let v;try{v=JSON.parse(text.slice(start,i));}catch{return null;}if(s==='key'||s==='first'&&f?.kind==='object'){f.key=v;f.state='colon';}else complete();continue;
  }
  if(c===':'&&s==='colon'){f.state='value';i++;continue;}
  if(c===','&&s==='after'&&f){f.state=f.kind==='object'?'key':'value';i++;continue;}
  if((c==='}'||c===']')&&f&&((c==='}'&&f.kind==='object')||(c===']'&&f.kind==='array'))&&['after','first'].includes(s)){stack.pop();complete();i++;continue;}
  if((c==='{'||c==='[')&&['value','first'].includes(s)&&!(s==='first'&&f?.kind==='object')){if(stack.length>=64)return null;const p=path();stack.push({kind:c==='{'?'object':'array',state:'first',path:p});i++;continue;}
  if(['value','first'].includes(s)&&!(s==='first'&&f?.kind==='object')){const m=text.slice(i,pos).match(/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)(?=\s|[,}\]]|$)/);if(m){i+=m[0].length;complete();continue;}const prefix=text.slice(i,pos);if(/^(?:t|tr|tru|f|fa|fal|fals|n|nu|nul)$/.test(prefix))return {key:false,path:f?.path||[],valuePath:path(),prefix,start:i,end:pos};}
  return null;
 }
 const s=state(),f=frame();if(!['key','value','first'].includes(s))return null;return {key:s==='key'||s==='first'&&f?.kind==='object',path:f?.path||[],valuePath:path(),prefix:'',start:pos,end:pos};
}
function suggestions(text,pos,type,field,cache={}){const c=context(text,pos);if(!c)return [];let model=schema(type,field),values=[];
 const descend=p=>{let x=model;for(const key of p){if(Array.isArray(x))x=x[0];else if(own(x,key))x=x[key];else return undefined;}return x;};
 if(c.key){const object=descend(c.path);if(object&&typeof object==='object'&&!Array.isArray(object))values=Object.keys(object).map(v=>({value:v,label:v}));}
 else {const p=c.valuePath,key=[type,field,...p].join('.'),example=descend(p);if(key==='room.climate.terrain')values=terrain.map(v=>({value:v,label:v}));else if(refs[key])values=(cache[refs[key]]||[]).map(x=>({value:x.id,label:x.id+(x.name?' · '+x.name:'')}));else if(typeof example==='boolean')values=[true,false].map(v=>({value:v,label:String(v)}));}
 return values.filter(x=>String(x.value).toLocaleLowerCase().startsWith(c.prefix.toLocaleLowerCase())).slice(0,30).map(x=>{let insert=JSON.stringify(x.value);if(c.key&&!/^\s*:/.test(text.slice(c.end)))insert+=': ';return {...x,insert,start:c.start,end:c.end};});
}
function diagnostic(text){if(text.length>100000)return 'Draft exceeds 100 KB assistance limit. Text is preserved; use the existing validator.';try{JSON.parse(text);return 'JSON syntax valid. Types, ranges and world references still need Save field and Creator Validate.';}catch(e){return 'JSON syntax: '+e.message+' Draft retained; nothing saved.';}}
let serial=0;function attach(ta){if(ta.dataset.assistAttached)return;ta.dataset.assistAttached='true';const box=document.createElement('div'),status=document.createElement('p'),list=document.createElement('div');box.className='creator-assist';status.setAttribute('role','status');list.id='creator-assist-'+(++serial);list.setAttribute('role','listbox');list.setAttribute('aria-label','JSON completions');list.hidden=true;box.append(status,list);ta.after(box);ta.setAttribute('aria-controls',list.id);ta.setAttribute('aria-expanded','false');ta.setAttribute('aria-autocomplete','list');const help=document.createElement('small');help.textContent='JSON help: Ctrl+Space for known keys/options, arrows to choose, Enter to insert, Escape to dismiss. Suggestions edit only this draft.';box.prepend(help);let choices=[],selected=0,source='',caret=0;const current=()=>ta.dataset.creatorWorld===ed.gameSlug&&ta.dataset.creatorType===ed.type&&ta.dataset.creatorEntry===String(ed.entryId)&&ta.dataset.creatorVersion===String(ed.selectionVersion||0);
 const close=()=>{list.hidden=true;list.replaceChildren();ta.setAttribute('aria-expanded','false');ta.removeAttribute('aria-activedescendant');choices=[];};
 const choose=index=>{const choice=choices[index];if(!choice)return;if(ta.value!==source||!current()||ta.selectionStart!==caret||ta.selectionEnd!==caret){close();return;}ta.setRangeText(choice.insert,choice.start,choice.end,'end');close();ta.dispatchEvent(new Event('input',{bubbles:true}));ta.focus();};
 const highlight=()=>{[...list.children].forEach((n,i)=>n.setAttribute('aria-selected',String(i===selected)));ta.setAttribute('aria-activedescendant',list.children[selected]?.id||'');};
 const show=()=>{close();if(ta.selectionStart!==ta.selectionEnd){status.textContent='Place the caret in one JSON token to request suggestions. Draft retained.';return;}source=ta.value;caret=ta.selectionStart;if(!current()){status.textContent='Selection changed. Reopen this field before requesting reference suggestions.';return;}choices=suggestions(ta.value,ta.selectionStart,ta.dataset.creatorType,ta.dataset.creatorJson,ed.entriesCache);if(!choices.length){status.textContent=diagnostic(ta.value)+' No known completion here.';return;}selected=0;for(const [i,choice]of choices.entries()){const n=document.createElement('button');n.type='button';n.id=list.id+'-'+i;n.setAttribute('role','option');n.textContent=choice.label;n.onmousedown=e=>e.preventDefault();n.onclick=()=>choose(i);list.append(n);}list.hidden=false;ta.setAttribute('aria-expanded','true');highlight();};
 ta.addEventListener('input',()=>{status.textContent=diagnostic(ta.value);const c=context(ta.value,ta.selectionStart);if(!list.hidden||(document.activeElement===ta&&c?.prefix.length))show();});ta.addEventListener('keydown',e=>{if(e.ctrlKey&&e.code==='Space'){e.preventDefault();show();}else if(!list.hidden&&['ArrowDown','ArrowUp','Enter','Escape'].includes(e.key)){e.preventDefault();e.stopPropagation();if(e.key==='Escape')close();else if(e.key==='Enter')choose(selected);else {selected=(selected+(e.key==='ArrowDown'?1:-1)+choices.length)%choices.length;highlight();}}});ta.addEventListener('keyup',e=>{if(['ArrowLeft','ArrowRight','Home','End','PageUp','PageDown'].includes(e.key))close();});ta.addEventListener('click',close);ta.addEventListener('blur',close);status.textContent=diagnostic(ta.value);
}
const scan=()=>document.querySelectorAll('textarea[data-creator-json]').forEach(attach);new MutationObserver(scan).observe(document.body,{childList:true,subtree:true});scan();window.ExpanseCreatorAssist={context,suggestions,diagnostic,scan};
})();
