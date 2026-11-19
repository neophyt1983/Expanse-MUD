/* Execute the served passage UI and movement controller on the repository DOM
 * double. Browser layout is covered separately; these tests exercise real click
 * handlers, stale room updates, and the host acknowledgement gate.
 * Run: node --test tests/test_street_actions.cjs
 */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const script=fs.readFileSync(process.env.STREET_ACTIONS_SCRIPT||path.join(__dirname,'../web/street-actions.js'),'utf8');
const controls=fs.readFileSync(path.join(__dirname,'../web/player-controls.js'),'utf8');
const route=(direction,label,kind='passage',blocked='')=>({direction,label,kind,blocked});
const exterior=[route('out','Passage out · Sheltered Vale Road'),route('approach east','Walk to Outside Dawnwatch Gilded Tankard')];
const interior=[route('step outside','Exit to Dawnwatch Civic Square','exit'),route('up','Stairs up · Bedroom','stairs')];
function packet({id='square',name='Dawnwatch Civic Square',kind='outdoors',character='player',passages=exterior}={}){
 const tile={id,name,current:true,x:0,y:0,z:0,terrain:kind==='building'?'floor':'grass'};
 return {type:'map',character:{id:character},location:{id,name},visual:{center:id,context:{id:kind+':'+id,kind},tiles:[tile],passages,exits:[]}};
}
function boot(initial=packet()){
 const {window,document,Event,flushMutations}=createDOM(),sent=[],errors=[],timers=new Map();let serial=0;
 const host=document.createElement('section');host.id='player-visual-map';
 const heading=document.createElement('div');heading.className='atlas-position-header';
 const location=document.createElement('div');heading.append(location);
 const viewport=document.createElement('div'),canvas=document.createElement('canvas'),inspect=document.createElement('div');
 viewport.append(canvas);host.append(heading,viewport,inspect);document.body.append(host);
 const form=document.createElement('form');form.id='input-form';document.body.append(form);
 Object.assign(window,{console,latestMap:initial,localStorage:{getItem:()=>null,setItem(){}},WebSocket:{OPEN:1},
  ws:{readyState:1,send:body=>sent.push(JSON.parse(body))},performance:{now:()=>0},
  setTimeout:fn=>{const id=++serial;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),
  append:(type,text)=>errors.push({type,text})});
 vm.runInNewContext(controls,window,{filename:'web/player-controls.js'});
 vm.runInNewContext(script,window,{filename:'web/street-actions.js'});
 const state={options:{},packet:initial,data:initial.visual,canvas,viewport,inspect,locationStatus:location,positions:[]};
 const f={window,document,Event,sent,errors,state,flushMutations,timers,
  get marker(){return document.querySelector('.tile-passage');},
  get dialog(){return document.getElementById('street-passage');},
  get status(){return state.passageStatus?.textContent||'';},
  button(label){return this.dialog.querySelectorAll('button').find(b=>b.textContent.startsWith(label));},
  update(next){window.latestMap=next;state.packet=next;state.data=next.visual;this.draw();},
  draw(){const point={tile:state.data.tiles[0],x:100,y:100,radius:24};state.positions=[point];window.ExpanseStreet.draw(state,point);},
 };
 f.draw();return f;
}

test('outdoor civic routes are available without a building exit label',()=>{
 const f=boot();assert.equal(f.marker.textContent,'Routes');
 f.marker.click();assert.equal(f.dialog.open,true);
 assert.equal(f.dialog.getAttribute('aria-label'),'Routes at Dawnwatch Civic Square');
 assert.ok(f.button('Passage out · Sheltered Vale Road'));assert.ok(f.button('Walk to Outside'));
 assert.equal(f.sent.length,0,'Opening local choices must not wait for a host round trip');
});

test('an interior exit remains named when stairs or other passages also exist',()=>{
 const f=boot(packet({id:'hall',name:'Hall',kind:'building',passages:interior}));
 assert.equal(f.marker.textContent,'↗ Exit…');f.marker.click();
 assert.ok(f.button('Exit to'));assert.ok(f.button('Stairs up'));
 f.button('Exit to').click();assert.equal(f.sent.length,1);
 assert.equal(f.sent[0].command,'go step outside');assert.equal(f.dialog.open,false);
});

test('a single outdoor entry is still Enter and uses the host movement gate',()=>{
 const f=boot(packet({passages:[route('enter building','Enter the Tankard','entry')]}));
 assert.equal(f.marker.textContent,'⌂ Enter');f.marker.click();
 assert.equal(f.sent[0].command,'go enter building');
});

test('a blocked exit can explain its restriction without sending movement',()=>{
 const f=boot(packet({kind:'building',passages:[route('out','Exit to courtyard','exit','The door is locked.')]}));
 assert.equal(f.marker.disabled,false);assert.equal(f.marker.textContent,'↗ Exit');f.marker.click();
 const action=f.button('Exit to courtyard');assert.equal(action.disabled,true);
 assert.equal(action.textContent,'Exit to courtyard');
 const reason=f.document.getElementById(action.getAttribute('aria-describedby'));
 assert.equal(reason.textContent,'The door is locked.');assert.equal(reason.tagName,'P');
 action.click();assert.equal(f.sent.length,0);
});

test('custody reasons stay readable beside disabled actions and update from the host',()=>{
 const reason=minutes=>"The judge's sentence has "+minutes+' game minutes remaining. You may use the facilities inside your place of custody.';
 const custody=minutes=>packet({id:'jail',name:'Dawnwatch Police Station Jail',kind:'building',passages:[
  route('south','Go to Dawnwatch Police Station','passage',reason(minutes)),
  route('out','Go to Dawnwatch Police Station Cell Corridor','passage',reason(minutes)),
 ]});
 const f=boot(custody(10));f.marker.click();
 const actions=f.dialog.querySelectorAll('.street-passage-action button');
 assert.equal(actions.length,2);
 const descriptions=actions.map(action=>{
  assert.equal(action.disabled,true);assert.ok(!action.textContent.includes(reason(10)));
  const id=action.getAttribute('aria-describedby'),description=f.document.getElementById(id);
  assert.equal(description.textContent,reason(10));assert.equal(description.className,'street-passage-reason');
  assert.equal(description.closest('button'),null);action.click();return id;
 });
 assert.notEqual(descriptions[0],descriptions[1]);assert.equal(f.sent.length,0);
 f.update(custody(9));
 assert.equal(f.dialog.querySelectorAll('.street-passage-reason').every(p=>p.textContent===reason(9)),true);
 assert.ok(f.dialog.textContent.includes('Available passages updated.'));
 assert.ok(!f.dialog.textContent.includes('Choose a current route'));
 assert.equal(f.dialog.querySelectorAll('.street-passage-action button').every(b=>b.disabled),true);
 assert.equal(f.sent.length,0);
});

test('pending host acknowledgement keeps the selected passage visible and allows retry',()=>{
 const f=boot(packet({id:'hall',kind:'building',passages:interior}));
 assert.equal(f.window.ExpansePlayerControls.move('go east'),true);
 const first=f.sent[0];f.marker.click();f.button('Exit to').click();
 assert.equal(f.sent.length,1,'Do not send a second step while the host has not acknowledged the first');
 assert.equal(f.dialog.open,true,'Do not dismiss a choice that was rejected locally');
 assert.match(f.dialog.textContent,/Waiting for your previous step/);assert.match(f.status,/Waiting for your previous step/);
 f.window.ExpansePlayerControls.receive({type:'response',movement_id:first.movement_id,step_taken:false});
 f.flushMutations();assert.match(f.dialog.textContent,/Ready\. Choose a passage again/);assert.match(f.status,/Ready\. Choose a passage again/);
 f.button('Exit to').click();assert.equal(f.sent.length,2);assert.equal(f.sent[1].command,'go step outside');
 assert.equal(f.dialog.open,false);
});

test('movement timeout replaces a rejected passage waiting message without another map',()=>{
 const f=boot();f.window.ExpansePlayerControls.move('go east');f.marker.click();f.button('Passage out').click();
 assert.match(f.status,/Waiting for your previous step/);
 for(const [id,fn] of [...f.timers]){f.timers.delete(id);fn();}
 f.flushMutations();assert.match(f.status,/last step has not been confirmed/);
 assert.match(f.dialog.textContent,/last step has not been confirmed/);
 f.button('Passage out').click();assert.equal(f.sent.length,2);assert.equal(f.dialog.open,false);
});

test('disconnect replaces a rejected passage waiting message with reconnect guidance',()=>{
 const f=boot();f.window.ExpansePlayerControls.move('go east');f.marker.click();f.button('Passage out').click();
 f.window.ws.readyState=3;f.window.ExpansePlayerControls.disconnect();f.flushMutations();
 assert.match(f.status,/Not connected\. Reconnect/);assert.match(f.dialog.textContent,/Not connected\. Reconnect/);
 assert.ok(!f.status.includes('Ready.'));assert.equal(f.sent.length,1);
});

test('a rejected direct exit opens retry choices with visible feedback',()=>{
 const f=boot(packet({kind:'building',passages:[interior[0]]}));
 f.window.ExpansePlayerControls.move('go east');f.marker.click();
 assert.equal(f.sent.length,1);assert.equal(f.dialog.open,true);
 assert.match(f.dialog.textContent,/Waiting for your previous step/);assert.ok(f.button('Exit to'));
});

test('disconnection or failed transport stays visible in the route chooser',()=>{
 for(const disconnect of [f=>{f.window.ws.readyState=3;},f=>{f.window.ws.send=()=>{throw Error('closed');};}]){
  const f=boot();disconnect(f);f.marker.click();f.button('Passage out').click();
  assert.equal(f.sent.length,0);assert.equal(f.dialog.open,true);
  assert.match(f.dialog.textContent,/Reconnect/);assert.match(f.status,/Reconnect/);
 }
});

test('an open chooser refreshes after room changes and old handlers cannot move',()=>{
 const f=boot();f.marker.click();const old=f.button('Passage out');
 f.update(packet({id:'hall',name:'Tankard Hall',kind:'building',passages:interior}));
 assert.equal(f.dialog.getAttribute('aria-label'),'Passages at Tankard Hall');
 assert.ok(f.button('Exit to'));assert.equal(f.button('Passage out'),undefined);
 old.onclick();assert.equal(f.sent.length,0);assert.match(f.dialog.textContent,/location changed/);
});

test('same-room character changes and newly blocked passages invalidate old choices',()=>{
 const f=boot();f.marker.click();const previousCharacter=f.button('Passage out');
 f.update(packet({character:'other'}));previousCharacter.onclick();assert.equal(f.sent.length,0);
 const previousDoor=f.button('Passage out');
 f.update(packet({character:'other',passages:[route('out','Passage out · Sheltered Vale Road','passage','The route is closed.')]}));
 previousDoor.onclick();assert.equal(f.sent.length,0);assert.match(f.dialog.textContent,/route is closed/);
});

test('a changed destination label invalidates an old same-direction action',()=>{
 const f=boot();f.marker.click();const old=f.button('Passage out');
 f.update(packet({passages:[route('out','Passage out · Different Road')]}));
 old.onclick();assert.equal(f.sent.length,0);assert.match(f.dialog.textContent,/passage changed/);
 assert.ok(f.button('Passage out · Different Road'));
});

test('a pointer press cannot activate a passage from a newly arrived room',()=>{
 const f=boot();f.marker.onpointerdown({button:0});
 f.update(packet({id:'hall',kind:'building',passages:[interior[0]]}));
 f.marker.click();assert.equal(f.sent.length,0);assert.match(f.status,/location or passage changed/);
});

test('a pointer press cannot activate a changed destination in the same direction',()=>{
 const f=boot(packet({passages:[exterior[0]]}));f.marker.onpointerdown({button:0});
 f.update(packet({passages:[route('out','Passage out · Different Road')]}));
 f.marker.click();assert.equal(f.sent.length,0);assert.match(f.status,/location or passage changed/);
});

test('reset closes passage choices and removes stale map controls',()=>{
 const f=boot();f.marker.click();const old=f.button('Passage out');
 f.window.ExpanseStreet.reset();f.state.packet=f.state.data=null;
 assert.equal(f.dialog.open,false);assert.equal(f.marker.hidden,true);assert.equal(f.marker.onclick,null);
 assert.equal(f.state.tileTargets.children.length,0);assert.equal(f.state.targetButtons.size,0);
 old.onclick();assert.equal(f.sent.length,0);
 f.update(packet());assert.equal(f.marker.hidden,false);f.marker.click();assert.equal(f.dialog.open,true);
});

test('live menu refresh cooperates with the real window chrome observer',()=>{
 const f=boot();
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/window-controls.js'),'utf8'),f.window,{filename:'web/window-controls.js'});
 f.flushMutations();f.marker.click();f.flushMutations();
 assert.equal(f.dialog.querySelectorAll('.expanse-window-bar').length,1);
 f.update(packet({id:'hall',name:'Hall',kind:'building',passages:interior}));f.flushMutations();
 assert.equal(f.dialog.querySelectorAll('.expanse-window-bar').length,1);
 assert.match(f.dialog.querySelector('.expanse-window-bar').textContent,/Passages at Hall/);
 assert.equal(f.dialog.open,true);assert.equal(f.sent.length,0);
});

test('the optional phone popup receives refreshed children after a room change',()=>{
 const f=boot(),popup=f.document.createElement('div');f.document.body.append(popup);let source=null;
 f.window.PhonePopups={visible:d=>source===d,
  open:d=>{source=d;popup.replaceChildren(...d.childNodes);},
  finish:d=>{d.replaceChildren(...popup.childNodes);source=null;}};
 f.marker.click();assert.match(popup.textContent,/Routes at Dawnwatch Civic Square/);
 f.update(packet({id:'hall',name:'Hall',kind:'building',passages:interior}));
 assert.match(popup.textContent,/Passages at Hall/);assert.ok(!popup.textContent.includes('Passage out'));
 const exit=popup.querySelectorAll('button').find(b=>b.textContent.startsWith('Exit to'));exit.click();
 assert.equal(f.sent[0].command,'go step outside');assert.equal(source,null);
});

test('root and web passage scripts stay identical',()=>{
 assert.equal(fs.readFileSync(path.join(__dirname,'../street-actions.js'),'utf8'),fs.readFileSync(path.join(__dirname,'../web/street-actions.js'),'utf8'));
 assert.equal(fs.readFileSync(path.join(__dirname,'../player-controls.js'),'utf8'),controls);
 assert.equal(fs.readFileSync(path.join(__dirname,'../visual-map.js'),'utf8'),fs.readFileSync(path.join(__dirname,'../web/visual-map.js'),'utf8'));
 assert.equal(fs.readFileSync(path.join(__dirname,'../visual-map.css'),'utf8'),fs.readFileSync(path.join(__dirname,'../web/visual-map.css'),'utf8'));
});
