/* Passive weather artwork, fed only by the location currently on screen. */
window.ExpanseSky=(()=>{
 const views=new Map(),motion=matchMedia('(prefers-reduced-motion: reduce)');
 const winds=['north','northeast','east','southeast','south','southwest','west','northwest'];
 const mod=(x,n)=>((x%n)+n)%n;
 function paint(v,stamp){
  const {overlay,weather:w,water}=v,width=overlay.clientWidth,height=overlay.clientHeight;
  const c=overlay.getContext('2d'),ratio=Math.min(devicePixelRatio||1,2);
  overlay.width=Math.round(width*ratio);overlay.height=Math.round(height*ratio);c.scale(ratio,ratio);
  const t=motion.matches?1:stamp/1000,kind=w.weather||'clear',intensity=Math.min(1,Math.max(.23,w.weather_intensity??.55));
  const dir=winds.indexOf(String(w.wind_direction||'').toLowerCase()),angle=dir*Math.PI/4;
  const dx=dir<0?0:Math.sin(angle),dy=dir<0?0:-Math.cos(angle),speed=Math.min(90,w.wind_kph||0);
  const freezing=w.precipitation==='snow'||kind==='snow',storm=/thunderstorm|tornado/.test(kind);
  const rain=w.precipitation==='rain'||(!w.precipitation&&(storm||kind==='rain')),dust=kind==='dust storm';
  if(!w.sheltered&&kind!=='sheltered'){
   if((kind==='sunny'||kind==='clear')&&w.daylight){
    const glow=c.createRadialGradient(width*.84,0,0,width*.84,0,Math.max(20,height*.7));glow.addColorStop(0,'#ffde8730');glow.addColorStop(1,'#ffde8700');c.fillStyle=glow;c.fillRect(0,0,width,height);
   }
   if(/cloudy|overcast|thunderstorm|tornado|fog/.test(kind)){
    const cloud=c.createLinearGradient(0,0,0,height*.65);cloud.addColorStop(0,storm?'#18212c80':'#8a9ba54a');cloud.addColorStop(1,'#64778a00');c.fillStyle=cloud;c.fillRect(0,0,width,height*.65);
    c.fillStyle=storm?'#56636c57':'#b6c2c634';
    for(let i=0;i<6;i++){const x=mod(i*121+(dx||.15)*t*3,width+100)-40;c.beginPath();c.ellipse(x,7+(i%3)*7,42,12,0,0,Math.PI*2);c.fill();}
   }
   if(dust){c.fillStyle='#c3974f37';c.fillRect(0,0,width,height);}
   const count=Math.ceil(Math.min(170,width*height/750)*(freezing||rain||dust?intensity:0));
   for(let i=0;i<count;i++){
    const x=mod(i*117.3+Math.sin(i)*53+dx*t*(speed+4)+(freezing?Math.sin(t+i)*7:0),width+10)-5;
    const y=mod(i*61.1+Math.cos(i)*81+t*(freezing?18:rain?145:9)+dy*t*speed*.15,height+18)-9;
    if(freezing||dust){c.fillStyle=freezing?'#eaf7faac':'#d4af647e';c.beginPath();c.arc(x,y,1+(i%3)*.55,0,Math.PI*2);c.fill();}
    else{c.strokeStyle='#a8cfdf95';c.lineWidth=1;c.beginPath();c.moveTo(x,y);c.lineTo(x+dx*(speed/15),y+6+intensity*6);c.stroke();}
   }
   if(speed>=8||kind==='wind'){c.strokeStyle='#d1ddd578';for(let i=0;i<8;i++){
    const sx=dx||(!dy?1:0),sy=dy;const x=mod(79*i+t*sx*(12+speed),width),y=mod(57*i+t*sy*(12+speed),height);
    c.beginPath();c.moveTo(x,y);c.quadraticCurveTo(x+sx*9-sy*3,y+sy*9+sx*3,x+sx*21,y+sy*21);c.stroke();
   }}
   if(storm&&(motion.matches||mod(t,7)<.48)){
    const x=width*(.28+.36*mod(Math.floor(t/7)*.618,1));c.strokeStyle='#f3dfa8';c.lineWidth=2;c.beginPath();c.moveTo(x,3);c.lineTo(x-6,height*.13);c.lineTo(x+3,height*.12);c.lineTo(x-11,height*.28);c.stroke();
   }
   if(kind==='tornado'){const x=width*.67;c.strokeStyle='#c0c4c7a0';for(let i=0;i<11;i++){c.beginPath();c.ellipse(x+Math.sin(t+i*.3)*4,8+i*3,22-i*1.65,3,0,0,Math.PI*2);c.stroke();}}
   if(kind==='rough seas'){c.strokeStyle='#bfdce7ac';for(let i=0;i<9;i++){const x=mod(79*i+t*14,width),y=mod(39*i,height);c.beginPath();c.moveTo(x-10,y);c.quadraticCurveTo(x,y-8,x+10,y);c.stroke();}}
  }
  if(water){const size=height*(water==='tsunami'?.29:.17);const y=height-size;c.fillStyle='#387a9c63';c.beginPath();c.moveTo(0,height);
   for(let x=0;x<=width+6;x+=6)c.lineTo(x,y+Math.sin(x/20+t*2.5)*3);c.lineTo(width,height);c.fill();
   c.strokeStyle='#aedfedb0';c.beginPath();for(let x=0;x<=width+6;x+=6){const h=y+Math.sin(x/20+t*2.5)*3;x?c.lineTo(x,h):c.moveTo(x,h);}c.stroke();
  }
 }
 function tick(v){
  clearTimeout(v.timer);const on=v.visible&&!document.hidden&&v.weather&&document.getElementById('map-weather-toggle')?.checked!==false;
  v.overlay.hidden=!on;if(!on)return;
  const kind=v.weather.weather||'clear';paint(v,performance.now());
  if(!motion.matches&&(v.water||(!['clear','sunny','sheltered'].includes(kind)||v.weather.wind_kph>=8)))v.timer=setTimeout(()=>tick(v),90);
 }
 function update(parent,weather,effects=[]){
  if(!parent)return;
  let v=views.get(parent);
  if(!v){const overlay=document.createElement('canvas');overlay.className='sky-effects';overlay.setAttribute('aria-hidden','true');parent.append(overlay);
   v={overlay,visible:true};views.set(parent,v);new IntersectionObserver(rows=>{v.visible=rows[0].isIntersecting;tick(v);}).observe(parent);new ResizeObserver(()=>tick(v)).observe(parent);}
  const water=(effects||[]).find(e=>e.type==='tsunami')||(effects||[]).find(e=>e.type==='flood');
  v.weather=weather;v.water=water?.type;v.overlay.dataset.weather=weather?.weather||'';v.overlay.dataset.water=v.water||'';tick(v);
 }
 function redraw(){for(const v of views.values())tick(v);}
 motion.addEventListener('change',redraw);document.addEventListener('visibilitychange',redraw);
 document.addEventListener('change',e=>{if(e.target.id==='map-weather-toggle')redraw();});
 return {update};
})();
