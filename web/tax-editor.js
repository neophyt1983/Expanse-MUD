/* Inert Creator tax policy authoring, deliberately separate from live economy. */
(()=>{'use strict';
const toolbar=document.getElementById('ed-save')?.parentElement;if(!toolbar)return;
const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
const button=text=>{const b=node('button',text);b.type='button';b.className='ed-btn';return b;};
const open=button('Tax plans');open.id='ed-tax-plans';toolbar.append(open);
let dialog=null,busy=false;
const previous=updateToolbar;
function permission(){open.hidden=!config.editor_enabled;open.disabled=busy||!!dialog||!ed.gameSlug;if(dialog&&(!config.editor_enabled||dialog.dataset.world!==ed.gameSlug))dialog.close();}
updateToolbar=function(){previous();permission();};permission();
open.onclick=async()=>{
 if(busy||dialog||!config.editor_enabled||!ed.gameSlug)return;
 const slug=ed.gameSlug,path='games/'+encodeURIComponent(slug)+'/tax-plans';busy=true;permission();
 try{
  const current=await apiGet(path);if(current.error)throw Error(current.error);
  if(slug!==ed.gameSlug||!config.editor_enabled)return;
  if(current.config.version!==1||current.config.mode!=='editor_only'||!Array.isArray(current.config.policies))throw Error('Unsupported tax plan file; nothing changed.');
  const d=node('dialog');dialog=d;d.id='tax-dialog';d.dataset.world=slug;d.setAttribute('aria-label','Editor-only tax plans');
  d.style.cssText='width:min(850px,94vw);max-height:90vh;overflow:auto;background:#161c24;color:#e2e8ed;padding:22px;border:1px solid #607c72';
  d.append(node('h2','Tax plans · '+slug),node('p','Editor only: design collection rules for future use. These plans do not charge players or NPCs, change prices, pay collectors, enforce penalties or run on the world clock. Save writes only the tax-plan file, not other unsaved Creator changes.'));
  const data=structuredClone(current.config);let revision=current.revision,working=false,selected=-1;
  const list=node('select');list.id='tax-list';list.setAttribute('aria-label','Tax plan');
  const form=node('fieldset'),status=node('p');status.id='tax-status';status.setAttribute('role','status');
  const controls={};
  function field(key,label,element){controls[key]=element;element.id='tax-'+key;const row=node('label',label+' ');row.style.cssText='display:block;margin:10px 0';row.append(element);form.append(row);element.oninput=()=>{if(selected<0)return;const p=data.policies[selected];p[key]=element.multiple?Array.from(element.selectedOptions,o=>o.value):['rate','interval_days'].includes(key)?Number(element.value):element.value;if(key==='basis')rateLabel();};return element;}
  function input(key,label,type='text'){const e=node('input');e.type=type;return field(key,label,e);}
  function select(key,label,rows,multiple=false){const e=node('select');e.multiple=multiple;if(multiple)e.size=6;for(const [value,text] of rows){const o=node('option',text);o.value=value;e.append(o);}return field(key,label,e);}
  input('id','Unique ID').maxLength=64;input('name','Name').maxLength=120;
  select('basis','Assess against',[['income','Income (percentage)'],['sale','Sales (percentage)'],['property','Property value (percentage)'],['flat','Fixed gold per payer']]);
  const rate=input('rate','Rate / amount','number');rate.min=0;rate.step='0.01';
  const period=input('interval_days','Collection interval (world days)','number');period.min=1;period.max=10000;period.step=1;
  select('rooms','Jurisdiction rooms (Ctrl/Shift to select several)',current.references.room.map(r=>[r.id,r.name+' ['+r.id+']']),true);
  select('recipient','Recipient faction',current.references.group.map(r=>[r.id,r.name+' ['+r.id+']']));
  select('collector','Collector NPC',[['','Unassigned'],...current.references.npc.map(r=>[r.id,r.name+' ['+r.id+']'])]);
  field('exemptions','Planned exemptions (design notes, not enforced)',node('textarea')).maxLength=2000;
  field('notes','Collection procedure / notes',node('textarea')).maxLength=2000;
  function rateLabel(){rate.max=controls.basis.value==='flat'?1000000:100;rate.title=controls.basis.value==='flat'?'Gold per payer per collection':'Percentage of the chosen assessed value per collection';}
  function render(){list.replaceChildren();data.policies.forEach((p,i)=>{const o=node('option',p.name||p.id);o.value=i;list.append(o);});list.value=selected;form.disabled=selected<0;remove.disabled=selected<0;const p=data.policies[selected]||{};for(const [k,e]of Object.entries(controls)){if(e.multiple)for(const o of e.options)o.selected=(p[k]||[]).includes(o.value);else e.value=p[k]??'';}rateLabel();}
  list.onchange=()=>{selected=Number(list.value);render();};
  const add=button('New plan'),remove=button('Remove plan'),save=button('Save plans'),close=button('Close');add.id='tax-add';save.id='tax-save';close.id='tax-close';remove.id='tax-remove';
  add.onclick=()=>{if(data.policies.length>=100){status.textContent='Maximum 100 plans.';return;}let n=1;while(data.policies.some(p=>p.id==='tax_'+n))n++;data.policies.push({id:'tax_'+n,name:'New tax plan',basis:'income',rate:0,interval_days:30,rooms:[],recipient:current.references.group[0]?.id||'',collector:'',exemptions:'',notes:''});selected=data.policies.length-1;render();};
  remove.onclick=()=>{if(selected<0)return;data.policies.splice(selected,1);selected=data.policies.length?0:-1;render();};
  save.onclick=async()=>{if(working)return;working=true;save.disabled=true;form.disabled=true;add.disabled=remove.disabled=list.disabled=true;
   try{const result=await apiPost(path,{revision,config:data});if(result.error)throw Error(result.error);revision=result.revision;status.textContent=result.text;}
   catch(e){status.textContent=e.message;}finally{working=false;save.disabled=false;add.disabled=list.disabled=false;render();}
  };
  close.onclick=()=>d.close();
  d.append(list,add,remove,form,node('p','Jurisdictions use saved room IDs; save new rooms/factions/NPCs in Creator before assigning them here. Rate 0 is valid. Overlapping plans are independent drafts, not combined bills. Exemptions and procedures are author notes until a future collection system exists.'),status,save,close);
  d.onclose=()=>{d.remove();dialog=null;permission();};document.body.append(d);selected=data.policies.length?0:-1;render();d.showModal();
 }catch(e){setStatus(e.message,'warn');}finally{busy=false;permission();}
};
})();
