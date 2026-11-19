/* Expanse field atlas. Original code-drawn pixel tiles; no external artwork.
   The server's room graph is the only source of routes. Clicking inspects,
   never teleports. Commands remain in the existing text client. */
(()=>{
 'use strict';
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
 const views=new Map(), cache=new Map();
 // DOM client coordinates include CSS/device zoom; canvas geometry uses layout pixels.
 function pointerPoint(canvas,event){const rect=canvas.getBoundingClientRect();return {
  x:(event.clientX-rect.left)*(canvas.clientWidth/Math.max(1,rect.width)),
  y:(event.clientY-rect.top)*(canvas.clientHeight/Math.max(1,rect.height))
 };}
 const artCache=new Map(),artDocuments=new Map();
 function loadPixelAssets(assets){for(const [id,art]of Object.entries(assets||{}).slice(0,256)){if(art?.id!==id)continue;if(artDocuments.size>=256)artDocuments.delete(artDocuments.keys().next().value);artDocuments.set(id,art);}}
 function customArt(art){
  if(art?.id&&!art.layers)art=artDocuments.get(art.id);
  if(!art||!art.id||!Array.isArray(art.layers)||!((art.kind==='tile'&&art.width===24&&art.height===24)||(['character','equipment'].includes(art.kind)&&[16,32].includes(art.width)&&art.height===art.width)))return null;
  if(artCache.has(art.id))return artCache.get(art.id);
  const canvas=make('canvas');canvas.width=art.width;canvas.height=art.height;const c=canvas.getContext('2d');
  if(art.layers.length>8)return null;
  for(const layer of art.layers){if(!Array.isArray(layer.pixels)||layer.pixels.length!==art.width*art.height)return null;if(layer.visible)for(let i=0;i<layer.pixels.length;i++){const p=layer.pixels[i];if(p===null)continue;if(typeof p!=='string'||!/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(p))return null;c.fillStyle=p;c.fillRect(i%art.width,Math.floor(i/art.width),1,1);}}
  if(artCache.size>=256)artCache.delete(artCache.keys().next().value);artCache.set(art.id,canvas);return canvas;
 }

 const hash=s=>{let n=2166136261;for(const c of String(s||''))n=Math.imul(n^c.charCodeAt(0),16777619);return n>>>0;};
 let terrainSheet=null,terrainLoading=null,terrainGeneration=0,terrainAttempts=0,terrainRetry=null;
 const neutralTile=make('canvas');neutralTile.width=neutralTile.height=24;
 const neutralContext=neutralTile.getContext('2d');neutralContext.fillStyle='#576264';neutralContext.fillRect(0,0,24,24);
 function loadTerrain(){
  if(terrainSheet||terrainLoading||terrainRetry||terrainAttempts>=3||!window.ExpanseAssets)return;
  const gen=terrainGeneration;
  const task=(async()=>{
   const index=await window.ExpanseAssets.get('assets/terrain/index.json');if(!index)return;
   let doc;try{doc=JSON.parse(await index.blob.text());}finally{index.release?.();}
   if(gen!==terrainGeneration)return;
   if(!Array.isArray(doc.keys)||!Array.isArray(doc.variants)||doc.size!==24||!Number.isInteger(doc.seeds)||doc.seeds<1||doc.seeds>64)return;
   const asset=await window.ExpanseAssets.get(doc.file);if(!asset)return;
   const image=new Image();try{image.src=asset.url;await image.decode();}finally{asset.release?.();}
   if(gen!==terrainGeneration)return;
   terrainSheet={doc,image};cache.clear();for(const view of views.values())view.schedule();
   window.dispatchEvent(new Event('expanse:sprite-ready'));
  })().catch(()=>{}).finally(()=>{
   if(gen!==terrainGeneration)return;
   if(terrainLoading===task)terrainLoading=null;
   if(!terrainSheet&&++terrainAttempts<3)terrainRetry=setTimeout(()=>{
    terrainRetry=null;if(gen===terrainGeneration)loadTerrain();
   },terrainAttempts===1?1000:3000);
  });
  terrainLoading=task;
 }
 window.addEventListener('expanse:world-assets',()=>{terrainGeneration++;clearTimeout(terrainRetry);terrainRetry=null;terrainAttempts=0;terrainLoading=null;terrainSheet=null;cache.clear();artCache.clear();artDocuments.clear();loadTerrain();});
 function tile(terrain,seed){return terrainTile(terrain,seed,null);}
 function terrainTile(terrain,seed,route){
  if(!terrainSheet){loadTerrain();return neutralTile;}
  const {doc,image}=terrainSheet,kind=doc.aliases?.[terrain]||terrain;
  let row=doc.keys.indexOf(kind);if(row<0)row=doc.keys.indexOf('unknown');if(row<0)return neutralTile;
  const variant=Math.max(0,doc.variants.indexOf(route?route.kind+':'+route.axis:''));
  const column=variant*doc.seeds+(seed>>>0)%doc.seeds,key=row+':'+column;
  if(!cache.has(key)){
   const canvas=make('canvas');canvas.width=canvas.height=24;
   canvas.getContext('2d').drawImage(image,column*24,row*24,24,24,0,0,24,24);cache.set(key,canvas);
  }
  return cache.get(key);
 }
 // Only already-disclosed, unambiguous adjacent cells can establish a bank.
 // No world lookup, missing-cell inference, or remote sailing-link inference.
 function shoreEdges(tiles){
  const cells=new Map(),edges=new Map();
  const key=t=>[t.x,t.y,t.z??0].join(':');
  for(const t of tiles){const k=key(t);cells.set(k,cells.has(k)?null:t);}
  const water=t=>!t.exterior&&(['ocean','water','river','lake'].includes(t.terrain));
  for(const t of tiles){
   if(t.exterior||water(t)||!['coast','plains','forest','rainforest','desert','wetland','road','town','settlement','valley','mountain','snow'].includes(t.terrain)||cells.get(key(t))!==t)continue;
   const sides=[];
   for(const [side,dx,dy] of [['north',0,-1],['east',1,0],['south',0,1],['west',-1,0]]){
    const n=cells.get([t.x+dx,t.y+dy,t.z??0].join(':'));
    if(n&&water(n))sides.push({side,kind:n.terrain==='ocean'?'sea':'fresh'});
   }
   if(sides.length)edges.set(t.id,sides);
  }
  return edges;
 }
 function drawShore(c,edges,x,y,size){
  if(!edges?.length)return;
  c.save();c.translate(x,y);c.scale(size/24,size/24);
  for(const edge of edges){
   // Sand at saltwater; darker earthy/reedy banks at freshwater. Water itself
   // stays in the authored water tile, never replaces walkable ground.
   c.fillStyle=edge.kind==='sea'?'#c5bea0':'#657655';
   const rect={north:[0,0,24,2],south:[0,22,24,2],west:[0,0,2,24],east:[22,0,2,24]}[edge.side];
   c.fillRect(...rect);
  }
  c.restore();
 }
 // Geological artwork is separate from the climate/terrain palette.
 const geologyKey=[['collision_range','Collision range'],['eroded_range','Eroded range'],['volcano','Volcano'],['lava_field','Molten lava'],['cooled_lava','Cooled lava'],['lava_tube','Lava tube'],['kimberlite_pipe','Kimberlite pipe'],['lamproite_pipe','Lamproite pipe'],['alluvial','Alluvial gravel']];
 function drawGeology(c,t,x,y,size){
  const kind=(t.ground_landform||t.geology?.landform);if(!kind||t.exterior)return;
  c.save();c.translate(x,y);c.scale(size/24,size/24);const r=(x,y,w,h,col)=>{c.fillStyle=col;c.fillRect(x,y,w,h);};
  r(1,1,22,22,'#4e5853');
  if(kind==='collision_range'){
   r(1,1,22,22,'#657362');for(const [xx,yy,h] of [[1,4,16],[9,1,20],[16,7,14]])for(let j=0;j<h;j++){const half=Math.floor(j/3);r(Math.max(1,xx+4-half),yy+j,Math.min(9,1+2*half),1,j%4===0?'#b7b39b':'#767d72');}r(12,4,1,8,'#d5d1b7');
  }else if(kind==='eroded_range'){
   r(1,1,22,22,'#637254');for(const [xx,yy] of [[1,5],[10,8],[3,14]]){r(xx+3,yy,5,2,'#9ba38a');r(xx+1,yy+2,9,3,'#848f74');r(xx,yy+5,11,3,'#737e67');r(xx+2,yy+4,7,1,'#b4b3a0');}r(15,2,1,6,'#b5b59a');
  }else if(kind==='volcano'){
   r(1,1,22,22,'#697263');for(let yy=6;yy<22;yy++){const half=Math.floor((yy-3)/2);r(12-half,yy,half*2,1,yy%4===0?'#71776b':'#555e59');}r(8,5,8,3,'#989d84');r(9,5,6,2,'#303c3b');r(13,10,2,9,'#7d8372');
  }else if(kind==='lava_field'){
   r(1,1,22,22,'#343c3d');r(3,1,4,9,'#cf763c');r(6,7,5,6,'#b95532');r(9,11,4,12,'#e58b3e');r(12,17,10,4,'#c56634');r(5,3,1,6,'#f0bd60');r(10,12,1,7,'#f0bd60');r(17,18,4,1,'#f0bd60');r(15,3,6,6,'#59645d');
  }else if(kind==='cooled_lava'){
   r(1,1,22,22,'#414b4b');for(const [xx,yy,ww] of [[2,3,8],[12,2,9],[4,10,7],[13,10,7],[2,18,10],[15,17,7]]){r(xx,yy,ww,4,'#626c64');r(xx+1,yy,ww-2,1,'#8a9080');}r(10,2,1,18,'#293838');
  }else if(kind==='lava_tube'){
   r(1,1,22,22,'#535f5b');r(2,4,20,3,'#8c9580');r(4,3,16,2,'#6e796d');r(4,7,16,14,'#263637');r(2,8,3,14,'#6e796d');r(19,8,3,14,'#6e796d');r(6,18,12,3,'#64766a');r(8,19,8,1,'#8b9a80');
  }else if(kind==='kimberlite_pipe'||kind==='lamproite_pipe'){
   const co=kind==='kimberlite_pipe'?'#71857d':'#8c7c67';r(1,1,22,22,'#646d5b');r(6,3,12,18,co);r(3,6,18,12,co);r(5,5,14,14,co);for(const [xx,yy] of [[7,5],[13,4],[5,11],[11,9],[16,10],[8,15],[14,17],[10,19]]){r(xx,yy,2,2,'#c1bda1');r(xx+1,yy+2,2,1,'#495f58');}r(10,6,2,2,'#4c5c53');
  }else if(kind==='alluvial'){
   r(1,1,22,22,'#a39c78');r(1,5,11,3,'#648c8d');r(9,7,6,4,'#648c8d');r(12,10,10,3,'#648c8d');r(7,10,3,10,'#648c8d');for(const [xx,yy] of [[3,3],[15,4],[18,16],[3,17],[12,20]]){r(xx,yy,3,2,'#d0c8a0');r(xx,yy+2,2,1,'#7b8069');}
  }
  c.restore();
 }
 function drawGeologyEffects(c,t,x,y,size){
  if(t.exterior)return;const effects=t.effects||[];if(!effects.length)return;
  c.save();c.translate(x,y);c.scale(size/24,size/24);const r=(x,y,w,h,col)=>{c.fillStyle=col;c.fillRect(x,y,w,h);};
  // Shared tiles show water above shaking; local labels retain every event.
  for(const e of effects.filter(e=>(e.type==='quake'||e.type==='earthquake'))){
   const co=e.phase==='recovering'?'#8c8a70':'#e1c794';for(const [xx,yy,ww] of [[2,4,6],[7,5,2],[8,6,3],[10,7,2],[11,8,6],[16,9,3],[18,10,3]])r(xx,yy,ww,1,co);
   if(e.phase!=='recovering'){r(2,2,2,2,'#5c4c3b');r(20,18,2,3,'#d6ae78');r(2,19,5,1,'#d6ae78');}
  }
  for(const e of effects.filter(e=>e.type==='eruption')){
   const recovering=e.phase==='recovering';r(2,19,20,3,recovering?'#70766b':'#c77339');r(9,7,5,3,recovering?'#8d8c79':'#e9a34e');if(!recovering){r(10,4,3,4,'#e5bb69');r(7,2,9,2,'#a0a28b');r(11,10,2,9,'#de8a3d');}
  }
  for(const e of effects.filter(e=>e.type==='flood'||e.type==='tsunami')){
   const active=e.phase!=='recovering',tsunami=e.type==='tsunami';
   if(active){r(1,tsunami?11:15,22,tsunami?12:8,tsunami?'#346578':'#4d7e81');r(2,tsunami?10:14,20,1,'#a9c9be');r(4,18,10,1,'#b8d2c4');r(14,21,6,1,'#8eb5ac');if(tsunami){r(5,8,6,2,'#d2ddd0');r(3,10,5,2,'#91b8b5');r(10,12,10,1,'#d2ddd0');}}
   else{r(1,19,22,3,'#788b76');r(3,17,7,2,'#658f89');r(16,20,5,2,'#658f89');r(11,22,3,1,'#c0b597');}
  }
  c.restore();
 }
 function geologicalText(t){
  const g=t.geology||{},parts=[];if(g.landform)parts.push(g.landform.replaceAll('_',' ')+(g.rock?' / '+g.rock:''));
  for(const e of t.effects||[])parts.push((e.type==='quake'?'earthquake':e.type)+' · '+e.phase+(e.magnitude!==undefined?' · M '+Number(e.magnitude).toFixed(1):''));
  return parts.length?' · '+parts.join('; '):'';
 }
 // Only authoritative, still-active consequences produce a condition marker.
 // Event art alone is never evidence of injury, damage or a closed route.
 function hasImpacts(t){return t&&!t.exterior&&t.impacts&&['structures','routes','resources','port_routes'].some(k=>t.impacts[k]?.length);}
 function impactText(t){
  if(!hasImpacts(t))return '';
  const i=t.impacts,parts=[];
  if(['structures','routes','resources','port_routes'].some(k=>(i[k]||[]).some(r=>r.cause==='storm')))parts.push('Storm damage');
  if(i.structures?.length)parts.push('Structural condition '+Math.round(i.condition)+'%'+(i.unusable?' · Workshops and facilities temporarily unavailable':' · Repairs underway'));
  for(const r of i.routes||[])parts.push('Passage closed: '+r.direction);
  for(const r of i.resources||[])parts.push('Resource temporarily unavailable: '+r.name);
  if(i.port_routes?.length)parts.push(i.port_routes.length+' boat service'+(i.port_routes.length===1?'':'s')+' temporarily unavailable');
  parts.push('Recovery in '+Math.ceil(i.remaining_minutes)+' simulated min');
  return ' · '+parts.join('; ');
 }
 function drawImpactMarker(c,p,tileSize){
  if(!hasImpacts(p.tile))return;
  // Compact upper-right warning stays within its room; full condition is in inspection.
  const width=tileSize<24?5:7,height=tileSize<24?6:9,x=Math.round(p.x+tileSize/2-width-1),y=Math.round(p.y-tileSize/2+1);
  c.save();c.fillStyle='#1c252a';c.fillRect(x,y,width,height);c.strokeStyle='#e9be7d';c.lineWidth=1;c.strokeRect(x+.5,y+.5,width-1,height-1);
  c.fillStyle='#ffe1ad';c.font='bold '+(tileSize<24?6:8)+'px system-ui';c.textAlign='center';c.textBaseline='middle';c.fillText('!',x+width/2,y+height/2+.5);c.restore();p.impactBadge={x,y,width,height};
 }
 function geologyLegend(){
  const details=make('details','atlas-terrain-key atlas-geology-key'),grid=make('div','atlas-terrain-grid');details.append(make('summary','','Geology key'));
  for(const [kind,label] of geologyKey){const item=make('span','atlas-geology-item'),icon=make('canvas');icon.width=icon.height=24;icon.setAttribute('aria-hidden','true');const c=icon.getContext('2d');c.drawImage(tile('mountain',0),0,0);drawGeology(c,{geology:{landform:kind}},0,0,24);item.append(icon,make('span','',label));grid.append(item);}
  for(const type of ['earthquake','eruption','flood','tsunami']){const item=make('span','atlas-geology-item'),icon=make('canvas');icon.width=icon.height=24;icon.setAttribute('aria-hidden','true');const c=icon.getContext('2d');c.drawImage(tile('plains',0),0,0);drawGeologyEffects(c,{effects:[{type,phase:'active'}]},0,0,24);item.append(icon,make('span','',type));grid.append(item);}
  details.append(grid);return details;
 }
 // Land and resource overlays describe one real room, not new traversable cells.
 const surfaceColors={yellow:'#d8bf58',gold:'#d8bf58',green:'#82a85c',orange:'#ca8b50',red:'#b56752',purple:'#a081a7',blue:'#769cae',brown:'#a48058',gray:'#b0b4a6',black:'#485153',white:'#d8d6c0'};
 // A baked ground texture inside one tile, never a line between room centers.
 function routeLegend(){
  const details=make('details','atlas-terrain-key'),grid=make('div','atlas-terrain-grid');details.append(make('summary','','Roads and open ground'));
  for(const [label,route] of [['Open ground',null],['Maintained road',{kind:'road',axis:'east_west'}],['Trodden trail',{kind:'trail',axis:'east_west'}]]){const item=make('span','atlas-route-item'),icon=make('canvas');icon.width=icon.height=24;icon.setAttribute('aria-hidden','true');icon.getContext('2d').drawImage(terrainTile('plains',0,route),0,0);item.append(icon,make('span','',label));grid.append(item);}
  details.append(grid,make('small','','Surface patterns identify authored roads/trails. Movement always follows real exits; blank map space is not a path.'));return details;
 }
 function drawFacility(c,t,x,y,size){
  const kind=t.facility_landmark?.kind;if(!['lodging','forge','workshop','market','residence'].includes(kind))return;
  c.save();c.translate(x,y);c.scale(size/24,size/24);const r=(x,y,w,h,color)=>{c.fillStyle=color;c.fillRect(x,y,w,h);};
  // Small authored landmark, with terrain retained around its footprint.
  if(kind==='market'){
   r(4,9,1,12,'#58432e');r(19,9,1,12,'#58432e');r(4,17,16,3,'#9b713e');
   for(let i=0;i<4;i++)r(3+i*5,6,5,5,i%2?'#e6c78b':'#a74c43');
   r(7,15,3,2,'#cdb76a');r(13,15,4,2,'#769359');
  }else{
   r(5,10,14,11,'#c2ac83');r(5,20,14,1,'#67513b');
   c.fillStyle=kind==='lodging'?'#9e493e':kind==='forge'?'#545662':'#697a58';
   c.beginPath();c.moveTo(3,11);c.lineTo(12,3);c.lineTo(21,11);c.closePath();c.fill();
   r(10,14,4,7,'#3a302b');r(6,13,3,3,'#efcb72');r(15,13,3,3,'#efcb72');
   if(kind==='residence'){r(15,3,2,6,'#854d3b');r(5,17,4,1,'#558659');r(6,18,2,2,'#97745d');}
   if(kind==='lodging'){r(19,11,1,7,'#55432f');r(18,12,5,4,'#d8b864');r(19,14,3,1,'#755238');}
   if(kind==='forge'){r(16,3,3,7,'#48474b');r(6,17,3,3,'#e88b39');r(17,1,2,1,'#c2c2b9');}
   if(kind==='workshop'){r(4,17,5,2,'#6b4930');r(5,16,3,1,'#b5b8b8');r(16,4,3,5,'#776451');}
  }
  c.restore();
 }
 function drawSurface(c,t,x,y,size){
  const surface=t.surface||{};if((!t.ground_use&&!t.surface)||t.exterior)return;
  c.save();c.translate(x,y);c.scale(size/24,size/24);
  const r=(x,y,w,h,col)=>{c.fillStyle=col;c.fillRect(x,y,w,h);};
  const land=t.ground_use||surface.land_use;
  if(land==='farm'){r(1,1,22,22,'#796449');for(let yy=4;yy<23;yy+=4)r(2,yy,20,1,'#b09a63');}
  if(land==='ranch'){r(2,2,20,20,'#64764b');for(const yy of [3,19]){r(2,yy,20,1,'#c5b68a');r(2,yy+2,20,1,'#8c835f');}for(const xx of [3,10,20])r(xx,2,1,20,'#c5b68a');}
  if(['house','rental','business'].includes(land)){
   r(1,1,22,22,'#617052');
   if(land==='business'){r(4,8,16,13,'#b6ac8d');r(2,6,20,4,'#786c5c');r(3,11,18,3,'#bf995e');for(let xx=3;xx<21;xx+=4)r(xx,11,2,3,'#d5c5a1');r(6,15,4,6,'#455951');r(13,16,5,3,'#6b8790');}
   else{for(const [xx,yy] of [[2,3],[13,12]]){r(xx+1,yy+5,8,7,'#c6b99a');for(let i=0;i<5;i++)r(xx+i,yy+4-i,10-2*i,1,'#985f4f');r(xx+4,yy+8,2,4,'#43554f');r(xx+2,yy+7,1,2,'#e2cd83');}if(land==='rental')r(11,2,1,20,'#b4aa80');}
  }
  if(land==='recreation'){r(1,1,22,22,'#718556');r(10,1,4,22,'#b4ad88');r(3,9,5,2,'#9e8057');r(3,12,5,1,'#c3ad7c');r(4,13,1,3,'#76694c');r(7,13,1,3,'#76694c');r(17,4,3,5,'#456347');r(18,9,1,3,'#776342');}
  // Hunting and reserve do not imply any individual tree was cut or planted.
  if(land==='hunting'){r(1,1,22,1,'#b3a478');r(1,1,1,22,'#b3a478');}
  if(land==='reserve'){r(1,1,3,1,'#adb393');r(1,1,1,3,'#adb393');r(20,22,3,1,'#adb393');r(22,20,1,3,'#adb393');}
  const features=(surface.resources||[]).filter(f=>f.kind==='crop'||f.kind==='mine').slice(0,3);
  features.forEach((f,i)=>{
   const left=1+Math.floor(i*22/features.length),right=1+Math.floor((i+1)*22/features.length),w=right-left;
   const col=({grain:'#d8bf58',carrot:'#82a85c',potato:'#79985b',onion:'#90a86c',fiber:'#9eac73',ore:'#b4aa93',crystal:'#c1d6d1',crop:'#8b9c69',mine:'#a4aaa0'})[f.color_key]||surfaceColors[f.color]||'#b0b4a6',stage=f.kind==='crop'&&f.in_season===false?'dormant':f.stage;
   if(f.kind==='crop'){
    r(left,2,w,20,'#786149');
    if(stage==='mature'){r(left,2,w,20,col);for(let yy=4;yy<22;yy+=4){r(left,yy,w,1,'#7e7f4c');for(let xx=left+1;xx<right;xx+=3)r(xx,yy-1,1,2,'#e0d294');}}
    else if(stage==='growing'){r(left,2,w,20,'#4d6647');for(let yy=5;yy<22;yy+=4)for(let xx=left+1;xx<right;xx+=3){r(xx,yy,1,3,'#9ab263');r(xx+1,yy+1,1,1,'#789950');}}
    else if(stage==='planted'){for(let yy=4;yy<22;yy+=4){r(left,yy,w,1,'#b09a72');for(let xx=left+1;xx<right;xx+=3)r(xx,yy-1,1,1,'#c3b08a');}}
    else if(stage==='dormant'){r(left,2,w,20,'#656a55');for(let yy=5;yy<22;yy+=5)r(left,yy,w,1,'#8b8c72');}
    else{for(let yy=4;yy<22;yy+=4){r(left,yy,w,1,'#a68a5b');for(let xx=left+1;xx<right;xx+=3)r(xx,yy-1,1,1,'#bdab75');}}
   }else{
    r(left,2,w,20,'#424b50');r(left,2,w,3,'#81847b');r(left+1,6,Math.max(1,w-2),15,'#29343b');
    const vein=stage==='available'?col:stage==='recovering'?'#727d75':'#414f51';
    for(let yy=7;yy<17;yy+=3){const xx=left+1+(yy%3);r(xx,yy,Math.max(1,w-4),1,vein);r(xx+1,yy+1,Math.max(1,w-5),1,vein);}
    r(left+1,20,Math.max(1,w-2),1,'#7f7e6c');if(stage==='exhausted'){r(left+1,7,Math.max(1,w-2),10,'#273438');r(left+1,16,Math.max(1,w-2),2,'#535e58');}if(stage!=='available'){r(left+1,18,Math.max(1,w-3),1,'#647068');r(right-2,17,1,2,'#8f8b76');}
   }
  });
  c.restore();
 }
 function surfaceText(t){
  const s=t.surface||{},parts=[];if(s.land_use)parts.push(s.land_use.replaceAll('_',' '));
  for(const f of s.resources||[])parts.push((f.material_name||f.name||f.kind)+' · '+(f.closure_reason?'temporarily unavailable':f.kind==='crop'&&f.in_season===false?'dormant / out of season':f.stage)+(f.remaining_batches!==undefined?' · '+f.remaining_batches+' batches left':''));
  return (parts.length?' · '+parts.join('; '):'')+geologicalText(t)+impactText(t);
 }
 function actor(c,a,x,y,size,self){
  const ap=a.appearance||{},seed=hash(ap.seed||a.id||a.subject||'visitor'),colors={black:'#3f4249',white:'#e4e1cc',grey:'#969e9d',gray:'#969e9d',brown:'#8d6950',red:'#b96459',blue:'#759dbd',green:'#88a06b',yellow:'#cfb36b',gold:'#d1b36b',silver:'#b9c4c1',purple:'#a58db9',violet:'#a58db9',pink:'#c990a5',orange:'#c38a58',blond:'#d4bb7e',blonde:'#d4bb7e',auburn:'#9a5d45',chestnut:'#80583f',copper:'#bb7957'};
  const coat=colors[ap.clothing_color]||['#8d9f97','#9a9280','#8797a0','#a3968e'][seed%4],body=colors[ap.body_color]||'#99977e',hair=colors[ap.hair_color]||'#6d6051',skin='#c7ad8b';
  const race=String(a.race||''),s=size/16,small=['dwarf','gnome','halfling'].includes(race),top=small?5:3;
  const shape=ap.silhouette||(ap.creature?'quadruped':'humanoid'),acc=ap.accessories||[];
  c.save();c.translate(Math.round(x-size/2),Math.round(y-size/2));c.scale(s,s);
  const r=(x,y,w,h,color)=>{c.fillStyle=color;c.fillRect(x,y,w,h);};
  r(3,14,11,1,'#101c22');
  if(shape==='bird'){
   r(5,7,7,6,body);r(8,4,4,5,body);r(12,6,3,2,'#c5ad75');r(10,5,1,1,'#15262b');r(3,8,5,3,colors[ap.clothing_color]||'#b1b5a3');r(6,13,1,2,'#c5ad75');r(10,13,1,2,'#c5ad75');
  }else if(shape==='insect'){
   r(6,5,4,8,body);r(7,3,2,3,body);for(const y of [6,9,12]){r(3,y,3,1,body);r(10,y,3,1,body);}r(5,2,1,3,body);r(10,2,1,3,body);r(6,6,4,1,'#d5c79c');r(6,9,4,1,'#d5c79c');
  }else if(shape==='arachnid'){
   r(5,5,6,7,body);r(6,12,4,2,body);for(const y of [5,7,10,12]){r(2,y,3,1,body);r(11,y,3,1,body);}r(6,5,1,1,'#d9dfcb');r(9,5,1,1,'#d9dfcb');
  }else if(shape==='crustacean'){
   r(4,8,8,5,body);r(1,5,3,4,body);r(12,5,3,4,body);r(2,4,1,3,'#d5c79c');r(13,4,1,3,'#d5c79c');for(const xx of [3,6,9,12])r(xx,12,1,3,body);r(6,7,1,2,'#d9dfcb');r(9,7,1,2,'#d9dfcb');
  }else if(shape==='mollusk'){
   r(3,8,10,6,body);r(5,5,6,3,body);r(7,3,2,3,body);r(4,12,8,2,'#d5cdb8');r(7,6,1,6,'#6d7f7e');r(5,8,1,4,'#6d7f7e');r(10,8,1,4,'#6d7f7e');
  }else if(shape==='reptile'){
   r(3,10,10,3,body);r(10,7,4,4,body);r(13,8,2,2,body);r(1,12,4,2,body);r(4,13,2,2,body);r(10,12,2,3,body);r(13,8,1,1,'#17242a');
  }else if(shape==='fish'){
   r(4,7,9,5,body);r(6,5,5,2,body);r(6,12,4,1,body);r(1,6,3,7,body);r(11,8,1,1,'#17242a');
  }else if(shape==='quadruped'){
   r(3,8,9,4,body);r(10,5,4,6,body);r(11,3,1,3,body);r(13,4,1,2,body);r(3,11,2,3,body);r(10,11,2,3,body);r(1,6,3,2,body);r(13,6,1,1,'#17242a');
  }else if(shape==='generic'){
   r(4,7,9,7,body);r(6,5,5,2,body);r(5,8,2,2,'#d9dfcb');r(10,8,1,2,'#d9dfcb');r(4,13,10,1,'#73847c');
  }else{
   r(5,top-1,6,5,'#17232b');r(6,top,4,4,race==='zombie'?'#8cab86':skin);r(6,top-1,4,2,hair);
   r(4,top+4,8,9-top,ap.clothing==='armor'?(colors[ap.clothing_color]||'#9ba9aa'):coat);r(3,top+5,1,4,skin);r(12,top+5,1,4,skin);r(5,13,2,2,'#b7ad97');r(9,13,2,2,'#b7ad97');
   if(['robe','dress'].includes(ap.clothing)){r(3,11,10,3,coat);r(7,8,1,5,'#c5b691');}
   if(ap.clothing==='armor'){r(5,top+5,6,1,'#d2d8ce');r(7,top+6,2,3,'#7b8e94');}
   if(race==='elf'){r(4,top+1,2,1,skin);r(10,top+1,2,1,skin);}
   if(race==='dwarf')r(6,top+3,4,3,hair);
   if(acc.includes('cloak')){r(2,top+4,2,8,coat);r(12,top+4,2,8,coat);}
   if(acc.includes('staff')){r(14,3,1,11,'#bea778');r(13,2,3,2,'#9adbd3');}
   if(acc.includes('shield')){r(1,8,4,5,'#b9c4c1');r(2,9,2,3,coat);}
   if(acc.includes('sword')){r(14,5,1,8,'#e0dfc9');r(13,10,3,1,'#bb9e65');}
   if(acc.includes('bow')){r(13,5,1,8,'#c3a36c');r(14,7,1,4,'#d3c4a0');}
   if(acc.includes('hood')){r(5,top-1,6,2,coat);r(5,top,1,4,coat);r(10,top,1,4,coat);}
   if(acc.includes('hat')){r(6,top-3,4,3,coat);r(4,top,8,1,coat);}
   if(acc.includes('helmet')){r(5,top-1,6,2,'#b6c1bb');r(5,top,1,3,'#b6c1bb');r(10,top,1,3,'#b6c1bb');}
   if(acc.includes('crown')){r(5,top-1,6,1,'#e1c275');for(const xx of [5,7,10])r(xx,top-3,1,2,'#e1c275');}
  }
  if(self){r(6,0,4,1,'#fff4c5');r(7,1,2,1,'#fff4c5');}
  c.restore();
 }
 // Players have their own paper doll. The NPC painter above is unchanged.
 const dollColors={black:'#3f4249',white:'#e4e1cc',gray:'#969e9d',brown:'#8d6950',red:'#b96459',blue:'#759dbd',green:'#88a06b',yellow:'#cfb36b',gold:'#d1b36b',silver:'#b9c4c1',purple:'#a58db9',pink:'#c990a5',orange:'#c38a58',blond:'#d4bb7e',auburn:'#9a5d45'};
 const dollMaterials={iron:'#8e9b9e',steel:'#b5c3c5',leather:'#93704c',woven:'#b1a17b',cloth:'#9aa79c',wood:'#9c8056',crystal:'#91c4cf',silk:'#c2a2c3',wool:'#c0b9a0',fur:'#998773',hide:'#99815e',chitin:'#828868',bone:'#d4c8a5',bronze:'#ba9568',copper:'#bb7957',silver:'#c9d2d0',gold:'#d1b36b',linen:'#d0c6a8',cotton:'#c7c2b0',velvet:'#8c719b',canvas:'#b4a284',scale:'#87998e',felt:'#a49b89',flax:'#bdb087',pearl:'#d7d8cd',stone:'#a0a5a2'};
 const dollTint=(hex,amount)=>'#'+[1,3,5].map(i=>{const n=parseInt(hex.slice(i,i+2),16);return Math.round(amount>0?n+(255-n)*amount:n*(1+amount)).toString(16).padStart(2,'0');}).join('');
 // Small bodies share the adult palette and equipment, with distinct silhouettes.
 const youngBodies={
  infant:['..hhh..','.hsssh.','.seses.','..sss..','.ttttt.','tuttttt','ttuuttt','.tttuu.','..ttt..'],
  preschool:['..hhhh..','.hhsssh.','.hseses.','..ssss..','...ss...','.stttts.','.stttts.','..tuut..','..p..p..','..b..b..'],
  school:['..hhhh..','.hhsssh.','.hseses.','..ssss..','...ss...','..tttt..','.stttts.','.stuuts.','..tttt..','..pppp..','..p..p..','.bb..bb.'],
  adolescent:['..hhhh..','.hhsssh.','.hseses.','..ssss..','...ss...','.tttttt.','.stttts.','.stttts.','.stuuts.','..tttt..','..pppp..','..p..p..','..p..p..','.bb..bb.']
 };
 function youngActor(c,a,x,y,size,self,skin,hair,gear){
  const doll=a.paperdoll,grid=youngBodies[doll.life_stage];
  if(!grid)return false;
  const coat=gear.filter(g=>g.layer==='body').at(-1)||{};
  const cloth=dollColors[coat.color]||'#608a79';
  const colors={s:skin,h:hair,e:'#293236',t:cloth,u:dollTint(cloth,.4),p:'#485963',b:'#493b35'};
  const width=grid[0].length,left=Math.floor((16-width)/2),top=16-grid.length;
  c.save();c.translate(Math.round(x-size/2),Math.round(y-size/2));c.scale(size/16,size/16);
  for(let row=0;row<grid.length;row++)for(let col=0;col<grid[row].length;col++){
   const shade=colors[grid[row][col]];
   if(shade){c.fillStyle=shade;c.fillRect(left+col,top+row,1,1);}
  }
  // Small details stay legible even when the map fits several people on a tile.
  const cut=doll.cut||({embroidered:'female',edged:'male'}[coat.pattern])||'neutral';
  const infant=doll.life_stage==='infant';
  if(!infant){
   c.fillStyle=dollTint(cloth,-.28);c.fillRect(left+width-3,top+5,1,2);
   c.fillStyle=colors.u;c.fillRect(left+3,top+5,2,1);
   if(doll.life_stage==='school'||doll.life_stage==='adolescent'){
    c.fillStyle='#805e43';c.fillRect(left+2,top+6,1,1);c.fillRect(left+3,top+7,1,1);c.fillRect(left+4,top+8,2,2);
    c.fillStyle='#ae8856';c.fillRect(left+4,top+8,2,1);
   }
  }
  c.fillStyle=infant?colors.u:hair;
  if(['female','feminine'].includes(cut)){c.fillRect(left+width-1,top+2,1,infant?1:3);}
  else if(['male','masculine'].includes(cut)){c.fillRect(left+1,top,1,1);}
  else{c.fillRect(left+width-2,top,1,1);}
  if(doll.characteristics?.ears==='pointed'&&!infant){
   c.fillStyle=skin;c.fillRect(left,top+2,1,1);c.fillRect(left+width-1,top+2,1,1);
  }
  c.restore();
  const equipped=gear.filter(g=>g.item_id||g.sprite_style||g.pixel_art);
  if(equipped.length){
   const fit=size*grid.length/16;
   playerActor(c,{...a,paperdoll:{...doll,equipment:equipped}},x,y+(size-fit)/2,fit,self,true);
  }
  return true;
 }
 function playerActor(c,a,x,y,size,self,gearOnly=false){
  const doll=a.paperdoll||{},ap=doll.characteristics||{},gear=(doll.equipment||[]).filter(g=>g&&typeof g==='object');
  const skin=({pale:'#e2cbb1',fair:'#d8b794',tan:'#c19b71',olive:'#b4a273',brown:'#956a4d',dark:'#684d3f',black:'#4f3c36'})[ap.skin_color]||dollColors[ap.skin_color]||dollColors[ap.body_color]||'#bea88e';
  const hair=dollColors[ap.hair_color]||'#786b5c',top=ap.stature==='short'?5:ap.stature==='tall'?3:4,left=ap.build==='broad'?3:ap.build==='slim'?5:4,wide=16-left*2;
  if(!gearOnly&&!doll.pixel_base&&youngActor(c,a,x,y,size,self,skin,hair,gear))return;
  const rig='humanoid:'+(ap.stature||'average')+':'+(ap.build||'average');
  const baseArt=doll.pixel_base?.rig===rig?customArt(doll.pixel_base):null;
  const animal=ap.silhouette&&ap.silhouette!=='humanoid';
  if(animal)actor(c,{...a,race:'',appearance:{...ap,seed:a.id,accessories:[]}},x,y,size,false);
  c.save();c.translate(Math.round(x-size/2),Math.round(y-size/2));c.scale(size/16,size/16);
  const r=(x,y,w,h,color)=>{c.fillStyle=color;c.fillRect(x,y,w,h);};
  const polygon=(points,color)=>{c.beginPath();points.forEach(([px,py],i)=>i?c.lineTo(px,py):c.moveTo(px,py));c.closePath();c.fillStyle=color;c.fill();};
  const color=g=>dollColors[g.color]||dollMaterials[g.material]||'#a6aaa0';
  const trim=g=>dollColors[g.trim_color]||dollTint(color(g),.38);
  const rows=layer=>gear.filter(g=>g.layer===layer).sort((a,b)=>{const weight=g=>g.slot==='armor'||g.slot==='head'?2:g.slot?.startsWith('appearance_')?0:1;return weight(a)-weight(b)||String(a.slot).localeCompare(String(b.slot));});
  // Decoration is clipped to its own panel. A cosmetic dye never leaks into
  // another garment, skin, weapon, or armor; material and pattern are independent.
  function panel(g,xx,yy,w,h){
   const co=color(g),hi=trim(g),lo=dollTint(co,-.32);r(xx,yy,w,h,co);c.save();c.beginPath();c.rect(xx,yy,w,h);c.clip();
   if(['iron','steel','bronze','copper','silver','gold'].includes(g.material)){r(xx,yy,w,.5,hi);r(xx+w-.5,yy,.5,h,lo);}
   if(['woven','linen','canvas','wool','flax','felt'].includes(g.material)){for(let y=yy+1;y<yy+h;y+=2)r(xx,y,w,.3,lo);}
   if(['leather','hide'].includes(g.material)){r(xx+.4,yy,.35,h,hi);r(xx+w-.7,yy,.35,h,lo);}
   if(['fur'].includes(g.material)){for(let y=yy;y<yy+h;y+=1.5)for(let x=xx;x<xx+w;x+=2)r(x,y,.5,.8,hi);}
   if(['chitin','scale','bone','stone'].includes(g.material)){for(let y=yy+1;y<yy+h;y+=1.5)r(xx+.5,y,w-1,.4,hi);}
   if(['silk','velvet','crystal','pearl'].includes(g.material))r(xx+w/3,yy,.6,h,hi);
   const p=g.pattern;
   if(['striped','stripes','banded','layered'].includes(p))for(let y=yy+1;y<yy+h;y+=2)r(xx,y,w,.6,hi);
   else if(['checked','checkered','plaid'].includes(p)){for(let y=yy;y<yy+h;y+=2)for(let x=xx;x<xx+w;x+=2)r(x,y,1,1,hi);}
   else if(['ribbed','ribbing','pleated','slats','grain'].includes(p))for(let x=xx+1;x<xx+w;x+=2)r(x,yy,.5,h,lo);
   else if(['quilted','diamond'].includes(p)){for(let y=yy;y<yy+h;y+=2)for(let x=xx;x<xx+w;x+=2){r(x,y,.5,.5,hi);r(x+.5,y+.5,.5,.5,hi);}}
   else if(['scaled','scales','chainmail','mail','rings'].includes(p)){for(let y=yy+.5;y<yy+h;y+=1.5)for(let x=xx+(Math.floor(y)%2?0:.5);x<xx+w;x+=1.5)r(x,y,1,.4,hi);}
   else if(['riveted','studded','dotted','rivets','beaded','felted'].includes(p)){for(let y=yy+.5;y<yy+h;y+=2)for(let x=xx+.5;x<xx+w;x+=2)r(x,y,.5,.5,hi);}
   else if(['embroidered','brocade','floral','filigree','carved','knotted'].includes(p)){r(xx+w/2-.5,yy+.5,1,h-1,hi);r(xx+1,yy+h/2,w-2,.5,hi);}
   else if(['edged','bordered','trimmed','braided','stitched','inlay'].includes(p)){r(xx,yy,.5,h,hi);r(xx+w-.5,yy,.5,h,hi);r(xx,yy+h-.5,w,.5,hi);}
   else if(['chevron','chevrons','herringbone','diagonal','lacing'].includes(p)){for(let x=0;x<w;x++)r(xx+x,yy+1+Math.min(x,w-1-x)*.5,.7,.5,hi);}
   if(['woven','crosshatch','lattice'].includes(p)){const ink=p==='woven'?dollTint(co,-.16):hi;for(let y=yy+.75;y<yy+h;y+=1.5)r(xx,y,w,.25,ink);for(let x=xx+.75;x<xx+w;x+=1.5)r(x,yy,.25,h,ink);}
   if(p==='plates'){r(xx,yy+h/2,w,.5,lo);r(xx+w/2,yy,.5,h,hi);}
   if(p==='mosaic'){for(let y=yy;y<yy+h;y+=1.5)for(let x=xx;x<xx+w;x+=1.5)r(x,y,1,1,hi);}
   if(p==='faceted'){polygon([[xx,yy],[xx+w,yy],[xx+w/2,yy+h]],hi);polygon([[xx,yy+h],[xx+w/2,yy+h/2],[xx+w,yy+h]],lo);}
   c.restore();
  }
  // The same construction texture follows curved and cut-out silhouettes,
  // not just rectangular panels (blades, shield faces, skirts and jewelry).
  function cut(g,points){const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);c.save();c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.clip();panel(g,Math.min(...xs),Math.min(...ys),Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));c.restore();}
  const shape=g=>g.shape||g.kind;
  function bodyTransform(){if(animal){c.translate(3,8);c.scale(1,.55);c.translate(-left,-(top+4));}}
  function headTransform(){if(animal){const side=['quadruped','reptile','bird'].includes(ap.silhouette);c.translate(side?4:0,side?1:2);c.scale(.75,.75);}}
  function customGear(g){
   if(animal||gearOnly===true)return false;
   if(g.pixel_art?.rig===rig&&g.pixel_art?.slot===g.slot){
    const art=customArt(g.pixel_art);if(art){c.drawImage(art,0,0,16,16);return true;}
   }
   if(!Number.isInteger(g.sprite_index))return false;
   const style=['slot','layer','kind','shape','material','pattern','detail','silhouette','color','trim_color'].map(k=>g[k]||'').join('|');
   return style===g.sprite_style&&!!window.ExpanseSpriteSheets?.gear(c,rig,g.sprite_index);
  }
  // Rear cloth is behind armor, but its edge and fastenings remain visible.
  for(const g of rows('cloak')){
   if(customGear(g))continue;
   const s=shape(g),yy=top+4,co=color(g),hi=trim(g);
   if(s==='half_cape'){panel(g,1.5,yy,3,5);r(2.5,yy+5,2,1,co);}
   else if(s==='circle_cloak'){cut(g,[[4,yy],[12,yy],[15,13],[13,15],[3,15],[1,13]]);r(2,13,12,.5,hi);}
   else if(s==='shoulder_shawl'){cut(g,[[2,yy],[14,yy],[8,yy+5]]);r(2,yy,12,.5,hi);}
   else if(s==='scarf_mantle'){panel(g,3,yy,2,7);panel(g,11,yy,2,7);r(3,yy,10,1,co);}
   else if(s==='collared_cape'){panel(g,2,yy,12,3);panel(g,4,yy-2,2,3);panel(g,10,yy-2,2,3);}
   else if(s==='travel_cape'){panel(g,2,yy,12,5);r(2,yy+1,12,.7,hi);}
   else if(s==='tabbed_cape'){panel(g,2,yy,12,4);for(let x=2;x<14;x+=2)r(x,yy+4,1,1,co);}
   else if(s==='rectangular_cloak'){panel(g,1.5,yy,3,7);panel(g,11.5,yy,3,7);}
   else if(s==='split_cloak'){panel(g,2,yy,2,7);panel(g,12,yy,2,7);r(1,14,3,1,co);r(12,14,3,1,co);}
   else{panel(g,2,yy,2,Math.min(7,15-yy));panel(g,12,yy,2,Math.min(7,15-yy));if(s==='hooded_cloak'){panel(g,4.5,top-1.5,7,2);panel(g,4.5,top,1,4);panel(g,10.5,top,1,4);}}
  }
  if(!gearOnly&&baseArt&&!animal)c.drawImage(baseArt,0,0,16,16);
  else if(!gearOnly&&!animal){
   const baked=window.ExpanseSpriteSheets?.body(c,doll.family,rig,skin);
   if(!baked){
   r(3,15,10,.6,'#101c22');if(ap.tail){r(12,11,3,1,skin);r(14,9,1,3,skin);}
   r(6,top,4,4,skin);r(left,top+4,wide,9-top,'#8d9a94');r(left-1,top+5,1,4,skin);r(16-left,top+5,1,4,skin);r(5,13,2,2,'#9a927f');r(9,13,2,2,'#9a927f');
   }
   if(ap.ears==='pointed'){r(4.5,top+1,1.5,1,skin);r(10,top+1,1.5,1,skin);}
   if(ap.hair_style!=='bald')r(6,top-1,4,2,hair);
   if(ap.hair_style==='long'){r(5,top,1,6,hair);r(10,top,1,6,hair);}
   if(ap.hair_style==='braided'){r(10,top,1,7,hair);r(9.5,top+5,2,.5,'#c5b18a');}
   if(ap.facial_hair==='beard')r(6,top+3,4,2,hair);
   if(ap.facial_hair==='mustache')r(6,top+3,4,.6,hair);
   if(ap.horns){r(4.5,top-2,1,3,'#d0c9af');r(10.5,top-2,1,3,'#d0c9af');}
   r(6.5,top+1.5,.5,.5,'#283638');r(9,top+1.5,.5,.5,'#283638');
  }
  for(const g of rows('body')){
   if(customGear(g))continue;
   c.save();bodyTransform();const s=shape(g),yy=top+4,co=color(g),hi=trim(g),lo=dollTint(co,-.35),armor=g.kind==='armor'||['lamellar_coat','scale_coat','war_coat','fauld_coat'].includes(s);
   const short=['vest','jerkin','waistcoat','cuirass','breastplate','segmented_cuirass'].includes(s);
   const long=['padded_robe','robe','dress','coat','gown','overcoat','frock_coat','kaftan','cassock','long_robe','greatcoat','longcoat','surcoat','tabard','apron','toga','wrap_robe'].includes(s)||['robe','dress','coat'].includes(g.kind);
   if(!['poncho','mantle','bolero','wrapped_sash','shoulder_stole'].includes(s))panel(g,left,yy,wide,short?3:13-yy);
   // Cloth sleeves and hem remain outside the protected torso silhouette.
   if(!armor&&!['vest','waistcoat','jerkin','bodice','sleeveless_top','sleeveless_tabard','long_tabard','wrapped_sash','shoulder_stole','bolero','mantle'].includes(s)){panel(g,left-1,yy,1,2);panel(g,16-left,yy,1,2);}
   if(long){panel(g,3,11,10,3);r(7.5,yy,.7,14-yy,hi);}
   if(['doublet','arming_jacket','quilted_tunic','padded_robe','gambeson'].includes(s)){r(7.5,yy,.5,4,hi);for(let y=yy+.5;y<12;y++)r(8.5,y,.5,.5,hi);}
   if(['vest','waistcoat'].includes(s)){r(7,yy,2,1,'#8d9a94');r(7.5,yy+1,1,2,'#8d9a94');}
   if(s==='waistcoat'){panel(g,left,11,2,2);panel(g,10,11,2,2);}
   if(s==='jerkin'){r(left,yy,wide,.5,hi);r(left,11,wide,1,lo);r(7,11,1,1,hi);}
   if(s==='longshirt'){panel(g,left,12,wide,2);r(left,13.5,wide,.5,hi);}
   if(s==='wrap_top'||s==='toga'||s==='wrap_robe'){for(let i=0;i<wide;i++)r(left+i,yy+i*.35,1,.7,hi);}
   if(s==='arming_jacket'){panel(g,left-1,yy,2,2);panel(g,15-left,yy,2,2);r(left,12,wide,.7,hi);}
   if(s==='gambeson'){panel(g,left-1,yy,2,3);panel(g,15-left,yy,2,3);r(left,12,wide,1,lo);}
   if(s==='quilted_tunic'){panel(g,left,12,wide,1.5);r(left+1,yy+1,wide-2,.7,hi);}
   if(armor){
    r(left,yy,wide,.6,hi);
    if(['hauberk','lamellar_coat','scale_coat','war_coat','fauld_coat'].includes(s)){panel(g,left,12,wide,1.5);panel(g,left-1,yy,1,2);panel(g,16-left,yy,1,2);}
    if(s==='cuirass'){r(7.5,yy+1,1,2,lo);r(left,11.5,wide,.6,hi);}
    else if(s==='breastplate'){panel(g,left-1,yy,2,1);panel(g,15-left,yy,2,1);r(left+1,yy+1,wide-2,.7,hi);r(7.5,yy+2,1,1,lo);}
    else if(s==='hauberk'){for(let y=yy+1;y<13;y++)for(let x=left;x<16-left;x+=2)r(x+(y%2)*.5,y,.5,.5,hi);}
    else if(s==='lamellar_coat'){for(let y=yy+1;y<13;y+=1.5)for(let x=left;x<16-left;x+=2){r(x,y,1.5,.7,hi);r(x,y,.3,1,lo);}}
    else if(s==='brigandine'){for(let y=yy+1;y<12;y+=1.5)for(let x=left+1;x<15-left;x+=2)r(x,y,.5,.5,hi);r(7.5,yy,1,4,lo);}
    else if(s==='scale_coat'){for(let y=yy+1;y<13;y+=1.5)for(let x=left;x<16-left;x+=2)polygon([[x,y],[x+1.5,y],[x+.75,y+1]],hi);}
    else if(s==='war_coat'){panel(g,left-1,yy,2,3);panel(g,15-left,yy,2,3);r(left,11.5,wide,1,lo);r(7,11.5,2,1,hi);}
    else if(s==='plated_mantle'){panel(g,left-2,yy,3,2);panel(g,15-left,yy,3,2);r(left,yy+1,wide,.8,hi);}
    else if(s==='fauld_coat'){for(let y=11;y<14;y++)r(left-.5,y,wide+1,.5,hi);r(7.5,yy,1,3,lo);}
    else if(s==='segmented_cuirass'){for(let y=yy+1;y<12;y++)r(left,y,wide,.5,hi);r(left+.5,yy,.5,3,lo);r(15-left,yy,.5,3,lo);}
    else{r(7.5,yy+1,1,3,lo);}
   }else if(!short&&!long){r(left,12,wide,.5,lo);}
   if(['shirt','high_collar_shirt'].includes(s)){r(7.5,yy,.5,2,hi);if(s==='high_collar_shirt')panel(g,6.5,yy-1,3,1);}
   if(s==='blouse'){panel(g,left-1,yy,2,2.5);panel(g,15-left,yy,2,2.5);r(left,11.5,wide,.7,hi);}
   if(s==='bodice'){r(left,yy,wide,.5,hi);for(let y=yy+.5;y<12;y++)r(7,y,2,.5,hi);}
   if(s==='undertunic'){panel(g,left,12,3,2);panel(g,9,12,3,2);}
   if(s==='wrap_shirt'){for(let i=0;i<wide;i++)r(left+i,yy+i*.4,1,.5,hi);r(left,12,wide,.6,hi);}
   if(s==='chemise'){panel(g,3.5,11,9,2.5);r(6,yy,4,.5,hi);r(7,yy+1,2,.5,hi);}
   if(s==='drawstring_top'){panel(g,left-1,yy,2,1.5);panel(g,15-left,yy,2,1.5);r(left,11,wide,.5,hi);r(7,11,1,2,hi);}
   if(s==='long_underrobe'){panel(g,4,11,8,3.5);r(7.5,yy,.5,6,hi);}
   if(s==='long_coat'){panel(g,2.5,11,4,3.5);panel(g,9.5,11,4,3.5);r(6,yy,1,3,hi);r(9,yy,1,3,hi);}
   if(s==='short_jacket'){r(left,11,wide,.7,hi);r(7.5,yy,.5,3,lo);}
   if(s==='over_robe'){panel(g,2,yy,2,4);panel(g,12,yy,2,4);panel(g,3,11,3,3.5);panel(g,10,11,3,3.5);}
   if(s==='tabard'){panel(g,5,12,6,2);r(5,yy,.5,6,hi);r(10.5,yy,.5,6,hi);}
   if(s==='poncho'){cut(g,[[8,yy-1],[1,11],[8,14],[15,11]]);r(6,yy,4,.6,hi);r(4,11,8,.6,hi);}
   if(s==='surcoat'){panel(g,3,11,4,3);panel(g,9,11,4,3);r(7,yy,2,3,hi);}
   if(s==='mantle'){panel(g,2,yy,12,2);panel(g,3,yy+2,10,1);r(6,yy,4,.7,hi);}
   if(s==='travel_duster'){panel(g,2.5,yy,11,1);panel(g,3,11,3,4);panel(g,10,11,3,4);r(6,yy,1,4,hi);r(9,yy,1,4,hi);}
   if(s==='bolero'){panel(g,3,yy,3,2);panel(g,10,yy,3,2);panel(g,3,yy+1,1,3);panel(g,12,yy+1,1,3);}
   if(s==='overgown'||s==='layered_gown'){cut(g,[[5,11],[11,11],[14,15],[2,15]]);r(3,13,10,.7,hi);if(s==='layered_gown')r(2,14.5,12,.5,hi);}
   if(s==='festival_tunic'){panel(g,2.5,yy,2,2.5);panel(g,11.5,yy,2,2.5);cut(g,[[5,11],[11,11],[13,14],[3,14]]);r(3,13.5,10,.5,hi);}
   if(s==='sleeveless_tabard'){panel(g,5,yy,6,6);r(5,13.5,6,.5,hi);}
   if(s==='heraldic_surcoat'){panel(g,4,11,3,3);panel(g,9,11,3,3);r(7,yy,2,3,hi);r(5,yy+1,6,1,hi);}
   if(s==='long_tabard'){panel(g,5.5,yy,5,7);r(5.5,14.5,5,.5,hi);}
   if(s==='wrapped_sash'){for(let i=0;i<wide;i++)panel(g,left+i,yy+i*.4,1,1.5);panel(g,10,11,2,4);}
   if(s==='ceremonial_robe'){panel(g,2,yy,2,4);panel(g,12,yy,2,4);panel(g,2,11,12,4);r(2,14,12,1,hi);}
   if(s==='apron_tunic'){panel(g,6,yy,4,3);panel(g,4,11,8,3);r(4,11,8,.7,hi);}
   if(s==='split_tunic'){panel(g,4,11,3,3);panel(g,9,11,3,3);r(7.5,yy,.5,3,hi);}
   if(s==='shoulder_stole'){panel(g,4,yy,2,6);panel(g,10,yy,2,6);r(4,13.5,2,.5,hi);r(10,13.5,2,.5,hi);}
   c.restore();
  }
  for(const g of rows('head')){
   if(customGear(g))continue;
   c.save();headTransform();const co=color(g),s=shape(g),hi=trim(g),lo=dollTint(co,-.45),yy=top;
   if(['headwrap','kerchief','veil','cowl','ear_wrap','snood','coif_cap'].includes(s)){
    if(s==='ear_wrap'){panel(g,5,yy,6,1);panel(g,4.5,yy+1,1.5,1.5);panel(g,10,yy+1,1.5,1.5);}
    else if(s==='headwrap'){panel(g,5,yy-1,6,2);r(5,yy,6,.5,hi);r(8,yy-1,.5,2,hi);}
    else if(s==='kerchief'){cut(g,[[5,yy-1],[11,yy-1],[10,yy+3],[5,yy+1]]);r(10,yy+2,2,1,hi);}
    else if(s==='veil'){panel(g,4.5,yy-1,7,1);panel(g,4.5,yy,1,6);panel(g,10.5,yy,1,6);r(4,yy+5,8,.5,hi);}
    else if(s==='cowl'){panel(g,4.5,yy-1.5,7,2);panel(g,4.5,yy,1.5,4);panel(g,10,yy,1.5,4);panel(g,5,yy+3.5,6,2);}
    else if(s==='snood'){panel(g,5.5,yy-1,5,1);panel(g,10,yy,2,4);r(10,yy+3,2,.5,hi);}
    else{panel(g,5.5,yy-1,5,1);r(5.5,yy,1,3,co);r(9.5,yy,1,3,co);r(5.5,yy+3,.5,2,hi);r(10,yy+3,.5,2,hi);}
   }else 
if(['crown','circlet','tiara','diadem'].includes(s)||g.kind==='crown'){
    panel(g,5,yy-1,6,1);for(const xx of s==='circlet'?[7]:[5,7,10])r(xx,yy-(s==='tiara'?2:3),1,s==='tiara'?1:2,co);r(7.5,yy-1,.7,.7,hi);
   }else if(['hood','coif'].includes(s)||g.kind==='hood'){
    panel(g,5,yy-1,6,2);panel(g,5,yy,1,4);panel(g,10,yy,1,4);if(s==='coif')r(5,yy+3,6,1,hi);else{panel(g,4,yy+3,2,2);panel(g,10,yy+3,2,2);}
   }else if(g.kind==='hat'||['cap','beret','bonnet','turban','wide_hat','pointed_hat','feather_hat','top_hat','tricorn','flat_cap','beanie','pillbox','sun_hat','wide_brim_hat'].includes(s)){
    if(['pointed_hat','wizard_hat'].includes(s)){cut(g,[[8,yy-4],[5,yy],[11,yy]]);r(4,yy,8,.7,co);}
    else if(s==='beret'){panel(g,4.5,yy-1.5,7,1.5);r(5,yy,6,.5,lo);r(8,yy-2,1,.5,co);}
    else if(s==='turban'){panel(g,5,yy-2,6,3);r(6,yy-1,5,.5,hi);r(5,yy,5,.5,hi);}
    else if(['wide_hat','sun_hat','wide_brim_hat'].includes(s)){panel(g,6,yy-2,4,2);r(3,yy,10,1,co);}
    else if(['top_hat','stovepipe','tall_hat'].includes(s)){panel(g,6,yy-4,4,4);r(4,yy,8,.7,co);r(6,yy-1,4,1,hi);}
    else if(s==='tricorn'){cut(g,[[3,yy],[5,yy-2],[8,yy-1],[11,yy-2],[13,yy]]);r(5,yy,6,.5,hi);}
    else if(s==='bonnet'){panel(g,5,yy-2,6,2);r(5,yy,1,3,co);r(10,yy,1,3,co);r(6,yy+3,4,.5,hi);}
    else if(s==='feather_hat'){panel(g,5,yy-2,6,2);r(4,yy,8,.7,co);r(10,yy-4,.7,3,hi);r(10.7,yy-3,.7,1,hi);}
    else if(['flat_cap','flat_hat'].includes(s)){panel(g,5,yy-1.5,6,1.5);r(8,yy,5,.6,co);}
    else if(s==='round_hat'){panel(g,5.5,yy-2,5,2);r(4.5,yy,7,.6,co);r(5.5,yy-2.5,5,.5,co);}
    else if(s==='floppy_hat'){panel(g,5,yy-2,5,2);panel(g,4,yy-3,4,1);r(3,yy,10,.7,co);r(3,yy+.7,2,.5,co);}
    else if(s==='sailor_hat'){panel(g,5,yy-1.5,6,1.5);r(4.5,yy,7,1,hi);r(4.5,yy-1,.5,2,hi);r(11,yy-1,.5,2,hi);}
    else if(s==='pillbox'){panel(g,5.5,yy-2,5,2);r(5.5,yy-1,5,.5,hi);}
    else if(s==='beanie'){panel(g,5.5,yy-2,5,2);r(5,yy,6,1,hi);r(7.5,yy-3,1,1,co);}
    else{panel(g,5.5,yy-1.5,5,1.5);r(5,yy,6,.6,hi);if(s==='soft_cap')r(7,yy-2,2,.5,co);}
   }else{
    panel(g,5,yy-1,6,2);panel(g,5,yy,1,3);panel(g,10,yy,1,3);
    if(s==='nasal_helm'){r(7.5,yy,1,3,hi);}
    else if(s==='visored_helm'){panel(g,6,yy+1,4,2);r(6,yy+1,4,.5,lo);r(6.5,yy+2,3,.4,hi);}
    else if(s==='crested_helm'){r(7,yy-3,2,3,hi);r(8,yy-4,2,1,co);}
    else if(s==='cheek_helm'){panel(g,5,yy+2,2,2);panel(g,9,yy+2,2,2);}
    else if(s==='gorget_helm'){panel(g,5,yy+3,6,2);r(6,yy+3,4,.5,hi);}
    else if(s==='full_helm'){panel(g,5,yy,6,4);r(6,yy+1,4,.6,lo);for(let x=6;x<10;x++)r(x,yy+2.5,.5,.5,lo);}
    else if(s==='open_helm'){r(6,yy-1,4,.6,hi);}
    else{r(7,yy+1,2,.7,lo);}
   }
   c.restore();
  }
  for(const g of rows('legs')){
   if(customGear(g))continue;
   const s=shape(g),hi=trim(g),co=color(g),lo=dollTint(co,-.35);
   if(['wrap_skirt','pleated_skirt','battle_skirt'].includes(s)){
    cut(g,[[5,11],[11,11],[13,14],[3,14]]);
    if(s==='pleated_skirt')for(let x=4;x<13;x+=1.5)r(x,12,.5,2,hi);
    else if(s==='wrap_skirt'){r(7,11,1,3,hi);r(3,14,5,.5,co);}
    else{r(5,12,1,2,hi);r(8,12,1,2,hi);r(11,12,1,2,hi);}
   }else for(const [i,xx] of [5,9].entries()){
    if(s==='greaves'){panel(g,xx,13,2,2);r(xx+.5,13,.5,2,hi);}
    else if(s==='half_greaves'){panel(g,xx,13,2,1);r(xx+.5,12.5,1,.5,co);}
    else if(s==='tassets'){panel(g,xx-.5,11,3,2);r(xx,12.5,2,.5,hi);}
    else if(s==='cuisses'){panel(g,xx,11,2,2);panel(g,xx-.5,12.5,3,1);}
    else if(s==='knee_guards'){panel(g,xx-.5,12,3,1.5);r(xx,12.5,2,.5,hi);}
    else if(s==='splint_legs'){panel(g,xx,11.5,2,3.5);r(xx+.75,11.5,.5,3.5,hi);}
    else if(s==='riding_legs'||s==='breeches'){panel(g,xx-.5,11,3,2);panel(g,xx,13,2,s==='breeches'?.7:2);}
    else if(s==='wide_trousers'){panel(g,xx-1,11,3.5,4);r(xx,11,.5,4,lo);}
    else if(s==='divided_skirt'){panel(g,xx-1,11,3.5,3);r(xx-1,13.5,3.5,.5,hi);}
    else if(s==='culottes'){panel(g,xx-.5,11,3,2.5);r(xx-.5,13,3,.5,hi);}
    else if(s==='shorts'){panel(g,xx-.5,11,3,1.5);r(xx-.5,12,3,.5,hi);}
    else if(s==='gaiters'){panel(g,xx,13,2,2);for(let y=13;y<15;y+=.7)r(xx+1,y,.5,.3,hi);}
    else if(s==='chausses'){panel(g,xx,11,2,4);r(xx,11.5,2,.5,hi);r(xx+.75,10.5,.5,1,co);}
    else if(s==='hose'){panel(g,xx+.25,11,1.5,4);}
    else if(s==='trousers'){panel(g,xx-.25,11,2.5,4);r(5,11,6,.5,hi);}
    else{panel(g,xx,12,2,3);}
   }
  }
  for(const g of rows('feet')){
   if(customGear(g))continue;
   const s=shape(g),hi=trim(g),co=color(g),lo=dollTint(co,-.35);
   for(const [i,xx] of [4,9].entries()){
    if(['sandals','strap_sandals'].includes(s)){r(xx,15.5,3,.5,co);r(xx+.5,14.5,.5,1,co);r(xx+2,14.5,.5,1,co);if(s==='strap_sandals')r(xx,15,3,.5,hi);}
    else if(s==='slippers'){panel(g,xx,15,3,1);r(xx+.5,14.5,1.5,.5,co);}
    else if(s==='dance_shoes'){panel(g,xx,15.25,3,.75);r(xx+1,14.5,.5,1,hi);}
    else if(s==='pointed_boots'||s==='ankle_shoes'){panel(g,xx,14,2.5,2);r(xx+(i===0?-1:2.5),15.5,1,.5,co);if(s==='pointed_boots')panel(g,xx+.5,13,2,1);}
    else if(s==='high_boots'||s==='high_soft_boots'){panel(g,xx+.5,12,2,3);panel(g,xx,15,3,1);if(s==='high_soft_boots')for(let y=12.5;y<15;y++)r(xx+1.5,y,.5,.5,hi);}
    else if(s==='riding_boots'){panel(g,xx+.5,12.5,2,3);r(xx+(i===0?0:2.5),12,.5,2,co);r(xx,15,3,1,co);r(xx+1,15.5,2,.5,lo);}
    else if(s==='marching_boots'||s==='walking_shoes'){panel(g,xx, s==='marching_boots'?13.5:14.5,3,s==='marching_boots'?2:1);r(xx,15.5,3,.5,lo);r(xx+1,14.5,1,.5,hi);}
    else if(s==='sabatons'){panel(g,xx,14,3,2);for(let x=xx+.5;x<xx+3;x++)r(x,15,.4,1,hi);}
    else if(s==='split_boots'){panel(g,xx+.5,13.5,2,2);r(xx,15,1,1,co);r(xx+1.5,15,1.5,1,co);}
    else if(s==='cuffed_boots'||s==='soft_boots'){panel(g,xx+.5,13,2,3);panel(g,xx,13,3,1);r(xx,15,3,1,co);if(s==='soft_boots')r(xx,13,3,.5,hi);}
    else if(s==='overboots'){panel(g,xx-.5,13.5,3.5,2.5);r(xx-.5,15.5,3.5,.5,hi);}
    else if(s==='wrap_shoes'){panel(g,xx,15,3,1);r(xx+.5,14,2,.5,hi);r(xx+.5,14.5,2,.5,co);}
    else if(s==='moccasins'){panel(g,xx-.25,14.5,3.25,1.5);r(xx+.5,15,1.5,.5,hi);r(xx-.5,14.5,.5,.5,co);}
    else if(s==='travel_spats'){panel(g,xx,13.5,3,2);r(xx+.5,15.5,2,.5,lo);for(let y=14;y<15.5;y+=.6)r(xx+2,y,.4,.4,hi);}
    else{panel(g,xx,14,3,2);}
   }
  }
  if(doll.workwear&&!gearOnly){
   const y=top+4,role=doll.occupation,apron='#c4ac83',thread='#e5ce9b',leather='#68513f';
   if(role==='producer'||role==='chef'){
    const shade=role==='chef'?'#d8d7bd':apron;
    r(6,y,4,5,shade);r(5,11,6,3,shade);r(6,y,1,2,leather);r(9,y,1,2,leather);
    r(7,11,2,1,leather);r(7,11,1,.5,thread);
   }else if(role==='guard'||role==='royalty'){
    r(6,y,4,6,role==='guard'?'#405965':'#67506d');r(6,y,4,.5,thread);
    r(7,10.5,2,.5,thread);r(7.5,10,.6,2,thread);if(role==='royalty'){r(left,y,wide,1,'#ded8c8');r(8,y,.7,.6,leather);}
   }else if(role==='pupil'||role==='merchant'||role==='driver'){
    for(let i=0;i<5;i++)r(5+i,y+.6*i,1,.6,leather);
    r(9,11,role==='merchant'?3:2.5,2,leather);r(9,11,2.5,.5,thread);
    if(role==='pupil'){r(9.5,11.5,1.5,1,'#4e6a70');r(10,12,1,.3,'#dadbc7');}
   }else if(role==='teacher'||role==='healer'){
    r(5,y,1.2,5,role==='healer'?'#dfd9c4':'#89788d');r(10,y,1.2,5,role==='healer'?'#dfd9c4':'#89788d');r(5,12,1.2,.5,thread);r(10,12,1.2,.5,thread);
   }else if(role==='performer'){r(left,y,wide,1.5,'#cd9961');r(7,11,4,.75,'#cd9961');}
   else if(role==='hunter'||role==='farmer'){r(left,11,wide,.7,leather);r(left+1,11,1,1,thread);}
  }
  for(const g of rows('hands')){
   if(customGear(g))continue;
   const s=shape(g),hi=trim(g),co=color(g),lo=dollTint(co,-.35),yy=top+7;
   for(const [i,xx] of [left-1,15-left].entries()){
    if(s==='bracers'||s==='wristguards'||s==='wrist_wraps'){panel(g,xx,yy-1.5,2,s==='bracers'?2:1);if(s==='wrist_wraps')r(xx,yy-1.2,2,.35,hi);}
    else if(s==='vambraces'){panel(g,xx-.5,yy-2,2.5,2.5);r(xx-.5,yy-2,2.5,.5,hi);}
    else if(s==='gauntlets'||s==='lobster_gauntlets'){panel(g,xx,yy,2,2);panel(g,xx-.5,yy-1.5,3,1.5);if(s==='lobster_gauntlets')for(let y=yy;y<yy+2;y+=.7)r(xx,y,2,.35,hi);}
    else if(s==='mitts'||s==='work_mitts'){panel(g,xx-.5,yy,2.5,2);r(xx+2,yy+.5,.5,1,co);if(s==='work_mitts')r(xx-.5,yy,2.5,.5,hi);}
    else if(s==='knuckle_guards'){panel(g,xx,yy+.5,2,.75);r(xx,yy,1,.5,hi);}
    else if(s==='duelist_gloves'){panel(g,xx,yy,2,2);if(i)panel(g,xx-.5,yy-2,3,2);}
    else if(s==='forearm_wraps'){panel(g,xx,yy-2,2,3);for(let y=yy-1.5;y<yy+1;y++)r(xx,y,2,.5,hi);}
    else if(s==='fingerless_gloves'){panel(g,xx,yy,2,1);r(xx+.5,yy+1,.5,.7,co);}
    else if(s==='long_gloves'){panel(g,xx,yy-2,1.5,4);}
    else if(s==='handwarmers'){panel(g,xx-.5,yy-1,2.5,2);r(xx+1.5,yy,.5,.5,lo);}
    else if(s==='cuffed_gloves'){panel(g,xx,yy,2,2);panel(g,xx-.5,yy-1,3,1);r(xx-.5,yy-1,3,.5,hi);}
    else if(s==='lace_cuffs'){panel(g,xx-.5,yy-1,3,1.5);for(let x=xx-.5;x<xx+2.5;x++)r(x,yy+.5,.5,.5,hi);}
    else if(s==='palm_wraps'){r(xx,yy+.5,2,.5,co);r(xx+.5,yy,1,1.5,hi);}
    else if(s==='sleeve_guards'){panel(g,xx-.5,yy-2,3,2);r(xx-.5,yy-2,3,.5,hi);r(xx-.5,yy-.5,3,.5,hi);}
    else{panel(g,xx,yy,2,2);if(s==='dress_gloves')r(xx,yy,2,.5,hi);}
   }
  }
  for(const g of rows('weapon')){
   if(customGear(g))continue;
   const co=color(g),kind=g.kind,s=shape(g),hi=trim(g),lo=dollTint(co,-.4);
   if(kind==='bow'){r(13,4,1,10,'#b99a69');r(14,6,1,6,co);r(12,4,.5,10,hi);}
   else if(kind==='lute'){panel(g,11,9,4,4);r(13,4,1,7,hi);r(12,10,2,2,'#534c3a');}
   else if(s==='hand_axe'){r(14,7,1,8,'#a99064');cut(g,[[14,5],[11,4],[10,5],[10,8],[13,8],[14,7]]);r(10,5,.5,3,hi);}
   else if(s==='flanged_mace'){r(14,7,1,8,'#a99064');panel(g,13,4,3,4);r(12.5,5,.5,2,hi);r(14,3,1,6,hi);}
   else if(s==='war_pick'){r(14,6,1,9,'#a99064');r(11,5,5,1,co);r(11,6,1,2,co);r(15,4,1,1,hi);}
   else if(['axe','hammer','mace','pick'].includes(kind)){r(14,5,1,10,'#a99064');if(kind==='axe')panel(g,11,5,4,3);else if(kind==='hammer'){panel(g,12,4,3,3);r(15,5,1,1,hi);}else if(kind==='pick')panel(g,11,5,5,1);else panel(g,13,4,3,3);}
   else if(kind==='staff'){panel(g,14,2,1,13);if(s==='quarterstaff'){r(14,2,1,1,hi);r(14,14,1,1,hi);r(14,7,1,3,lo);}else panel(g,13,2,3,2);}
   else if(kind==='spear'){r(14,5,1,10,'#a99064');cut(g,[[14.5,1],[13,4],[14.5,6],[16,4]]);r(14.25,2,.5,3,hi);}
   else if(s==='falchion'){cut(g,[[14,3],[16,2],[16,7],[15,11],[14,11]]);r(15,4,.5,6,hi);r(13,11,3,1,hi);r(14,12,1,3,'#887251');}
   else if(s==='rapier'){r(14.25,2,.5,10,co);r(13,11,3,.5,hi);r(13,11,.5,2,hi);r(13,12.5,2.5,.5,hi);r(14,12,1,3,'#887251');}
   else if(['sword','dagger'].includes(kind)){const y=kind==='dagger'?8:3;cut(g,[[14.5,y],[15,y+1],[15,11],[14,11],[14,y+1]]);r(14, y+1,.5,10-y,hi);r(13,11,3,1,hi);r(14,12,1,3,'#887251');}
   else{panel(g,13,9,2,4);r(14,12,1,2,'#887251');}
  }
  if(!gearOnly&&doll.accent){
   const ink=dollColors[doll.accent.color]||'#b1a17b';
   if(doll.accent.mark==='collar'){r(left+1,top+4,wide-2,.6,ink);r(7.5,top+4,1,1.8,ink);}
   if(doll.accent.mark==='sash')for(let i=0;i<wide;i++)r(left+i,top+4+i*.31,1,.8,ink);
   if(doll.accent.mark==='cuffs'){r(left-1,top+7,1.5,.7,ink);r(15-left,top+7,1.5,.7,ink);}
  }
  for(const g of rows('offhand')){
   if(customGear(g))continue;
   const s=shape(g),co=color(g),hi=trim(g),lo=dollTint(co,-.3);
   const disc=(cx,cy,rx,ry,col)=>{c.save();c.fillStyle=col;c.beginPath();c.ellipse(cx,cy,rx,ry,0,0,Math.PI*2);c.fill();if(col===co){c.clip();panel(g,cx-rx,cy-ry,rx*2,ry*2);}c.restore();};
   if(['buckler','spiked_buckler','targe','round_shield','oval_shield'].includes(s)){
    const big=s==='round_shield',oval=s==='oval_shield',cx=2,cy=10.5,rx=big?3:s==='targe'?2.3:2,ry=oval?4:big?3:2;
    disc(cx,cy,rx,ry,hi);disc(cx,cy,rx-.5,ry-.5,co);disc(cx,cy,s==='spiked_buckler'?1:.6,s==='spiked_buckler'?1:.6,hi);if(s==='targe'){disc(cx,cy,1.5,1.5,lo);disc(cx,cy,1,1,hi);}if(s==='spiked_buckler')r(1.5,9,1,2,lo);
   }else if(s==='kite_shield'||s==='heater_shield'){
    const base=s==='kite_shield'?15:13;cut(g,[[0,7],[4,7],[5,9],[2,base],[-1,9]]);r(1.5,8,1,base-9,hi);r(0,8,4,.5,hi);
   }else if(s==='pavise'){panel(g,-.5,8,5,7);panel(g,.5,7,3,1);r(1.5,8,1,7,hi);}
   else if(s==='tower_shield'){panel(g,-.5,7,5,8);r(-.5,7,5,.7,hi);r(-.5,14.3,5,.7,hi);r(0,7,.5,8,lo);}
   else if(s==='scalloped_shield'){cut(g,[[0,7],[1,8],[2,7],[3,8],[4,7],[4,11],[2,14],[0,11]]);r(1.5,9,1,3,hi);}
   else{panel(g,0,8,4,5);r(1,9,2,3,g.kind==='shield'?lo:hi);if(g.kind==='shield')r(1,10,2,1,hi);}
  }
  for(const g of rows('charm')){
   if(customGear(g))continue;
   const s=shape(g),co=color(g),hi=trim(g),yy=top+5,lo=dollTint(co,-.4);
   const disc=(xx,yy,rx,ry,col)=>{c.save();c.fillStyle=col;c.beginPath();c.ellipse(xx,yy,rx,ry,0,0,Math.PI*2);c.fill();if(col===co){c.clip();panel(g,xx-rx,yy-ry,rx*2,ry*2);}c.restore();};
   if(['brooch','rosette'].includes(s)){disc(10,yy,.95,.95,co);if(s==='brooch'){disc(10,yy,.5,.5,lo);r(9,yy,2,.4,hi);}else{for(const [x,y] of [[9,yy],[11,yy],[10,yy-1],[10,yy+1]])disc(x,y,.5,.5,hi);}}
   else if(s==='torc'){r(6,yy-1,.5,2,co);r(9.5,yy-1,.5,2,co);r(6,yy+.5,1.5,.5,co);r(8.5,yy+.5,1.5,.5,co);r(7,yy,.5,1,hi);r(8.5,yy,.5,1,hi);}
   else if(s==='bead_strand'||s==='necklace'){for(const [x,y] of [[6,yy-1],[6.5,yy],[7,yy+.5],[8,yy+1],[9,yy+.5],[9.5,yy],[10,yy-1]])disc(x,y,s==='necklace'?.25:.4,.4,co);if(s==='necklace')r(7.5,yy+1,1,1,hi);}
   else{
    r(6.5,yy-1,.5,1.5,hi);r(9,yy-1,.5,1.5,hi);r(7,yy,.5,.5,hi);r(8.5,yy,.5,.5,hi);
    if(s==='pendant'){cut(g,[[8,yy],[9,yy+1.5],[8,yy+2],[7,yy+1.5]]);}
    else if(s==='medallion'){disc(8,yy+1,1.4,1.4,hi);disc(8,yy+1,1,1,co);}
    else if(s==='locket'){disc(8,yy+1,1,1.5,co);r(8,yy,.4,2,hi);}
    else if(s==='talisman'){panel(g,6.5,yy,3,2);r(7,yy+.5,2,.5,hi);}
    else if(s==='seal'){cut(g,[[8,yy],[9.5,yy+1.5],[8,yy+3],[6.5,yy+1.5]]);r(7.5,yy+1,1,1,hi);}
    else if(s==='prayer_wheel'){disc(8,yy+1,1.5,1.5,co);r(6.5,yy+.75,3,.5,hi);r(7.75,yy-.5,.5,3,hi);}
    else if(s==='knot_charm'){disc(7.3,yy+.5,.8,.8,co);disc(8.7,yy+.5,.8,.8,hi);disc(8,yy+1.5,.8,.8,co);r(7.5,yy+.5,1,1,lo);}
    else{panel(g,7,yy,2,2);}
   }
  }
  if(gear.some(g=>g.kind==='generic'))r(10,11,2,2,'#d3c6a3');
  if(self){r(6,0,4,1,'#fff4c5');r(7,1,2,1,'#fff4c5');}
  c.restore();
 }
 function drawRest(c,a,x,y,size,self){const custom=customArt(a.pixel_art);if(custom){c.drawImage(custom,Math.round(x-size/2),Math.round(y-size/2),size,size);return;}if(a.subject&&window.ExpanseSpriteSheets?.creature(c,a.subject,x,y,size))return;if(a.paperdoll?.version===1)playerActor(c,a,x,y,size,self);else actor(c,a,x,y,size,self);}
 function drawActor(c,a,x,y,size,self){
  if(a.combat_pose&&window.ExpanseCombatArt?.draw(c,a,x,y,size,self,drawRest,playerActor,customArt))return;
  const kind=a.activity?.kind;
  if(kind==='sleep'){
   c.save();c.translate(x,y);c.rotate(-Math.PI/2);c.scale(.83,.86);
   drawRest(c,a,0,0,size,self);c.restore();
  }else if(window.ExpanseCombatArt?.drawActivity(c,a,x,y,size,drawRest)){
   if(['work','study','harvest','trade','meal','music','social'].includes(kind))return;
  }else drawRest(c,a,x,y,size,self);
  window.ExpanseSpriteSheets?.activity(c,kind,x,y,size);
 }
 function campMarker(c,actions,x,y,zoom){
  if(!actions?.tent)return;
  c.save();c.translate(Math.round(x-12*zoom),Math.round(y-12*zoom));c.scale(zoom,zoom);
  const r=(x,y,w,h,col)=>{c.fillStyle=col;c.fillRect(x,y,w,h);};
  for(let i=0;i<7;i++)r(4-Math.floor(i/2),14+i,2+Math.floor(i/2)*2,1,i%2?'#c0aa77':'#a99566');
  r(4,17,2,4,'#3b4c43');r(0,21,11,1,'#6e7055');
  if(actions.campfire){r(18,20,6,1,'#826448');r(19,21,4,1,'#ac8052');r(20,15,2,6,'#cf783f');r(19,17,4,3,'#de9c4c');r(21,14,1,4,'#e9b858');r(21,18,1,3,'#f0d18b');}
  c.restore();
 }
 const terrainKey=[['plains','Plains'],['forest','Forest'],['rainforest','Rainforest'],['desert','Desert'],['mountain','Mountain'],['valley','Valley'],['wetland','Wetland'],['coast','Shore / coast'],['ocean','Ocean'],['town','Settlement'],['cave','Cave'],['road','Road'],['water','Freshwater'],['interior','Interior floor'],['building','Building exterior'],['snow','Snow (authored)'],['unknown','Unspecified']];
 function terrainLegend(){
  const details=make('details','atlas-terrain-key'),grid=make('div','atlas-terrain-grid');details.append(make('summary','','Terrain key'));
  for(const [kind,label] of terrainKey){const item=make('span','atlas-terrain-item'),icon=make('canvas');item.dataset.terrain=kind;icon.width=icon.height=24;icon.setAttribute('aria-hidden','true');icon.getContext('2d').drawImage(tile(kind,0),0,0);item.append(icon,make('span','',label));grid.append(item);}
  details.append(grid);return details;
 }
 function surfaceLegend(){
  const details=make('details','atlas-terrain-key atlas-surface-key'),grid=make('div','atlas-terrain-grid');details.append(make('summary','','Working land key'));
  const examples=[...['house','rental','business','farm','ranch','recreation','hunting','reserve'].map(k=>[k,{land_use:k}]),...['planted','growing','mature','harvested','dormant'].map(stage=>['Grain · '+stage,{resources:[{kind:'crop',stage,color_key:'grain'}]}]),...['available','depleted','recovering'].map(stage=>['Ore · '+stage,{resources:[{kind:'mine',stage,color_key:'ore'}]}])];
  for(const [label,surface] of examples){const item=make('span','atlas-surface-item'),icon=make('canvas');icon.width=icon.height=24;icon.setAttribute('aria-hidden','true');const c=icon.getContext('2d');c.drawImage(tile('plains',0),0,0);drawSurface(c,{surface},0,0,24);item.append(icon,make('span','',label));grid.append(item);}
  details.append(grid);return details;
 }
 // Counts are observation data, not a default for every explored room.
 window.addEventListener('expanse:sprite-ready',()=>{for(const s of views.values())s.schedule();if(window.latestMap){window.ExpanseCharacter?.render(window.latestMap);window.renderRoomPanel?.(window.latestMap);}});
 const npcCount=t=>!t.exterior&&Number.isSafeInteger(t.npc_count)&&t.npc_count>=0?t.npc_count:null;
 function npcText(t){const n=npcCount(t);return n===null?' · NPC count unknown':' · '+n+' NPC'+(n===1?'':'s')+' (living; includes creatures and companions, excludes players)';}
 function coordinateText(value){
  if(!value)return '';
  if(value.tile){
   const t=value.tile;
   return 'X '+t.x+' m · Y '+t.y+' m · Z '+t.z+' m · Latitude '+t.lat.toFixed(8)+'° · Longitude '+t.lon.toFixed(8)+'° · Altitude '+t.alt+' m';
  }
  const local=value.local,world=value.world;
  const layout=local?'Layout X '+local.x+', Y '+local.y+', Z '+local.z+(local.source==='layout'?' (automatic)':''):'';
  const geographic=world?'World X '+world.x+', Y '+world.y+' '+(world.units||'world units')+(world.region?' · '+world.region:''):'World position not placed';
  return [layout,geographic].filter(Boolean).join(' · ');
 }
 function nearby(t){return t.visibility==='visible'&&t.visited===false;}
 function visitText(t){return t.current?' · Your current room':nearby(t)?'':' · Explored room';}
 function roomText(t){return t.name+(nearby(t)?' · Visible nearby · Not yet visited':'')+' · '+((t.exterior||Array.isArray(t.roof_joins))?'Building exterior':t.terrain.replaceAll('_',' '))+(t.facility_landmark?' · '+t.facility_landmark.label:'')+surfaceText(t)+npcText(t)+(t.coordinates?' · '+coordinateText(t.coordinates):'');}
 function shortTipText(value,limit){const chars=Array.from(String(value||'').replace(/\s+/g,' ').trim());return chars.length>limit?chars.slice(0,limit-1).join('')+'…':chars.join('');}
 function roomPreview(t,named){
  const count=npcCount(t),parts=[];
  if(hasImpacts(t))parts.push('! Conditions');
  if(count!==null)parts.push(count+' NPC'+(count===1?'':'s'));
  if(named)parts.push(t.exterior||Array.isArray(t.roof_joins)?'Building':shortTipText(String(t.terrain||'').replaceAll('_',' '),18));
  return {title:named?shortTipText(t.name,52):'Nearby area',meta:parts.filter(Boolean).join(' · ')};
 }
 function drawNpcCount(c,p,tileSize){
  const n=npcCount(p.tile);if(!n)return;
  // Anchor the whole badge inside its owning tile. A lower gutter made the
  // south-room count look like a separate marker far below the player.
  // Keep readable screen-pixel text; abbreviate only when the tile is narrow.
  const height=14,available=Math.floor(tileSize)-2;
  c.save();c.font='bold 12px system-ui';c.textAlign='center';c.textBaseline='middle';
  let text=n>999?'999+':String(n);
  for(const limit of [99,9])if(Math.ceil(c.measureText(text).width)+2>available&&n>limit)text=limit+'+';
  if(Math.ceil(c.measureText(text).width)+2>available)text='+';
  const width=Math.ceil(c.measureText(text).width)+2,x=Math.round(p.x-tileSize/2+1),y=Math.round(p.y+tileSize/2-height-1);
  // Outline the digits rather than cover the terrain with an opaque plate.
  c.strokeStyle='#071218';c.lineWidth=2;c.lineJoin='round';c.strokeText(text,x+width/2,y+height/2+.5);
  c.fillStyle='#ffffff';c.fillText(text,x+width/2,y+height/2+.5);c.restore();
  p.badge={x,y,width,height};
 }
 function build(host,options){
  const state={host,options,data:null,zoom:1,offset:{x:0,y:0},selected:null,drag:null,positions:[],lastContext:null,frame:0};
  host.classList.add('field-atlas');
  const title=make('div','atlas-heading'),eyebrow=make('span','atlas-eyebrow','FIELD ATLAS'),context=make('strong','atlas-context','Uncharted'),floor=make('span','atlas-floor');title.append(eyebrow,context,floor);
  const coordinateStatus=make('div','atlas-coordinates');coordinateStatus.setAttribute('aria-label','Current room coordinates');coordinateStatus.hidden=true;coordinateStatus.title='Survey coordinates in metres. X increases eastward, Y northward and Z upward.';
  const locationStatus=make('div','atlas-current-room');locationStatus.hidden=true;
  const sightStatus=make('div','atlas-sight-status');sightStatus.hidden=true;sightStatus.setAttribute('role','status');sightStatus.setAttribute('aria-live','polite');
  const toolbar=make('div','atlas-tools'),follow=make('button','atlas-button','Recenter'),zoom=make('select','atlas-zoom');follow.type='button';follow.title='Follow your current room again';zoom.setAttribute('aria-label','Map tile size');
  for(const [v,label] of [['auto','Automatic'],[.75,'Small'],[1,'Standard'],[1.5,'Large'],[2,'Extra large']])zoom.append(new Option(label,v));zoom.value=window.ExpanseDisplay?.values.tiles||'auto';
  toolbar.append(follow,zoom,make('span','atlas-help',options.designer?'Drag to pan · select to inspect':'Click to walk · Shift-click to inspect · drag to pan'));
  const namedTile=t=>options.designer||t.current||t.visited===true||t.visibility==='visited';
  const locations=make('select','atlas-zoom');locations.setAttribute('aria-label','Discovered map locations');locations.setAttribute('aria-describedby',host.id+'-tooltip');toolbar.append(locations);
  const viewport=make('div','atlas-viewport'),canvas=make('canvas','atlas-canvas');canvas.tabIndex=0;canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Explored and currently visible terrain map. Select a tile to walk, or select a doorway to enter or leave. Arrow keys pan this view.');
  const tip=make('div','atlas-tip'),empty=make('div','atlas-empty','Create or resume a character to chart your surroundings.');tip.hidden=true;tip.id=host.id+'-tooltip';tip.setAttribute('role','tooltip');const arrival=make('div','atlas-arrival');arrival.hidden=true;arrival.setAttribute('role','status');viewport.append(canvas,tip,empty);
  const bubble=make('div','atlas-speech');bubble.hidden=true;bubble.setAttribute('role','status');viewport.append(bubble);state.bubble=bubble;
  const positionHeader=make('div','atlas-position-header'),sightBadge=make('div','atlas-sight-badge');sightBadge.hidden=true;positionHeader.append(locationStatus,sightBadge,arrival);
  const inspect=make('div','atlas-inspect',options.designer?'Select a tile to inspect.':'Click a tile to walk there, or select the marked doorway for a passage.');inspect.setAttribute('role','status');
  const impactStatus=make('div','atlas-impact-status');impactStatus.hidden=true;impactStatus.setAttribute('role','status');impactStatus.setAttribute('aria-live','polite');
  const legend=make('div','atlas-key');for(const [style,label] of [['portal','Door / passage'],['self',options.designer?'Selected room':'You']]){const item=make('span');item.append(make('i','atlas-key-'+style),document.createTextNode(label));legend.append(item);}
  const mapBuild=make('span','atlas-map-build');legend.append(mapBuild);state.mapBuild=mapBuild;
  const countKey=make('span','atlas-npc-key','Numbers = living NPCs (creatures and companions included; players excluded). A + marks an abbreviated count; hover or select for the exact number.');countKey.style.cssText='font-size:12px;line-height:1.5;color:#e4eeee';legend.append(countKey);
  const impactKey=make('span','atlas-impact-key','! = Damage or temporary closure. Inspect for condition and recovery.');impactKey.hidden=true;legend.append(impactKey);
  const actors=make('div','atlas-actors');actors.setAttribute('aria-label','People and creatures in this room');
  const accessible=make('div','atlas-accessible');accessible.id=host.id+'-accessible';canvas.setAttribute('aria-describedby',accessible.id+' '+tip.id);host.replaceChildren(...(options.designer?[title,positionHeader,sightStatus,coordinateStatus,toolbar,viewport]:[positionHeader,toolbar,viewport,title,sightStatus,coordinateStatus]),inspect,impactStatus,legend,terrainLegend(),routeLegend(),surfaceLegend(),geologyLegend(),actors,accessible);
  Object.assign(state,{locations,namedTile,sightBadge,arrival,canvas,viewport,tip,empty,inspect,impactStatus,impactKey,context,floor,coordinateStatus,locationStatus,sightStatus,actors,accessible,follow,zoomControl:zoom});
  function schedule(){if(!state.frame)state.frame=requestAnimationFrame(()=>{state.frame=0;draw(state);});}
  state.schedule=schedule;
  follow.onclick=()=>{state.offset={x:0,y:0};schedule();};
  zoom.onchange=()=>{if(window.ExpanseDisplay)window.ExpanseDisplay.choose('tiles',zoom.value);else state.zoom=Number(zoom.value)||1;schedule();};
  window.addEventListener('expanse:display',()=>{
   const value=window.ExpanseDisplay.values.tiles;
   if(zoom.value!==value)zoom.value=value;
   schedule();
  });
  function hideTip(){tip.hidden=true;tip.textContent='';state.tipId=null;}
  // Hoverable tooltip must not eat selection of the tile underneath it.
  tip.onpointerdown=e=>{const init={bubbles:true,pointerId:e.pointerId,pointerType:e.pointerType,isPrimary:e.isPrimary,button:e.button,buttons:e.buttons,clientX:e.clientX,clientY:e.clientY};hideTip();canvas.dispatchEvent(new PointerEvent('pointerdown',init));};
  function showTip(p){const tile=p&&state.data?.tiles.find(t=>t.id===p.tile.id);if(!tile||(!namedTile(tile)&&npcCount(tile)===null)){hideTip();return;}const preview=roomPreview(tile,namedTile(tile)),text=preview.title+'\n'+preview.meta;if(!tip.hidden&&state.tipId===tile.id&&tip.textContent===text)return;state.tipId=tile.id;tip.replaceChildren(make('strong','atlas-tip-title',preview.title),document.createTextNode('\n'),make('span','atlas-tip-meta',preview.meta));tip.hidden=false;tip.style.left=Math.max(4,Math.min(viewport.clientWidth-tip.offsetWidth-4,p.x+15))+'px';tip.style.top=Math.max(4,Math.min(viewport.clientHeight-tip.offsetHeight-4,p.y-30))+'px';}
  state.showTip=showTip;state.hideTip=hideTip;
  function selectKnown(){const tile=state.data?.tiles.find(t=>t.id===locations.value&&namedTile(t));if(!tile){hideTip();return;}state.selected=tile.id;inspect.textContent=roomText(tile)+visitText(tile);showTip(state.positions.find(p=>p.tile.id===tile.id)||{tile,x:8,y:40});schedule();}
  locations.onchange=selectKnown;locations.onfocus=selectKnown;locations.onblur=hideTip;locations.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();hideTip();}};
  function locate(e){const {x,y}=pointerPoint(canvas,e),painted=[...state.positions].reverse();return painted.find(p=>[p.impactBadge,p.badge].some(b=>b&&x>=b.x&&x<b.x+b.width&&y>=b.y&&y<b.y+b.height))||painted.find(p=>x>=p.x-p.radius&&x<p.x+p.radius&&y>=p.y-p.radius&&y<p.y+p.radius);}
  canvas.onpointerdown=e=>{if(e.button!==0||state.drag)return;state.drag={id:e.pointerId,x:e.clientX,y:e.clientY,point:pointerPoint(canvas,e),start:{...state.offset},hit:locate(e),context:state.data?.context?.id,floor:state.data?.floor,character:state.packet?.character?.id,moved:false};canvas.setPointerCapture(e.pointerId);};
  canvas.onpointermove=e=>{if(state.drag&&e.pointerId===state.drag.id){const d=state.drag;d.moved=d.moved||Math.abs(e.clientX-d.x)+Math.abs(e.clientY-d.y)>5;if(!d.moved)return;const p=pointerPoint(canvas,e);state.offset={x:d.start.x+p.x-d.point.x,y:d.start.y+p.y-d.point.y};hideTip();schedule();return;}const p=locate(e);showTip(p);canvas.style.cursor=p?'pointer':'grab';};
  canvas.onpointerleave=e=>{if(e.pointerType!=='touch'&&e.relatedTarget!==tip&&!tip.contains(e.relatedTarget))hideTip();};tip.onpointerleave=e=>{if(e.pointerType!=='touch'&&e.relatedTarget!==canvas)hideTip();};
  canvas.onpointerup=e=>{
   const d=state.drag;if(!d||d.id!==e.pointerId)return;state.drag=null;
   if(d.moved||Math.hypot(e.clientX-d.x,e.clientY-d.y)>5||d.context!==state.data?.context?.id||d.floor!==state.data?.floor||d.character!==state.packet?.character?.id)return;
   const p=d.hit;if(!p){hideTip();return;}
   // Keep the room pressed, even if a confirmed step repaints the map before
   // release. Its old "current" flag must never open the new room's passage.
   const tile={...(state.data.tiles.find(t=>t.id===p.tile.id)||p.tile),current:p.tile.id===state.data.center};
   state.selected=tile.id;inspect.textContent=roomText(namedTile(tile)?tile:{...tile,name:'Nearby area',coordinates:null})+visitText(tile);showTip({...p,tile});options.onSelect?.(tile.id);
   if(!tile.scenery&&!e.shiftKey&&!options.designer&&host.id==='player-visual-map'){
    if(tile.current&&!p.tile.current)window.ExpansePlayerControls?.walkTo?.(tile.id);
    else if(!window.ExpanseStreet?.select(state,tile))window.ExpansePlayerControls?.walkTo?.(tile.id);
   }
   schedule();
  };
  canvas.onpointercancel=()=>{if(state.drag)state.offset=state.drag.start;state.drag=null;hideTip();schedule();};
  canvas.onfocus=()=>{const tile=state.data?.tiles.find(t=>t.id===(state.selected||state.data.center)&&namedTile(t));if(tile)showTip(state.positions.find(p=>p.tile.id===tile.id)||{tile,x:8,y:40});};canvas.onblur=hideTip;
  canvas.onkeydown=e=>{if(!options.designer&&window.ExpansePlayerControls?.usesMovementKey?.(e.code))return;if(e.key==='Escape'){e.preventDefault();hideTip();return;}const vector={ArrowLeft:[32,0],ArrowRight:[-32,0],ArrowUp:[0,32],ArrowDown:[0,-32]}[e.key];if(vector){e.preventDefault();hideTip();state.offset.x+=vector[0];state.offset.y+=vector[1];schedule();}else if(e.key==='Home'){e.preventDefault();follow.click();}};
  new ResizeObserver(()=>{if(state.drag?.moved)state.drag=null;hideTip();schedule();}).observe(viewport);
  if(!options.designer){
   const panel=host.closest('#player-map-panel');
   if(panel){
    const more=make('details','atlas-more'),caption=make('summary','','Map details and legend');more.append(caption);
    more.append(title,sightStatus,coordinateStatus,inspect,impactStatus,legend,...host.querySelectorAll('.atlas-terrain-key'),actors);
    for(const child of [...host.children])if(![positionHeader,toolbar,viewport,accessible].includes(child))more.append(child);
    for(const id of ['map-exits','map-legend']){const el=document.getElementById(id);if(el)more.append(el);}
    const moves=document.getElementById('map-move');if(moves)host.append(moves);
    host.append(more);panel.classList.add('play-map-pane');
   }
  }
  views.set(host.id,state);return state;
 }
 function drawGround(c,tile,banks,left,top,tileSize){
  c.drawImage(terrainTile(tile.terrain,hash(tile.surface_id || tile.id),tile.route_surface),left,top,tileSize,tileSize);
  const art=customArt(tile.pixel_art);
  if(art)c.drawImage(art,left,top,tileSize,tileSize);
  drawShore(c,banks.get(tile.id),left,top,tileSize);
  drawGeology(c,tile,left,top,tileSize);
  drawSurface(c,tile,left,top,tileSize);
  drawFacility(c,tile,left,top,tileSize);
  drawGeologyEffects(c,tile,left,top,tileSize);
  window.ExpanseStreet?.roof(c,tile,left,top,tileSize);
  
 }
 function drawWatchScene(canvas,scene){
  const w=canvas.clientWidth,h=canvas.clientHeight;
  if(!w||!h)return;
  const ratio=window.devicePixelRatio||1;canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);
  const c=canvas.getContext('2d');c.scale(ratio,ratio);c.imageSmoothingEnabled=false;c.fillStyle='#122026';c.fillRect(0,0,w,h);
  const center=scene.tiles.find(t=>t.current);if(!center)return;
  loadPixelAssets(scene.pixel_assets);
  const size=Math.max(16,Math.floor(Math.min((w-16)/3,(h-6)/3))),cx=Math.round(w/2),cy=Math.round(h/2);
  const banks=shoreEdges(scene.tiles);
  for(const t of scene.tiles){
   const x=Math.round(cx+(t.x-center.x)*size-size/2),y=Math.round(cy+(t.y-center.y)*size-size/2);
   drawGround(c,t,banks,x,y,size);
   if(!scene.daylight){c.fillStyle=scene.lit?'#08142033':'#08142088';c.fillRect(x,y,size,size);}
  }
  const [subject,...others]=scene.actors;
  for(const [i,a] of others.entries())drawActor(c,a,cx+(i%2?1:-1)*size*.32,cy+(i<2?-1:1)*size*.32,size*.29,false);
  if(subject)drawActor(c,subject,cx,cy,size*.66,false);
  c.fillStyle='#c7d9d1';c.font='12px system-ui';c.fillText('N ↑',10,17);
 }
 function centerTile(view){return view?.tiles.find(t=>t.current) || view?.tiles.find(t=>t.id===view.center);}
 function draw(s){
  const width=Math.max(1,s.viewport.clientWidth),height=Math.max(1,s.viewport.clientHeight),dpr=window.devicePixelRatio||1,c=s.canvas.getContext('2d');
  const pw=Math.round(width*dpr),ph=Math.round(height*dpr);
  if(s.canvas.width!==pw)s.canvas.width=pw;if(s.canvas.height!==ph)s.canvas.height=ph;
  c.setTransform(dpr,0,0,dpr,0,0);c.imageSmoothingEnabled=false;c.fillStyle='#121e24';c.fillRect(0,0,width,height);
  s.positions=[];const v=s.data;if(!v){s.bubble.hidden=true;return;}
  const center=centerTile(v);if(!center)return;
  if(s.motion&&window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)s.motion=null;
  const remaining=s.motion?Math.max(0,1-(performance.now()-s.motion.start)/s.motion.duration):0;
  const motionScale=remaining*remaining;
  if(s.motion&&!remaining)s.motion=null;
  const display=window.ExpanseDisplay;
  if(display&&s.zoomControl.value!==display.values.tiles)s.zoomControl.value=display.values.tiles;
  s.zoom=display?.tileZoom(width,height)??s.zoom;
  s.canvas.dataset.tilePixels=String(Math.round(24*s.zoom));
  const tileSize=Math.round(24*s.zoom),unit=tileSize,ox=Math.round(width/2+s.offset.x+(s.motion?.dx||0)*unit*motionScale),oy=Math.round(height/2+s.offset.y+(s.motion?.dy||0)*unit*motionScale);
  c.fillStyle='#1a292f';for(let y=((oy%unit)+unit)%unit;y<height;y+=unit)for(let x=((ox%unit)+unit)%unit;x<width;x+=unit)c.fillRect(Math.round(x),Math.round(y),1,1);
  const coords=new Map();for(const t of v.tiles){const p={tile:t,x:Math.round(ox+(t.x-center.x)*unit),y:Math.round(oy+(t.y-center.y)*unit),radius:tileSize/2};for(const id of [t.id,...(t.room_ids || [])]){
    const prev=coords.get(id);
    if(!prev || Math.abs(p.x-ox)+Math.abs(p.y-oy)<Math.abs(prev.x-ox)+Math.abs(prev.y-oy))coords.set(id,p);
  }if(p.x+Math.max(tileSize,20)>0&&p.x-Math.max(tileSize,20)<width&&p.y+tileSize+24>0&&p.y-tileSize<height)s.positions.push(p);}
  const banks=shoreEdges(v.tiles);
  for(const p of s.positions)drawGround(c,p.tile,banks,Math.round(p.x-tileSize/2),Math.round(p.y-tileSize/2),tileSize);
  // Shade the whole terrain surface. Navigation marks and people are drawn above it.
  if(!s.options.designer&&(v.sight?.daylight??s.packet?.weather?.daylight)===false){
   const lit=!!v.sight?.light_source;
   const shade=c.createRadialGradient(ox,oy,0,ox,oy,Math.max(unit*3,Math.min(width,height)*(lit?.75:.57)));
   shade.addColorStop(0,lit?'rgba(7,14,33,.16)':'rgba(7,14,33,.50)');
   shade.addColorStop(.56,lit?'rgba(7,14,33,.32)':'rgba(7,14,33,.62)');
   shade.addColorStop(1,'rgba(4,9,22,.74)');
   c.fillStyle=shade;c.fillRect(0,0,width,height);
  }
  // Route geometry remains server data, but no lines or arrowheads cover terrain.
  for(const p of s.positions){
   if((v.links||[]).some(l=>l.kind==='portal'&&l.from===p.tile.id)||(p.tile.current&&(v.exits||[]).some(e=>e.kind==='portal'))){const x=p.x+tileSize/2-7*s.zoom,y=p.y-tileSize/2+2*s.zoom;c.fillStyle='#13262d';c.fillRect(x,y,6*s.zoom,8*s.zoom);c.strokeStyle='#a9c5c9';c.lineWidth=s.zoom;c.strokeRect(x,y,6*s.zoom,8*s.zoom);}
  }
  const groups=new Map();
  for(const actor of [...(v.actors||[]),...(v.nearby_actors||[])]){
   const room=actor.room||v.center;
   if(!groups.has(room))groups.set(room,[]);
   groups.get(room).push(actor);
  }
  // A single placement pass keeps spell cues on the exact sprite, including
  // other players and the self sprite held steady during terrain interpolation.
  const placements=[];let speaker=null;
  for(const [room,group] of groups){
   const tile=coords.get(room);if(!tile)continue;
   const self=group.find(a=>a.self||a.kind==='self'||a.id&&a.id===s.packet?.character?.id);
   const others=group.filter(a=>a!==self);
   let side=Math.ceil(Math.sqrt(others.length+(self?1:0)));if(self&&side%2===0)side++;
   const cell=tileSize/Math.max(side,1);
   let index=0;
   for(const actor of others){
    if(self&&index===Math.floor(side/2)*side+Math.floor(side/2))index++;
    const x=tile.x-tileSize/2+(index%side+.5)*cell,y=tile.y-tileSize/2+(Math.floor(index/side)+.5)*cell;
    placements.push({actor,room,x,y,size:Math.min(cell,16*s.zoom),self:false});index++;
   }
   if(self){const x=Math.round(width/2+s.offset.x),y=Math.round(height/2+s.offset.y);placements.push({actor:self,room,x,y,size:Math.min(16*s.zoom,others.length?cell:tileSize),self:true});}
  }
  const magic=window.ExpanseMapEffects?.begin(s,placements,coords);
  window.ExpanseMapEffects?.ground(magic);
  for(const point of placements){
   const {actor,x,y,size,self}=point;
   if(!window.ExpanseMapEffects?.actor(magic,point,drawActor))drawActor(c,actor,x,y,size,self);
   if(self)campMarker(c,actor.actions,x,y,s.zoom);
   if(actor.speech_bubble)speaker={actor,x,y};
  }
  window.ExpanseStreet?.draw(s,coords.get(center.id));
  window.ExpanseMapEffects?.front(magic);
  for(const p of s.positions){drawNpcCount(c,p,tileSize);drawImpactMarker(c,p,tileSize);}
  window.ExpanseDamage?.draw(s,coords,coords.get(center.id));
  if(speaker&&!s.options.designer&&speaker.x>=0&&speaker.x<width&&speaker.y>=0&&speaker.y<height){
   const {actor,x,y}=speaker,msg=actor.speech_bubble;
   const text=actor.name+(msg.tone?' '+msg.tone:'')+'\n'+msg.symbol+(msg.words?' '+msg.words:'');
   if(s.bubble.textContent!==text)s.bubble.textContent=text;s.bubble.title=text;s.bubble.setAttribute('aria-label',text);
   s.bubble.hidden=false;
   const bw=s.bubble.offsetWidth,bh=s.bubble.offsetHeight;
   s.bubble.style.left=Math.max(2,Math.min(width-bw-2,x-bw/2))+'px';
   const above=y-tileSize/2-bh-4;
   s.bubble.style.top=Math.max(1,Math.min(height-bh-1,above>=0?above:y+tileSize/2+4))+'px';
  }else{s.bubble.hidden=true;}
  if(remaining)s.schedule();
  c.fillStyle='#afc0bc';c.font='10px system-ui';c.fillText('N ↑',12,19); // Compass label is outside the tile artwork.
 }
 function render(packet,options={}){
  loadPixelAssets(packet?.visual?.pixel_assets);
  const id=options.hostId||'player-visual-map',host=document.getElementById(id);
  if(id==='player-visual-map'&&!options.designer){window.ExpanseMapEffects?.context(packet);window.ExpanseActorRenderer.latestPacket=packet;window.dispatchEvent(new CustomEvent('expanse:player-map',{detail:packet}));}
  if(!host)return;
  const s=views.get(id)||build(host,options);s.packet=packet;const v=packet.visual;
  if(!v||v.version!==1||(!Array.isArray(v.tiles)||!v.tiles.some(t=>t.id===v.center))){if(id==='player-visual-map'&&!options.designer)window.ExpanseStreet?.reset();s.empty.hidden=false;s.empty.textContent='Terrain view unavailable for this host. Check the Location page for details.';s.data=null;s.motion=null;s.locations.replaceChildren();s.locationSignature=null;s.hideTip();s.arrival.hidden=true;s.lastCenter=null;s.lastContext=null;s.sightBadge.hidden=true;s.sightBadge.textContent='';s.locationStatus.hidden=s.sightStatus.hidden=true;s.locationStatus.textContent=s.sightStatus.textContent='';s.coordinateStatus.hidden=true;s.coordinateStatus.textContent='';s.actors.replaceChildren();s.accessible.textContent='';s.impactStatus.hidden=true;s.impactKey.hidden=true;s.schedule();return;}
  s.mapBuild.textContent=v.map_build?'Map engine · '+v.map_build:
    v.terrain_release==='1.6'?'Map engine · 1.6 · Update the host to display disconnected building footprints.':'';
  s.mapBuild.hidden=!s.mapBuild.textContent;
  const old=s.data,oldTile=centerTile(old),newTile=centerTile(v);
  const sameCharacter=!s.lastCharacter||!packet.character?.id||s.lastCharacter===packet.character.id;
  if(!options.designer&&sameCharacter&&oldTile&&newTile&&old.center!==v.center){
   const samePlane=old.context.id===v.context.id&&old.floor===v.floor;
   const deltaX=newTile.x-oldTile.x,deltaY=newTile.y-oldTile.y;
   const adjacent=samePlane&&Number.isFinite(deltaX)&&Number.isFinite(deltaY)&&Math.abs(deltaX)<=1&&Math.abs(deltaY)<=1;
   const dx=adjacent?Math.sign(deltaX):0,dy=adjacent?Math.sign(deltaY):0;
   const geometric=(dy<0?'north':dy>0?'south':'')+(dx<0?'west':dx>0?'east':'');
   const exits=old.exits?.filter(e=>e.target===newTile.id)||[];
   const direction=samePlane&&exits.length===1?exits[0].direction:geometric;
   const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
   const fraction=s.motion?Math.max(0,1-(performance.now()-s.motion.start)/s.motion.duration)**2:0;
   const speed=Number.isFinite(packet.travel_speed_multiplier)&&packet.travel_speed_multiplier>=.25&&packet.travel_speed_multiplier<=4?packet.travel_speed_multiplier:1;
   // Finish a normal step within the walk controller's 95/speed cadence.
   // Carry any unfinished displacement so a rapid confirmation cannot jump
   // the painted terrain. Positions still come only from confirmed packets.
   s.motion=!reduced&&direction===geometric&&(dx||dy)?{dx:dx+(s.motion?.dx||0)*fraction,dy:dy+(s.motion?.dy||0)*fraction,start:performance.now(),duration:95/speed}:null;
   s.arrival.textContent=(direction?'Moved '+direction:'Arrived')+' · '+newTile.name;
   s.arrival.hidden=false;
  }else if(!oldTile||!sameCharacter||options.designer){s.motion=null;s.arrival.hidden=true;}
  s.lastCharacter=packet.character?.id||null;
  const changed=s.lastCenter!==v.center||s.lastContext!==v.context.id;
  if(changed){s.offset={x:0,y:0};if(!sameCharacter||old?.context?.id!==v.context.id||old?.floor!==v.floor||s.drag?.moved)s.drag=null;s.selected=null;s.inspect.textContent=(s.lastContext&&s.lastContext!==v.context.id?'Entered '+v.context.label+'. ':'')+(options.designer?'Select a tile to inspect.':'Click a tile to walk there, or select the marked doorway for a passage.');}
  s.data=v;s.lastCenter=v.center;s.lastContext=v.context.id;s.context.textContent=v.context.label;s.floor.textContent='Level '+v.floor;s.empty.hidden=!!v.tiles.length;
  const currentTile=centerTile(v),hereName=currentTile?.name||packet.location?.name;
  s.locationStatus.hidden=!!options.designer||!hereName;
  const hereText=s.locationStatus.hidden?'':'Here: '+hereName;
  if(s.locationStatus.textContent!==hereText)s.locationStatus.textContent=hereText;
  const sight=v.sight;
  s.sightStatus.hidden=!!options.designer||!sight||typeof sight.daylight!=='boolean'||typeof sight.light_source!=='boolean';
  s.sightBadge.hidden=s.sightStatus.hidden;
  const badgeText=s.sightBadge.hidden?'':sight.daylight?'Daylight':sight.light_source?'Night · working light':'Night · no working light';
  if(s.sightBadge.textContent!==badgeText)s.sightBadge.textContent=badgeText;
  const sightText=s.sightStatus.hidden?'':!sight.daylight&&!sight.light_source?
   'Night: nearby terrain is dim and fades quickly with distance. Available exits remain visible; you can keep traveling. A working lantern brightens your surroundings.':
   (sight.daylight?'Daylight: nearby reachable spaces are visible.':'Night with light: your lantern brightens nearby terrain and slows the distance fade.')+' This map follows you.';
  if(s.sightStatus.textContent!==sightText)s.sightStatus.textContent=sightText;
  const coordinates=v.coordinates||centerTile(v)?.coordinates;s.coordinateStatus.hidden=!coordinates;s.coordinateStatus.textContent=coordinateText(coordinates);
  s.actors.replaceChildren();for(const a of v.actors||[]){const item=make('span','atlas-person'),icon=make('canvas');icon.width=icon.height=16;drawActor(icon.getContext('2d'),a,8,8,16,a.self||a.kind==='self'||a.id===packet.character?.id);const label=(a.self||a.kind==='self'||a.id===packet.character?.id?'You · ':'')+a.name;
   if(a.activity?.label||a.combat_pose)item.title=a.combat_pose?'Fighting · '+(window.ExpanseCombatArt?.labels[a.combat_pose.stance]||'Combat'):a.activity.label;
   item.append(icon,document.createTextNode(label));s.actors.append(item);}

  s.accessible.textContent='Explored and currently visible rooms in '+v.context.label+': '+v.tiles.map(t=>t.name+(nearby(t)?' (visible nearby, not yet visited)':'')+(t.facility_landmark?' · '+t.facility_landmark.label:'')+surfaceText(t)+npcText(t)+(t.current?' (you are here)':'')).join(', ')+'. Exits: '+(packet.exits||[]).join('; ');
  const affected=v.tiles.filter(hasImpacts),current=centerTile(v);s.impactKey.hidden=s.impactStatus.hidden=!affected.length;
  s.impactStatus.textContent=hasImpacts(current)?'World recovery'+impactText(current):affected.length+' mapped location'+(affected.length===1?' is':'s are')+' recovering. Select a ! marker for details.';
  // Refresh an inspected count on updates without losing the chosen room or pan.
  const selected=v.tiles.find(t=>t.id===s.selected);if(selected)s.inspect.textContent=roomText(s.namedTile(selected)?selected:{...selected,name:'Nearby area',coordinates:null})+visitText(selected);else if(s.selected){s.selected=null;s.inspect.textContent='That nearby location is no longer visible. Select a tile to inspect.';}
  const namedLocations=v.tiles.filter(s.namedTile),signature=JSON.stringify(namedLocations.map(t=>[t.id,t.name,t.exterior]));
  if(signature!==s.locationSignature){const previousLocation=s.locations.value;s.locationSignature=signature;s.locations.replaceChildren(new Option('Choose a discovered location',''));
   for(const tile of namedLocations)s.locations.append(new Option(tile.name+(tile.exterior?' · building':''),tile.id));
   if([...s.locations.options].some(o=>o.value===previousLocation))s.locations.value=previousLocation;
  }
  if(s.tipId){const tile=v.tiles.find(t=>t.id===s.tipId&&(s.namedTile(t)||npcCount(t)!==null));if(tile)s.showTip(s.positions.find(p=>p.tile.id===tile.id)||{tile,x:8,y:40});else s.hideTip();}
  s.schedule();
 }
 window.ExpanseActorRenderer={drawActor,playerActor,latestPacket:window.latestMap||null};
 window.dispatchEvent(new Event('expanse:actor-renderer-ready'));
 // Read-only cached terrain artwork for the full-window room atlas.
 function reset(){window.ExpanseStreet?.reset();window.ExpanseMapEffects?.reset();window.ExpanseCountryView?.reset();for(const s of views.values()){if(s.options.designer)continue;if(s.frame)cancelAnimationFrame(s.frame);s.frame=0;s.motion=null;s.data=null;s.packet=null;s.lastCenter=null;s.lastContext=null;s.lastCharacter=null;s.arrival.hidden=true;s.arrival.textContent='';s.sightBadge.hidden=true;s.sightBadge.textContent='';s.locationStatus.hidden=s.sightStatus.hidden=true;s.actors.replaceChildren();s.accessible.textContent='';s.tip.hidden=true;s.tipId=null;s.locations.replaceChildren();s.locationSignature=null;s.selected=null;s.drag=null;s.schedule();}}
 window.ExpanseMap={render,reset,drawWatchScene,drawFacility,customArt,loadPixelAssets,pointerPoint,redraw:()=>{for(const s of views.values())s.schedule();},getTerrainTile:(terrain,roomId,route)=>terrainTile(terrain,hash(String(roomId)),route)};
 if(window.latestMap)(window.ExpanseCountryView?.render || render)(window.latestMap);
 else{const host=document.getElementById('player-visual-map');if(host)build(host,{});}
})();
