/* Execute the real theft UI; the DOM double tests events, never CSS geometry. */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/theft-ui.js'),'utf8');

function boot(){
 const {window,document}=createDOM(),sent=[],log=[],timers=new Map();let timerID=0;
 Object.assign(window,{ws:{readyState:1,send:body=>sent.push(JSON.parse(body))},
  append:(type,text)=>log.push({type,text}),
  setTimeout:fn=>{timers.set(++timerID,fn);return timerID;},clearTimeout:id=>timers.delete(id)});
 vm.runInNewContext(source,window,{filename:'web/theft-ui.js'});
 const content=document.createElement('div');document.body.append(content);
 const packet={visual:{travel_world:'realm'},character:{id:'p'},location:{id:'market'},
  theft:{level:42,observation:17,blocked:'',targets:[{id:'npc-1',name:'Arden <b>Lightbrook</b>',kind:'npc'},{id:'p2',name:'Traveller',kind:'player'}]}};
 const keyed=(e,...parts)=>{e.dataset.viewKey=JSON.stringify(parts);return e;};
 const render=()=>{content.replaceChildren();for(const person of packet.theft?.targets||[]){
  const card=document.createElement('section');card.append(document.createTextNode(person.name));
  content.append(keyed(card,person.kind==='player'?'Players here':'People and creatures',person.id));
 }window.dispatchEvent(new window.CustomEvent('expanse:build-room-content',{detail:{packet,content,keyed}}));};
 render();
 return {window,document,content,packet,sent,log,timers,render,
  open:()=>window.ExpanseTheft.open('npc-1'),
  dialog:()=>document.getElementById('theft-action'),
  button:label=>document.getElementById('theft-action')?.querySelectorAll('button').find(b=>b.textContent===label),
  quantity:value=>{document.getElementById('theft-action').querySelector('input').value=String(value);}};
}

test('each local actor has an explicit theft choice and no private pocket list',()=>{
 const f=boot();assert.equal(f.content.querySelectorAll('button').length,2);assert.equal(f.sent.length,0);
 f.open();assert.equal(f.dialog().open,true);assert.match(f.dialog().textContent,/This is theft/);
 assert.match(f.dialog().textContent,/Burgling: 42\/100/);assert.match(f.dialog().textContent,/Steal from Arden <b>Lightbrook<\/b>\?/);
 assert.equal(f.dialog().querySelector('b'),null);assert.equal(f.dialog().querySelector('select'),null);
 f.quantity(4);f.button('Attempt theft').click();
 assert.deepEqual(f.sent,[{command:'steal action',theft_ui:true,action:'steal',sequence:1,request_id:'theft-1',actor_id:'p',room:'market',target_id:'npc-1',quantity:4}]);
});

test('one request stays pending through refresh and cannot be sent twice or retargeted',()=>{
 const f=boot();f.open();f.button('Attempt theft').click();f.button('Attempt theft').click();f.render();
 assert.equal(f.sent.length,1);assert.equal(f.button('Attempt theft').disabled,true);
 f.button('Close').click();f.window.ExpanseTheft.open('p2');
 assert.equal(f.dialog().open,true);assert.match(f.dialog().textContent,/Wait for the current theft result/);
 assert.match(f.dialog().textContent,/Steal from Arden/);assert.equal(f.sent.length,1);
 f.window.ExpanseTheft.receive({theft_action:true,request_id:'someone-else',text:'Not this result'});
 assert.equal(f.button('Attempt theft').disabled,true);
 f.window.ExpanseTheft.receive({theft_action:true,request_id:'theft-1',text:'You take 2 bread.'});
 f.packet.theft.blocked='Wait 1 game minute before another theft attempt.';f.render();
 assert.match(f.dialog().textContent,/You take 2 bread/);assert.match(f.dialog().textContent,/Wait 1 game minute/);
 assert.equal(f.button('Attempt theft').disabled,true);assert.equal(f.timers.size,0);
});

test('invalid quantities and disconnected sessions never send an attempt',()=>{
 const f=boot();f.open();
 for(const value of ['','0','-1','1.5','1000001','NaN']){f.quantity(value);f.button('Attempt theft').click();assert.equal(f.sent.length,0);}
 f.quantity(2);f.window.ws.readyState=3;f.button('Attempt theft').click();assert.match(f.dialog().textContent,/Reconnect/);assert.equal(f.sent.length,0);
});

test('world, room and character changes invalidate old controls and late results',()=>{
 for(const change of [f=>{f.packet.character.id='new';},f=>{f.packet.location.id='lane';},f=>{f.packet.visual.travel_world='other';}]){
  const f=boot();f.open();const old=f.button('Attempt theft');old.click();change(f);f.render();
  assert.equal(f.dialog().open,false);old.click();assert.equal(f.sent.length,1);
  f.open();f.window.ExpanseTheft.receive({theft_action:true,request_id:'theft-1',text:'Old result'});
  assert.doesNotMatch(f.dialog().textContent,/Old result/);f.button('Attempt theft').click();assert.equal(f.sent[1].sequence,2);
 }
});

test('a departed target cannot be reopened by the pending-action guard',()=>{
 const f=boot();f.open();f.button('Attempt theft').click();f.packet.theft.targets.shift();f.render();
 assert.equal(f.dialog().open,false);assert.equal(f.timers.size,0);
 f.window.ExpanseTheft.open('p2');assert.match(f.dialog().textContent,/Steal from Traveller/);
 f.window.ExpanseTheft.receive({theft_action:true,request_id:'theft-1',text:'An old result'});
 assert.doesNotMatch(f.dialog().textContent,/An old result/);
});

test('timeout shows uncertainty without silently retrying or claiming a transfer',()=>{
 const f=boot();f.open();f.button('Attempt theft').click();[...f.timers.values()][0]();
 assert.equal(f.sent.length,1);assert.match(f.dialog().textContent,/not been confirmed/);
 assert.match(f.dialog().textContent,/Check Conversation and your inventory/);
});

test('character reset and hosts without the feature leave no actionable stale dialog',()=>{
 const f=boot();f.open();f.window.dispatchEvent(new f.window.CustomEvent('expanse:character-reset'));
 assert.equal(f.dialog().open,false);f.button('Attempt theft').click();assert.equal(f.sent.length,0);
 delete f.packet.theft;f.render();assert.equal(f.content.children.length,0);f.window.ExpanseTheft.open('npc-1');assert.equal(f.dialog().open,false);
});

test('root and web theft interfaces remain identical',()=>{
 assert.equal(fs.readFileSync(path.join(__dirname,'../theft-ui.js'),'utf8'),source);
});
