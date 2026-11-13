/* Display preferences belong to the device. The native desktop shares them
   across worlds and hosts. A standalone client keeps its own origin settings. */
(() => {
 'use strict';
 const defaults = {scale:'auto', layout:'auto', character:'auto', tiles:'auto'};
 const choices = {
  layout:['auto','columns','tabs'], character:['auto','show','hide'],
  tiles:['auto','0.75','1','1.5','2']
 };
 const storage = 'expanse.display.v1';
 function valid(key,value){
  if(key==='scale')return value==='auto'||(/^\d+$/.test(value)&&Number(value)>=60&&Number(value)<=250);
  return choices[key]?.includes(value)===true;
 }
 function read(){
  try{return JSON.parse(localStorage.getItem(storage))||{};}catch{return {};}
 }
 function clean(values){
  return Object.fromEntries(Object.keys(defaults).map(key=>[key,valid(key,values[key])?values[key]:'auto']));
 }
 let values=clean(window.ExpanseNativeFileMenu?defaults:read()), percent=100, pending=[];
 function announce(){window.dispatchEvent(new Event('expanse:display'));}
 function fallbackZoom(){
  if(window.ExpanseNativeFileMenu)return;
  percent=values.scale==='auto'?Math.max(100,Math.min(150,5*Math.round((100+75*(Math.min(innerWidth/1920,innerHeight/1060)-1))/5))):Number(values.scale);
  document.documentElement.style.zoom=percent===100?'':String(percent/100);
 }
 function saveFallback(){try{localStorage.setItem(storage,JSON.stringify(values));}catch{}fallbackZoom();}
 function send(command){
  const bridge=window.expanseDeviceDisplay;
  if(bridge){if(command.length)bridge.choose(...command);else bridge.reset();}
  else if(window.ExpanseNativeFileMenu)pending.push(command);
  else saveFallback();
 }
 function choose(key,value){
  value=String(value);
  if(!valid(key,value)||values[key]===value)return;
  values={...values,[key]:value};send([key,value]);announce();
 }
 function reset(){values={...defaults};send([]);announce();}
 function sync(snapshot){
  if(pending.length){
   const queued=pending;pending=[];queued.forEach(send);
  }else values=clean(snapshot);
  percent=snapshot.percent;announce();
 }
 function tabs(){
  return values.layout==='tabs'||(values.layout==='auto'&&(document.documentElement.clientWidth<1050||document.documentElement.clientHeight<510));
 }
 function character(){
  return values.character==='show'||(values.character==='auto'&&document.documentElement.clientWidth>=2000&&document.documentElement.clientHeight>=860);
 }
 function tileZoom(width,height){
  if(values.tiles!=='auto')return Number(values.tiles);
  if(width>=800&&height>=650)return 2;
  if(width>=600&&height>=460)return 1.5;
  return height<86||width<200?.75:1;
 }
 window.ExpanseDisplay={choose,reset,sync,tabs,character,tileZoom,get values(){return {...values};},get percent(){return percent;}};
 window.addEventListener('storage',e=>{
  if(e.key===storage&&!window.ExpanseNativeFileMenu){values=clean(read());fallbackZoom();announce();}
 });
 window.addEventListener('resize',()=>{fallbackZoom();announce();});
 if(window.expanseDeviceDisplay)sync(JSON.parse(window.expanseDeviceDisplay.snapshot));else fallbackZoom();
})();
