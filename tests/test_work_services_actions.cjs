/* Host-authoritative work/service cards; real geometry has a Qt probe. */
'use strict';
const assert=require('node:assert/strict'),{test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/work-services-ui.js'),'utf8');
function boot(){
 const {window,document}=createDOM(),sent=[],timers=new Map();let timerId=0;
 Object.assign(window,{ws:{readyState:1,send:raw=>sent.push(JSON.parse(raw))},append(){},
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id)});
 vm.runInNewContext(source,window,{filename:'web/work-services-ui.js'});
 const content=document.createElement('div');document.body.append(content);
 const apply={id:'job:helper:apply',service:'employment',action:'apply',label:'Apply for kitchen work',enabled:true,reason:'',revision:'job-revision-1'};
 const begin={id:'art:poem:begin',service:'art',action:'begin',label:'Begin a poem',enabled:true,reason:'',revision:'art-revision-1'};
 const care={id:'clinic:treatment',service:'clinical',action:'treatment',label:'Request treatment · 8 gold',enabled:false,
  reason:'The actual care cabinet needs a bandage and clean water.',revision:'care-revision-1'};
 const packet={visual:{travel_world:'realm'},character:{id:'p',gold:8},location:{id:'market'},work_services:{cards:[
  {id:'employment',title:'Paid work',lines:['Wages come from the counter treasury.'],entries:[{id:'helper',title:'Kitchen helper',lines:['3 gold for 5 game minutes of real work.'],actions:[apply]}]},
  {id:'art',title:'Artistic work',lines:[],entries:[{id:'poem',title:'A local verse',lines:['One paper and one ink are required.'],actions:[begin]}]},
  {id:'clinical',title:'Medical care',lines:[],entries:[{id:'treatment',title:'A staffed local treatment',lines:['8 gold from the patient’s purse.'],actions:[care]}]}
 ]}};
 const render=()=>{content.replaceChildren();window.dispatchEvent(new window.CustomEvent('expanse:build-room-content',
  {detail:{packet,content,keyed:e=>e}}));};render();
 return {window,document,content,packet,apply,begin,care,sent,timers,render,
  button:label=>content.querySelectorAll('button').find(b=>b.textContent===label)};
}

test('cards show only projected terms and readable reasons without performing work',()=>{
 const f=boot();assert.equal(f.sent.length,0);f.render();assert.equal(f.sent.length,0);
 assert.equal(f.content.querySelectorAll('.work-service-card').length,3);
 assert.match(f.content.textContent,/3 gold for 5 game minutes/);assert.match(f.content.textContent,/One paper and one ink/);
 const button=f.button(f.care.label);assert.equal(button.disabled,true);
 const reason=f.document.getElementById(button.getAttribute('aria-describedby'));
 assert.equal(reason.textContent,f.care.reason);assert.equal(reason.closest('button'),null);
 button.click();assert.equal(f.sent.length,0);
});

test('a choice sends only current identity, offer and revision; it does not award money locally',()=>{
 const f=boot(),before=JSON.stringify(f.packet);f.button(f.apply.label).click();
 assert.deepEqual(f.sent,[{command:'work action',work_ui:true,service:'employment',action:'apply',
  sequence:1,request_id:'work-1',actor_id:'p',room:'market',offer_id:'job:helper:apply',revision:'job-revision-1'}]);
 assert.equal(JSON.stringify(f.packet),before);
 for(const button of f.content.querySelectorAll('button'))assert.equal(button.disabled,true);
 assert.match(f.content.textContent,/Waiting for a response/);
});

test('pending requests survive refresh and only their own response releases controls',()=>{
 const f=boot();f.button(f.begin.label).click();f.render();f.button(f.apply.label).click();
 assert.equal(f.sent.length,1);
 f.window.ExpanseWorkServices.receive({work_action:true,request_id:'unrelated',text:'Another result'});
 assert.equal(f.button(f.begin.label).disabled,true);
 assert.doesNotMatch(f.content.textContent,/Another result/);
 f.window.ExpanseWorkServices.receive({work_action:true,request_id:'work-1',text:'The paper was reserved; work is in progress.'});
 assert.equal(f.button(f.begin.label).disabled,false);assert.equal(f.button(f.care.label).disabled,true);
 assert.equal(f.timers.size,0);f.render();assert.match(f.content.textContent,/paper was reserved/);
});

test('old button quotes cannot submit changed prices, revisions or disabled offers',()=>{
 for(const changed of ['revision','terms','disabled']){
  const f=boot(),old=f.button(f.apply.label);
  if(changed==='revision')f.apply.revision='job-revision-2';
  if(changed==='terms')f.apply.label='Apply for work · 2 gold per batch';
  if(changed==='disabled'){f.apply.enabled=false;f.apply.reason='Another worker filled the vacancy.';}
  f.render();old.click();assert.equal(f.sent.length,0);assert.match(f.content.textContent,/offer changed/);
  if(changed!=='disabled'){
   f.button(f.apply.label).click();assert.equal(f.sent.length,1);assert.equal(f.sent[0].revision,f.apply.revision);
  }
 }
});

test('removed offers and old world, room or actor controls cannot submit or leak responses',()=>{
 for(const changed of ['world','actor','room','removed']){
  const f=boot(),old=f.button(f.apply.label);old.click();
  if(changed==='world')f.packet.visual.travel_world='different-world';
  if(changed==='actor')f.packet.character.id='different-person';
  if(changed==='room')f.packet.location.id='street';
  if(changed==='removed')f.packet.work_services.cards[0].entries=[];
  f.render();old.click();assert.equal(f.sent.length,1);
  if(changed!=='removed'){
   f.window.ExpanseWorkServices.receive({work_action:true,request_id:'work-1',text:'Old private wage information'});
   assert.doesNotMatch(f.content.textContent,/Old private wage/);
   f.button(f.apply.label).click();assert.equal(f.sent[1].request_id,'work-2');
  }
 }
});

test('disconnection, send failure and an unconfirmed timeout never simulate completion',()=>{
 const f=boot();f.window.ws.readyState=3;f.button(f.apply.label).click();
 assert.equal(f.sent.length,0);assert.match(f.content.textContent,/Reconnect/);
 f.window.ws.readyState=1;f.window.ws.send=()=>{throw Error('Closed socket');};f.button(f.apply.label).click();
 assert.equal(f.sent.length,0);assert.match(f.content.textContent,/request was not sent/);
 assert.equal(f.button(f.apply.label).disabled,false);assert.equal(f.timers.size,0);
 f.window.ws.send=raw=>f.sent.push(JSON.parse(raw));f.button(f.apply.label).click();
 const timeout=[...f.timers.values()][0];timeout();
 assert.equal(f.sent.length,1);assert.match(f.content.textContent,/not been confirmed/);
 assert.equal(f.packet.character.gold,8);assert.equal(f.button(f.care.label).disabled,true);
 f.button(f.begin.label).click();timeout();
 assert.equal(f.button(f.begin.label).disabled,true);assert.equal(f.sent.length,2);
});

test('character reset removes private status and safe text rendering preserves labels literally',()=>{
 const f=boot();f.packet.work_services.cards[0].title='<b>Private offer</b>';
 f.care.reason='<img src=x> Bring supplies.';f.render();
 assert.equal(f.content.querySelector('b'),null);assert.equal(f.content.querySelector('img'),null);
 assert.match(f.content.textContent,/<b>Private offer<\/b>/);
 f.button(f.apply.label).click();f.window.dispatchEvent(new f.window.CustomEvent('expanse:character-reset'));
 f.window.ExpanseWorkServices.receive({work_action:true,request_id:'work-1',text:'Old private result'});f.render();
 assert.doesNotMatch(f.content.textContent,/Old private result/);assert.equal(f.timers.size,0);
 assert.equal(fs.readFileSync(path.join(__dirname,'../work-services-ui.js'),'utf8'),source);
});
