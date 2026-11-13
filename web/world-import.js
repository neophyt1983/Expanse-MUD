(() => {
  'use strict';
  const dialog = document.createElement('dialog');
  dialog.id = 'world-import';
  dialog.setAttribute('aria-labelledby', 'world-import-title');
  dialog.innerHTML = `
    <h2 id="world-import-title">Import world</h2>
    <p>World files in <strong data-home>your Expanse folder</strong></p>
    <label for="world-import-list">Available worlds</label>
    <select id="world-import-list" size="5"></select>
    <div class="world-import-actions">
      <button type="button" data-install>Import selected world</button>
      <button type="button" data-refresh>Refresh</button>
      <button type="button" data-browse>Browse elsewhere…</button>
      <input type="file" accept=".expanse" hidden>
    </div>
    <p data-status role="status" aria-live="polite"></p>
    <div class="world-import-actions">
      <button type="button" data-play hidden>New game</button>
      <button type="button" data-close>Close</button>
    </div>`;
  document.body.append(dialog);
  const get = selector => dialog.querySelector(selector);
  const list = get('select');
  const status = get('[data-status]');
  const play = get('[data-play]');
  const fileInput = get('input');
  let files = [], token = '', selectedWorld = '', busy = false;

  function lock(value) {
    busy = value;
    for (const control of dialog.querySelectorAll('button,select')) control.disabled = value;
    get('[data-install]').disabled = value || list.selectedIndex < 0;
    list.disabled = value || !files.length;
    dialog.setAttribute('aria-busy', String(value));
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || result.error) throw Error(result.error || 'Could not complete the import.');
    return result;
  }

  async function refresh() {
    if (busy) return;
    lock(true);
    const previous = list.selectedOptions[0]?.textContent;
    status.textContent = 'Looking for world files…';
    try {
      const config = await request('/api/config');
      if (!config.can_manage_server) throw Error('Only the host can import a world on this computer.');
      token = config.control_token;
      const data = await request('/api/world-import/files');
      get('[data-home]').textContent = data.home;
      files = data.files;
      list.replaceChildren();
      for (const [index, file] of files.entries()) {
        const label = file.member ? file.member + ' (in ' + file.path + ')' : file.path;
        list.add(new Option(label, String(index)));
      }
      const priorIndex = [...list.options].findIndex(o => o.textContent === previous);
      list.selectedIndex = files.length ? Math.max(priorIndex, 0) : -1;
      status.textContent = files.length ? '' : 'No .expanse files found. Copy one into this folder and choose Refresh, or browse for it.';
      if (data.unreadable) status.textContent += ' Some folders could not be read.';
    } catch (error) {
      files = [];
      list.replaceChildren();
      status.textContent = error.message;
    } finally {
      lock(false);
    }
  }

  async function install(upload) {
    if (busy || (!upload && list.selectedIndex < 0)) return;
    lock(true);
    play.hidden = true;
    status.textContent = 'Checking and importing the world…';
    try {
      const result = upload
        ? await request('/api/world-import/upload', {
            method: 'POST', headers: {'X-Expanse-Control': token}, body: upload
          })
        : await request('/api/world-import/install', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({...files[list.selectedIndex], control_token: token})
          });
      selectedWorld = result.id;
      status.textContent = result.name + (result.already_installed ? ' is already installed.' : ' is ready to play.');
      localStorage.setItem('expanse.lastImportedWorld', selectedWorld);
      document.dispatchEvent(new CustomEvent('expanse-world-imported', {detail: result}));
      play.hidden = typeof window.openAdventureMenu !== 'function';
    } catch (error) {
      status.textContent = error.message;
    } finally {
      lock(false);
      if (!play.hidden) play.focus();
    }
  }

  function open() {
    if (dialog.open) return;
    play.hidden = true;
    dialog.showModal();
    refresh();
  }
  get('[data-refresh]').onclick = refresh;
  get('[data-install]').onclick = () => install();
  get('[data-browse]').onclick = () => fileInput.click();
  fileInput.onchange = () => {
    const file = fileInput.files[0];
    if (file) install(file);
    fileInput.value = '';
  };
  play.onclick = () => {
    dialog.close();
    window.openAdventureMenu('single', selectedWorld);
  };
  get('[data-close]').onclick = () => dialog.close();
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  document.getElementById('open-world-import')?.addEventListener('click', open);
  document.getElementById('ed-import')?.addEventListener('click', open);
  window.ExpanseWorldImport = {open};
})();
