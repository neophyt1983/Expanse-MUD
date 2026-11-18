/* Protocol/error/cancellation tests executing the real client in a JS VM.
 * Browser disk persistence is covered separately by the real-engine probe.
 * Run: node --test tests/test_world_assets.cjs
 */
'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createHash,webcrypto}=require('node:crypto');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../web/world-assets.js'),'utf8');
const pathName='assets/terrain/fixture.png';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function until(condition){for(let n=0;n<50;n++){if(condition())return;await tick();}assert.fail('Condition did not settle');}
function boot({protocol=1,auto=true,crypto=webcrypto,storage,native}={}){
 const sent=[],urls=[],revoked=[],timers=new Map();let time=0,nextTimer=0;
 const fixture={bytes:Buffer.from('host-approved public artwork'),mime:'image/png',scope:'public-presentation'};
 const window={dispatchEvent(){},crypto,ExpanseBundledAssets:native};
 if(storage==='denied')Object.defineProperty(window,'indexedDB',{get(){throw Error('Storage denied');}});
 else if(storage==='open-error')window.indexedDB={open(){throw Error('Storage unavailable');}};
 const context=vm.createContext({window,Map,Promise,Uint8Array,Blob,Event,
  setTimeout:(fn,delay)=>{const id=++nextTimer;timers.set(id,{fn,at:time+delay});return id;},
  clearTimeout:id=>timers.delete(id),
  URL:{createObjectURL(blob){const url='blob:fixture-'+urls.length;urls.push({url,blob});return url;},revokeObjectURL:url=>revoked.push(url)},
  atob:value=>Buffer.from(value,'base64').toString('binary')});
 function response(request,overrides={}){
  const bytes=fixture.bytes;
  if(request.command==='world asset info')return {type:'world_asset_info',name:request.name,request_id:request.request_id,
   scope:fixture.scope,sha256:createHash('sha256').update(bytes).digest('hex'),size:bytes.length,mime:fixture.mime,...overrides};
  return {type:'world_asset',name:request.name,request_id:request.request_id,offset:request.offset,
   size:bytes.length,mime:fixture.mime,data:bytes.subarray(request.offset,request.offset+(fixture.chunk||96*1024)).toString('base64'),...overrides};
 }
 window.expanseAssetSend=request=>{sent.push(request);if(auto)queueMicrotask(()=>window.ExpanseAssets.receive(response(request)));return true;};
 vm.runInContext(script,context,{filename:'web/world-assets.js'});
 const api=window.ExpanseAssets;
 api.receive({type:'map',media_world:'world-session-a',media_protocol:protocol});
 return {api,sent,fixture,urls,revoked,response,window,
  advance(ms){time+=ms;for(const [id,timer]of [...timers])if(timer.at<=time){timers.delete(id);timer.fn();}},
  reset(world='world-session-b',version=protocol){api.receive({type:'map',media_world:world,media_protocol:version});},
  reply(request,overrides={}){api.receive(response(request,overrides));},
  requests(command){return sent.filter(r=>r.command===command);}};
}

test('legacy hosts keep transient transport and same-page request coalescing',async()=>{
 const f=boot({protocol:0});const a=f.api.get(pathName),b=f.api.get(pathName);
 const [asset,other]=await Promise.all([a,b]);assert.equal(await asset.blob.text(),f.fixture.bytes.toString());
 assert.equal(asset.blob,other.blob);assert.notEqual(asset.url,other.url);
 assert.equal(f.sent.length,1);assert.equal(f.sent[0].command,'world asset');
 const third=await f.api.get(pathName);assert.equal(third.blob,asset.blob);assert.equal(f.api.statistics().transientDownloads,1);
 other.release();other.release();assert.deepEqual(f.revoked,[other.url]);
 f.reset();assert.deepEqual(new Set(f.revoked),new Set([asset.url,other.url,third.url]));assert.notEqual(await f.api.get(pathName),asset);
});

test('v1 approvals verify bytes even when persistent storage is absent or denied',async()=>{
 for(const storage of [undefined,'denied','open-error']){
  const f=boot({storage});const asset=await f.api.get(pathName);
  assert.ok(asset,storage);assert.equal(await asset.blob.text(),f.fixture.bytes.toString());
  assert.equal(f.requests('world asset info').length,1);assert.equal(f.requests('world asset').length,1);
  assert.equal(f.api.statistics().persistentWrites,0);assert.equal(f.api.statistics().transientDownloads,0);
 }
});

test('transient and unsupported approvals never consult the installed bundle',async()=>{
 let calls=0;const native={get(){calls++;return Promise.resolve('should-not-be-read');}};
 for(const scope of ['transient','unknown']){
  const f=boot({native});f.fixture.scope=scope;assert.ok(await f.api.get(pathName));assert.equal(calls,0);
  assert.equal(f.api.statistics().transientDownloads,1);
 }
 const old=boot({protocol:0,native});assert.ok(await old.api.get(pathName));assert.equal(calls,0);
 const insecure=boot({crypto:null,native});assert.ok(await insecure.api.get(pathName));assert.equal(insecure.requests('world asset info').length,0);
});

test('corrupt approved network bytes fail closed and the next request can retry',async()=>{
 const f=boot({auto:false}),pending=f.api.get(pathName);
 const info=f.sent[0];f.reply(info,{sha256:'0'.repeat(64)});
 await until(()=>f.sent.length===2);f.reply(f.sent[1]);
 assert.equal(await pending,null);assert.equal(f.urls.length,0);assert.equal(f.api.statistics().integrityFailures,1);
 const retry=f.api.get(pathName);f.reply(f.sent.at(-1));await until(()=>f.sent.at(-1).command==='world asset');
 f.reply(f.sent.at(-1));assert.ok(await retry);
});

test('malformed, mismatched and changing chunk metadata cannot publish an asset',async()=>{
 for(const change of [{data:'@@@='},{size:NaN},{offset:7},{mime:'audio/ogg'},
  {data:Buffer.from('unexpected longer bytes'.repeat(10)).toString('base64')}]){
  const f=boot({auto:false}),pending=f.api.get(pathName);f.reply(f.sent[0]);
  await until(()=>f.sent.length===2);f.reply(f.sent[1],change);
  assert.equal(await pending,null);assert.equal(f.urls.length,0);
 }
 const f=boot({auto:false,protocol:0});f.fixture.bytes=Buffer.from('abcdef');
 const pending=f.api.get(pathName);f.reply(f.sent[0],{data:Buffer.from('abc').toString('base64')});
 await until(()=>f.sent.length===2);f.reply(f.sent[1],{size:7,data:Buffer.from('def').toString('base64')});
 assert.equal(await pending,null);
});

test('info timeout falls back to legacy transport and ignores a late approval',async()=>{
 const f=boot({auto:false}),pending=f.api.get(pathName),info=f.sent[0];
 f.advance(3000);await until(()=>f.sent.length===2);f.reply(info);f.reply(f.sent[1]);
 const asset=await pending;assert.ok(asset);assert.equal(f.api.statistics().transientDownloads,1);
 assert.equal(f.api.statistics().persistentWrites,0);
});

test('missing or timed out legacy chunks resolve and remain retryable',async()=>{
 const f=boot({auto:false,protocol:0}),first=f.api.get(pathName);
 f.reply(f.sent[0],{missing:true});assert.equal(await first,null);
 const second=f.api.get(pathName);f.advance(15000);assert.equal(await second,null);
 const third=f.api.get(pathName);f.reply(f.sent.at(-1));assert.ok(await third);
});

test('disconnect and same-world reconnection cancel stale work before it reaches the UI',async()=>{
 const f=boot({auto:false}),first=f.api.get(pathName),info=f.sent[0];f.reply(info);
 await until(()=>f.sent.length===2);const stale=f.sent[1];f.api.disconnect();assert.equal(await first,null);
 f.reset('world-session-a');f.reply(stale);assert.equal(f.urls.length,0);
 const next=f.api.get(pathName);const current=f.sent.at(-1);assert.equal(current.command,'world asset info');
 assert.notEqual(current.request_id,info.request_id);f.reply(current);
 await until(()=>f.sent.at(-1).command==='world asset');f.reply(f.sent.at(-1));assert.ok(await next);
});

test('approved bundled bytes are verified before use; a broken bridge falls back',async()=>{
 const bytes=Buffer.from('host-approved public artwork');
 const f=boot({native:{get:async hash=>{assert.match(hash,/^[a-f0-9]{64}$/);return bytes.toString('base64');}}});
 assert.equal(await (await f.api.get(pathName)).blob.text(),bytes.toString());
 assert.equal(f.requests('world asset').length,0);assert.equal(f.api.statistics().bundledHits,1);
 for(const native of [{get:async()=>Buffer.from('corrupt').toString('base64')},{get(){throw Error('bridge');}}]){
  const broken=boot({native});assert.ok(await broken.api.get(pathName));assert.equal(broken.requests('world asset').length,1);
  assert.equal(broken.api.statistics().bundledHits,0);
 }
});

test('slow bundled lookup is bounded and cancellation does not issue a fallback request',async()=>{
 let resolve,calls=0;const f=boot({native:{get(){calls++;return new Promise(done=>{resolve=done;});}}});
 const pending=f.api.get(pathName);await until(()=>calls===1);f.api.disconnect();assert.equal(await pending,null);
 resolve(f.fixture.bytes.toString('base64'));await tick();await tick();assert.equal(f.requests('world asset').length,0);
 assert.equal(f.urls.length,0);
 const slow=boot({native:{get:()=>new Promise(()=>{})}}),loaded=slow.api.get(pathName);
 await until(()=>slow.requests('world asset info').length===1);await tick();await tick();slow.advance(1500);
 assert.ok(await loaded);assert.equal(slow.requests('world asset').length,1);
});

test('bounded FIFO admission never starts more than two media loads at a time',async()=>{
 const f=boot({protocol:0,auto:false}),pending=[];
 for(let i=0;i<131;i++)pending.push(f.api.get('assets/terrain/'+i+'.png'));
 assert.equal(f.sent.length,2);assert.equal(f.api.statistics().activeLoads,2);
 assert.equal(f.api.statistics().queuedLoads,128);assert.equal(await pending.at(-1),null);
 f.reply(f.sent[0]);assert.ok(await pending[0]);
 await until(()=>f.sent.length===3);assert.equal(f.sent[2].name,'assets/terrain/2.png');
 f.api.disconnect();assert.ok((await Promise.all(pending.slice(1))).every(value=>value===null));
});

test('a large but bounded bundled response uses a stack-safe decoder',async()=>{
 const bytes=Buffer.alloc(512*1024,73),f=boot({native:{get:async()=>bytes.toString('base64')}});
 f.fixture.bytes=bytes;
 const asset=await f.api.get(pathName);assert.ok(asset);assert.equal(asset.blob.size,bytes.length);
 assert.equal(f.api.statistics().bundledHits,1);assert.equal(f.requests('world asset').length,0);asset.release();
});

test('reusable page cache evicts old entries without revoking a caller-owned active URL',async()=>{
 const f=boot({protocol:0});let active;
 for(let i=0;i<257;i++){
  const asset=await f.api.get('assets/terrain/'+i+'.png');
  if(i===0)active=asset;else asset.release();
 }
 assert.equal(f.api.statistics().memoryEntries,256);assert.equal(f.api.statistics().activeLeases,1);
 assert.ok(!f.revoked.includes(active.url));assert.equal(await active.blob.text(),f.fixture.bytes.toString());
 const count=f.requests('world asset').length,again=await f.api.get('assets/terrain/0.png');
 assert.equal(f.requests('world asset').length,count+1);again.release();active.release();
 assert.equal(f.api.statistics().activeLeases,0);
});

test('more than 64 MiB of sequential authored media remains playable with bounded Blob reuse',async()=>{
 const f=boot({protocol:0});f.fixture.bytes=Buffer.alloc(10*1024*1024,79);
 let first;
 for(let i=0;i<7;i++){
  const loaded=await f.api.get('assets/audio/track-'+i+'.ogg');assert.ok(loaded);
  if(i===0)first=loaded;else loaded.release();
 }
 assert.ok(f.api.statistics().memoryBytes<=64*1024*1024);
 assert.ok(!f.revoked.includes(first.url));assert.equal(first.blob.size,10*1024*1024);
 assert.equal(f.api.statistics().activeLeases,1);first.release();assert.equal(f.api.statistics().activeLeases,0);
});
