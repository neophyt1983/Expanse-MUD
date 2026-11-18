/* Exercises the legacy host protocol against world-assets.js in isolated page contexts.
 * This is a protocol/JS probe, not a browser persistence or rendering test. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/world-assets.js'),'utf8');

function page(host){
 const count={requests:0,bytes:0}, window={dispatchEvent(){}};
 const context=vm.createContext({window,Map,Promise,Uint8Array,Blob,Event,setTimeout,clearTimeout,
  URL:{createObjectURL(){return 'blob:measurement-fixture';},revokeObjectURL(){}},
  atob:value=>Buffer.from(value,'base64').toString('binary')});
 window.expanseAssetSend=packet=>{
  count.requests++;
  const bytes=Buffer.from(host.data);
  queueMicrotask(()=>{count.bytes+=bytes.length;window.ExpanseAssets.receive({type:'world_asset',
   name:packet.name,offset:packet.offset,request_id:packet.request_id,size:bytes.length,
   mime:'application/octet-stream',data:bytes.toString('base64')});});
  return true;
 };
 vm.runInContext(source,context,{filename:'web/world-assets.js'});
 window.ExpanseAssets.reset('fixture-world-session');
 return {api:window.ExpanseAssets,count};
}

(async()=>{
 const host={data:'original public artwork'}, first=page(host), name='assets/terrain/fixture.png';
 const [a,b]=await Promise.all([first.api.get(name),first.api.get(name)]);
 assert.equal(first.count.requests,1);assert.equal(a.blob,b.blob);
 host.data='changed public artwork';
 const unchanged=await first.api.get(name);
 assert.equal(await unchanged.blob.text(),'original public artwork');
 assert.equal(first.count.requests,1);
 const fresh=page(host);assert.equal(await (await fresh.api.get(name)).blob.text(),host.data);
 assert.equal(fresh.count.requests,1);
 first.api.reset('new-host-session');
 assert.equal(await (await first.api.get(name)).blob.text(),host.data);
 assert.equal(first.count.requests,2);
 console.log(JSON.stringify({passed:true,source:'web/world-assets.js',
  same_page_duplicate_requests:1,new_page_download_requests:1,
  same_session_edit_detected:false,host_session_change_refetches:true,
  persistent_store_used:false,
  scope:'legacy host without media_protocol, isolated JS contexts; no browser disk cache exercised'}));
})().catch(error=>{console.error(error);process.exitCode=1;});
