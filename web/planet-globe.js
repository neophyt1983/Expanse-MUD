/* Orthographic globe of room placements permitted by the atlas server. */
window.ExpanseGlobe = (() => {
 const rad=Math.PI/180, step=7.5;
 let lon=0,lat=0,scale=1,frame=null;
 const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
 const wrap=v=>((v+180)%360+360)%360-180;
 function center(p){if(p){lon=p.lon;lat=p.lat;}}
 function rotate(x,y){lon=wrap(lon+x);lat=clamp(lat+y,-89.99,89.99);}
 function zoom(k){scale=clamp(scale*k,.5,850);}
 function project(a,b){
  const u=(a-lon)*rad,v=b*rad,t=lat*rad,cv=Math.cos(v);
  return {x:cv*Math.sin(u),y:Math.sin(v)*Math.cos(t)-cv*Math.cos(u)*Math.sin(t),
          z:Math.sin(v)*Math.sin(t)+cv*Math.cos(u)*Math.cos(t)};
 }
 // Invert the same orthographic projection used to paint the globe. Pointer
 // positions and the radius are in CSS pixels, independent of pixel density.
 function grabPoint(x,y){
  if(!frame)return null;
  const u=(x-frame.cx)/frame.radius,v=(frame.cy-y)/frame.radius;
  const depth=1-u*u-v*v;
  if(depth<0)return null;
  const z=Math.sqrt(depth),t=lat*rad;
  return {lon:wrap(lon+Math.atan2(u,z*Math.cos(t)-v*Math.sin(t))/rad),
          lat:Math.asin(clamp(v*Math.cos(t)+z*Math.sin(t),-1,1))/rad};
 }
 function dragTo(anchor,x,y){
  if(!frame||!anchor)return false;
  let u=(x-frame.cx)/frame.radius,v=(frame.cy-y)/frame.radius;
  // Limit a drag outside the disk to the visible limb. A point's parallel
  // also limits how far it can move horizontally on a north-up globe.
  const length=Math.hypot(u,v);
  if(length>.999999){u*=.999999/length;v*=.999999/length;}
  const parallel=Math.cos(anchor.lat*rad);
  u=clamp(u,-parallel,parallel);
  const z=Math.sqrt(Math.max(0,1-u*u-v*v));
  const tilt=Math.atan2(v,z);
  const phi=Math.asin(clamp(Math.sin(anchor.lat*rad)/Math.max(1e-12,Math.hypot(v,z)),-1,1));
  const candidates=[wrap((phi-tilt)/rad),wrap((Math.PI-phi-tilt)/rad)];
  candidates.sort((a,b)=>Math.abs(a-lat)-Math.abs(b-lat));
  const next=candidates.find(a=>a>=-90&&a<=90)??clamp(candidates[0],-90,90);
  if(parallel>1e-8)lon=wrap(anchor.lon-Math.atan2(u,z*Math.cos(next*rad)-v*Math.sin(next*rad))/rad);
  lat=next;return true;
 }
 function key(p){return p.lon+','+p.lat;}
 function grid(c,screen){
  function line(points){c.beginPath();let seen=false;for(const [a,b] of points){const p=project(a,b);if(p.z<0){seen=false;continue;}const at=screen(p);if(seen)c.lineTo(at.x,at.y);else c.moveTo(at.x,at.y);seen=true;}c.stroke();}
  c.strokeStyle='rgba(175,205,216,.24)';c.lineWidth=.8;
  for(let a=-180;a<180;a+=30)line(Array.from({length:91},(_,i)=>[a,-90+i*2]));
  for(let b=-60;b<=60;b+=30)line(Array.from({length:181},(_,i)=>[-180+i*2,b]));
 }
 function closeUp(p,width,height){
  if(!p)return;
  center(p);
  const radius=Math.max(1,Math.min(width||480,height||480)*.46);
  const span=p.cell?step:.08;
  const pixels=p.cell?96:42;
  scale=clamp(pixels/(radius*span*rad*Math.max(.15,Math.cos(p.lat*rad))),p.cell?1:12,p.cell?12:850);
 }
 // Settlements share one planetary coordinate. At street scale use the authored
 // room offsets on the current floor without inventing latitude or longitude.
 function streets(c,rows,origin,at,spacing,w,h,colors,layerColor){
  const cells=new Map();
  for(const room of rows){
   if(room.z!==origin.z||!Number.isFinite(room.x)||!Number.isFinite(room.y)||room.planet.cell||room.planet.survey)continue;
   const x=at.x+(room.x-origin.x)*spacing,y=at.y+(room.y-origin.y)*spacing;
   if(x < -spacing||x>w+spacing||y < -spacing||y>h+spacing)continue;
   const key=room.x+','+room.y;
   if(!cells.has(key))cells.set(key,{x,y,rooms:[],radius:spacing/2,street:true});
   cells.get(key).rooms.push(room);
  }
  for(const cell of cells.values()){
   const room=cell.rooms.find(r=>r.id===origin.id)||cell.rooms.find(r=>!r.learnedOnly)||cell.rooms[0];
   if(room.learnedOnly)continue;
   const left=Math.round(cell.x-spacing/2),top=Math.round(cell.y-spacing/2),size=Math.ceil(spacing);
   c.fillStyle=layerColor?.(room)||colors[room.terrain]||colors.unknown;c.fillRect(left,top,size,size);
   if(!layerColor&&window.ExpanseMap?.getTerrainTile){
    const tile=window.ExpanseMap.customArt?.(room.pixel_art)||window.ExpanseMap.getTerrainTile(room.terrain,room.id,room.route_surface);
    if(tile){c.imageSmoothingEnabled=false;c.drawImage(tile,left,top,size,size);}
    window.ExpanseMap.drawFacility?.(c,room,left,top,size);
   }
  }
  return [...cells.values()];
 }
 function fitBasin(places,w,h){
  const positions=places.map(r=>r.planet).filter(Boolean);
  if(!positions.length)return;
  const base=positions[0].lon;
  let west=0,east=0,south=90,north=-90;
  for(const p of positions){const delta=wrap(p.lon-base);west=Math.min(west,delta);east=Math.max(east,delta);
   south=Math.min(south,p.lat);north=Math.max(north,p.lat);}
  center({lat:(south+north)/2,lon:wrap(base+(west+east)/2)});
  const radius=Math.max(1,Math.min(w,h)*.46);
  scale=clamp(Math.min(.82*w/(radius*Math.max(.3,east-west)*rad*Math.max(.15,Math.cos(lat*rad))),
                     .78*h/(radius*Math.max(.3,north-south)*rad)),.5,850);
 }
 // Interpolate the host's surveyed planetary cells at overview scale. The player
 // atlas never receives this complete surface. Room picking still uses real cells.
 let rasterCache=null;
 function overviewSurface(rooms){
  const cells=rooms.filter(r=>r.planet?.cell&&!r.learnedOnly);
  if(cells.length!==48*24)return null;
  if(rasterCache?.first===cells[0])return rasterCache;
  const land=new Float32Array(1152),height=new Float32Array(1152);
  for(const room of cells){
   const x=Math.floor((room.planet.lon+180)/step),y=Math.floor((90-room.planet.lat)/step),i=y*48+x;
   const kind=room.water?.kind||room.terrain;
   land[i]=kind==='ocean'?-1:kind==='coast'||kind==='shore'?.15:1;
   height[i]=Math.max(0,room.elevation_m||0);
  }
  const width=768,heightPx=384,color=new Uint8ClampedArray(width*heightPx*3);
  const mix=(a,b,t)=>a+(b-a)*t;
  function sample(field,x,y){
   const cx=Math.floor(x),cy=Math.floor(y),dx=x-cx,dy=y-cy;
   const at=(xx,yy)=>field[clamp(yy,0,23)*48+((xx%48)+48)%48];
   return mix(mix(at(cx,cy),at(cx+1,cy),dx),mix(at(cx,cy+1),at(cx+1,cy+1),dx),dy);
  }
  for(let y=0;y<heightPx;y++)for(let x=0;x<width;x++){
   const gx=(x+.5)/16-.5,gy=(y+.5)/16-.5,coast=sample(land,gx,gy),z=sample(height,gx,gy);
   const light=clamp((sample(height,gx-.2,gy-.2)-z)/28,-16,16);
   const low=[92,120,101],high=[164,155,132],shore=[179,165,128],sea=[46,82,105],shelf=[70,119,136];
   const weight=clamp(z/1600,0,1),i=(y*width+x)*3;
   for(let k=0;k<3;k++){
    const inland=mix(low[k],high[k],weight)+light;
    color[i+k]=coast<0?mix(sea[k],shelf[k],Math.pow(1+coast,2)):mix(shore[k],inland,Math.min(1,coast*3));
   }
  }
  rasterCache={first:cells[0],width,height:heightPx,color};return rasterCache;
 }
 function paintOverview(c,surface,w,h,radius){
  const sampling=2,width=Math.ceil(w/sampling),height=Math.ceil(h/sampling);
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const ctx=canvas.getContext('2d'),pixels=ctx.createImageData(width,height);
  const cs=Math.cos(lat*rad),sn=Math.sin(lat*rad);
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
   const u=((x+.5)*sampling-w/2)/radius,v=(h/2-(y+.5)*sampling)/radius,depth=1-u*u-v*v;
   if(depth<0)continue;
   const z=Math.sqrt(depth),a=wrap(lon+Math.atan2(u,z*cs-v*sn)/rad),b=Math.asin(clamp(v*cs+z*sn,-1,1))/rad;
   const px=clamp(Math.floor((a+180)/360*surface.width),0,surface.width-1);
   const py=clamp(Math.floor((90-b)/180*surface.height),0,surface.height-1);
   const from=(py*surface.width+px)*3,to=(y*width+x)*4;
   for(let k=0;k<3;k++)pixels.data[to+k]=surface.color[from+k];
   pixels.data[to+3]=255;
  }
  ctx.putImageData(pixels,0,0);c.save();c.imageSmoothingEnabled=true;c.drawImage(canvas,0,0,width*sampling,height*sampling);c.restore();
 }
 function drawChannels(c,rooms,positions,screen,w,h,regional){
  const sources=new Map(rooms.filter(r=>r.planet&&!r.learnedOnly).map(r=>[r.id,r]));
  const street=new Map();
  for(const cell of positions)if(cell.street)for(const room of cell.rooms)street.set(room.id,cell);
  function point(room){
   if(street.has(room.id))return street.get(room.id);
   const projected=project(room.planet.lon,room.planet.lat);
   return projected.z>0?screen(projected):null;
  }
  c.save();c.lineCap='round';c.lineJoin='round';
  const incoming=new Map();
  for(const room of sources.values())if(room.water?.downstream&&!incoming.has(room.water.downstream))incoming.set(room.water.downstream,room);
  const labels=new Map();
  for(const src of sources.values()){
   if(src.water?.kind==='lake'||regional&&src.planet.cell)continue;
   const dst=sources.get(src.water?.downstream);if(!dst)continue;
   const a=point(src),b=point(dst);if(!a||!b)continue;
   if(Math.max(a.x,b.x)<0||Math.min(a.x,b.x)>w||Math.max(a.y,b.y)<0||Math.min(a.y,b.y)>h)continue;
   const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy);if(length<.1)continue;
   const brook=['stream','tributary'].includes(src.water.kind);
   c.strokeStyle=brook?'#9cdacd':'#6bbbe4';c.lineWidth=brook?1.5:3;
   const prev=incoming.get(src.id),next=sources.get(dst.water?.downstream);
   const p=prev&&point(prev)||a,n=next&&point(next)||b;
   c.beginPath();c.moveTo(a.x,a.y);
   c.bezierCurveTo(a.x+(b.x-p.x)/6,a.y+(b.y-p.y)/6,b.x-(n.x-a.x)/6,b.y-(n.y-a.y)/6,b.x,b.y);c.stroke();
   if(src.water.name&&!labels.has(src.water.name)&&length>=4&&a.x>60&&a.x<w-90&&a.y>40&&a.y<h-30)
    labels.set(src.water.name,{x:a.x+7,y:a.y-5,brook});
   if(length>=24){
    const x=a.x+dx*.6,y=a.y+dy*.6,ux=dx/length,uy=dy/length;
    c.beginPath();c.moveTo(x-ux*5-uy*3,y-uy*5+ux*3);c.lineTo(x,y);c.lineTo(x-ux*5+uy*3,y-uy*5-ux*3);c.stroke();
   }
  }
  const placed=[];c.font='12px system-ui';c.textAlign='left';
  for(const [name,label] of labels){
   const width=c.measureText(name).width, {x,y}=label;
   if(placed.some(box=>Math.abs(box.y-y)<19&&x<box.right+5&&x+width>box.x-5))continue;
   placed.push({x,y,right:x+width});c.lineWidth=3;c.strokeStyle='#22363a';c.strokeText(name,x,y);
   c.fillStyle=label.brook?'#c8eee3':'#e0f2ff';c.fillText(name,x,y);
  }
  c.restore();
 }
 function draw(c,w,h,rooms,current,selected,colors,scope='explored',saved=[],layerColor=null,waterLayer=false){
  const radius=Math.max(1,Math.min(w,h)*.46*scale),cx=w/2,cy=h/2,groups=new Map();
  const screen=p=>({x:cx+p.x*radius,y:cy-p.y*radius});
  c.save();c.beginPath();c.arc(cx,cy,radius,0,2*Math.PI);c.clip();
  const shade=c.createRadialGradient(cx-radius*.25,cy-radius*.25,1,cx,cy,radius);
  shade.addColorStop(0,'#40545d');shade.addColorStop(1,'#243740');c.fillStyle=shade;c.fillRect(0,0,w,h);
  for(const r of rooms){if(!r.planet||(scope!=='complete'&&r.visited===false&&!r.learnedOnly&&r.id!==current))continue;const k=key(r.planet);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}
  const positions=[],markers=[];
  const overview=scope==='complete'&&waterLayer?overviewSurface(rooms):null;
  if(overview)paintOverview(c,overview,w,h,radius);
  const ordered=[...groups.values()].sort((a,b)=>Number(b.some(r=>r.planet.cell))-Number(a.some(r=>r.planet.cell)));
  for(const rows of ordered){
   const p=rows[0].planet,mid=project(p.lon,p.lat);
   if(mid.z<-.14)continue;
   const cell=rows.find(r=>(r.planet.cell||r.planet.survey||r.planet.field)&&!r.learnedOnly);
   const span=cell?.planet.field?3.75:cell?.planet.survey ? .08 : step;
   if(cell&&!(overview&&cell.planet.cell)){
    const corners=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,y])=>project(p.lon+x*span/2,p.lat+y*span/2));
    // Only the visible portion of a cell contributes to this hemisphere.
    const poly=[];
    for(let j=0;j<4;j++){const a=corners[j],b=corners[(j+1)%4];if(a.z>=0)poly.push(a);
     if((a.z<0)!==(b.z<0)){const t=a.z/(a.z-b.z),x=a.x+t*(b.x-a.x),y=a.y+t*(b.y-a.y),n=Math.hypot(x,y);poly.push({x:x/n,y:y/n});}}
    if(poly.length>2){c.beginPath();poly.map(screen).forEach((v,i)=>i?c.lineTo(v.x,v.y):c.moveTo(v.x,v.y));c.closePath();c.fillStyle=layerColor?.(cell)||colors[cell.terrain]||colors.unknown;c.fill();c.strokeStyle=c.fillStyle;c.lineWidth=.6;c.stroke();
     const width=radius*rad*span*Math.max(.15,Math.cos(p.lat*rad));
     if(!layerColor&&width>=18&&mid.z>.12&&window.ExpanseMap?.getTerrainTile){
      const tile=window.ExpanseMap.customArt?.(cell.pixel_art)||window.ExpanseMap.getTerrainTile(cell.terrain,cell.id,cell.route_surface);
      if(tile){c.save();c.clip();const bounds=poly.map(screen),xs=bounds.map(v=>v.x),ys=bounds.map(v=>v.y),x=Math.min(...xs),y=Math.min(...ys);c.imageSmoothingEnabled=false;c.drawImage(tile,x,y,Math.max(1,Math.max(...xs)-x),Math.max(1,Math.max(...ys)-y));c.restore();}
     }
    }
   }
   if(mid.z<0)continue;
   const at=screen(mid),marked=rows.some(r=>r.id===selected||r.id===current);
   const origin=rows.find(r=>r.id===selected)||rows.find(r=>r.id===current);
   if(scale>=12&&origin&&!origin.planet.cell&&!origin.planet.survey&&Number.isFinite(origin.x)&&Number.isFinite(origin.y)){
    const spacing=Math.max(6,radius*rad*.08*Math.max(.15,Math.cos(p.lat*rad)));
    const detail=streets(c,rows,origin,at,spacing,w,h,colors,layerColor);
    for(const location of detail){
     positions.push(location);
     markers.push({rows:location.rooms,cell:true,at:location,marked:location.rooms.some(r=>r.id===selected||r.id===current)});
    }
    continue;
   }
   if(at.x < -radius*rad*span || at.y < -radius*rad*span || at.x > w+radius*rad*span || at.y > h+radius*rad*span)continue;
   positions.push({...at,rooms:rows,radius:Math.max(4,radius*rad*span/2)});
   markers.push({rows,cell,at,marked});
  }
  const light=c.createLinearGradient(cx-radius,cy-radius,cx+radius,cy+radius);
  light.addColorStop(0,'rgba(255,255,232,.12)');light.addColorStop(.55,'rgba(0,0,0,0)');light.addColorStop(1,'rgba(0,13,26,.40)');
  c.fillStyle=light;c.fillRect(0,0,w,h);
  grid(c,screen);
  if(waterLayer){
   const selectedRoom=rooms.find(r=>r.id===selected);
   drawChannels(c,rooms,positions,screen,w,h,scale>5&&selectedRoom?.planet?.survey);
  }
  for(const {rows,cell,at,marked} of markers){
   if(!cell&&rows.some(r=>r.planet.survey&&!r.learnedOnly)){
    c.fillStyle=colors[rows[0].terrain]||colors.unknown;c.fillRect(at.x-1,at.y-1,2,2);
   }
   if((!cell&&!rows.some(r=>r.planet.survey))||marked||rows.some(r=>r.host_players?.length)){
    if(layerColor&&!waterLayer&&!rows.every(r=>r.learnedOnly)){c.fillStyle=layerColor(rows[0]);c.fillRect(at.x-6,at.y-6,12,12);}
    c.beginPath();c.arc(at.x,at.y,marked?6:3,0,2*Math.PI);c.strokeStyle=marked?'#ffe184':'#d7e6e3';c.stroke();
    if(rows.some(r=>r.host_players?.length)){c.fillStyle='#e4a6ea';c.fillRect(at.x-2,at.y-2,4,4);}
   }
  }
  c.restore();
  const pinRooms=new Set(saved.map(row=>row.room_id));
  let caption=null;
  for(const {rows,at} of markers){
   const learned=rows.some(r=>r.learnedOnly), pinned=rows.some(r=>pinRooms.has(r.id)), mine=rows.find(r=>r.id===current), pick=rows.find(r=>r.id===selected);
   if(learned||pinned){c.save();c.translate(at.x,at.y);c.rotate(Math.PI/4);c.strokeStyle=pinned?'#e9a5ff':'#a0ddea';c.lineWidth=2;c.strokeRect(-5,-5,10,10);c.restore();}
   if((mine||pick)&&(!caption||pick))caption={at,row:pick||mine};
  }
  c.beginPath();c.arc(cx,cy,radius,0,2*Math.PI);c.strokeStyle='#9bb4bc';c.stroke();
  if(caption){
   const {at,row}=caption;
   c.save();c.fillStyle='#ef9e70';c.strokeStyle='#12212a';c.lineWidth=2;
   c.beginPath();c.moveTo(at.x,at.y);c.bezierCurveTo(at.x-20,at.y-20,at.x-9,at.y-33,at.x,at.y-33);c.bezierCurveTo(at.x+11,at.y-33,at.x+19,at.y-22,at.x,at.y);c.fill();c.stroke();
   const text=(scope==='explored'&&row.id===current?'You are here · ':'')+row.name;
   c.font='bold 13px system-ui';const tw=Math.min(w-16,c.measureText(text).width+18);
   const x=clamp(at.x-tw/2,8,w-tw-8),y=clamp(at.y-61,8,h-34);
   c.fillStyle='#152731';c.fillRect(x,y,tw,23);c.strokeStyle='#a98767';c.strokeRect(x+.5,y+.5,tw-1,22);c.fillStyle='#fff0dd';c.fillText(text,x+9,y+16,tw-17);c.restore();
  }
  frame={cx,cy,radius,groups,positions};return positions;
 }
 function hit(x,y){
  if(!frame)return null;
  const {cx,cy,radius,groups,positions}=frame;
  const street=positions.find(p=>p.street&&Math.abs(p.x-x)<=p.radius&&Math.abs(p.y-y)<=p.radius);
  if(street)return street;
  const dx=(x-cx)/radius,dy=(cy-y)/radius,z2=1-dx*dx-dy*dy;
  if(z2<0)return null;
  const v=Math.sqrt(z2),t=lat*rad;
  const a=wrap(lon+Math.atan2(dx,v*Math.cos(t)-dy*Math.sin(t))/rad);
  const b=Math.asin(clamp(dy*Math.cos(t)+v*Math.sin(t),-1,1))/rad;
  const p={lon:(Math.floor((a+180)/step)+.5)*step-180,lat:90-(clamp(Math.floor((90-b)/step),0,23)+.5)*step};
  const direct=positions.filter(v=>v.rooms.some(r=>!r.planet.cell && ((r.planet.survey && Math.abs(b-r.planet.lat)<=.04 && Math.abs(wrap(a-r.planet.lon))<=.04)||Math.hypot(v.x-x,v.y-y)<6))).sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y))[0];
  const rows=groups.get(key(p));return direct||(rows?.some(r=>r.planet.cell)?{x,y,rooms:rows}:null);
 }
 return {center,rotate,zoom,closeUp,fitBasin,grabPoint,dragTo,reset:()=>{lon=lat=0;scale=1;frame=null;},fit:()=>{scale=1;},draw,hit};
})();
