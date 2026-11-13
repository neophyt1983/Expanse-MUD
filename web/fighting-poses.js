/* Full-body combat poses on the same registered 32-pixel canvas as the wardrobe. */
(()=>{'use strict';
const labels={unarmed:'Empty-hand guard',blade:'Blade guard',dagger:'Low knife guard',haft:'Overhead swing',spear:'Braced thrust',staff:'Staff guard',bow:'Drawn bow',shield:'Shield guard',dual:'Paired weapons',instrument:'Instrument guard',natural:'Natural attack'};
const strokes={
 unarmed:[[8,19,12,13],[22,19,19,11]],blade:[[7,21,12,18],[22,20,21,16]],
 dagger:[[7,16,11,13],[23,22,21,20]],haft:[[9,20,17,14],[22,16,21,12]],
 spear:[[10,20,17,17],[20,21,11,19]],staff:[[8,20,14,17],[23,19,21,13]],
 bow:[[10,16,23,15],[22,16,14,13]],shield:[[6,18,9,16],[22,20,19,14]],
 dual:[[7,21,9,17],[23,20,21,15]],instrument:[[10,21,13,17],[22,19,19,15]],
 natural:[[9,22,13,18],[23,20,23,15]]
};
const angles={blade:31,dagger:60,haft:-32,spear:68,staff:14,bow:3,dual:28,instrument:29,shield:14};
const tones={fair:'#d8b794',pale:'#e2cbb1',tan:'#c19b71',olive:'#b4a273',brown:'#956a4d',dark:'#684d3f',gray:'#969e9d',green:'#88a06b',blue:'#759dbd',black:'#4f3c36'};
const bytes=new WeakMap();let revision=0;
window.addEventListener('expanse:sprite-ready',()=>revision++);
function tile(){const canvas=document.createElement('canvas');canvas.width=canvas.height=32;return canvas;}
function line(c,ax,ay,bx,by,width,color){
 let x=Math.round(ax),y=Math.round(ay),x2=Math.round(bx),y2=Math.round(by);
 const dx=Math.abs(x2-x),dy=-Math.abs(y2-y),sx=x<x2?1:-1,sy=y<y2?1:-1;let err=dx+dy;
 c.fillStyle=color;
 for(;;){c.fillRect(x-(width>>1),y-(width>>1),width,width);if(x===x2&&y===y2)break;
  const twice=2*err;if(twice>=dy){err+=dy;x+=sx;}if(twice<=dx){err+=dx;y+=sy;}}
}
function inkAt(c,x,y,fallback){const p=c.getImageData(x,y,1,1).data;return p[3]>180?'rgb('+[p[0],p[1],p[2]].join(',')+')':fallback;}
function compose(actor,drawRest,paintGear,customArt){
 const pose=actor.combat_pose,style=labels[pose.stance]?pose.stance:'unarmed';
 const output=tile(),c=output.getContext('2d');c.imageSmoothingEnabled=false;
 const authored=customArt(actor.pose_art)||customArt(actor.paperdoll?.pose_base);
 const doll=actor.paperdoll,traits=doll?.characteristics||{},equipment=doll?.equipment||actor.held_gear||[];
 const handLayer=g=>['weapon','offhand'].includes(g.layer)||['weapon','mainhand','offhand'].includes(g.slot);
 const held=equipment.filter(g=>handLayer(g)&&g.item_id!==undefined);
 // Remote actors intentionally carry pixels only. Approved actual hand layers
 // are explicitly marked so their item IDs never have to cross a room boundary.
 if(actor.held_visual)for(const g of actor.held_visual)held.push(g);
 const standing=tile(),base=standing.getContext('2d');base.imageSmoothingEnabled=false;
 drawRest(base,{...actor,combat_pose:null,paperdoll:doll?{...doll,equipment:equipment.filter(g=>!handLayer(g))}:undefined},16,16,32,false);
 const animal=!!actor.subject||!!(traits.silhouette&&traits.silhouette!=='humanoid');
 if(authored){
  c.drawImage(authored,0,0,32,32);
  if(!actor.pose_art&&doll)paintGear(c,{paperdoll:{characteristics:traits,equipment:equipment.filter(g=>!handLayer(g))}},16,16,32,false,'isolated');
 }else if(animal){
  if(pose.defending)c.drawImage(standing,0,0,32,32,0,5,31,26);
  else{c.save();c.translate(16,20);c.rotate(-.14);c.drawImage(standing,-17,-19,34,29);c.restore();}
 }else{
  const bend=pose.defending?2:1;
  c.drawImage(standing,0,0,32,24,0,bend,32,23);
  c.drawImage(standing,0,24,16,8,-2,24,16,8);c.drawImage(standing,16,24,16,8,18,24,16,8);
 }
 const top=traits.stature==='short'?10:traits.stature==='tall'?6:8;
 const wide=traits.build==='slim'?10:traits.build==='broad'?6:8;
 const rig={stature:traits.stature||'average',build:traits.build||'average'};
 const poseRows=strokes[style],wrist=[];
 const skin=tones[traits.skin_color]||inkAt(base,16,top+4,'#b69c80'),sleeve=inkAt(base,wide+2,top+10,'#809590');
 poseRows.forEach(([ex,ey,wx,wy],i)=>{
  if(i===0&&pose.shield){ex=7;ey=18;wx=9;wy=15;}
  if(pose.defending&&style!=='bow'){wy-=2;wx+=i?-1:1;}
  wrist.push([wx,wy]);if(animal||authored)return;
  const sx=i?31-wide:wide,sy=top+9;
  line(c,sx,sy,ex,ey,4,'#303c3f');line(c,sx,sy,ex,ey,3,sleeve);
  line(c,ex,ey,wx,wy,3,'#46433e');line(c,ex,ey,wx,wy,2,skin);
  c.fillStyle=skin;c.fillRect(wx-1,wy-1,3,3);
 });
 for(const g of held){
  const off=g.layer==='offhand'||g.slot==='offhand',shield=off&&g.kind==='shield';
  const art=tile(),ctx=art.getContext('2d');ctx.imageSmoothingEnabled=false;
  paintGear(ctx,{paperdoll:{characteristics:rig,equipment:[g]}},16,16,32,false,'isolated');
  const right=style==='bow'?wrist[0]:wrist[1],w=off?wrist[0]:right;
  const grip=shield?[4,21]:style==='bow'?[27,17]:g.kind==='lute'?[26,20]:[29,25];
  c.save();c.translate(w[0],w[1]);
  const angle=shield?-12:off?-38:angles[style]||18;c.rotate(angle*Math.PI/180);
  const scale=style==='spear'||style==='haft'?.78:style==='bow'?.92:.86;c.scale(scale,scale);
  c.drawImage(art,-grip[0],-grip[1]);c.restore();
 }
 if(style==='bow'&&pose.projectile){
  const [bx,by]=wrist[0],[dx,dy]=wrist[1];
  line(c,bx-1,by-9,dx,dy,1,'#e5dec1');line(c,dx,dy,bx-1,by+8,1,'#e5dec1');
  line(c,dx,dy,29,by,1,'#bb995f');c.fillStyle='#cfcebc';c.fillRect(28,by-1,2,2);
 }
 return output;
}
function draw(c,actor,x,y,size,self,drawRest,paintGear,customArt){
 if(!actor.combat_pose)return false;
 let hit=bytes.get(actor);if(!hit||hit.rev!==revision){hit={rev:revision,tile:compose(actor,drawRest,paintGear,customArt)};bytes.set(actor,hit);}
 c.save();c.imageSmoothingEnabled=false;c.drawImage(hit.tile,Math.round(x-size/2),Math.round(y-size/2),size,size);
 if(self){c.fillStyle='#fff4c5';c.fillRect(Math.round(x-size/8),Math.round(y-size/2),Math.max(2,Math.round(size/4)),Math.max(1,Math.round(size/16)));}c.restore();return true;
}
function drawActivity(c,actor,x,y,size,drawRest){
 const kind=actor.activity?.kind;
 if(!kind||kind==='idle'||kind==='sleep'||!actor.paperdoll)return false;
 const phase=window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?0:(window.latestMap?.calendar?.minute||0)%2;
 const cache=activities.get(actor);
 let picture=cache&&cache.kind===kind&&cache.phase===phase&&cache.rev===revision?cache.picture:null;
 if(!picture){
  picture=tile();const body=tile(),base=body.getContext('2d'),ctx=picture.getContext('2d');
  base.imageSmoothingEnabled=ctx.imageSmoothingEnabled=false;drawRest(base,actor,16,16,32,false);
  if(kind==='walk'||kind==='patrol'||kind==='search'){
   ctx.drawImage(body,0,0,32,24,0,phase?1:0,32,24);
   const stride=phase?2:-2;ctx.drawImage(body,0,24,16,8,-stride,24,16,8);ctx.drawImage(body,16,24,16,8,16+stride,24,16,8);
  }else if(kind==='rest'||kind==='meal'||kind==='study'){
   ctx.drawImage(body,0,0,32,25,0,2,32,24);ctx.drawImage(body,0,25,32,7,1,25,31,6);
  }else if(kind==='work'||kind==='harvest'||kind==='hunt'){
   ctx.drawImage(body,0,0,32,22,phase?1:0,phase?2:0,32,22);ctx.drawImage(body,0,22,32,10,0,22,32,10);
  }else ctx.drawImage(body,0,0);
  const busy=['work','study','harvest','trade','meal','music','social'].includes(kind);
  if(busy){
   const props={work:[22,16],harvest:[22,19],study:[18,20],meal:[18,20],music:[22,16],trade:[22,20],social:[21,14]};
   const [wx,yy]=props[kind],wy=yy+(phase&&kind!=='study'?2:0);
   const skin=tones[actor.paperdoll.characteristics?.skin_color]||inkAt(base,16,12,'#bba185');
   line(ctx,23,18,wx,wy,3,inkAt(base,10,19,'#819385'));line(ctx,wx,wy,wx+1,wy-1,2,skin);
   window.ExpanseSpriteSheets?.prop(ctx,kind,wx-3,wy-7,10);
  }
  activities.set(actor,{kind,phase,rev:revision,picture});
 }
 c.save();c.imageSmoothingEnabled=false;c.drawImage(picture,Math.round(x-size/2),Math.round(y-size/2),size,size);c.restore();return true;
}
const activities=new WeakMap();
window.ExpanseCombatArt={draw,drawActivity,labels};
})();
