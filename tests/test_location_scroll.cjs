/* Scroll-intent regression for the real room-panel renderer. Geometry here is
 * explicit test data; browser clipping is checked by the Qt layout probe. */
'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');
const source=fs.readFileSync(path.join(__dirname,'../web/workspace.js'),'utf8');

function boot(){
 const {window,document,Event,Option}=createDOM(),resize=[];
 const make=(id,parent=document.body)=>{const n=document.createElement('div');n.id=id;parent.append(n);return n;};
 const game=make('tab-game');make('log',game);make('input-form',game);
 const grid=make('ed-grid');for(let i=0;i<4;i++)make('col-'+i,grid);
 make('designer-map-panel');make('map-center');
 class ResizeObserver{constructor(callback){this.callback=callback;}observe(target){resize.push({target,callback:this.callback});}}
 Object.assign(window,{console,Option,ResizeObserver,CSS:{escape:s=>s.replace(/[\\"]/g,'\\$&')},
  selectGame:async()=>{},refreshDesignerMap:async()=>{},setStatus(){}});
 vm.runInNewContext(source,window,{filename:'web/workspace.js'});
 const panel=document.getElementById('location-panel'),content=document.getElementById('location-content');
 panel.clientHeight=200;panel.scrollHeight=1000;let top=0,nextHeight=1000;
 Object.defineProperty(panel,'scrollTop',{get:()=>top,set:value=>{top=Math.max(0,Math.min(value,Math.max(0,panel.scrollHeight-panel.clientHeight)));}});
 const replace=content.replaceChildren.bind(content);
 content.replaceChildren=(...nodes)=>{replace(...nodes);panel.scrollHeight=nextHeight;};
 const packet={character:{id:'p',name:'Player',hp:10,max_hp:10,gold:0,inventory:[]},
  location:{id:'square',name:'Square',description:'The town square.',players:[],npcs:[],items:[]}};
 return {panel,content,document,
  render(height=nextHeight){nextHeight=height;window.renderRoomPanel(packet);},
  scroll(value){panel.scrollTop=value;panel.dispatchEvent(new Event('scroll'));},
  resize(height){panel.clientHeight=height;for(const observer of resize)if(observer.target===panel)observer.callback();},
 };
}

test('the end of Location & Inventory stays visible when a refresh adds lines',()=>{
 const f=boot();f.render();f.scroll(800);f.render(1100);
 assert.equal(f.panel.scrollTop,900);
 f.render(900);assert.equal(f.panel.scrollTop,700,'Removing content also keeps the end visible');
});

test('reading an earlier item retains the existing anchor instead of jumping to the end',()=>{
 const f=boot();f.render();f.scroll(400);f.render(1100);
 assert.equal(f.panel.scrollTop,400);
 f.resize(120);assert.equal(f.panel.scrollTop,400);
});

test('a shorter or reflowed dock retains the bottom after the player reached it',()=>{
 const f=boot();f.render();f.scroll(800);f.resize(120);
 assert.equal(f.panel.scrollTop,880);
 f.resize(400);assert.equal(f.panel.scrollTop,600);
 f.scroll(200);f.resize(160);assert.equal(f.panel.scrollTop,200);
});

test('an initial or unscrolled panel starts at the top as content grows',()=>{
 const f=boot();f.render();f.render(1400);f.resize(100);
 assert.equal(f.panel.scrollTop,0);
});

test('a hidden panel does not erase the bottom intent during a layout change',()=>{
 const f=boot();f.render();f.scroll(800);f.resize(0);f.scroll(0);f.render(1200);f.resize(150);
 assert.equal(f.panel.scrollTop,1050);
});
