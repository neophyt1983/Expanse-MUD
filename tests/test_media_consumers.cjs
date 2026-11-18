/* Execute production media consumers with DOM/audio doubles, not rendering.
 * Run: node --test tests/test_media_consumers.cjs
 */
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function settle(){for(let i=0;i<8;i++)await tick();}
function boot(file,get){
 const listeners=new Map(),events=[],timers=new Map();let timerId=0,clock=0;
 const context2d=new Proxy({},{get:(obj,key)=>key in obj?obj[key]:(()=>{}),set:(obj,key,value)=>{obj[key]=value;return true;}});
 const window={ExpanseAssets:{get},addEventListener(name,fn){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push(fn);},
  dispatchEvent(event){events.push(event.type);for(const fn of listeners.get(event.type)||[])fn(event);}};
 const document={querySelector:()=>null,getElementById:()=>null,createElement:()=>({getContext:()=>context2d})};
 const audios=[];
 class Audio{constructor(){this.paused=true;this.src='';audios.push(this);}pause(){this.paused=true;}play(){this.paused=false;return Promise.resolve();}removeAttribute(name){if(name==='src')this.src='';}getAttribute(name){return this[name]||null;}load(){}}
 class Image{decode(){return Promise.resolve();}}
 const context=vm.createContext({window,document,Audio,Image,Blob,Map,Set,Promise,Event,Uint8Array,
  Date:class extends Date{static now(){return clock;}},
  setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,at:clock+delay});return id;},clearTimeout:id=>timers.delete(id)});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/',file),'utf8'),context,{filename:file});
 return {window,events,audios,advance(ms){clock+=ms;for(const [id,timer]of [...timers])if(timer.at<=clock){timers.delete(id);timer.fn();}},
  event(name){window.dispatchEvent(new Event(name));},get timers(){return timers.size;}};
}
function asset(text,releases){return {url:'blob:'+releases.length,blob:new Blob([text]),release(){releases.push(text);}};}

test('sprite atlas null failure retries with backoff and releases parsed JSON lease',async()=>{
 let attempts=0;const releases=[],doc=JSON.stringify({png:'data:image/png;base64,fixture',families:[],rigs:[]});
 const f=boot('character-sheets.js',async()=>++attempts===1?null:asset(doc,releases));
 assert.equal(await f.window.ExpanseSpriteSheets.load('sprite-bodies'),null);assert.equal(attempts,1);
 assert.equal(await f.window.ExpanseSpriteSheets.load('sprite-bodies'),null);assert.equal(attempts,1);
 f.advance(1000);await settle();assert.equal(attempts,2);assert.equal(releases.length,1);
 assert.equal((await f.window.ExpanseSpriteSheets.load('sprite-bodies')).bitmap instanceof Object,true);
 assert.ok(f.events.includes('expanse:sprite-ready'));
});

test('sprite retry budget is bounded and a world change resets it',async()=>{
 let attempts=0;const f=boot('character-sheets.js',async()=>{attempts++;return null;});
 await f.window.ExpanseSpriteSheets.load('sprite-bodies');f.advance(1000);await settle();f.advance(3000);await settle();
 for(let i=0;i<8;i++)await f.window.ExpanseSpriteSheets.load('sprite-bodies');
 assert.equal(attempts,3);assert.equal(f.timers,0);
 f.event('expanse:world-assets');await f.window.ExpanseSpriteSheets.load('sprite-bodies');assert.equal(attempts,4);
});

test('terrain null failure retries and releases index and image leases after decode',async()=>{
 let indexes=0;const releases=[],doc=JSON.stringify({keys:['plains'],variants:[''],size:24,seeds:1,file:'assets/terrain/sheet.png'});
 const f=boot('visual-map.js',async path=>path.endsWith('index.json')?(++indexes===1?null:asset(doc,releases)):asset('png bytes',releases));
 f.window.ExpanseMap.getTerrainTile('plains','start');await settle();assert.equal(indexes,1);
 f.window.ExpanseMap.getTerrainTile('plains','start');await settle();assert.equal(indexes,1);
 f.advance(1000);await settle();assert.equal(indexes,2);assert.equal(releases.length,2);
 assert.ok(f.events.includes('expanse:sprite-ready'));assert.equal(f.timers,0);
});

test('audio owns three independent leases and releases replaced/stale/disconnected sources',async()=>{
 const releases=[],pending=[];
 const f=boot('world-audio.js',path=>new Promise(resolve=>pending.push({path,resolve})));
 const audio=f.window.ExpanseWorldAudio;
 audio.mix('song-a',0,.5,.5);pending.shift().resolve(asset('song-a',releases));await settle();
 assert.equal(releases.length,0);assert.equal(f.audios[0].paused,false);
 audio.mix('song-b',0,.5,.5);assert.deepEqual(releases,['song-a']);
 audio.mix('song-c',0,.5,.5);pending.shift().resolve(asset('song-b',releases));pending.shift().resolve(asset('song-c',releases));await settle();
 assert.deepEqual(releases,['song-a','song-b']);
 const cue=audio.cue('effect');pending.shift().resolve(asset('effect',releases));await cue;
 const thunder=audio.thunder('thunder');pending.shift().resolve(asset('thunder',releases));await thunder;
 f.event('expanse:world-assets');assert.deepEqual(new Set(releases),new Set(['song-a','song-b','song-c','effect','thunder']));
 assert.ok(f.audios.every(a=>a.paused&&!a.src));
});
