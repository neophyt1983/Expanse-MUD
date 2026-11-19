/* Real viewport state: rebuilt world geometry must replace cached terrain. */
'use strict';
const assert=require('node:assert/strict'),{test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/travel-viewport.js'),'utf8');
function boot(){const window={};vm.runInNewContext(source,{window});return new window.ExpanseTravelViewport();}
function tile(id,dx,terrain='road'){return {id,dx,dy:0,x:dx,y:0,z:0,terrain,current:id==='here'};}
function packet(revision=1,opening=[tile('here',0),tile('old-roof',3,'building')]){
 return {character:{id:'p'},visual:{center:'here',floor:0,context:{id:'outdoors',kind:'outdoors'},travel_world:'world',geometry_revision:revision,
  tiles:[tile('here',0)],opening_tiles:opening,opening_extent:[3,3],surface_survey:true}};
}
test('a geometry rebuild removes distant old roofs and accepts new real footprints',()=>{
 const v=boot();v.update(packet());let id;
 v.measure(1000,800,40,(_center,_extent,request)=>{id=request;});
 assert.equal(v.receive({request_id:id,center:'here',geometry_revision:1,tiles:[tile('here',0),tile('old-far',8,'building')]}),true);
 assert(v.tiles(tile('here',0)).some(t=>t.id==='old-far'));
 v.update(packet(2,[tile('here',0),tile('new-roof',2,'building')]));
 const ids=v.tiles(tile('here',0)).map(t=>t.id);
 assert(ids.includes('new-roof'));assert(!ids.includes('old-far'));assert(!ids.includes('old-roof'));
 assert.equal(v.receive({request_id:id,center:'here',geometry_revision:1,tiles:[tile('here',0),tile('old-far',8)]}),false);
});
test('a mismatched geometry response cannot overwrite the current floor even with a matching request ID',()=>{
 const v=boot();v.update(packet(4));let id;
 v.measure(1000,800,40,(_center,_extent,request)=>{id=request;});
 assert.equal(v.receive({request_id:id,center:'here',geometry_revision:3,tiles:[tile('here',0),tile('phantom',1)]}),false);
 assert(!v.tiles(tile('here',0)).some(t=>t.id==='phantom'));
 assert.equal(v.receive({request_id:id,center:'here',geometry_revision:4,tiles:[tile('here',0),tile('current',1)]}),true);
});
test('same geometry preserves the outer survey while an authoritative complete local survey removes its missing cell',()=>{
 const v=boot();v.update(packet());let id;
 v.measure(1000,800,40,(_center,_extent,request)=>{id=request;});
 v.receive({request_id:id,center:'here',geometry_revision:1,tiles:[tile('here',0),tile('old-roof',3,'building'),tile('far',8)]});
 v.update(packet(1,[tile('here',0)]));const ids=v.tiles(tile('here',0)).map(t=>t.id);
 assert(!ids.includes('old-roof'));assert(ids.includes('far'));
});
test('unsolicited responses and a different character never inherit previous terrain',()=>{
 const v=boot();v.update(packet());
 assert.equal(v.receive({center:'here',tiles:[tile('here',0)]}),false);
 const next=packet(1,[tile('here',0)]);next.character.id='someone-else';v.update(next);
 assert.equal(v.tiles(tile('here',0)).length,1);
 assert.equal(fs.readFileSync(path.join(__dirname,'../travel-viewport.js'),'utf8'),source);
});
