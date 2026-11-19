/* Personal custody UI uses explicit host state; browser time and missing data
 * never decide a verdict, sentence, or release. */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/workspace.js'),'utf8');
const pending=()=>({id:'case-1',status:'awaiting_hearing',active:true,title:'In custody — awaiting hearing',
 accusation:'theft',reason:'A witnessed theft was reported at Dawnwatch Civic Square involving a locked cabinet.',
 witness_count:2,remaining_minutes:2,next_event:'hearing',deadline_minute:110,custody_place:'Holding room',
 release_place:'Dawnwatch Civic Square',allowed_facilities:['Holding room'],fine_paid:null,
 instructions:['No verdict or fine has been decided. The hearing runs automatically as game time advances.'],
 outcome:null,can_wait:true,wait_command:'wait 2'});
const sentenced=()=>({...pending(),status:'sentenced',title:'In custody — sentence',remaining_minutes:10,
 next_event:'release',deadline_minute:120,custody_place:'Dawnwatch Police Station Jail',fine_paid:5,
 allowed_facilities:['Dawnwatch Police Station Jail','Jail washroom'],
 instructions:['Release is automatic when the sentence ends in game time.'],wait_command:'wait 10'});
const released=()=>({...sentenced(),status:'released',active:false,title:'Released from custody',remaining_minutes:null,
 next_event:null,deadline_minute:null,instructions:['You may travel normally.'],
 outcome:'Your sentence is complete. You were released at Dawnwatch Civic Square.',can_wait:false,wait_command:null});

function boot({map=true}={}){
 const {window,document,Event,CustomEvent,Option}=createDOM(),sent=[],notices=[],frames=[],revealed=[];
 const make=(id,parent=document.body)=>{const n=document.createElement('div');n.id=id;parent.append(n);return n;};
 const game=make('tab-game');make('log',game);make('input-form',game);
 const grid=make('ed-grid');for(let i=0;i<4;i++)make('col-'+i,grid);
 make('designer-map-panel');make('map-center');
 function addMap(){const host=make('player-visual-map',game),header=make('map-heading',host);header.className='atlas-position-header';return header;}
 if(map)addMap();
 Object.assign(window,{console,Option,CSS:{escape:s=>s.replace(/[\\"]/g,'\\$&')},
  selectGame:async()=>{},refreshDesignerMap:async()=>{},setStatus(){},
  ws:{readyState:1,send:body=>sent.push(JSON.parse(body))},WebSocket:{OPEN:1},append:(type,text)=>notices.push({type,text}),
  requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},ExpansePanels:{reveal:id=>revealed.push(id)},
  ExpansePlayerControls:{stopWalking(){}}});
 vm.runInNewContext(source,window,{filename:'web/workspace.js'});
 return {window,document,Event,sent,notices,revealed,
  get notice(){return document.getElementById('player-custody-notice');},
  get details(){return document.getElementById('custody-details');},
  render(custody,{character='player',world='world-one',npcs=[]}={}){
   const packet={character:{id:character,name:'Player',hp:10,max_hp:10,gold:20,inventory:[]},
    location:{id:'holding',name:'Holding room',description:'A waiting area.',players:[],npcs,items:[]},
    visual:{travel_world:world},custody};window.renderRoomPanel(packet);return packet;
  },
  addMapAfterEvent(){window.dispatchEvent(new CustomEvent('expanse:player-map',{detail:{}}));addMap();for(const fn of frames.splice(0))fn();},
  button(label,root=this.notice){return root.querySelectorAll('button').find(b=>b.textContent===label);},
 };
}

test('awaiting hearing prominently states an accusation without inferring guilt',()=>{
 const f=boot();f.render(pending());
 assert.equal(f.notice.hidden,false);assert.equal(f.notice.parentElement.className,'atlas-position-header');
 assert.match(f.notice.textContent,/awaiting hearing/);assert.match(f.notice.textContent,/Accusation: theft/);
 assert.match(f.notice.textContent,/Hearing in 2 game minutes/);assert.match(f.notice.textContent,/No verdict or fine/);
 assert.match(f.details.textContent,/locked cabinet/);assert.match(f.details.textContent,/Allowed facilities: Holding room/);
 assert.equal(f.document.getElementById('player-custody-badge').parentElement.id,'character-strip');
 assert.equal(f.button('Dismiss notice'),undefined);assert.equal(f.sent.length,0);
 f.button('Custody details').click();assert.deepEqual(f.revealed,['location']);assert.equal(f.document.activeElement,f.details);
});

test('only host updates change the sentence countdown and ordinary NPC updates keep the notice',()=>{
 const f=boot();f.render(sentenced());const title=f.notice.firstChild;
 f.render(sentenced(),{npcs:[{id:'npc',name:'A passing guard',description:'The guard talks.',marker:'G'}]});
 assert.equal(f.notice.firstChild,title,'Unrelated NPC changes must not rebuild the live notice');
 assert.match(f.notice.textContent,/Automatic release in 10 game minutes/);
 assert.match(f.details.textContent,/Fine paid: 5 gold/);assert.match(f.details.textContent,/Jail washroom/);
 f.render({...sentenced(),remaining_minutes:9,wait_command:'wait 9'});
 assert.match(f.notice.textContent,/Automatic release in 9 game minutes/);assert.equal(f.sent.length,0);
 f.render({...sentenced(),remaining_minutes:0,wait_command:null,can_wait:false});
 assert.match(f.notice.textContent,/Automatic release is due; awaiting the host update/);
 assert.ok(!f.notice.textContent.includes('Released from custody'));
});

test('explicit outcomes remain outside chatter until dismissed and dismissal is case-and-owner scoped',()=>{
 const f=boot();f.render(released());assert.match(f.notice.textContent,/Your sentence is complete/);
 f.render(released());assert.equal(f.notice.hidden,false);
 f.button('Dismiss notice').click();assert.equal(f.notice.hidden,true);
 assert.equal(f.document.getElementById('player-custody-badge'),null);
 f.render(released());assert.equal(f.notice.hidden,true);assert.match(f.details.textContent,/Your sentence is complete/);
 f.render({...released(),id:'case-2'});assert.equal(f.notice.hidden,false);
 f.render(released(),{character:'other-player'});assert.equal(f.notice.hidden,false);
 f.render(released(),{world:'other-world'});assert.equal(f.notice.hidden,false);
});

test('missing or unsupported custody state never fabricates a release',()=>{
 const f=boot();f.render(sentenced());
 for(const value of [null,undefined,{...released(),status:'unknown'}]){
  f.render(value);assert.equal(f.notice.hidden,true);assert.equal(f.details,null);
  assert.ok(!f.notice.textContent.includes('released'));
 }
});

test('only an explicit valid host-approved solo wait is offered and stale controls cannot send',()=>{
 const f=boot();f.render(sentenced());const old=f.button('Wait 10 game minutes');
 assert.ok(old);assert.equal(f.sent.length,0);old.click();assert.equal(f.sent[0].command,'wait 10');
 f.render(released());old.onclick();assert.equal(f.sent.length,1);
 f.render({...sentenced(),can_wait:false});assert.equal(f.button('Wait 10 game minutes'),undefined);
 f.render({...sentenced(),wait_command:'teleport somewhere'});assert.equal(f.notice.querySelectorAll('button').length,1);
 f.render(pending());const priorCharacter=f.button('Wait 2 game minutes');
 f.render(pending(),{character:'other-player'});priorCharacter.onclick();assert.equal(f.sent.length,1);
});

test('reset removes private case details and delayed map construction can mount a fresh notice',()=>{
 const f=boot({map:false});f.render(pending());f.addMapAfterEvent();assert.equal(f.notice.hidden,false);
 const stale=f.button('Wait 2 game minutes');f.window.ExpanseCustody.reset();
 assert.equal(f.notice.hidden,true);assert.equal(f.notice.textContent,'');assert.equal(f.details,null);
 stale.onclick();assert.equal(f.sent.length,0);f.render(pending());assert.equal(f.notice.hidden,false);
});
