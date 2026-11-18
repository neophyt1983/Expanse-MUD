/* Host-selected media. Only freshly approved public presentation bytes enter
 * the bounded persistent cache; world state and private media never do. */
(() => {
  'use strict';
  const MAX_ASSET=32*1024*1024, MAX_PUBLIC=16*1024*1024;
  const CACHE_BYTES=64*1024*1024, CACHE_ENTRIES=256;
  const DB_NAME='expanse-public-world-media-v1', STORE='blobs';
  const PUBLIC_TYPES=new Set(['image/png','application/json','audio/ogg']);
  const memory=new Map(), requests=new Map(), leases=new Set(), queue=[];
  const counts={infoRequests:0,assetRequests:0,downloadedBytes:0,persistentHits:0,
    persistentWrites:0,bundledHits:0,integrityFailures:0,transientDownloads:0};
  let sequence=0,generation=0,current='',protocol=0,database,running=0,memoryBytes=0;
  const active=token=>token===generation&&!!current;

  function reset(world,version=0,force=false){
    world=typeof world==='string'?world:'';version=version===1?1:0;
    if(!force&&world===current&&version===protocol)return;
    generation++;current=world;protocol=version;
    for(const job of requests.values())job.finish(null);
    for(const job of memory.values())job.finish(null);
    for(const lease of leases)lease.release();
    memory.clear();queue.length=0;memoryBytes=0;
    window.dispatchEvent(new Event('expanse:world-assets'));
  }
  function disconnect(){reset('',0,true);}

  // Blocked/unavailable storage and quota failures retain transient transport.
  // This module never opens or clears any save, account or general app store.
  function openDatabase(){
    if(database)return database;
    database=new Promise(resolve=>{
      let indexedDB;
      try{indexedDB=window.indexedDB;}catch{resolve(null);return;}
      if(!indexedDB){resolve(null);return;}
      let settled=false,opening;
      const finish=value=>{if(settled){value?.close();return;}settled=true;clearTimeout(timer);resolve(value);};
      const timer=setTimeout(()=>finish(null),1500);
      try{
        opening=indexedDB.open(DB_NAME,1);
        opening.onupgradeneeded=()=>{
          const db=opening.result;
          if(!db.objectStoreNames.contains(STORE))db.createObjectStore(STORE,{keyPath:'hash'});
        };
        opening.onerror=opening.onblocked=()=>finish(null);
        opening.onsuccess=()=>{
          const db=opening.result;
          db.onversionchange=()=>{db.close();database=null;};finish(db);
        };
      }catch{finish(null);}
    });return database;
  }
  async function storage(mode,action,fallback=null){
    let db;try{db=await openDatabase();}catch{return fallback;}if(!db)return fallback;
    return new Promise(resolve=>{
      let transaction,result=fallback,settled=false;
      const finish=value=>{if(settled)return;settled=true;clearTimeout(timer);resolve(value);};
      const timer=setTimeout(()=>{try{transaction?.abort();}catch{}finish(fallback);},2000);
      try{
        transaction=db.transaction(STORE,mode);
        transaction.oncomplete=()=>finish(result);
        transaction.onabort=transaction.onerror=()=>finish(fallback);
        action(transaction.objectStore(STORE),value=>{result=value;});
      }catch{finish(fallback);}
    });
  }
  function remove(hash){return storage('readwrite',store=>{store.delete(hash);});}
  function read(hash){return storage('readonly',(store,result)=>{
    store.get(hash).onsuccess=event=>result(event.target.result||null);
  });}
  function touch(hash){return storage('readwrite',store=>{
    store.get(hash).onsuccess=event=>{const row=event.target.result;if(row)store.put({...row,used:Date.now()});};
  });}
  function remember(info,blob){
    // Account/evict/put in one serialized transaction, also across pages.
    // Quota errors abort it atomically, preserving previous good entries.
    return storage('readwrite',(store,result)=>{
      store.getAll().onsuccess=event=>{
        const rows=[];let total=0;
        for(const row of event.target.result){
          if(row.hash===info.sha256)continue;
          if(!Number.isSafeInteger(row.size)||row.size<=0||row.size>MAX_PUBLIC||
              !(row.blob instanceof Blob)||row.blob.size!==row.size||
              typeof row.hash!=='string'||!/^[a-f0-9]{64}$/.test(row.hash)){
            store.delete(row.hash);continue;
          }
          rows.push(row);total+=row.size;
        }
        rows.sort((a,b)=>(a.used||0)-(b.used||0));
        while(rows.length&&(total+blob.size>CACHE_BYTES||rows.length>=CACHE_ENTRIES)){
          const oldest=rows.shift();total-=oldest.size;store.delete(oldest.hash);
        }
        store.put({hash:info.sha256,size:blob.size,mime:info.mime,blob,used:Date.now()});result(true);
      };
    },false);
  }
  function approved(row,path){
    return row?.scope==='public-presentation'&&row.name===path&&
      typeof row.sha256==='string'&&/^[a-f0-9]{64}$/.test(row.sha256)&&
      Number.isSafeInteger(row.size)&&row.size>0&&row.size<=MAX_PUBLIC&&PUBLIC_TYPES.has(row.mime);
  }
  async function matches(blob,info){
    if(!(blob instanceof Blob)||blob.size!==info.size||blob.type!==info.mime)return false;
    try{
      const digest=await window.crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
      return Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('')===info.sha256;
    }catch{return false;}
  }
  function decode(data,limit){
    if(typeof data!=='string'||data.length>limit||data.length%4)return null;
    const padding=data.endsWith('==')?2:data.endsWith('=')?1:0;
    // A single character-class scan remains linear for multi-megabyte native
    // responses; repeated capture groups can exhaust a browser regexp stack.
    if(/[^A-Za-z0-9+/]/.test(data.slice(0,data.length-padding)))return null;
    try{return Uint8Array.from(atob(data),c=>c.charCodeAt(0));}catch{return null;}
  }
  function ask(type,command,path,token,fields={},timeout=15000){
    return new Promise(resolve=>{
      if(!active(token)){resolve(null);return;}
      const id=++sequence;let settled=false;
      const finish=row=>{if(settled)return;settled=true;clearTimeout(timer);requests.delete(id);resolve(active(token)?row:null);};
      const timer=setTimeout(()=>finish(null),timeout);
      requests.set(id,{finish,receive:row=>finish(row.type===type&&row.name===path?row:null)});
      if(command==='world asset info')counts.infoRequests++;else counts.assetRequests++;
      try{if(!window.expanseAssetSend?.({command,name:path,...fields,request_id:id}))finish(null);}catch{finish(null);}
    });
  }
  async function download(path,token,info){
    const chunks=[];let offset=0,size,mime;
    while(active(token)){
      const row=await ask('world_asset','world asset',path,token,{offset});
      if(!row||!active(token)||row.missing||row.offset!==offset||
          !Number.isSafeInteger(row.size)||row.size<0||row.size>MAX_ASSET||
          typeof row.mime!=='string'||!row.mime||row.mime.length>128)return null;
      if(size===undefined){size=row.size;mime=row.mime;}
      if(row.size!==size||row.mime!==mime||(info&&(size!==info.size||mime!==info.mime)))return null;
      const bytes=decode(row.data,128*1024);
      if(!bytes||offset+bytes.length>size||(!bytes.length&&offset!==size))return null;
      chunks.push(bytes);offset+=bytes.length;counts.downloadedBytes+=bytes.length;
      if(offset===size)return new Blob(chunks,{type:mime});
    }return null;
  }
  async function bundled(info,token){
    if(!active(token)||info.size>512*1024||typeof window.ExpanseBundledAssets?.get!=='function')return null;
    let timer;
    try{
      const data=await Promise.race([
        Promise.resolve().then(()=>active(token)?window.ExpanseBundledAssets.get(info.sha256):null),
        new Promise(resolve=>{timer=setTimeout(()=>resolve(null),1500);})
      ]);
      if(!active(token))return null;
      const bytes=decode(data,4*Math.ceil(info.size/3));
      if(!bytes||bytes.length!==info.size)return null;
      const blob=new Blob([bytes],{type:info.mime});
      if(!await matches(blob,info))return null;
      if(!active(token))return null;
      counts.bundledHits++;return blob;
    }catch{return null;}finally{clearTimeout(timer);}
  }
  async function load(path,token){
    let info=null;
    // Insecure/old browsers keep legacy transient media without disk reuse.
    if(protocol===1&&window.crypto?.subtle){
      const row=await ask('world_asset_info','world asset info',path,token,{},3000);
      if(!active(token))return null;
      if(approved(row,path))info=row;
    }
    if(info){
      const stored=await read(info.sha256);if(!active(token))return null;
      if(stored){
        if(stored.hash===info.sha256&&stored.size===info.size&&stored.mime===info.mime&&await matches(stored.blob,info)){
          if(!active(token))return null;
          counts.persistentHits++;void touch(info.sha256);return stored.blob;
        }
        counts.integrityFailures++;await remove(info.sha256);if(!active(token))return null;
      }
    }
    let blob=info?await bundled(info,token):null;
    if(!active(token))return null;
    if(!blob)blob=await download(path,token,info);
    if(!blob||!active(token))return null;
    if(info){
      if(!await matches(blob,info)){counts.integrityFailures++;return null;}
      if(!active(token))return null;
      if(await remember(info,blob))counts.persistentWrites++;
      if(!active(token))return null;
    }else counts.transientDownloads++;
    return blob;
  }
  function trimMemory(){
    // Active consumers own separate URLs/leases. Evicting a reusable Blob here
    // never revokes music that is still playing or an image being decoded.
    const completed=[...memory.entries()].filter(([,job])=>job.blob).sort((a,b)=>a[1].used-b[1].used);
    while(completed.length&&(memoryBytes>CACHE_BYTES||memory.size>CACHE_ENTRIES)){
      const [path,job]=completed.shift();
      if(memory.get(path)===job){memory.delete(path);memoryBytes-=job.blob.size;}
    }
  }
  function pump(){
    while(running<2&&queue.length){
      const job=queue.shift();if(job.settled||!active(job.token))continue;
      running++;
      load(job.path,job.token).then(blob=>job.finish(blob)).catch(()=>job.finish(null)).finally(()=>{running--;pump();});
    }
  }
  function get(path){
    if(!current||typeof path!=='string'||!path||path.length>512)return Promise.resolve(null);
    const token=generation;
    let job=memory.get(path);
    if(!job){
      if(queue.length>=128)return Promise.resolve(null);
      let resolve;
      job={path,token,promise:new Promise(done=>{resolve=done;}),blob:null,settled:false,used:Date.now(),
        finish(blob){
          if(job.settled)return;job.settled=true;if(!active(token))blob=null;job.blob=blob;
          if(blob){memoryBytes+=blob.size;job.used=Date.now();trimMemory();}
          else if(memory.get(path)===job)memory.delete(path);
          resolve(blob);
        }};
      memory.set(path,job);trimMemory();queue.push(job);pump();
    }else job.used=Date.now();
    return job.promise.then(blob=>{
      if(!blob||!active(token))return null;
      const asset={url:URL.createObjectURL(blob),blob,release(){
        if(!leases.delete(asset))return;URL.revokeObjectURL(asset.url);
      }};
      leases.add(asset);return asset;
    });
  }
  function receive(row){
    if(!row||typeof row!=='object')return false;
    if(row.type==='map')reset(row.media_world||'',row.media_protocol);
    if(row.type!=='world_asset'&&row.type!=='world_asset_info')return false;
    requests.get(row.request_id)?.receive(row);return true;
  }
  window.ExpanseAssets={get,receive,reset,disconnect,statistics:()=>({...counts,
    memoryBytes,memoryEntries:memory.size,activeLoads:running,queuedLoads:queue.length,activeLeases:leases.size})};
})();
