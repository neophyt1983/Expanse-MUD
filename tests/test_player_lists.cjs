/* Execute the real served player-list script on the project's explicit DOM
 * double. This verifies DOM/events and packet handling, not browser rendering.
 * Run: node --test tests/test_player_lists.cjs
 */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const script=fs.readFileSync(process.env.PLAYER_LISTS_SCRIPT||path.join(__dirname,'../web/player-lists.js'),'utf8');
const refusal='Finish the lesson, then meet the Guide at the Hearthmere Training Hall.';
const rows=()=>[{id:'learn_interface',label:'Learn the Interface',actions:[
 {label:'Complete quest',command:'complete learn_interface'},
 {label:'Track quest',command:'track learn_interface'},
 {label:'Unavailable action',command:'locked learn_interface',disabled:true,reason:'Not ready'},
]},{id:'duplicate',label:'Same quest in another group',actions:[{label:'Complete duplicate',command:'complete learn_interface'}]}];
function boot(){
 const {window,document,Event}=createDOM(),sent=[];
 const session=document.createElement('div');session.id='session-actions';document.body.append(session);
 Object.assign(window,{console,ws:{readyState:1,send:body=>sent.push(JSON.parse(body))}});
 vm.runInNewContext(script,window,{filename:'web/player-lists.js'});
 return {window,document,Event,sent,api:window.ExpansePlayerLists,
  get dialog(){return document.getElementById('player-lists');},
  get status(){return document.getElementById('player-lists-status').textContent;},
  get content(){return document.getElementById('player-lists-content');},
  button(label){return [...this.dialog.querySelectorAll('button')].find(b=>b.textContent===label);},
  requests(prefix){return sent.filter(message=>message.command.startsWith(prefix));},
 };
}
function list(f,{kind='quests',groups=rows(),note='Known entries only.',request=f.requests('ui list ').at(-1)}={}){
 assert.ok(request,'List request is missing');
 f.api.receive({type:'player_list',kind,request_id:request.request_id,title:kind,note,groups});
}
function opened(){const f=boot();f.api.open('quests');list(f);return f;}
function action(f,label='Complete quest'){
 const button=f.button(label);assert.ok(button,label+' missing');button.click();
 return f.sent.at(-1);
}
function result(f,request,{type='response',text=refusal,...extra}={}){
 return f.api.receive({type,text,request_id:request.request_id,player_list_action:true,...extra});
}

test('completion rejection remains visible through automatic and manual list refreshes',()=>{
 const f=opened(),request=action(f);
 assert.equal(request.command,'complete learn_interface');
 assert.equal(result(f,request),false,'Action result must still reach the transcript');
 assert.ok(f.status.includes(refusal));
 assert.equal(request.player_list_action,true);
 assert.equal(typeof request.request_id,'string');
 assert.ok(f.status.includes('Loading your known quests'));
 assert.equal(f.requests('ui list ').length,2);
 list(f,{note:'Refreshed quest state.'});
 assert.ok(f.status.includes(refusal));assert.ok(f.status.includes('Refreshed quest state.'));
 f.button('Refresh').click();assert.ok(f.status.includes(refusal));
 list(f,{note:'Manually refreshed.'});assert.ok(f.status.includes(refusal));
 assert.equal(f.button('Complete quest').disabled,false);
 const count=f.requests('ui list ').length;
 result(f,request,{text:'Stale duplicate response'});
 assert.equal(f.requests('ui list ').length,count);
 assert.ok(f.status.includes(refusal));assert.ok(!f.status.includes('Stale duplicate'));
});

test('pending actions reject duplicate clicks and unrelated or malformed results',()=>{
 const f=opened(),request=action(f),count=f.sent.length;
 assert.equal(f.button('Complete quest').disabled,true);
 assert.equal(f.button('Complete duplicate').disabled,true);
 f.button('Complete quest').click();f.button('Complete duplicate').onclick();
 assert.equal(f.sent.length,count);
 const waiting=f.status;
 for(const packet of [
  {type:'response',text:'Other response'},
  {type:'error',text:'Other error'},
  {type:'response',request_id:request.request_id,text:'Missing action envelope'},
  {type:'error',request_id:request.request_id,text:'Missing action envelope'},
  {type:'response',player_list_action:true,request_id:'wrong-id',text:'Wrong request'},
  {type:'response',player_list_action:true,request_id:123,text:'Malformed request'},
 ]){f.api.receive(packet);assert.equal(f.status,waiting);}
 assert.equal(f.sent.length,count);
 assert.equal(f.button('Complete quest').disabled,true);
 f.button('Refresh').click();list(f);
 assert.equal(f.button('Complete quest').disabled,true,'A list refresh must retain the pending action guard');
 assert.equal(f.button('Complete duplicate').disabled,true);
 result(f,request,{type:'error',text:'Current request rejected'});
 assert.equal(f.button('Complete quest').disabled,false);
 assert.equal(f.button('Complete duplicate').disabled,false);
 assert.equal(f.button('Unavailable action').disabled,true);
 assert.ok(f.status.includes('Current request rejected'));
});

test('different actions have independent IDs and older outcomes do not replace the latest feedback',()=>{
 const f=opened(),complete=action(f),track=action(f,'Track quest');
 assert.notEqual(complete.request_id,track.request_id);
 assert.equal(f.button('Complete quest').disabled,true);
 assert.equal(f.button('Track quest').disabled,true);
 result(f,complete,{text:'Older complete response'});
 assert.ok(f.status.includes('Track quest requested'));
 assert.ok(!f.status.includes('Older complete response'));
 list(f);
 assert.equal(f.button('Complete quest').disabled,false);
 assert.equal(f.button('Track quest').disabled,true);
 result(f,track,{type:'error',text:'Tracking rejected by the server'});
 assert.equal(f.button('Track quest').disabled,false);
 assert.ok(f.status.includes('Tracking rejected by the server'));
 result(f,complete,{text:'Stale complete response'});
 assert.ok(!f.status.includes('Stale complete response'));
});

test('an action result cannot replace another list kind and feedback remains scoped to its list',()=>{
 const f=opened(),request=action(f);
 f.api.open('inventory');list(f,{kind:'inventory',groups:[],note:'Inventory note.'});
 const count=f.requests('ui list ').length,status=f.status;
 result(f,request);
 assert.equal(f.status,status);assert.equal(f.requests('ui list ').length,count);
 f.api.open('quests');assert.ok(f.status.includes(refusal));list(f);
 assert.ok(f.status.includes(refusal));
 f.api.open('inventory');list(f,{kind:'inventory',groups:[],note:'Inventory note.'});
 assert.equal(f.status,'Inventory note.');
});

test('closing or disconnecting invalidates pending replies and feedback',()=>{
 for(const clear of [f=>f.api.close(),f=>f.api.disconnect(),
  f=>f.api.receive({event:'character_entered',player_id:'another-character',type:'system'}),
  f=>f.api.receive({type:'character_required'}),f=>f.api.receive({type:'saved_exit'})]){
  const f=opened(),old=action(f);clear(f);
  assert.equal(f.dialog.open,false);
  f.api.open('quests');list(f);
  const count=f.sent.length;
  result(f,old,{text:'Previous character rejection'});
  assert.equal(f.sent.length,count);assert.ok(!f.status.includes('Previous character'));
  assert.ok(!f.status.includes('requested'));
  const current=action(f);assert.notEqual(current.request_id,old.request_id);
  result(f,current,{text:'Current character result'});
  assert.ok(f.status.includes('Current character result'));
 }
});

test('list refresh errors preserve the acknowledged action rejection',()=>{
 const f=opened(),request=action(f);result(f,request);
 const refresh=f.requests('ui list ').at(-1);
 assert.equal(f.api.receive({type:'error',request_id:refresh.request_id,text:'Refresh unavailable'}),true);
 assert.ok(f.status.includes(refusal));assert.ok(f.status.includes('Refresh unavailable'));
});

test('offline send preserves rule-disabled buttons and allows retry after reconnect',()=>{
 const f=opened();f.window.ws.readyState=3;
 const count=f.sent.length;f.button('Complete quest').click();
 assert.equal(f.sent.length,count);assert.ok(f.status.includes('Connection unavailable.'));
 assert.equal(f.button('Complete quest').disabled,false);
 assert.equal(f.button('Unavailable action').disabled,true);
 f.window.ws.readyState=1;
 const current=action(f);assert.equal(current.player_list_action,true);
 assert.equal(f.button('Complete quest').disabled,true);
});

test('locally handled lesson buttons do not send action commands',()=>{
 const f=opened(),calls=[];
 f.window.ExpanseInterfaceTour={openQuest:id=>(calls.push(['resume',id]),true),openAlternative:id=>(calls.push(['alternative',id]),true)};
 f.api.open('quests');list(f,{groups:[{id:'guide',label:'Learn the Interface',actions:[
  {label:'Resume lesson',command:'interface resume guide'},
  {label:'Another quest',command:'interface alternative guide'},
 ]}]});
 const count=f.sent.length;f.button('Resume lesson').click();f.button('Another quest').click();
 assert.deepEqual(calls,[['resume','guide'],['alternative','guide']]);
 assert.equal(f.sent.length,count);
});

test('map focus and navigation requests retain their ordinary envelopes',()=>{
 const f=opened();f.api.open('quests');list(f,{groups:[{label:'A place',location:{id:'training_hall',name:'Training Hall'}}]});
 f.button('Show Training Hall on map').click();
 const focus=f.sent.at(-1);assert.equal(focus.command,'ui focus training_hall');
 assert.equal(typeof focus.request_id,'string');assert.equal(focus.player_list_action,undefined);
 assert.equal(f.api.receive({type:'error',request_id:focus.request_id,text:'Location unavailable'}),true);
 assert.ok(f.status.includes('Location unavailable'));
 f.api.requestNavigation();const navigation=f.sent.at(-1);
 assert.equal(navigation.command,'ui navigation');assert.equal(navigation.player_list_action,undefined);
 assert.notEqual(navigation.request_id,focus.request_id);
});
