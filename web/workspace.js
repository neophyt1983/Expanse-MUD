/* Shared workspace structure; original editor fields and command handlers remain authoritative. */
(()=>{
  const $=id=>document.getElementById(id);
  const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
  function send(command,label){
    if(!ws||ws.readyState!==WebSocket.OPEN){append('error','Connect to the game first.');return;}
    ws.send(JSON.stringify({command}));append('user','> '+(label||'Action')); 
  }
  function action(label,command){const b=make('button','ed-btn',label);b.type='button';b.title=label;b.dataset.action=command;b.onclick=()=>{if(command==='skills'&&window.ExpanseSkills){window.ExpanseSkills.open();return;}if(command==='watch'&&window.ExpanseResidentWatch){window.ExpanseResidentWatch.open();return;}if(command==='history'&&window.ExpanseChronicles){window.ExpanseChronicles.open();return;}if((command==='news'||command==='news editions')&&window.ExpanseGazette){window.ExpanseGazette.open(command==='news editions');return;}const lists={inventory:'inventory',quests:'quests',adventures:'adventures',journal:'journal',market:'markets',survey:'survey',catalog:'catalog',wardrobe:'wardrobe',recipes:'recipes',condition:'condition'};if(lists[command]&&window.ExpansePlayerLists)window.ExpansePlayerLists.open(lists[command]);else send(command,label);};return b;}
  const game=$('tab-game'),conversation=make('div','workspace-panel conversation');
  conversation.append(make('h2','panel-title','Conversation'));
  const quick=make('div','quick-actions');for(const [l,c] of [['Look','look'],['Watch','watch'],['Inventory','inventory'],['Status','score'],['Skills','skills'],['Help','help'],['Guide','guide'],['Bookshelves','books'],['Newspaper','news'],['Chronicles','history'],['Quests','quests'],['Adventures','adventures'],['Markets','market'],['Survey','survey'],['Catalog','catalog'],['Wardrobe','wardrobe'],['Recipes','recipes'],['Condition','condition']])quick.append(action(l,c));conversation.append(quick,$('log'),$('input-form'));
  const status=make('div');status.id='character-strip';status.setAttribute('role','status');status.textContent='Connecting to your character…';
  const location=make('aside','workspace-panel');location.id='location-panel';location.setAttribute('aria-label','Current location and actions');location.append(make('h2','panel-title','Current location'));
  const content=make('div','location-content');content.id='location-content';content.textContent='Create or resume a character to see your surroundings.';location.append(content);
  game.prepend(status,conversation);game.append(location);
  // Only the host's personal custody projection supplies this notice. Missing
  // data never means release, and elapsed browser time never changes a case.
  const custodyNotice=make('section','custody-notice');custodyNotice.id='player-custody-notice';custodyNotice.hidden=true;
  custodyNotice.setAttribute('role','status');custodyNotice.setAttribute('aria-live','polite');custodyNotice.setAttribute('aria-atomic','true');
  const dismissedCustody=new Set();let custody=null,custodyOwner='',custodySignature='';
  const custodyKey=()=>JSON.stringify([custodyOwner,custody?.id]);
  const custodyStates=new Set(['awaiting_hearing','sentenced','released','dismissed','closed_deceased']);
  function placeCustodyNotice(){
    const header=document.querySelector('#player-visual-map .atlas-position-header');
    if(header&&custodyNotice.parentElement!==header)header.append(custodyNotice);
  }
  function custodyTime(c){
    if(!c.active||!Number.isInteger(c.remaining_minutes)||c.remaining_minutes<0)return '';
    const event=c.next_event==='hearing'?'Hearing':c.next_event==='release'?'Automatic release':'';
    if(!event)return '';
    return c.remaining_minutes?event+' in '+c.remaining_minutes+' game minute'+(c.remaining_minutes===1?'':'s')+'.':event+' is due; awaiting the host update.';
  }
  function showCustodyDetails(){
    window.ExpansePanels?.reveal('location');
    const card=$('custody-details');card?.scrollIntoView({block:'start'});card?.focus({preventScroll:true});
  }
  function dismissCustody(key,button){
    if(!custody||custody.active||key!==custodyKey())return;
    dismissedCustody.add(key);custodyNotice.hidden=true;$('player-custody-badge')?.remove();
    if(button){button.disabled=true;button.textContent='Notice dismissed';}
  }
  function custodyActions(c,compact=false){
    const actions=make('div','custody-actions'),key=custodyKey();
    if(compact){const details=make('button','ed-btn','Custody details');details.type='button';details.onclick=showCustodyDetails;actions.append(details);}
    const wait=typeof c.wait_command==='string'&&/^wait ([1-9][0-9]*)$/.exec(c.wait_command);
    if(c.active&&c.can_wait===true&&wait){
      const label='Wait '+wait[1]+' game minute'+(wait[1]==='1'?'':'s'),button=make('button','ed-btn',label);button.type='button';
      button.onclick=()=>{
        if(key!==custodyKey()||!custody?.active||custody.can_wait!==true||custody.wait_command!==c.wait_command)return;
        window.ExpansePlayerControls?.stopWalking();send(c.wait_command,label);
      };actions.append(button);
    }
    if(!c.active&&!dismissedCustody.has(key)){
      const dismiss=make('button','ed-btn','Dismiss notice');dismiss.type='button';dismiss.onclick=()=>dismissCustody(key,dismiss);actions.append(dismiss);
    }
    return actions;
  }
  function updateCustody(m){
    custodyOwner=JSON.stringify([m.visual?.travel_world||'',m.character?.id||'']);
    custody=m.custody&&typeof m.custody.id==='string'&&custodyStates.has(m.custody.status)?m.custody:null;
    const signature=JSON.stringify([custodyOwner,custody,custody&&!custody.active&&dismissedCustody.has(custodyKey())]);
    placeCustodyNotice();if(signature===custodySignature)return;custodySignature=signature;
    custodyNotice.replaceChildren();custodyNotice.hidden=!custody||(!custody.active&&dismissedCustody.has(custodyKey()));
    if(!custody)return;
    custodyNotice.classList.toggle('custody-outcome',!custody.active);
    custodyNotice.append(make('strong',null,custody.title));
    const charge=custody.accusation?(custody.status==='awaiting_hearing'?'Accusation: ':custody.status==='sentenced'?'Sentence for ':'Case: ')+custody.accusation:'';
    custodyNotice.append(make('p',null,[charge,custodyTime(custody)].filter(Boolean).join(' · ')));
    const next=custody.active?custody.instructions?.[0]:custody.outcome;
    if(next)custodyNotice.append(make('p',null,next));
    custodyNotice.append(custodyActions(custody,true));
  }
  function custodyCard(){
    if(!custody)return null;
    const c=custody,card=keyed(make('section','custody-card'),'custody',c.id);card.id='custody-details';card.tabIndex=-1;
    card.setAttribute('aria-label','Your custody status');card.append(make('h3',null,c.title));
    if(c.reason)card.append(make('p',null,c.reason));
    if(Number.isInteger(c.witness_count))card.append(make('p',null,'Witness reports in this case: '+c.witness_count+'.'));
    const time=custodyTime(c);if(time)card.append(make('p','custody-timing',time));
    if(c.custody_place&&c.active)card.append(make('p',null,'Place of custody: '+c.custody_place+'.'));
    if(c.allowed_facilities?.length)card.append(make('p',null,'Allowed facilities: '+c.allowed_facilities.join(', ')+'.'));
    if(Number.isInteger(c.fine_paid))card.append(make('p',null,'Fine paid: '+c.fine_paid+' gold.'));
    for(const instruction of c.instructions||[])card.append(make('p',null,instruction));
    if(c.outcome)card.append(make('p','custody-outcome-text',c.outcome));
    card.append(custodyActions(c));return card;
  }
  function resetCustody(){custody=null;custodyOwner=custodySignature='';custodyNotice.hidden=true;custodyNotice.replaceChildren();$('custody-details')?.remove();$('player-custody-badge')?.remove();}
  window.ExpanseCustody={reset:resetCustody};
  window.addEventListener('expanse:player-map',()=>{placeCustodyNotice();requestAnimationFrame(placeCustodyNotice);});
  const sectionOpen = new Map();
  const atEnd = () => location.clientHeight > 0 && location.scrollTop > 0 &&
    location.scrollHeight - location.clientHeight - location.scrollTop <= 2;
  let keepEnd = false, endScrollTop = 0;
  const wantsEnd = () => atEnd() || (keepEnd && Math.abs(location.scrollTop - endScrollTop) <= 1);
  location.addEventListener('scroll', () => {
    // A scroll event from our own refresh can arrive after a dock resize but
    // before ResizeObserver. The same scroll position still means "at end";
    // an actual move away from it gives control back to the reader.
    if (location.clientHeight) keepEnd = wantsEnd();
    if (keepEnd) endScrollTop = location.scrollTop;
  }, {passive:true});
  // A dock resize or display-scale change can shorten the visible panel after
  // its last line was reached. Keep that end in view without moving readers
  // who deliberately scrolled back to an earlier item.
  new ResizeObserver(() => {
    if (location.clientHeight) {
      keepEnd = wantsEnd();
      if (keepEnd) location.scrollTop = location.scrollHeight;
    }
    if (keepEnd) endScrollTop = location.scrollTop;
  }).observe(location);
  function keyed(element, ...key) {
    element.dataset.viewKey = JSON.stringify(key);
    return element;
  }
  function disclosure(title, label, initiallyOpen, className) {
    const group = make('details', className);
    group.dataset.section = title;
    group.open = sectionOpen.get(title) ?? initiallyOpen;
    group.append(keyed(make('summary', null, label), 'heading', title));
    return group;
  }
  function captureView() {
    // Read the live controls, including a disclosure opened in this same event turn.
    for (const group of content.querySelectorAll('details[data-section]')) {
      sectionOpen.set(group.dataset.section, group.open);
    }
    const scroll = location.scrollTop;
    const top = location.getBoundingClientRect().top;
    let anchor = null;
    if (scroll > 0 && location.clientHeight) {
      for (const row of content.querySelectorAll('[data-view-key]')) {
        const bounds = row.getBoundingClientRect();
        if (bounds.height && bounds.top <= top && bounds.bottom > top) {
          anchor = {key: row.dataset.viewKey, offset: bounds.top - top};
          break;
        }
      }
    }
    const active = document.activeElement;
    const owner = content.contains(active) && active.closest('[data-view-key]');
    const focus = owner ? {key: owner.dataset.viewKey, tag: active.tagName, label: active.textContent} : null;
    return {scroll, anchor, focus, end:location.clientHeight ? wantsEnd() : keepEnd};
  }
  function restoreView({scroll, anchor, focus, end}) {
    const find = key => content.querySelector('[data-view-key="' + CSS.escape(key) + '"]');
    if (focus) {
      const row = find(focus.key);
      const control = row?.tagName === focus.tag ? row :
        Array.from(row?.querySelectorAll('button, select') || []).find(el =>
          el.tagName === focus.tag && (el.tagName === 'SELECT' || el.textContent === focus.label));
      control?.focus({preventScroll: true});
    }
    keepEnd = end;
    const row = anchor && find(anchor.key);
    if (end && location.clientHeight) {
      // Packet refreshes can add or wrap lines below the preserved top anchor.
      // Preserve the bottom instead when the reader had already reached it.
      location.scrollTop = location.scrollHeight;
    } else if (row && location.offsetHeight && row.getBoundingClientRect().height) {
      const viewport = location.getBoundingClientRect();
      const delta = row.getBoundingClientRect().top - viewport.top - anchor.offset;
      location.scrollTop += delta * location.offsetHeight / viewport.height;
    } else {
      // Includes a last item picked up from the floor. The browser clamps to the new end.
      location.scrollTop = scroll;
    }
    if (keepEnd) endScrollTop = location.scrollTop;
  }
  window.renderRoomPanel=m=>{
    if(!m.character||!m.location)return;
    const view = captureView();
    updateCustody(m);
    window.ExpanseTrade?.update(m);
    const p=m.character,r=m.location;status.replaceChildren();
    const name=make('strong',null,p.name);status.append(name);
    if(custody&&(custody.active||!dismissedCustody.has(custodyKey()))){
      const badge=make('button','ed-btn custody-strip-badge',custody.title);badge.id='player-custody-badge';badge.type='button';
      badge.title=[custody.title,custodyTime(custody),custody.outcome].filter(Boolean).join(' ');badge.setAttribute('aria-label',badge.title+' Open custody details.');badge.onclick=showCustodyDetails;status.append(badge);
    }
    status.append(make('span',null,[p.race_name||p.race,p.class_name||p.char_class].filter(Boolean).join(' / ')||'Adventurer'));
    const meter=make('meter');meter.min=0;meter.max=Math.max(1,p.max_hp);meter.value=p.hp;meter.setAttribute('aria-label','Health');status.append(meter,make('span',null,'HP '+p.hp+' / '+p.max_hp),make('span',null,'Gold '+p.gold),make('span',null,r.name));
    if(p.advancement){const a=p.advancement;const badge=make('span',null,'Level '+a.level+' · XP '+a.xp+(a.next_xp?' / '+a.next_xp:' · Level cap'));badge.title='Earn experience through new discoveries, quests, NPC relationships, crafting, gathering and threats overcome. Repeat successful work earns diminishing practice XP within a daily budget; discoveries remain once-only.\n'+a.recent.join('\n');status.append(badge);if(a.practice)status.append(make('span',null,'Practice XP '+a.practice.used+' / '+a.practice.limit+' today'));}
    if(m.weather)status.append(make('span',null,m.weather.season+' · '+m.weather.weather+' · '+m.weather.temperature_c+' °C'));
    if(m.living){const c=m.living.conditions;status.append(make('span',null,'Mana '+c.mana+'/'+c.max_mana),make('span',null,m.calendar_text||('Day '+(Math.floor(m.living.minute/1500)+1))));}
    const next = document.createDocumentFragment();
    next.append(keyed(make('h2',null,r.name),'room',r.id));
    const ownCase=custodyCard();if(ownCase)next.append(ownCase);
    next.append(keyed(make('div','location-description',r.description),'description',r.id));
    if(m.market_summary){const counter=keyed(make('div','action-card',m.market_summary),'market',r.id);counter.append(action('View provisions','market'));next.append(counter);}
    function section(title, rows, build) {
      const group = disclosure(title, title+' ('+rows.length+')', title!=='Your inventory' && title!=='Posted reading', 'player-list-section');
      if (!rows.length) group.append(make('div','empty-state','None here.'));
      for (const row of rows) group.append(keyed(build(row), title, row.id));
      next.append(group);
    }
    section('Players here',r.players||[],x=>make('div','action-card',x.name+' ['+x.marker+']'));
    section('People and creatures',r.npcs||[],x=>{const card=make('div','action-card',x.name);
      const expression=(m.social?.npcs||[]).find(n=>n.id===x.id)?.expression;
      if(typeof expression?.summary==='string'&&expression.summary)card.append(make('small','npc-expression','Expression · '+expression.summary));
      const actor=(m.visual?.actors||[]).find(a=>a.id===x.id);
      if(actor&&window.ExpanseActorRenderer){
        const portrait=make('canvas','npc-portrait');portrait.width=portrait.height=64;portrait.setAttribute('role','img');portrait.setAttribute('aria-label',x.name+' portrait');
        const ctx=portrait.getContext('2d');ctx.imageSmoothingEnabled=false;window.ExpanseActorRenderer.drawActor(ctx,actor,32,32,64,false);card.prepend(portrait);
        if(actor.activity||actor.combat_pose){const text=actor.combat_pose?'Fighting · '+(window.ExpanseCombatArt?.labels[actor.combat_pose.stance]||'Combat stance'):actor.activity.label;card.append(make('small','npc-activity','Now · '+text));}
        if(actor.paperdoll?.occupation)card.append(make('small',null,actor.paperdoll.occupation));
      }
      if(x.title)card.append(make('small',null,x.title));card.append(make('small',null,'Location: '+r.name),make('small',null,x.description||''));const buttons=make('div','action-buttons');if(m.social){if((m.social.npcs||[]).some(n=>n.id===x.id)){const talk=make('button','ed-btn','Talk');talk.type='button';talk.title='Choose an emotion or gift for this NPC';talk.onclick=()=>window.openNpcSocial(x.id);buttons.append(talk);}buttons.append(action('Quest dialogue','dialogue '+x.id));}else buttons.append(action('Talk','talk '+x.name));if(x.trade_available===true){const trade=make('button','ed-btn','Trade');trade.type='button';trade.onclick=()=>window.ExpanseTrade?.open(x.id,x.name);buttons.append(trade);}for(const offer of x.escorts||[])buttons.append(action(offer.mode==='follow'?'Follow guide':'Lead companion',offer.mode+' '+offer.quest));const observe=make('button','ed-btn','Watch');observe.type='button';observe.onclick=()=>window.ExpanseResidentWatch.open(x.id);buttons.append(observe);const attack=action('Attack','attack '+x.id);attack.classList.add('combat');buttons.append(attack);card.append(buttons);return card;});
    function stacks(items){const grouped=new Map();for(const x of items){const key=JSON.stringify(x);if(grouped.has(key))grouped.get(key).quantity++;else grouped.set(key,{...x,quantity:1});}return [...grouped.values()];}
    function itemCard(x,carried){const card=make('div','action-card',x.name+(x.quantity>1?' × '+x.quantity:'')+(x.equipped?' · equipped':''));card.dataset.itemId=x.id;card.dataset.quantity=x.quantity;if(x.description)card.append(make('small',null,x.description));card.append(make('small',null,'Location: '+(x.location||r.name)),make('small',null,'Designated origin: '+(x.origin||r.name)));if(['weapon','armor'].includes(x.type))card.append(make('small',null,'Condition: '+x.durability+'%'));const fixedHere=!carried&&x.anchored_readable===true;const buttons=make('div','action-buttons');if(!fixedHere){const placement=make('select');placement.title='Place object';placement.append(new Option(r.name,r.id),new Option('Your inventory','inventory'));placement.value=carried?'inventory':r.id;placement.onchange=()=>{if(placement.value==='inventory'&&!carried)send('get '+x.id);else if(placement.value===r.id&&carried)send('place '+x.id+' at '+r.id);};card.append(placement);}
      if(!carried&&!fixedHere){buttons.append(action('Take one','take '+x.id));if(x.quantity>1)buttons.append(action('Take all','take all '+x.id));}
      if(x.readable)buttons.append(action('Read','read '+x.id));
      if(carried){if(x.type==='consumable')buttons.append(action('Use','use '+x.id));if(x.equipped)buttons.append(action('Unequip','unequip '+x.id));else if(x.slot||['weapon','armor'].includes(x.type))buttons.append(action('Equip','equip '+x.id));if(m.needs_economy&&!x.equipped&&(r.npcs||[]).some(n=>n.merchant))buttons.append(action('Sell one','sell '+x.id));buttons.append(action('Drop one','drop '+x.id));if(x.quantity>1)buttons.append(action('Drop all','drop all '+x.id));}
      card.append(buttons);return card;}
    const ground=stacks(r.items||[]);
    section('On the ground',ground.filter(x=>!x.anchored_readable),x=>itemCard(x,false));
    const posted=ground.filter(x=>x.anchored_readable&&!x.publication);
    const books=ground.filter(x=>x.publication);if (books.length) {
      const shelf = disclosure('Bookshelves', 'Bookshelves ('+books.length+')', false, 'action-section');
      for (const genre of [...new Set(books.map(b=>b.publication.genre))].sort()) {
        const group = disclosure('genre:'+genre, genre, false);
        for (const book of books.filter(b=>b.publication.genre===genre)) {
          group.append(keyed(action(book.name,'read '+book.name), 'book', book.id));
        }
        shelf.append(group);
      }
      next.append(shelf);
    }
    if(posted.length)section('Posted reading',posted,x=>itemCard(x,false));
    section('Your inventory',stacks(p.inventory||[]),x=>itemCard(x,true));
    // Include fixtures and trail signs before replacing the scrollable content.
    window.dispatchEvent(new CustomEvent('expanse:build-room-content', {detail:{packet:m, content:next, keyed}}));
    content.replaceChildren(next);
    restoreView(view);
  };
  const grid=$('ed-grid'),cols=Array.from(grid.children),library=make('div','creator-library');cols.slice(0,3).forEach(c=>library.append(c));
  const inspector=cols[3];inspector.classList.add('creator-inspector');const preview=make('div');preview.id='creator-preview';preview.textContent='Select a map room or catalogue entry. Edit its fields below, then Save and Apply.';inspector.prepend(preview);
  grid.prepend(library);grid.insertBefore($('designer-map-panel'),inspector);$('designer-map-panel').open=true;
  window.creatorSelection=(obj,type)=>{preview.textContent=(obj.name||obj.id)+'\n'+(obj.description||'No description yet.')+'\nLocation: '+(obj.location||'Choose a location below')+(obj.read_text?'\n\nReadable text: '+obj.read_text:'');if(type==='room'){$('map-center').value=obj.id;refreshDesignerMap().catch(e=>setStatus(e.message,'warn'));}};
  if(window.latestMap)window.renderRoomPanel(window.latestMap);
  const oldSelectGame=selectGame;selectGame=async(...args)=>{await oldSelectGame(...args);await refreshDesignerMap();};
})();
