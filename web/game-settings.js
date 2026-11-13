/* Local presentation preferences, never quest progress or authority. */
(()=>{'use strict';
 const key='expanse.preferences.v1';let prefs={questCompass:true},lastFocus=null;
 function read(){try{const value=JSON.parse(localStorage.getItem(key)||'null');prefs={...(value&&typeof value==='object'&&!Array.isArray(value)?value:{}),questCompass:typeof value?.questCompass==='boolean'?value.questCompass:true};}catch{prefs.questCompass=true;}}
 const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const dialog=make('dialog');dialog.id='game-settings';dialog.setAttribute('aria-labelledby','game-settings-title');const title=make('h2','Game settings');title.id='game-settings-title';
 const heading=make('h3','Navigation and display'),label=make('label'),compass=make('input');compass.type='checkbox';compass.id='setting-quest-compass';label.append(compass,document.createTextNode(' Show quest compass'));
 const bubbleLabel=make('label'),bubbles=make('input');bubbles.type='checkbox';bubbles.id='setting-speech-bubbles';bubbleLabel.append(bubbles,document.createTextNode(' Show speech bubbles'));
 const help=make('p','Show a direction for each tracked quest at the top of the Terrain Map. Select a direction for the next objective and destination. This setting is saved on this device.');help.id='setting-quest-compass-help';compass.setAttribute('aria-describedby',help.id);
 const display=window.ExpanseDisplay;
 const displayGroup=make('fieldset');displayGroup.id='display-settings';
 displayGroup.append(make('legend','Display'));
 const selectors={};
 function select(key,title,options){
  const label=make('label',title),input=make('select');input.id='display-'+key;
  for(const [value,name] of options)input.append(new Option(name,value));
  input.onchange=()=>display.choose(key,input.value);
  label.append(input);displayGroup.append(label);selectors[key]=input;
 }
 select('scale','Interface size',[['auto','Automatic'],...[75,90,100,110,125,150,175,200,250].map(n=>[String(n),n+'%'])]);
 select('layout','Panels',[['auto','Automatic'],['columns','Side by side'],['tabs','One panel at a time']]);
 select('character','Character panel',[['auto','Show when there is room'],['show','Always show'],['hide','Keep hidden']]);
 select('tiles','Map tile size',[['auto','Fit the map panel'],['0.75','Small'],['1','Standard'],['1.5','Large'],['2','Extra large']]);
 const summary=make('p'),automatic=make('button','Use automatic display settings');
 summary.id='display-summary';automatic.type='button';automatic.onclick=()=>display.reset();
 displayGroup.append(summary,automatic);
 function refreshDisplay(){
  const values=display.values;
  for(const [key,input] of Object.entries(selectors)){
   if(key==='scale'&&![...input.options].some(o=>o.value===values[key]))input.append(new Option(values[key]+'%',values[key]));
   input.value=values[key];
  }
  summary.textContent='Current view · '+display.percent+'% · '+(display.tabs()?'one panel at a time':'side by side')+' · Character '+(display.character()?'shown':'hidden');
 }
 window.addEventListener('expanse:display',refreshDisplay);refreshDisplay();
 const close=make('button','Close');close.type='button';
 const status=make('p');status.setAttribute('role','status');
 dialog.append(title,displayGroup,heading,label,help,bubbleLabel,make('h3','Controls'));
 if(window.ExpansePlayerControls?.controls)dialog.append(window.ExpansePlayerControls.controls);
 dialog.append(status,close);document.body.append(dialog);
 const entry=make('button','Settings');entry.type='button';entry.className='ed-btn';entry.id='game-settings-open';entry.setAttribute('aria-label','Game settings');(document.getElementById('start-utilities')||document.getElementById('session-actions')||document.body).append(entry);
 function apply(notify=false){bubbles.checked=prefs.speechBubbles!==false;document.documentElement.classList.toggle('hide-speech-bubbles',!bubbles.checked);compass.checked=prefs.questCompass;const el=document.getElementById('quest-compass');if(el)el.hidden=!prefs.questCompass;const entry=document.getElementById('quest-compass-open');if(entry)entry.hidden=!prefs.questCompass;const mapCompass=document.getElementById('map-quest-compass');if(mapCompass)mapCompass.hidden=!prefs.questCompass;if(notify)window.dispatchEvent(new CustomEvent('expanse:preferences',{detail:{questCompass:prefs.questCompass}}));}
 function dismiss(){dialog.close();if(lastFocus?.isConnected)lastFocus.focus();lastFocus=null;}
 function open(){read();apply();status.textContent='';if(dialog.open)return;lastFocus=document.activeElement;dialog.showModal();compass.focus();}
 compass.onchange=bubbles.onchange=()=>{prefs.questCompass=compass.checked;prefs.speechBubbles=bubbles.checked;apply(true);try{localStorage.setItem(key,JSON.stringify(prefs));status.textContent='Saved on this device.';}catch{status.textContent='Applied for now, but this device could not save the preference.';}};
 entry.onclick=open;close.onclick=dismiss;dialog.oncancel=e=>{e.preventDefault();dismiss();};
 window.addEventListener('storage',e=>{if(e.key===key){read();apply(true);}});read();apply();window.ExpanseSettings={open,openDisplay(){open();selectors.scale.focus();},questCompassVisible:()=>prefs.questCompass};
})();
