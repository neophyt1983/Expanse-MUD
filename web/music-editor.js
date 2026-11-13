(()=>{
 'use strict';
 const toolbar=document.getElementById('ed-save')?.parentElement;
 if(!toolbar)return;
 const make=(tag,text)=>Object.assign(document.createElement(tag),{textContent:text||''});
 const entry=make('button','Soundtrack');entry.type='button';entry.id='ed-soundtrack';entry.className='ed-btn';toolbar.append(entry);
 const previous=updateToolbar;
 let dialog,loading=false;
 function permission(){
   entry.hidden=!config.editor_enabled;entry.disabled=loading||!!dialog||!ed.gameSlug;
   if(dialog&&(!config.editor_enabled||ed.gameSlug!==dialog.dataset.world))dialog.close();
 }
 updateToolbar=function(){previous();permission();};permission();
 entry.onclick=async()=>{
   if(entry.disabled||!config.editor_enabled)return;
   const slug=ed.gameSlug,path='games/'+encodeURIComponent(slug)+'/soundtrack';
   loading=true;permission();
   try{
     const value=await apiGet(path);if(value.error)throw Error(value.error);
     if(slug!==ed.gameSlug||!config.editor_enabled)return;
     const d=make('dialog');dialog=d;d.dataset.world=slug;d.id='soundtrack-editor';d.className='style-dialog';
     d.setAttribute('aria-label','World soundtrack');const fields=make('div'),rows=new Map();
     function select(id,inherit=false){
       const s=make('select');if(inherit)s.add(new Option('Use inherited music',''));
       for(const [key,name] of Object.entries(value.tracks))s.add(new Option(name,key));
       s.value=id;return s;
     }
     const world=select(value.config.world);const base=make('label','Whole world ');base.append(world);
     for(const [key,name] of Object.entries(value.areas)){
       const l=make('label',name+' · '+(key.startsWith('region:')?'region':'edition area')+' '),s=select(value.config.areas[key]||'',true);
       l.append(s);fields.append(l);rows.set(key,s);
     }
     const interiors=make('div'),venues=new Map();
     for(const [key,name] of Object.entries(value.venues)){
       const l=make('label',name+' '),s=select(key);s.add(new Option('Keep area music','inherit'));
       s.value=value.config.venues?.[key]||key;l.append(s);interiors.append(l);venues.set(key,s);
     }
     const status=make('p'),save=make('button','Save soundtrack'),close=make('button','Close');
     status.setAttribute('role','status');d.append(make('h2','World soundtrack'),base,make('p','Each city changes the arrangement for welcoming, neutral, wary or hostile standing toward the listener.'),make('h3','Area music'),make('p','A town or city can override its region, then its country, then the world.'),fields,make('h3','Inside buildings'),interiors,status,save,close);
     for(const l of d.querySelectorAll('label'))l.style.display='block';
     save.onclick=async()=>{
       save.disabled=true;
       try{const response=await apiPost(path,{revision:value.revision,config:{world:world.value,venues:Object.fromEntries([...venues].map(([k,s])=>[k,s.value])),areas:Object.fromEntries([...rows].filter(([,s])=>s.value).map(([k,s])=>[k,s.value]))}});
       if(response.error)throw Error(response.error);value.revision=response.revision;status.textContent='Soundtrack saved. Run or reload this world to hear it.';}
       catch(e){status.textContent=e.message;}finally{save.disabled=false;}
     };
     close.onclick=()=>d.close();d.onclose=()=>{d.remove();dialog=null;permission();};document.body.append(d);d.showModal();
   }catch(e){setStatus(e.message,'warn');}finally{loading=false;permission();}
 };
})();
