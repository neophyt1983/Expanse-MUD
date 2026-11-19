/* Player-facing theft wording uses the host's actual permission decision. */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/locks-ui.js'),'utf8');

function boot(permitted=false){
 const {window,document,Option}=createDOM(),sent=[],errors=[];
 Object.assign(window,{Option,ws:{readyState:1,send:body=>sent.push(JSON.parse(body))},
  append:(type,text)=>errors.push({type,text})});
 vm.runInNewContext(source,window,{filename:'web/locks-ui.js'});
 const content=document.createElement('div');document.body.append(content);
 const row={id:'kitchen:pantry',name:'Pantry cabinet',kind:'container',locked:false,permitted,
  contents:[{id:'bread',name:'Bread',count:2,movable:true}],deposit_items:[]};
 const packet={character:{id:'gorimore'},location:{id:'kitchen'},locks:[row]};
 const render=()=>{content.replaceChildren();window.dispatchEvent(new window.CustomEvent('expanse:build-room-content',
  {detail:{packet,content,keyed:node=>node}}));};
 render();return {document,content,sent,errors,row,render,
  button:label=>content.querySelectorAll('button').find(button=>button.textContent===label)};
}

test('private containers say Steal and explain theft before any action is sent',()=>{
 const f=boot(false),all=f.button('Steal contents'),selected=f.button('Steal selected');
 assert.ok(all);assert.ok(selected);assert.equal(f.button('Take contents'),undefined);
 const warning=f.document.getElementById(all.getAttribute('aria-describedby'));
 assert.match(warning.textContent,/without permission is theft/);
 assert.match(warning.textContent,/Witnesses may report/);
 assert.equal(selected.getAttribute('aria-describedby'),warning.id);
 assert.equal(warning.closest('button'),null);assert.equal(f.sent.length,0);
 selected.click();assert.equal(f.sent.length,1);
 assert.equal(f.sent[0].action,'take_item');assert.equal(f.sent[0].quantity,1);
 assert.equal(f.sent[0].actor_id,'gorimore');assert.equal(f.sent[0].room,'kitchen');
 assert.equal(f.sent[0].target,'kitchen:pantry');
});

test('permission refresh changes both theft labels without taking or moving items',()=>{
 const f=boot(false);f.row.permitted=true;f.render();
 assert.ok(f.button('Take contents'));assert.ok(f.button('Take selected'));
 assert.equal(f.button('Steal contents'),undefined);
 assert.equal(f.content.querySelectorAll('.lock-permission-warning').length,0);
 assert.equal(f.sent.length,0);
 f.button('Take contents').click();assert.equal(f.sent[0].action,'take');
});

test('an empty private container cannot send a theft and unknown permission is not invented',()=>{
 const f=boot(false);f.row.contents=[];f.render();
 const all=f.button('Steal contents');assert.equal(all.disabled,true);all.click();
 assert.equal(f.sent.length,0);assert.equal(f.button('Steal selected'),undefined);
 delete f.row.permitted;f.render();assert.ok(f.button('Take contents'));
 assert.equal(f.content.querySelectorAll('.lock-permission-warning').length,0);
});

test('door warning names lock tampering and host text is rendered literally',()=>{
 const f=boot(false);f.row.kind='door';f.row.locked=true;f.row.pickable=true;
 f.row.permission_warning='Owner <b>Arden</b>: picking this lock may be reported as lock tampering.';
 f.render();const pick=f.button('Pick lock');
 const warning=f.document.getElementById(pick.getAttribute('aria-describedby'));
 assert.equal(warning.textContent,f.row.permission_warning);assert.equal(warning.children.length,0);
 assert.equal(f.button('Steal contents'),undefined);assert.equal(f.sent.length,0);
});

test('root and web lock interfaces remain identical',()=>{
 assert.equal(fs.readFileSync(path.join(__dirname,'../locks-ui.js'),'utf8'),source);
});
