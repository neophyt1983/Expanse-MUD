/* Complete portable-world files alongside the structured Creator inspectors. */
(() => {
  'use strict';
  const toolbar = document.getElementById('ed-save')?.parentElement;
  if (!toolbar) return;
  const make = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, id) => {
    const node = make('button', text);
    node.type = 'button'; node.className = 'ed-btn';
    if (id) node.id = id;
    return node;
  };
  const open = button('World files', 'ed-world-files');
  open.title = 'Edit all authored JSON, world settings and media in this draft';
  toolbar.append(open);
  let active = null, opening = false;
  function permission() {
    open.hidden = !config.editor_only || !config.editor_enabled;
    open.disabled = opening || !!active || !ed.gameSlug;
    if (active && (!config.editor_enabled || active.slug !== ed.gameSlug)) active.dialog.close();
  }
  const oldToolbar = updateToolbar;
  updateToolbar = function () { oldToolbar(); permission(); };
  new MutationObserver(permission).observe(document.querySelector('header nav button[data-tab="editor"]'),
    {attributes: true, attributeFilter: ['disabled', 'hidden']});
  permission();

  open.onclick = async () => {
    if (open.disabled || !config.editor_only || !config.editor_enabled) return;
    opening = true; permission();
    const slug = ed.gameSlug, path = 'games/' + encodeURIComponent(slug) + '/';
    try {
      const inventory = await apiGet(path + 'files');
      if (inventory.error) throw Error(inventory.error);
      if (slug !== ed.gameSlug || !config.editor_enabled) return;
      const dialog = make('dialog'); dialog.className = 'editor-files'; dialog.id = 'editor-files-dialog';
      dialog.setAttribute('aria-labelledby', 'editor-files-title');
      const heading = make('h2', 'World files — ' + (ed.gameName || slug)); heading.id = 'editor-files-title';
      const help = make('p', 'Edit any authored JSON file or add, replace and download world media. These changes stay in your draft. Export the complete .expanse file when ready.');
      const pending = make('p'); pending.className = 'editor-files-note';
      const choices = make('select'); choices.id = 'editor-file-select'; choices.setAttribute('aria-label', 'World file');
      const actions = make('div'); actions.className = 'editor-files-actions';
      const add = button('New JSON file', 'editor-file-new'), upload = button('Upload / replace file', 'editor-file-upload');
      const reload = button('Reload file', 'editor-file-reload'), save = button('Save file to draft', 'editor-file-save');
      const remove = button('Delete file', 'editor-file-delete'), close = button('Close', 'editor-file-close');
      const download = make('a', 'Download file'); download.className = 'ed-btn'; download.id = 'editor-file-download'; download.download = '';
      actions.append(add, upload, reload, download, save, remove, close);
      const input = make('input'); input.type = 'file'; input.hidden = true;
      input.accept = '.json,.png,.jpg,.jpeg,.webp,.gif,.ogg,.mp3,.wav';
      const details = make('p'); details.className = 'editor-files-details'; details.id = 'editor-file-details';
      const text = make('textarea'); text.id = 'editor-file-text'; text.spellcheck = false;
      text.setAttribute('aria-label', 'JSON file contents'); text.setAttribute('aria-describedby', 'editor-file-details');
      const binary = make('p', 'This media file can be downloaded or replaced using Upload / replace file.');
      const status = make('p'); status.id = 'editor-file-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
      dialog.append(heading, help, pending, choices, actions, input, details, text, binary, status);
      let current = null, saved = '', busy = false, listing = inventory;
      active = {dialog, slug};
      const dirty = () => current && !text.hidden && (!current.exists || text.value !== saved);
      function state() {
        choices.disabled = add.disabled = upload.disabled = reload.disabled = busy;
        save.disabled = busy || !current || text.hidden || text.readOnly || !dirty();
        remove.disabled = busy || !current?.exists || current.readonly || current.pending || ['metadata.json', 'rooms.json'].includes(current.name);
        download.hidden = !current?.exists;
        close.disabled = busy;
      }
      function showInventory(packet, selected) {
        listing = packet;
        choices.replaceChildren();
        for (const row of packet.files || []) {
          const option = make('option', row.name + ' · ' + row.size.toLocaleString() + ' bytes');
          option.value = row.name; choices.append(option);
        }
        if (selected && !(packet.files || []).some(row => row.name === selected)) {
          const option = make('option', selected + ' · new file'); option.value = selected; choices.append(option);
        }
        choices.value = selected || packet.files?.find(row => row.name === 'metadata.json')?.name || packet.files?.[0]?.name || '';
        pending.hidden = !packet.pending?.length;
        pending.textContent = packet.pending?.length ? 'Staged record edits: ' + packet.pending.join(', ') + '. Use Save draft in the main toolbar before replacing those files or exporting.' : '';
      }
      async function load(name) {
        if (!name) return;
        busy = true; state();
        try {
          const packet = await apiGet(path + 'file?name=' + encodeURIComponent(name));
          if (packet.error) throw Error(packet.error);
          current = packet;
          text.hidden = !Object.prototype.hasOwnProperty.call(packet, 'text'); binary.hidden = !text.hidden;
          text.readOnly = !!packet.readonly || !!packet.pending;
          text.value = packet.text || (text.hidden ? '' : '{}\n'); saved = text.value;
          choices.value = name; download.href = packet.download_url;
          details.textContent = name + ' · ' + packet.size.toLocaleString() + ' bytes' +
            (packet.readonly ? ' · Generated by Export; read only.' : packet.pending ? ' · Save or revert staged record edits before changing this file.' : text.hidden ? '' : ' · JSON is saved exactly as typed, including large integer seeds.');
          status.textContent = packet.exists ? 'File loaded from the draft.' : 'New file. Enter JSON and save it to the draft.';
        } catch (error) {
          choices.value = current?.name || '';
          status.textContent = error.message || String(error);
          throw error;
        } finally { busy = false; state(); }
      }
      const canDiscard = () => !dirty() || confirm('Discard the unsaved text in this file?');
      const fail = error => { status.textContent = error.message || String(error); };
      choices.onchange = () => {
        const chosen = choices.value;
        if (!canDiscard()) { choices.value = current?.name || ''; return; }
        load(chosen).catch(fail);
      };
      text.addEventListener('input', state);
      reload.onclick = () => { if (current && canDiscard()) load(current.name).catch(fail); };
      add.onclick = () => {
        if (!canDiscard()) return;
        const name = prompt('New supported world JSON file, or JSON under assets/:', 'assets/world-notes.json');
        if (!name) return;
        if (!name.endsWith('.json')) { fail(Error('Choose a JSON filename. Use Upload / replace file for media.')); return; }
        showInventory(listing, name); load(name).catch(fail);
      };
      save.onclick = async () => {
        if (save.disabled) return;
        busy = true; state();
        try {
          const result = await apiPost(path + 'file', {name: current.name, text: text.value, revision: current.revision});
          if (result.error) throw Error(result.error);
          saved = text.value; current.revision = result.revision; current.exists = true;
          const packet = await apiGet(path + 'files'); if (packet.error) throw Error(packet.error);
          showInventory(packet, current.name); status.textContent = result.text;
          await refreshEntriesCache();
        } catch (error) { fail(error); }
        finally { busy = false; state(); }
      };
      upload.onclick = () => { if (canDiscard()) input.click(); };
      input.onchange = async () => {
        const file = input.files?.[0]; input.value = '';
        if (!file) return;
        const limit = file.name.endsWith('.json') ? inventory.max_file_bytes : inventory.max_media_bytes;
        if (file.size > limit) { fail(Error('This file must be at most ' + Math.floor(limit / 1048576) + ' MiB.')); return; }
        const suggested = file.name.endsWith('.json') ? file.name : 'assets/' + file.name;
        const name = prompt('Save this file at this path inside the world:', suggested);
        if (!name) return;
        busy = true; state();
        try {
          const found = current?.name === name ? current : await apiGet(path + 'file?name=' + encodeURIComponent(name));
          if (found.error) throw Error(found.error);
          if (found.exists && !confirm('Replace ' + name + ' in this draft?')) return;
          const data = await new Promise((resolve, reject) => {
            const reader = new FileReader(); reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(Error('The selected file could not be read.')); reader.readAsDataURL(file);
          });
          const result = await apiPost(path + 'file-upload', {name, data, revision: found.revision});
          if (result.error) throw Error(result.error);
          const packet = await apiGet(path + 'files'); if (packet.error) throw Error(packet.error);
          showInventory(packet, name); await load(name); status.textContent = result.text;
          await refreshEntriesCache();
        } catch (error) { fail(error); }
        finally { busy = false; state(); }
      };
      remove.onclick = async () => {
        if (remove.disabled || !canDiscard() || !confirm('Delete ' + current.name + ' from this draft? Update any references before exporting.')) return;
        busy = true; state();
        try {
          const result = await apiPost(path + 'file-delete', {name: current.name, revision: current.revision});
          if (result.error) throw Error(result.error);
          const packet = await apiGet(path + 'files'); if (packet.error) throw Error(packet.error);
          current = null; showInventory(packet); await load(choices.value); status.textContent = result.text;
          await refreshEntriesCache();
        } catch (error) { fail(error); }
        finally { busy = false; state(); }
      };
      const leave = () => { if (!busy && canDiscard()) dialog.close(); };
      close.onclick = leave;
      dialog.addEventListener('cancel', event => { event.preventDefault(); leave(); });
      const unload = event => { if (dirty()) { event.preventDefault(); event.returnValue = ''; } };
      window.addEventListener('beforeunload', unload);
      dialog.addEventListener('close', () => {
        window.removeEventListener('beforeunload', unload); dialog.remove(); active = null; permission(); open.focus();
      }, {once: true});
      showInventory(inventory);
      document.body.append(dialog); dialog.showModal();
      await load(choices.value);
    } catch (error) { setStatus(error.message || String(error), 'warn'); }
    finally { opening = false; permission(); }
  };
})();
