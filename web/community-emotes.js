(() => {
  'use strict';
  const entries = [["angry", "Angry"], ["back", "Welcome back"], ["blush", "Blush"], ["book", "Reading"], ["bow", "Bow"], ["brb", "Be right back"], ["build", "Building"], ["celebrate", "Celebrate"], ["chat", "Let’s talk"], ["clap", "Applause"], ["confused", "Confused"], ["cool", "Cool"], ["cry", "Crying"], ["explore", "Explore"], ["facepalm", "Facepalm"], ["farm", "Farming"], ["goodgame", "Good game"], ["grin", "Big grin"], ["heal", "Healing"], ["heart_eyes", "Heart eyes"], ["hug", "Hug"], ["hype", "Hype"], ["idea", "Idea"], ["laugh", "Laugh"], ["love", "Love"], ["lurking", "Lurking"], ["magic", "Magic"], ["map", "Map"], ["nervous", "Nervous"], ["no", "No"], ["potion", "Potion"], ["proud", "Proud"], ["question", "Question"], ["sad", "Sad"], ["salute", "Salute"], ["shield", "Shield"], ["sing", "Singing"], ["sleepy", "Sleepy"], ["smile", "Smile"], ["sorry", "Sorry"], ["sword", "Sword"], ["thanks", "Thank you"], ["think", "Thinking"], ["thumbs_down", "Thumbs down"], ["thumbs_up", "Thumbs up"], ["trade", "Trading"], ["warning", "Warning"], ["wave", "Wave"], ["wink", "Wink"], ["wolf", "Wolf"], ["wow", "Wow"], ["yes", "Yes"], ["npc_blade", "Blade stance"], ["npc_bow_pose", "Bow stance"], ["npc_harvesting", "Harvesting"], ["npc_natural_attack", "Natural attack"], ["npc_performing", "Performing"], ["npc_shield_pose", "Shield stance"], ["npc_spear", "Spear stance"], ["npc_studying", "Studying"], ["npc_trading", "Trading NPC"], ["npc_unarmed", "Unarmed"], ["npc_walking", "Walking NPC"], ["npc_working", "Working NPC"]];
  const index = new Map(entries.map(([name], i) => [name.toLowerCase(), i]));
  const symbols = {"😠": "angry", "😡": "angry", "☺": "blush", "😊": "blush", "📚": "book", "📖": "book", "🙇": "bow", "🛠": "build", "🔨": "build", "🎉": "celebrate", "🥳": "celebrate", "💬": "chat", "👏": "clap", "😕": "confused", "😧": "confused", "😎": "cool", "😢": "cry", "😭": "cry", "🧭": "explore", "🤦": "facepalm", "🌾": "farm", "😁": "grin", "🩹": "heal", "😍": "heart_eyes", "🥰": "heart_eyes", "🤗": "hug", "🫂": "hug", "🤩": "hype", "💡": "idea", "😄": "laugh", "😂": "laugh", "🤣": "laugh", "😆": "laugh", "❤": "love", "💕": "love", "💖": "love", "👀": "lurking", "🪄": "magic", "🗺": "map", "😬": "nervous", "😰": "nervous", "🙅": "no", "❌": "no", "🧪": "potion", "😌": "proud", "❓": "question", "🙁": "sad", "☹": "sad", "😔": "sad", "🫡": "salute", "🛡": "shield", "🎤": "sing", "🎶": "sing", "😴": "sleepy", "🥱": "sleepy", "🙂": "smile", "😀": "smile", "😃": "smile", "🥺": "sorry", "⚔": "sword", "🗡": "sword", "🙏": "thanks", "🤔": "think", "😐": "think", "👎": "thumbs_down", "😒": "thumbs_down", "👍": "thumbs_up", "🤝": "trade", "⚠": "warning", "👋": "wave", "😉": "wink", "😏": "wink", "🐺": "wolf", "😮": "wow", "😲": "wow", "✅": "yes"};
  const graphemes = new Intl.Segmenter(undefined, {granularity: 'grapheme'});
  function icon(name, label) {
    const i = index.get(name.toLowerCase());
    const span = document.createElement('span');
    span.className = 'expanse-emote';
    span.style.backgroundPosition = (i % 8 * 100 / 7) + '% ' + (Math.floor(i / 8) * 100 / 7) + '%';
    span.setAttribute('role', 'img');
    span.setAttribute('aria-label', label || entries[i][1]);
    span.title = label || entries[i][1];
    return span;
  }
  function render(node, value) {
    const text = String(value ?? '');
    if (!/[:\u2000-\uFFFF]/u.test(text) && !/\p{Extended_Pictographic}/u.test(text)) {
      node.textContent = text;
      return;
    }
    const result = document.createDocumentFragment();
    let plain = '';
    function addIcon(name) {
      if (plain) { result.append(plain); plain = ''; }
      result.append(icon(name));
    }
    for (const part of text.split(/(:[A-Za-z_]+:)/)) {
      const name = part.startsWith(':') && part.endsWith(':') ? part.slice(1,-1).toLowerCase() : '';
      if (index.has(name)) { addIcon(name); continue; }
      if (!/\p{Extended_Pictographic}/u.test(part)) { plain += part; continue; }
      for (const {segment} of graphemes.segment(part)) {
        const key = segment.replace(/[\uFE0E\uFE0F\u{1F3FB}-\u{1F3FF}]/gu, '');
        if (Object.hasOwn(symbols, key)) addIcon(symbols[key]);
        else plain += segment;
      }
    }
    if (plain) result.append(plain);
    node.replaceChildren(result);
  }
  function installPicker() {
    const input = document.getElementById('input');
    if (!input || !input.form || document.getElementById('expanse-emote-picker')) return;
    const trigger = document.createElement('button');
    trigger.type = 'button'; trigger.className = 'emote-trigger'; trigger.append(icon('smile'));
    trigger.title = 'Choose an Expanse emote'; trigger.setAttribute('aria-label',trigger.title);
    const dialog = document.createElement('dialog');
    dialog.id = 'expanse-emote-picker'; dialog.setAttribute('aria-label','Expanse emotes');
    const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Close emotes';
    close.onclick = () => dialog.close();
    const grid = document.createElement('div'); grid.className = 'emote-grid-picker';
    for (const [name, label] of entries) {
      const button = document.createElement('button'); button.type = 'button';
      button.append(icon(name)); button.setAttribute('aria-label',label); button.title = label;
      button.onclick = () => {
        const token = ':' + name + ':';
        if (!input.value.trim()) input.value = 'say ' + token;
        else input.setRangeText(token, input.selectionStart, input.selectionEnd, 'end');
        dialog.close(); input.focus(); input.dispatchEvent(new Event('input', {bubbles:true}));
      };
      grid.append(button);
    }
    dialog.append(close,grid); document.body.append(dialog);
    trigger.onclick = () => dialog.showModal();
    input.insertAdjacentElement('afterend', trigger);
  }
  window.ExpanseEmotes = {render,icon};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installPicker);
  else installPicker();
})();
