/* Read-only Skills & Knowledge behavior; real layout has a separate Qt probe. */
'use strict';
const assert=require('node:assert/strict'),{test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/skills-ui.js'),'utf8');
function boot(){
 const {window,document}=createDOM(),sent=[];
 window.ws={readyState:1,send:value=>sent.push(value)};
 vm.runInNewContext(source,window);
 const packet={visual:{travel_world:'realm'},character:{id:'p',skills:{scale:100,
  skills:[{id:'farming',name:'Farming',level:25,proficiency:'Apprentice',practice:22.5,next_practice:91},
          {id:'reading',name:'Reading',level:100,proficiency:'Master',practice:0,next_practice:null}],
  knowledge:{recipes:[{id:'bread',name:'Learned bread'}],techniques:[],books:[]}}}};
 const render=()=>window.dispatchEvent(new window.CustomEvent('expanse:build-room-content',{detail:{packet}}));
 render();window.ExpanseSkills.open();return {window,document,packet,render,sent,dialog:document.getElementById('player-skills')};
}
test('levels, proficiency, partial practice and only supplied learned knowledge are readable',()=>{
 const f=boot();assert.match(f.dialog.textContent,/Farming25\/100 · Apprentice/);
 assert.match(f.dialog.textContent,/22.5 \/ 91/);assert.match(f.dialog.textContent,/Known recipes \(1\)/);
 assert.match(f.dialog.textContent,/Learned bread/);assert.match(f.dialog.textContent,/Maximum skill level/);
 assert.equal(f.dialog.querySelectorAll('progress').length,1);assert.equal(f.sent.length,0);
});
test('an authoritative update refreshes the open view without sending a practice command',()=>{
 const f=boot();f.packet.character.skills.skills[0].practice=31;f.render();
 assert.match(f.dialog.textContent,/31 \/ 91/);assert.equal(f.sent.length,0);
 assert.equal(Number(f.dialog.querySelector('progress').value),31);
});
test('world and character switches close the old view and remove its private knowledge',()=>{
 const f=boot();f.packet.character={id:'other',skills:{skills:[],knowledge:{recipes:[]}}};f.render();
 assert.equal(f.dialog.open,false);f.window.ExpanseSkills.open();assert.doesNotMatch(f.dialog.textContent,/Learned bread/);
 f.window.ExpanseSkills.reset();assert.equal(f.dialog.open,false);assert.equal(f.sent.length,0);
});
test('labels are rendered as text, scripts match, and the ordinary Close button works',()=>{
 const f=boot();f.packet.character.skills.knowledge.recipes[0].name='<img src=x>';f.render();
 assert.equal(f.dialog.querySelector('img'),null);assert.match(f.dialog.textContent,/<img src=x>/);
 f.dialog.querySelector('button').click();assert.equal(f.dialog.open,false);
 assert.equal(fs.readFileSync(path.join(__dirname,'../skills-ui.js'),'utf8'),source);
});
