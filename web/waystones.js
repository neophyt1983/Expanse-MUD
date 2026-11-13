/* Current-room posted signs. Server remains authoritative for every movement. */
(()=>{
  window.addEventListener('expanse:build-room-content', event=>{
    const {packet,content:host,keyed}=event.detail;
    const rows=packet.waymarks||[];
    if(!rows.length)return;
    const panel=document.createElement('section');panel.className='waystones';
    panel.setAttribute('aria-label','Posted trail signs');
    const title=document.createElement('h3');title.textContent='Posted trail signs';panel.append(keyed(title,'trail signs'));
    for(const row of rows){
      const button=document.createElement('button');button.type='button';button.className='ed-btn';button.disabled=!!row.closed;
      button.textContent=row.direction+' · '+row.label+(row.closed?' (blocked)':'');
      button.onclick=()=>{const cmd='go '+row.direction;if(window.expanseAtlasSend(cmd))append('user','> '+cmd);};
      panel.append(keyed(button,'sign',row.direction,row.label));
    }
    host.prepend(panel);
  });
})();
