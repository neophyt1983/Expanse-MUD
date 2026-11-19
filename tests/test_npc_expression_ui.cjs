/* The real Talk and Nearby renderers show a mixture, never infer it from prose. */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const read=name=>fs.readFileSync(path.join(__dirname,'..',name),'utf8');
const mix=()=>({summary:'sad, angry, anxious, hopeful',emotions:[
 {id:'sad',label:'Sad',symbol:'😢',intensity:52,causes:['Recent experience']},
 {id:'angry',label:'Angry',symbol:'😠',intensity:60,causes:['Recent experience']},
 {id:'anxious',label:'Anxious',symbol:'😟',intensity:65,causes:['Reporting an experienced event to an officer','Past authority experiences']},
 {id:'hopeful',label:'Hopeful',symbol:'🌤',intensity:40,causes:['Seeking help from an officer']},
]});

function boot(){
 const {window,document,Option}=createDOM(),sent=[];
 const make=(id,parent=document.body)=>{const e=document.createElement('div');e.id=id;parent.append(e);return e;};
 const game=make('tab-game');make('log',game);make('input-form',game);make('session-actions',game);
 const grid=make('ed-grid');for(let i=0;i<4;i++)make('col-'+i,grid);make('designer-map-panel');make('map-center');
 Object.assign(window,{console,Option,CSS:{escape:x=>x},selectGame:async()=>{},refreshDesignerMap:async()=>{},setStatus(){},
  ws:{readyState:1,send:body=>sent.push(JSON.parse(body))},append(){},requestAnimationFrame(){},
  ExpanseResidentWatch:{open(){}},ExpansePlayWindows:{open(){}}});
 vm.runInNewContext(read('web/workspace.js'),window,{filename:'workspace.js'});
 vm.runInNewContext(read('web/society-ui.js'),window,{filename:'society-ui.js'});
 function packet(expression=mix(),present=true){return {
  character:{id:'player',name:'Player',hp:20,max_hp:20,gold:5,inventory:[]},
  location:{id:'square',name:'Square',description:'A square.',players:[],items:[],
   npcs:present?[{id:'mira',name:'Mira',description:'A resident.'}]:[]},
  social:{emotions:{happy:'🙂',serious:'😐'},npcs:present?[{id:'mira',name:'Mira',awake:true,adult:true,
   trust:10,needs:'',likes:'',quests:[],commerce:{},expression}]:[]},
 };}
 return {window,document,sent,packet,render(expression,present){window.renderRoomPanel(packet(expression,present));},
  get expression(){return document.getElementById('npc-emotion-state');}};
}

test('Talk shows all simultaneous emotions and the server supplied causes',()=>{
 const f=boot();f.render();f.window.openNpcSocial('mira');
 assert.equal(f.expression.hidden,false);
 assert.deepEqual(f.expression.querySelectorAll('li').map(row=>row.firstChild.textContent),['😢 Sad','😠 Angry','😟 Anxious','🌤 Hopeful']);
 assert.match(f.expression.textContent,/Past authority experiences/);
 assert.match(f.expression.textContent,/Seeking help from an officer/);
 assert.deepEqual(f.sent,[{command:'social begin mira'}]);
 assert.match(f.document.querySelector('.npc-expression').textContent,/sad, angry, anxious, hopeful/);
});

test('updates replace an expression and a departed NPC leaves no stale emotional profile',()=>{
 const f=boot();f.render();f.window.openNpcSocial('mira');
 const fresh={summary:'relieved',emotions:[{id:'relieved',label:'Relieved',symbol:'😮‍💨',causes:['Recent experience']}]};
 f.render(fresh);assert.equal(f.expression.querySelectorAll('li').length,1);assert.match(f.expression.textContent,/Relieved/);
 assert.ok(!f.expression.textContent.includes('Angry'));
 f.render(undefined,false);assert.equal(f.expression.hidden,true);assert.equal(f.expression.textContent,'');
 assert.equal(f.document.querySelector('.npc-expression'),null);
});

test('legacy packets and dramatic prose do not fabricate emotions',()=>{
 const f=boot(),p=f.packet(null);p.location.npcs[0].description='Mira shouts ALERT! Very angry-looking text.';
 f.window.renderRoomPanel(p);f.window.openNpcSocial('mira');
 assert.equal(f.expression.hidden,true);assert.equal(f.document.querySelector('.npc-expression'),null);
});

test('expression labels and causes render as text without HTML and remain bounded',()=>{
 const f=boot(),state=mix();state.emotions[0].label='<img src=x onerror=alert(1)>';
 state.emotions[0].causes=['<b>Only text</b>'];
 for(let i=0;i<30;i++)state.emotions.push({label:'Extra '+i,causes:['Known reason']});
 f.render(state);f.window.openNpcSocial('mira');
 assert.equal(f.expression.querySelectorAll('li').length,16);assert.match(f.expression.textContent,/<img src=x/);
 assert.match(f.expression.textContent,/<b>Only text<\/b>/);assert.equal(f.expression.querySelector('img'),null);assert.equal(f.expression.querySelector('b'),null);
});

test('both map entrypoints retain complete accessible expression descriptions',()=>{
 const root=read('visual-map.js'),web=read('web/visual-map.js');assert.equal(root,web);
 assert.match(web,/msg\.emotion_summary/);assert.match(web,/setAttribute\('aria-label',accessible\)/);
});
