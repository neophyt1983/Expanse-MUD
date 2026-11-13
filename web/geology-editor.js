/* Creator-only geology settings. Draft -> validate -> save -> explicit Apply. */
(() => {
  'use strict';
  const toolbar = document.getElementById('ed-save')?.parentElement;
  if (!toolbar) return;
  const el = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, id) => {
    const node = el('button', text);
    node.type = 'button';
    node.className = 'ed-btn';
    if (id) node.id = id;
    return node;
  };
  const open = button('Geology settings', 'ed-geology');
  open.title = 'Edit optional geological events for the selected world';
  toolbar.append(open);
  let dialog = null;
  let opening = false;
  const syncPermission = () => {
    open.hidden = !config.editor_enabled;
    open.disabled = opening || !config.editor_enabled || !ed.gameSlug;
    if (!config.editor_enabled && dialog) dialog.close();
  };
  const oldToolbar = updateToolbar;
  updateToolbar = function () { oldToolbar(); syncPermission(); };
  new MutationObserver(syncPermission).observe(
    document.querySelector('header nav button[data-tab="editor"]'),
    {attributes: true, attributeFilter: ['disabled']}
  );
  syncPermission();

  const example = {
    enabled: false, seed: 17,
    faults: [{id: 'ridge_fault', rooms: ['REPLACE_WITH_FAULT_ROOM'],
      tension_rate: 0.005, quake_rate: 0.01, initial_tension: 0.1,
      min_magnitude: 2, max_magnitude: 6, duration_minutes: 3, recovery_minutes: 30,
      consequences: {actor_exposure: [], structures: [], routes: [], resources: [], port_routes: [], recovery_minutes: 120}}],
    volcanoes: [{id: 'volcanic_peak', rooms: ['REPLACE_WITH_VOLCANO_ROOM'],
      rate: 0.005, min_intensity: 0.2, max_intensity: 0.9,
      duration_minutes: 8, recovery_minutes: 60}],
    basins: [{id: 'river_basin', rooms: ['REPLACE_WITH_BASIN_ROOM'],
      source: 'river_overflow', storm_rate: 0.01, flood_chance: 0.4,
      min_intensity: 0.2, max_intensity: 0.8, duration_minutes: 15, recovery_minutes: 45}]
  };
  open.onclick = async () => {
    if (!config.editor_enabled || !ed.gameSlug || opening || dialog) return;
    const slug = ed.gameSlug;
    const name = ed.gameName || slug;
    // Pin all requests to the selected world, including after async responses.
    const path = 'games/' + encodeURIComponent(slug) + '/geology';
    opening = true;
    syncPermission();
    try {
      const current = await apiGet(path);
      if (current.error) throw Error(current.error);
      if (ed.gameSlug !== slug || !config.editor_enabled) return;
      let revision = current.revision;
      let baseline = current.geology_json;
      let busy = false;
      dialog = el('dialog');
      const activeDialog = dialog;
      dialog.id = 'geology-dialog';
      dialog.setAttribute('aria-labelledby', 'geology-heading');
      dialog.style.cssText = 'box-sizing:border-box;width:min(760px,94vw);max-height:90vh;overflow:auto;background:#161c24;color:#e2e8ed;border:1px solid #607c72;border-radius:10px;padding:22px';
      const heading = el('h2', 'Geology · ' + name + ' (' + slug + ')');
      heading.id = 'geology-heading';
      const hint = el('p', 'Optional simulation is disabled by default. Opening or editing this dialog changes nothing. Edit only metadata.geology here; set "enabled": true deliberately to enable it. Static room geology is edited in each room’s fields. Events also require living rules; enable those separately with the creator toolbar if needed.');
      const workflow = el('p', 'Validate checks saved rooms. Save room edits with the main Save button first. Save geology writes only these settings, without applying them. Then use Apply to running game, or Run this world, in the creator toolbar.');
      const label = el('label', 'Geology configuration (JSON)');
      label.htmlFor = 'geology-json';
      const input = el('textarea');
      input.id = 'geology-json';
      input.rows = 15;
      input.spellcheck = false;
      input.value = baseline;
      input.style.cssText = 'box-sizing:border-box;display:block;width:100%;min-height:220px;resize:vertical;background:#0d1218;color:#def1e9;border:1px solid #53675f;padding:10px;font:13px/1.45 monospace';
      const result = el('p', current.geology?.enabled === true ? 'Saved setting: enabled. Changes require Save, then Apply.' : 'Saved setting: disabled. No simulation is enabled by viewing this dialog.');
      result.id = 'geology-status';
      result.setAttribute('role', 'status');
      result.setAttribute('aria-live', 'polite');
      result.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere';
      const details = el('details');
      const sample = el('pre', JSON.stringify(example, null, 2));
      sample.style.cssText = 'white-space:pre-wrap;max-height:220px;overflow:auto';
      const useExample = button('Copy example into draft', 'geology-example');
      details.append(el('summary', 'Schema and disabled example'),
        el('p', 'Use enabled (boolean), seed (nonnegative integer), and faults, volcanoes, basins (arrays). Sources need unique IDs and explicit room IDs. At most 32 sources per array and 128 rooms per source. Rates are 0–1, quake magnitudes 0–9.9, intensities 0–1. Durations are 1–1440 simulated minutes, visual recovery 0–10080 minutes. Sources without consequences remain visual-only. Nothing in this dialog silently enables damage or selects targets.'),
        el('p', 'Flood source must be heavy_rain, river_overflow or snowmelt. A volcano may reference fault_id. Tsunamis require an explicitly configured offshore/seafloor-displacement source, magnitude threshold, chance and coastal rooms; they are never inferred from ordinary quakes. See docs/GEOLOGICAL-EVENTS.txt in the installation for the full schema.'),
        el('p', 'Optional consequences on each source explicitly target actor_exposure [{"room":"ROOM_ID","exposure":0.25}], structures [{"building":"BUILDING_ID"}] or [{"room":"PROPERTY_PLOT_ROOM_ID"}], routes [{"source":"ROOM_ID","direction":"east","destination":"OTHER_ROOM_ID"}], resources [{"room":"ROOM_ID","resource":"RESOURCE_ID"}], and port_routes [{"origin":"PORT_ROOM_ID","destination":"OTHER_PORT_ROOM_ID"}]. Each target must exist. Actors, resources, structures and route origins must be in that source’s affected rooms; all rooms in a targeted building must be included. A route destination may be outside the affected area.'),
        el('p', 'Consequence recovery_minutes is 1–1440 (default 120). At most 128 targets per list and 256 per source. Explicit exposure can cause bounded HP loss. Already badly wounded characters still follow ordinary mortality rules. Structures may need repair; workshops, resources and selected passages or boat services may become temporarily unavailable. These are persisted conditions, not permanent destruction, and may outlast event artwork. Engine safety limits favor players and NPCs, preserve safe escape, and prevent supervolcano-scale harm.'),
        el('p', 'The example is disabled, has empty consequence target lists, and uses placeholder room IDs. Remove unwanted sources and replace every placeholder before saving. Empty lists do not select any target. Save geology preserves the rest of your world; Apply remains a separate step.'), sample, useExample);
      const rooms = el('details');
      rooms.append(el('summary', 'Saved room IDs (' + current.room_ids.length + ')'), el('pre', current.room_ids.join('\n') || 'No saved rooms.'));
      const controls = el('div');
      controls.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin-top:16px';
      const validate = button('Validate draft', 'geology-validate');
      const save = button('Save geology', 'geology-save');
      const reload = button('Reload saved', 'geology-reload');
      const cancel = button('Cancel', 'geology-cancel');
      controls.append(validate, save, reload, cancel);
      const setBusy = value => {
        busy = value;
        for (const b of [validate, save, reload, cancel, useExample]) b.disabled = value;
        input.disabled = value;
      };
      const status = (text, error = false) => {
        result.textContent = text;
        result.style.color = error ? '#ffba9d' : '#badacb';
      };
      const stillSelected = () => {
        if (ed.gameSlug !== slug || !config.editor_enabled) throw Error('The selected world or creator permissions changed. Close this dialog and reopen Geology settings.');
      };
      input.oninput = () => status(input.value === baseline ? 'No draft changes.' : 'Draft changes only. Nothing has been saved or applied.');
      useExample.onclick = () => {
        if (input.value !== baseline && !confirm('Replace this unsaved geology draft with the example?')) return;
        input.value = JSON.stringify(example, null, 2);
        status('Disabled example copied into the draft. Replace placeholder room IDs before validating or saving.');
      };
      const submit = async validateOnly => {
        if (busy) return;
        try {
          stillSelected();
          const value = JSON.parse(input.value);
          if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Geology must be a JSON object.');
          setBusy(true);
          status(validateOnly ? 'Validating draft…' : 'Saving geology…');
          const response = await apiPost(path, {geology_json: input.value, validate_only: validateOnly, revision});
          if (response.error) throw Error(response.error);
          if (!activeDialog.isConnected) return;
          if (!validateOnly) {
            revision = response.revision;
            baseline = response.geology_json;
            input.value = baseline;
            cancel.textContent = 'Close';
            setStatus(response.text, 'ok');
          }
          status(response.text);
        } catch (error) { status(error.message, true); }
        finally { setBusy(false); }
      };
      validate.onclick = () => submit(true);
      save.onclick = () => submit(false);
      reload.onclick = async () => {
        if (busy) return;
        if (input.value !== baseline && !confirm('Discard the unsaved geology draft and reload saved settings?')) return;
        try {
          stillSelected(); setBusy(true);
          const response = await apiGet(path);
          if (response.error) throw Error(response.error);
          if (!activeDialog.isConnected) return;
          revision = response.revision;
          baseline = response.geology_json;
          input.value = baseline;
          cancel.textContent = 'Cancel';
          status('Reloaded saved settings. Nothing was changed or applied.');
        } catch (error) { status(error.message, true); }
        finally { setBusy(false); }
      };
      cancel.onclick = () => activeDialog.close();
      dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
      dialog.addEventListener('close', () => { activeDialog.remove(); if (dialog === activeDialog) dialog = null; open.focus(); });
      dialog.append(heading, hint, workflow, label, input, result, details, rooms, controls);
      document.body.append(dialog);
      dialog.showModal();
      input.focus();
    } catch (error) { setStatus(error.message, 'warn'); }
    finally { opening = false; syncPermission(); }
  };
})();
