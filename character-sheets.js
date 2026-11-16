/* Decoded once per needed anatomy. Every tile preserves its registration point. */
(()=>{'use strict';
const sheets=new Map(), tinted=new Map(), waiting=new Map();
let revision=0;
function clear(){revision++;waiting.clear();sheets.clear();tinted.clear();}
window.addEventListener('expanse:world-assets',clear);
window.addEventListener('expanse:art-selection',clear);
async function source(name){
 const path='assets/sprites/'+name+'.json';
 if(window.expanseEditorWorld&&document.querySelector('#tab-editor.active')){
  const response=await fetch('/api/editor/art/'+encodeURIComponent(window.expanseEditorWorld)+'/'+path);
  return response.ok?response.json():null;
 }
 const asset=await window.ExpanseAssets.get(path);
 return asset?JSON.parse(await asset.blob.text()):null;
}
function load(name){
 if(waiting.has(name))return waiting.get(name);
 const generation=revision;
 const task=source(name).then(async doc=>{
  if(!doc)return null;
  const bitmap=new Image();bitmap.src=doc.png;await bitmap.decode();if(generation!==revision)return null;delete doc.png;
  sheets.set(name,{...doc,bitmap});window.dispatchEvent(new Event('expanse:sprite-ready'));return sheets.get(name);
 }).catch(()=>{waiting.delete(name);return null;});
 waiting.set(name,task);return task;
}
function ready(name){if(!sheets.has(name))load(name);return sheets.get(name);}
function gearName(rig){return 'sprite-gear-'+rig.split(':').slice(1).join('-');}
function gear(c,rig,index){
 if(!Number.isInteger(index)||index<0)return false;
 const plate=ready(gearName(rig));if(!plate||index>=plate.count)return false;
 c.drawImage(plate.bitmap,index%32*32,Math.floor(index/32)*32,32,32,0,0,16,16);return true;
}
function body(c,family,rig,skin){
 if(!family)return false;
 const plate=ready('sprite-bodies');if(!plate)return false;
 const row=plate.families.indexOf(family),col=plate.rigs.indexOf(rig);if(row<0||col<0)return false;
 const key=[family,rig,skin].join('/');let tile=tinted.get(key);
 if(!tile){
  tile=document.createElement('canvas');tile.width=tile.height=32;const ctx=tile.getContext('2d');
  ctx.drawImage(plate.bitmap,col*32,row*32,32,32,0,0,32,32);
  const image=ctx.getImageData(0,0,32,32),px=image.data;
  const rgb=[1,3,5].map(i=>parseInt(skin.slice(i,i+2),16));
  for(let i=0;i<px.length;i+=4){
   // Canvas privacy protections can alter readback channels by a few levels.
   // Match only the three skin-mask colors, so a missed marker cannot stay pink.
   if(Math.abs(px[i+2]-128)>2||px[i+3]<253)continue;
   const shadow=Math.abs(px[i]-160)<=2&&px[i+1]<=2;
   const base=px[i]>=253&&px[i+1]<=2,highlight=px[i]>=253&&Math.abs(px[i+1]-64)<=2;
   if(!shadow&&!base&&!highlight)continue;
   const tint=shadow?-.24:highlight?.22:0;
   rgb.forEach((v,ch)=>{px[i+ch]=Math.round(tint>0?v+(255-v)*tint:v*(1+tint));});
   px[i+3]=255;
  }
  ctx.putImageData(image,0,0);if(tinted.size>=300)tinted.delete(tinted.keys().next().value);tinted.set(key,tile);
 }
 c.drawImage(tile,0,0,16,16);return true;
}
function creature(c,id,x,y,size){
 const plate=ready('sprite-wildlife');if(!plate)return false;
 const i=plate.subjects.indexOf(id);if(i<0)return false;
 c.drawImage(plate.bitmap,i%16*32,Math.floor(i/16)*32,32,32,Math.round(x-size/2),Math.round(y-size/2),size,size);return true;
}
function activity(c,kind,x,y,size){
 if(!kind||kind==='idle')return;
 const plate=ready('sprite-activities');if(!plate)return;
 const index=plate.subjects.indexOf(kind);if(index<0)return;
 const side=Math.max(5,Math.round(size*.45));const xx=Math.round(x+size*.50-side),yy=Math.round(y+size*.50-side);
 c.save();c.imageSmoothingEnabled=false;c.fillStyle='#1a282ecc';c.fillRect(xx,yy,side,side);
 c.drawImage(plate.bitmap,index*16,0,16,16,xx,yy,side,side);c.restore();
}
function prop(c,kind,x,y,side){
 const plate=ready('sprite-activities');const i=plate?.subjects.indexOf(kind)??-1;
 if(i>=0)c.drawImage(plate.bitmap,i*16,0,16,16,x,y,side,side);
}
window.ExpanseSpriteSheets={body,gear,creature,activity,prop,load,gearName};
})();
