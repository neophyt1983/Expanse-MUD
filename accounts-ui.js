(async()=>{
 const state=await fetch('/api/accounts/status').then(r=>r.json()).catch(()=>({}));if(!state.enabled)return;
 const button=document.createElement('button');button.textContent='Accounts';document.querySelector('header')?.append(button);
 const d=document.createElement('dialog');d.style.cssText='background:#141a23;color:#bdd0d8;border:1px solid #527b69;max-width:520px;width:90%;padding:24px';
 const title=document.createElement('h2');title.textContent='Expanse account';d.append(title);
 const notice=document.createElement('p');notice.textContent='Accounts belong to this host. Security records include your recovery email, IP, client information and a random installation ID. Connection logs expire after 30 days. These identifiers do not prove a person’s or machine’s identity.';d.append(notice);
 const namePolicy=typeof config!=='undefined'&&typeof config.character_name_locked==='boolean'?config.character_name_locked:state.character_name_locked;
 const editableName=namePolicy===false;
 const fixedName=typeof state.character_name==='string'?state.character_name.trim():'';
 if(editableName||fixedName){const [first,...last]=fixedName.split(/\s+/);for(const [id,value] of [['cc-first',first],['cc-last',last.join(' ')]]){const field=document.getElementById(id);if(field){field.readOnly=!editableName;if(!editableName)field.value=value;}}}
 const status=document.createElement('p');status.setAttribute('role','status');d.append(status);
 const fields={};for(const [name,type,label] of [['username','text','Character name'],['email','email','Recovery email'],['password','password','Password (15–128 characters)'],['code','text','Emailed verification or recovery code']]){
 const l=document.createElement('label');l.textContent=label;l.style.display='block';const i=document.createElement('input');i.type=type;i.style.cssText='display:block;width:95%;margin:5px 0 12px';i.maxLength=name==='password'?128:254;i.autocomplete=name==='password'?'current-password':name==='code'?'one-time-code':name;fields[name]=i;l.append(i);d.append(l);}
 let installation=localStorage.getItem('expanse.installation');if(!installation){installation=crypto.randomUUID();localStorage.setItem('expanse.installation',installation);}
 for(const [action,label] of [['login','Sign in'],['register','Register'],['verify','Verify email'],['recover','Email recovery code'],['reset','Reset password'],['logout','Sign out']]){
 const b=document.createElement('button');b.textContent=label;b.style.margin='4px';b.onclick=async()=>{b.disabled=true;status.textContent='Working…';try{
 const body={installation};for(const [k,v] of Object.entries(fields))body[k]=v.value;
 const result=await fetch('/api/accounts/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());fields.password.value='';fields.code.value='';status.textContent=(result.error||result.text)+(result.recovery_key?' Recovery key (keep safely): '+result.recovery_key:'');
 if(!result.error&&!result.recovery_key&&['login','logout','reset'].includes(action))location.reload();
 }catch(e){status.textContent='Unable to reach the account server.';}finally{b.disabled=false;}};d.append(b);}
 const close=document.createElement('button');close.textContent='Close';close.onclick=()=>d.close();d.append(close);document.body.append(d);button.onclick=()=>d.showModal();
 if(location.origin!==state.public_url){status.textContent='Open '+state.public_url+' using Join Network Game to sign in.';return;}if(!state.signed_in)d.showModal();
})();
