/* Shared workspace structure; original editor fields and command handlers remain authoritative. */
(()=>{
  const $=id=>document.getElementById(id);
  const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
  function send(command,label){
    if(!ws||ws.readyState!==WebSocket.OPEN){append('error','Connect to the game first.');return;}
    ws.send(JSON.stringify({command}));append('user','> '+(label||'Action')); 
  }
  function action(label,command){const b=make('button','ed-btn',label);b.type='button';b.title=label;b.dataset.action=command;b.onclick=()=>{if(command==='watch'&&window.ExpanseResidentWatch){window.ExpanseResidentWatch.open();return;}if(command==='history'&&window.ExpanseChronicles){window.ExpanseChronicles.open();return;}if((command==='news'||command==='news editions')&&window.ExpanseGazette){window.ExpanseGazette.open(command==='news editions');return;}const lists={inventory:'inventory',quests:'quests',adventures:'adventures',journal:'journal',market:'markets',survey:'survey',catalog:'catalog',wardrobe:'wardrobe',recipes:'recipes',condition:'condition'};if(lists[command]&&window.ExpansePlayerLists)window.ExpansePlayerLists.open(lists[command]);else send(command,label);};return b;}
  const game=$('tab-game'),conversation=make('div','workspace-panel conversation');
  conversation.append(make('h2','panel-title','Conversation'));
  const quick=make('div','quick-actions');for(const [l,c] of [['Look','look'],['Watch','watch'],['Inventory','inventory'],['Status','score'],['Help','help'],['Guide','guide'],['Bookshelves','books'],['Newspaper','news'],['Chronicles','history'],['Quests','quests'],['Adventures','adventures'],['Markets','market'],['Survey','survey'],['Catalog','catalog'],['Wardrobe','wardrobe'],['Recipes','recipes'],['Condition','condition']])quick.append(action(l,c));conversation.append(quick,$('log'),$('input-form'));
  const status=make('div');status.id='character-strip';status.setAttribute('role','status');status.textContent='Connecting to your character…';
  const location=make('aside','workspace-panel');location.id='location-panel';location.setAttribute('aria-label','Current location and actions');location.append(make('h2','panel-title','Current location'));
  const content=make('div','location-content');content.id='location-content';content.textContent='Create or resume a character to see your surroundings.';location.append(content);
  game.prepend(status,conversation);game.append(location);
  const sectionOpen = new Map();
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
    return {scroll, anchor, focus};
  }
  function restoreView({scroll, anchor, focus}) {
    const find = key => content.querySelector('[data-view-key="' + CSS.escape(key) + '"]');
    if (focus) {
      const row = find(focus.key);
      const control = row?.tagName === focus.tag ? row :
        Array.from(row?.querySelectorAll('button, select') || []).find(el =>
          el.tagName === focus.tag && (el.tagName === 'SELECT' || el.textContent === focus.label));
      control?.focus({preventScroll: true});
    }
    const row = anchor && find(anchor.key);
    if (row && location.offsetHeight && row.getBoundingClientRect().height) {
      const viewport = location.getBoundingClientRect();
      const delta = row.getBoundingClientRect().top - viewport.top - anchor.offset;
      location.scrollTop += delta * location.offsetHeight / viewport.height;
    } else {
      // Includes a last item picked up from the floor. The browser clamps to the new end.
      location.scrollTop = scroll;
    }
  }
  window.renderRoomPanel=m=>{
    if(!m.character||!m.location)return;
    const view = captureView();
    window.ExpanseTrade?.update(m);
    const p=m.character,r=m.location;status.replaceChildren();
    const name=make('strong',null,p.name);status.append(name);
    status.append(make('span',null,[p.race_name||p.race,p.class_name||p.char_class].filter(Boolean).join(' / ')||'Adventurer'));
    const meter=make('meter');meter.min=0;meter.max=Math.max(1,p.max_hp);meter.value=p.hp;meter.setAttribute('aria-label','Health');status.append(meter,make('span',null,'HP '+p.hp+' / '+p.max_hp),make('span',null,'Gold '+p.gold),make('span',null,r.name));
    if(p.advancement){const a=p.advancement;const badge=make('span',null,'Level '+a.level+' · XP '+a.xp+(a.next_xp?' / '+a.next_xp:' · Level cap'));badge.title='Earn experience through new discoveries, quests, NPC relationships, crafting, gathering and threats overcome. Repeat successful work earns diminishing practice XP within a daily budget; discoveries remain once-only.\n'+a.recent.join('\n');status.append(badge);if(a.practice)status.append(make('span',null,'Practice XP '+a.practice.used+' / '+a.practice.limit+' today'));}
    if(m.weather)status.append(make('span',null,m.weather.season+' · '+m.weather.weather+' · '+m.weather.temperature_c+' °C'));
    if(m.living){const c=m.living.conditions;status.append(make('span',null,'Mana '+c.mana+'/'+c.max_mana),make('span',null,m.calendar_text||('Day '+(Math.floor(m.living.minute/1500)+1))));}
    const next = document.createDocumentFragment();
    next.append(keyed(make('h2',null,r.name),'room',r.id),
                keyed(make('div','location-description',r.description),'description',r.id));
    if(m.market_summary){const counter=keyed(make('div','action-card',m.market_summary),'market',r.id);counter.append(action('View provisions','market'));next.append(counter);}
    function section(title, rows, build) {
      const group = disclosure(title, title+' ('+rows.length+')', title!=='Your inventory' && title!=='Posted reading', 'player-list-section');
      if (!rows.length) group.append(make('div','empty-state','None here.'));
      for (const row of rows) group.append(keyed(build(row), title, row.id));
      next.append(group);
    }
    section('Players here',r.players||[],x=>make('div','action-card',x.name+' ['+x.marker+']'));
    section('People and creatures',r.npcs||[],x=>{const card=make('div','action-card',x.name);
      const actor=(m.visual?.actors||[]).find(a=>a.id===x.id);
      if(actor&&window.ExpanseActorRenderer){
        const portrait=make('canvas','npc-portrait');portrait.width=portrait.height=64;portrait.setAttribute('role','img');portrait.setAttribute('aria-label',x.name+' portrait');
        const ctx=portrait.getContext('2d');ctx.imageSmoothingEnabled=false;window.ExpanseActorRenderer.drawActor(ctx,actor,32,32,64,false);card.prepend(portrait);
        if(actor.activity||actor.combat_pose){const text=actor.combat_pose?'Fighting · '+(window.ExpanseCombatArt?.labels[actor.combat_pose.stance]||'Combat stance'):actor.activity.label;card.append(make('small','npc-activity','Now · '+text));}
        if(actor.paperdoll?.occupation)card.append(make('small',null,actor.paperdoll.occupation));
      }
      if(x.title)card.append(make('small',null,x.title));card.append(make('small',null,'Location: '+r.name),make('small',null,x.description||''));const buttons=make('div','action-buttons');if((m.social?.npcs||[]).some(n=>n.id===x.id)){const talk=make('button','ed-btn','Talk');talk.type='button';talk.title='Choose an emotion or gift for this NPC';talk.onclick=()=>window.openNpcSocial(x.id);buttons.append(talk);}const dialogue=make('button','ed-btn',m.social?'Quest dialogue':'Talk');dialogue.type='button';dialogue.onclick=()=>window.ExpanseNpcConversation?.dialogue(x.id);buttons.append(dialogue);if(x.trade_available===true){const trade=make('button','ed-btn','Trade');trade.type='button';trade.onclick=()=>window.ExpanseTrade?.open(x.id,x.name);buttons.append(trade);}for(const offer of x.escorts||[])buttons.append(action(offer.mode==='follow'?'Follow guide':'Lead companion',offer.mode+' '+offer.quest));const observe=make('button','ed-btn','Watch');observe.type='button';observe.onclick=()=>window.ExpanseResidentWatch.open(x.id);buttons.append(observe);const attack=action('Attack','attack '+x.id);attack.classList.add('combat');buttons.append(attack);card.append(buttons);return card;});
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
