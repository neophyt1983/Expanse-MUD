/* UI contract for persistent guild work; no simulated CSS layout assertions. */
'use strict';
const assert=require('node:assert/strict'),{test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/guild-ui.js'),'utf8');
function boot(){
 const {window,document}=createDOM(),sent=[],timers=new Map();let next=0;
 Object.assign(window,{ws:{readyState:1,send:text=>sent.push(JSON.parse(text))},append(){},
  setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id)});
 vm.runInNewContext(source,window,{filename:'web/guild-ui.js'});
 const content=document.createElement('div');document.body.append(content);
 const g={id:'farmers',name:'Farmers & Growers',tasks:[{id:'farming',name:'Farming',level:12}],member:false,
  join:{enabled:true,reason:'',fee:2},
  lessons:[{id:'soil',name:'Working the soil',skill:'farming',level:12,min_level:0,max_level:20,gain:1,cost:3,enabled:false,reason:'Join this guild first.',revision:null}],
  quests:[{id:'winter-grain',name:'Replenish the store',description:'Bring grain to the storekeeper.',skill:'farming',difficulty:10,tier:'Apprentice',status:'available',remaining:7,revision:100,
   accept:{enabled:true,reason:''},complete:{enabled:false,reason:'Accept this request before contributing.'},reward:'1 gold per unit delivered.'}]};
 const packet={visual:{travel_world:'realm'},character:{id:'p'},location:{id:'hall'},guilds:{room:'hall',memberships:[],guilds:[g]}};
 const render=()=>{content.replaceChildren();window.dispatchEvent(new window.CustomEvent('expanse:build-room-content',
  {detail:{packet,content,keyed:e=>e}}));};render();
 return {window,document,packet,g,content,sent,timers,render,
  button:label=>content.querySelectorAll('button').find(b=>b.textContent===label)};
}
test('local learning and work show skill, difficulty, fees, need and readable prerequisites',()=>{
 const f=boot();assert.match(f.content.textContent,/Farming 12\/100/);assert.match(f.content.textContent,/Apprentice · skill 10/);
 assert.match(f.content.textContent,/Still needed: 7/);assert.match(f.content.textContent,/1 gold per unit delivered/);
 assert.equal(f.sent.length,0);const lesson=f.button('Learn');assert.equal(lesson.disabled,true);
 const reason=f.document.getElementById(lesson.getAttribute('aria-describedby'));assert.match(reason.textContent,/Join this guild first/);assert.equal(reason.closest('button'),null);
});
test('join sends only the authenticated scope and current action',()=>{
 const f=boot();f.button('Join · 2 gold').click();
 assert.deepEqual(f.sent,[{command:'guild action',guild_ui:true,action:'join',sequence:1,request_id:'guild-1',actor_id:'p',room:'hall',guild_id:'farmers'}]);
 for(const b of f.content.querySelectorAll('button'))assert.equal(b.disabled,true);
});
test('need actions carry the quote revision and a changed quote invalidates old buttons',()=>{
 const f=boot(),old=f.button('Accept quest');f.g.quests[0].remaining=4;f.g.quests[0].revision=101;f.render();old.click();
 assert.equal(f.sent.length,0);assert.match(f.content.textContent,/offer changed/);
 f.button('Accept quest').click();assert.equal(f.sent[0].revision,101);assert.equal(f.sent[0].offer_id,'winter-grain');
 assert.equal(f.sent[0].action,'accept');assert.equal('remaining' in f.sent[0],false);assert.equal('reward' in f.sent[0],false);
});
test('a pending action cannot duplicate across refresh; only its own response releases it',()=>{
 const f=boot();f.button('Accept quest').click();f.render();f.button('Accept quest').click();assert.equal(f.sent.length,1);
 f.window.ExpanseGuilds.receive({guild_action:true,request_id:'other',text:'Unrelated'});
 assert.equal(f.button('Accept quest').disabled,true);
 f.window.ExpanseGuilds.receive({guild_action:true,request_id:'guild-1',text:'Request accepted. Find the grain.'});f.render();
 assert.match(f.content.textContent,/Find the grain/);assert.equal(f.timers.size,0);
});
test('completion is a host request and never locally reduces the outstanding need',()=>{
 const f=boot();f.g.quests[0].status='active';f.g.quests[0].complete={enabled:true,reason:''};f.render();
 f.button('Contribute').click();assert.equal(f.sent[0].action,'complete');assert.match(f.content.textContent,/Still needed: 7/);
 f.window.ExpanseGuilds.receive({guild_action:true,request_id:'guild-1',text:'Another worker already filled this need.'});
 assert.match(f.content.textContent,/Another worker already filled/);assert.equal(f.g.quests[0].remaining,7);
 f.g.quests[0].remaining=0;f.g.quests[0].complete={enabled:false,reason:'This need is met.'};f.render();
 assert.match(f.content.textContent,/returns only if the need returns/);assert.equal(f.button('Contribute').disabled,true);
});
test('stale scope, disconnected sockets and timeouts cannot silently submit work',()=>{
 const f=boot(),old=f.button('Accept quest');f.packet.character.id='other';f.render();old.click();assert.equal(f.sent.length,0);
 f.window.ws.readyState=3;f.button('Accept quest').click();assert.match(f.content.textContent,/Reconnect/);assert.equal(f.sent.length,0);
 f.window.ws.readyState=1;f.button('Accept quest').click();[...f.timers.values()][0]();assert.equal(f.sent.length,1);assert.match(f.content.textContent,/not been confirmed/);
 f.window.dispatchEvent(new f.window.CustomEvent('expanse:character-reset'));
 f.window.ExpanseGuilds.receive({guild_action:true,request_id:'guild-1',text:'Old private result'});
 f.render();assert.doesNotMatch(f.content.textContent,/Old private result/);
});
test('authored labels render literally and both delivered scripts match',()=>{
 const f=boot();f.g.name='<b>Guild</b>';f.g.quests[0].description='<img src=x>';f.render();
 assert.equal(f.content.querySelector('b'),null);assert.equal(f.content.querySelector('img'),null);
 assert.match(f.content.textContent,/<b>Guild<\/b>/);
 assert.equal(fs.readFileSync(path.join(__dirname,'../guild-ui.js'),'utf8'),source);
});
