/* Duration choices issue ordinary authoritative commands; no predicted time or healing. */
(()=>{'use strict';
 const make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const entry=make('button','Rest / sleep…'),wake=make('button','Wake / stop resting');entry.id='rest-duration-open';wake.id='rest-wake';entry.type=wake.type='button';entry.className=wake.className='ed-btn';document.querySelector('.quick-actions')?.append(entry,wake);
 const dialog=make('dialog');dialog.id='rest-duration';dialog.setAttribute('aria-labelledby','rest-duration-heading');const title=make('h2','Rest or sleep');title.id='rest-duration-heading';
 const help=make('p','Choose how many game hours. Location, danger and interruptions still apply. In single player, time advances in short, interruptible steps; a hosted world keeps its normal shared clock.');
 const label=make('label','Duration '),hours=make('select');hours.id='rest-duration-hours';hours.setAttribute('aria-label','Rest duration in game hours');for(let h=1;h<=25;h++)hours.append(new Option(h+' game hour'+(h===1?'':'s'),h));label.append(hours);
 const status=make('p');status.setAttribute('role','status');const rest=make('button','Rest for selected duration'),sleep=make('button','Sleep for selected duration'),close=make('button','Cancel');for(const b of [rest,sleep,close])b.type='button';dialog.append(title,help,label,status,rest,sleep,close);document.body.append(dialog);
 function dismiss(){dialog.close();(document.getElementById('conversation-commands')||entry).focus();}
 function send(command){if(typeof ws==='undefined'||!ws||ws.readyState!==1){status.textContent='Not connected. Reconnect before requesting rest.';append('error',status.textContent);return false;}try{ws.send(JSON.stringify({command,rest_ui:true}));window.ExpansePlayerControls?.remember(command);append('user','> '+command);return true;}catch{status.textContent='The request was not sent. Reconnect and try again.';return false;}}
 function begin(kind){if(!dialog.open)return;const h=Number(hours.value);if(!Number.isInteger(h)||h<1||h>25){status.textContent='Choose 1 to 25 whole game hours.';return;}if(send(kind+' '+h*60))dismiss();}
 entry.onclick=()=>{if(dialog.open)return;status.textContent='The conversation will report whether the game starts or refuses your request.';dialog.showModal();hours.focus();};rest.onclick=()=>begin('rest');sleep.onclick=()=>begin('sleep');close.onclick=dismiss;dialog.oncancel=e=>{e.preventDefault();dismiss();};wake.onclick=()=>send('wake self');
 window.ExpanseRestControls={disconnect:()=>{if(dialog.open)dismiss();status.textContent='Disconnected. Rest stops when you disconnect.';}};
})();
