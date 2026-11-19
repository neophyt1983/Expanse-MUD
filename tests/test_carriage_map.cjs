/* Exercise actual map placement with canvas/DOM doubles. No pixel snapshots. */
'use strict';
const assert=require('node:assert/strict'),{test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createDOM}=require('./support/menu-dom.cjs');

function boot(){
 const {window,document,Node,Option,Event,CustomEvent,ResizeObserver}=createDOM();
 const frames=new Map();let next=0,placements=[];
 const canvas=new Proxy({measureText:text=>({width:String(text).length*6}),createRadialGradient:()=>({addColorStop(){}})},
  {get:(obj,key)=>key in obj?obj[key]:()=>{},set:(obj,key,value)=>{obj[key]=value;return true;}});
 Node.prototype.getContext=()=>canvas;
 const host=document.createElement('div');host.id='player-visual-map';document.body.append(host);
 Object.assign(window,{console,Option,Event,CustomEvent,ResizeObserver,performance:{now:()=>0},
  requestAnimationFrame:callback=>{const id=++next;frames.set(id,callback);return id;},cancelAnimationFrame:id=>frames.delete(id),
  ExpanseMapEffects:{context(){},begin(state,points){placements=points;return {};},ground(){},front(){},actor(){return true;}}});
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/visual-map.js'),'utf8'),window,{filename:'web/visual-map.js'});
 return {render(actors,nearby=[]){
  window.ExpanseMap.render({character:{id:'self'},exits:[],visual:{version:1,center:'stand',floor:0,
   context:{id:'outdoors',kind:'outdoors',label:'Town'},
   tiles:[{id:'stand',name:'Carriage Stand',x:0,y:0,z:0,current:true,visited:true,terrain:'road'},
          {id:'lane',name:'Lane',x:1,y:0,z:0,visited:true,terrain:'road'}],actors,nearby_actors:nearby,links:[],exits:[]}});
  for(const [id,callback] of [...frames]){frames.delete(id);callback();}
  return placements.map(({actor,x,y,size})=>({id:actor.id,subject:actor.subject,room:actor.room,x,y,size}));
 }};
}
const person=(id='self',room='stand')=>({id,name:id,kind:id==='self'?'self':'npc',room,appearance:{}});
const carriage=()=>({...person('coach'),subject:'carriage',stationary:true});
const point=rows=>rows.find(row=>row.subject==='carriage');

test('a parked carriage does not shift or shrink when the crowd changes',()=>{
 const map=boot(),initial=point(map.render([person(),carriage()]));
 for(const count of [1,3,8,20,2,0]){
  const crowd=Array.from({length:count},(_,i)=>person('walker-'+i));
  const points=map.render([...crowd,carriage(),person()]);
  assert.deepEqual(point(points),initial,'Carriage changed with '+count+' passersby');
  for(const actor of points.filter(p=>p.id!=='coach')){
   const overlap=Math.abs(actor.x-initial.x)<(actor.size+initial.size)/2-0.001&&
    Math.abs(actor.y-initial.y)<(actor.size+initial.size)/2-0.001;
   assert.equal(overlap,false,'A passerby or player covers the parked carriage');
  }
 }
});

test('an anonymized nearby carriage retains its anchor without revealing identity',()=>{
 const map=boot(),coach={subject:'carriage',stationary:true,room:'lane',kind:'npc',appearance:{}};
 const initial=point(map.render([person()],[coach]));
 const crowd=Array.from({length:12},()=>({room:'lane',kind:'npc',appearance:{}}));
 assert.deepEqual(point(map.render([person()],[...crowd,coach])),initial);
 assert.equal(initial.id,undefined);
});

test('an ordinary movable carriage is not anchored by its appearance alone',()=>{
 const map=boot(),coach={...carriage(),stationary:false};
 const before=point(map.render([person(),coach]));
 const after=point(map.render([person(),...Array.from({length:15},(_,i)=>person('walker-'+i)),coach]));
 assert.notDeepEqual({x:before.x,y:before.y,size:before.size},{x:after.x,y:after.y,size:after.size});
});
