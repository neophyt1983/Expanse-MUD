/* Original Expanse pixel-art document format. Data only: no URLs or executable art. */
(function(root){
'use strict';
const sizes=Object.freeze({tile:24,character:16,equipment:16});
const rigs=Array.from(['short','average','tall'],s=>['slim','average','broad'].map(b=>'humanoid:'+s+':'+b)).flat();
const slots=['body','armor','head','hands','legs','feet','weapon','offhand','charm','appearance_tunic','appearance_cloak','appearance_hat'];
const color=/^#[0-9a-f]{6}([0-9a-f]{2})?$/i;
function text(value,max){if(typeof value!=='string'||value.length>max)throw Error('Invalid text field');return value;}
function validate(d){
 if(!d||d.version!==1||!Object.hasOwn(sizes,d.kind))throw Error('Unsupported art document');
 const size=d.kind!=='tile'&&d.width===32?32:sizes[d.kind];if(d.width!==size||d.height!==size)throw Error(d.kind+' requires '+size+' × '+size+' pixels');
 text(d.name,80);text(d.author,120);text(d.license,200);
 if(!Array.isArray(d.layers)||d.layers.length<1||d.layers.length>8)throw Error('Use 1–8 layers');
 d.layers.forEach(l=>{text(l.name,80);if(typeof l.visible!=='boolean'||!Array.isArray(l.pixels)||l.pixels.length!==size*size)throw Error('Invalid layer dimensions');l.pixels.forEach(p=>{if(p!==null&&(typeof p!=='string'||!color.test(p)))throw Error('Pixels must be transparent or hex colors');});});
 const registration={};
 if(d.pose!==undefined){if(d.kind!=='character'||!['unarmed','blade','dagger','haft','spear','staff','bow','shield','dual','instrument','natural'].includes(d.pose))throw Error('Invalid fighting pose');registration.pose=d.pose;}
 if(d.rig!==undefined){if(!rigs.includes(d.rig)||d.kind==='tile')throw Error('Invalid anatomy registration');registration.rig=d.rig;}if(d.slot!==undefined){if(d.kind!=='equipment'||!slots.includes(d.slot))throw Error('Invalid equipment slot');registration.slot=d.slot;}
 return {...registration,version:1,kind:d.kind,width:size,height:size,name:d.name,author:d.author,license:d.license,layers:d.layers.map(l=>({name:l.name,visible:l.visible,pixels:[...l.pixels]}))};
}
function create(kind='tile'){if(!Object.hasOwn(sizes,kind))throw Error('Unknown asset kind');const n=sizes[kind];return validate({version:1,kind,width:n,height:n,name:'Untitled',author:'',license:'',layers:[{name:'Base',visible:true,pixels:Array(n*n).fill(null)}]});}
function parse(s){if(typeof s!=='string'||s.length>200000)throw Error('Art file exceeds 200 KB');return validate(JSON.parse(s));}
function paint(d,layer,x,y,value){if(!Number.isInteger(x)||!Number.isInteger(y)||x<0||y<0||x>=d.width||y>=d.height)return false;if(!d.layers[layer])throw Error('Missing layer');if(value!==null&&!color.test(value))throw Error('Invalid color');d.layers[layer].pixels[y*d.width+x]=value;return true;}
const api={sizes,rigs,slots,create,parse,validate,paint};root.ExpansePixelArt=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
