/* Creator authoring keeps theft plans staged and exact-target based. */
'use strict';
const assert=require('node:assert/strict'),{test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/locks-editor.js'),'utf8');

function boot(){
 const {window,document,Option}=createDOM(),saved=[],posted=[];
 Object.assign(window,{Option,structuredClone,LIVING_DEFAULTS:{room:{},npc:{},class:{},item:{}},
  ed:{type:'npc',entryId:'burglar',gameSlug:'example',selectionVersion:7,entriesCache:{
   room:[{id:'market',name:'Market'}],npc:[{id:'merchant',name:'Merchant'}],
   item:[{id:'bread',name:'Bread'}],group:[]}},
  buildFieldWidget:()=>document.createElement('textarea'),renderMultiSelect:()=>document.createElement('select'),
  saveField:(key,value)=>saved.push({key,value}),gpath:name=>'/creator/example/'+name,
  apiPost:async(url,body)=>{posted.push({url,body:JSON.parse(JSON.stringify(body))});return {};}});
 vm.runInNewContext(source,window,{filename:'web/locks-editor.js'});
 return {window,document,saved,posted,render(key,value){const box=window.buildFieldWidget(key,'object',value,'burglar');document.body.append(box);return box;}};
}
const plan=()=>({enabled:true,targets:[{room:'market',kind:'actor',npc:'merchant',item:'bread',quantity:6}]});
const button=(box,label)=>box.querySelectorAll('button').find(node=>node.textContent===label);

test('Burgling, Observation and target difficulty expose bounded numeric authoring',()=>{
 const f=boot();
 for(const key of ['burglary','observation','theft_difficulty']){
  const input=f.render(key,73);assert.equal(input.type,'number');
  assert.equal(Number(input.min),0);assert.equal(Number(input.max),100);assert.equal(Number(input.step),1);
  input.value='81';input.onchange();assert.deepEqual(f.saved.at(-1),{key,value:81});
 }
 assert.deepEqual(JSON.parse(JSON.stringify(f.window.LIVING_DEFAULTS.npc.burglary_plan)),{});
 assert.equal(f.window.LIVING_DEFAULTS.class.observation,0);
 assert.equal(f.posted.length,0);
});

test('an explicit NPC plan stays local until its staged save is requested',async()=>{
 const f=boot(),original=plan(),box=f.render('burglary_plan',original);
 const quantity=box.querySelector('[data-burglary-field="quantity"]');quantity.value='4';quantity.oninput();
 assert.equal(original.targets[0].quantity,6);assert.equal(f.posted.length,0);
 assert.match(box.textContent,/one configured local target per game day/);
 assert.match(box.textContent,/Failed attempts also use/);
 await button(box,'Stage Burgling plan').onclick();
 assert.equal(f.posted.length,1);assert.equal(f.posted[0].url,'/creator/example/setfield');
 assert.deepEqual(f.posted[0].body,{type:'npc',id:'burglar',field:'burglary_plan',
  value:{enabled:true,targets:[{room:'market',kind:'actor',npc:'merchant',item:'bread',quantity:4}]}});
 assert.match(box.textContent,/Staged\. Validate, Save and Apply/);
});

test('changing target type removes the prior selector instead of leaving ambiguous names',async()=>{
 const f=boot(),box=f.render('burglary_plan',plan());
 const type=box.querySelector('[data-burglary-field="kind"]');type.value='entity';type.onchange();
 const exact=box.querySelector('[data-burglary-field="entity"]');exact.value='connected-player-42';exact.oninput();
 await button(box,'Stage Burgling plan').onclick();
 assert.deepEqual(f.posted[0].body.value.targets,[{room:'market',kind:'actor',entity:'connected-player-42',item:'bread',quantity:6}]);
 assert.match(exact.getAttribute('aria-label'),/Exact character ID/);
});

test('stale Creator selections cannot stage a plan onto another NPC or world',async()=>{
 for(const key of ['entryId','gameSlug','selectionVersion']){
  const f=boot(),box=f.render('burglary_plan',plan());f.window.ed[key]='changed';
  await button(box,'Stage Burgling plan').onclick();
  assert.equal(f.posted.length,0);assert.match(box.textContent,/Selection changed/);
 }
});

test('root and web authoring scripts remain identical',()=>{
 assert.equal(fs.readFileSync(path.join(__dirname,'../locks-editor.js'),'utf8'),source);
});
