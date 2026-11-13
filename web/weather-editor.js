/* Creator-only regional_weather settings. Draft -> validate -> save -> explicit Apply. */
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
  const open = button('Weather settings', 'ed-regional_weather');
  open.title = 'Edit optional weather events for the selected world';
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

  const example = {version:1,enabled:false,seed:17,regions:[{
    id:'local_vale',name:'Local vale',rooms:['OUTDOOR_ROOM','PUBLIC_SHELTER'],
    shelters:['PUBLIC_SHELTER'],severe_chance:0.03,tornado_chance:0.01,
    tornado_rooms:['OUTDOOR_ROOM'],consequences:true
  }]};
  open.onclick = async () => {
    if (!config.editor_enabled || !ed.gameSlug || opening || dialog) return;
    const slug = ed.gameSlug;
    const name = ed.gameName || slug;
    // Pin all requests to the selected world, including after async responses.
    const path = 'games/' + encodeURIComponent(slug) + '/regional_weather';
    opening = true;
    syncPermission();
    try {
      const current = await apiGet(path);
      if (current.error) throw Error(current.error);
      if (ed.gameSlug !== slug || !config.editor_enabled) return;
      let revision = current.revision;
      let baseline = current.regional_weather_json;
      let busy = false;
      dialog = el('dialog');
      const activeDialog = dialog;
      dialog.id = 'regional_weather-dialog';
      dialog.setAttribute('aria-labelledby', 'regional_weather-heading');
      dialog.style.cssText = 'box-sizing:border-box;width:min(760px,94vw);max-height:90vh;overflow:auto;background:#161c24;color:#e2e8ed;border:1px solid #607c72;border-radius:10px;padding:22px';
      const heading = el('h2', 'Weather · ' + name + ' (' + slug + ')');
      heading.id = 'regional_weather-heading';
      const hint = el('p', 'Optional simulation is disabled by default. Opening or editing this dialog changes nothing. Edit only metadata.regional_weather here; set "enabled": true deliberately to enable it. Shelter and climate fields are edited on each room. Events also require living rules; enable those separately with the creator toolbar if needed.');
      const workflow = el('p', 'Validate checks saved rooms. Save room edits with the main Save button first. Save weather writes only these settings, without applying them. Then use Apply to running game, or Run this world, in the creator toolbar.');
      const label = el('label', 'Weather configuration (JSON)');
      label.htmlFor = 'regional_weather-json';
      const input = el('textarea');
      input.id = 'regional_weather-json';
      input.rows = 15;
      input.spellcheck = false;
      input.value = baseline;
      input.style.cssText = 'box-sizing:border-box;display:block;width:100%;min-height:220px;resize:vertical;background:#0d1218;color:#def1e9;border:1px solid #53675f;padding:10px;font:13px/1.45 monospace';
      const result = el('p', current.regional_weather?.enabled === true ? 'Saved setting: enabled. Changes require Save, then Apply.' : 'Saved setting: disabled. No simulation is enabled by viewing this dialog.');
      result.id = 'regional_weather-status';
      result.setAttribute('role', 'status');
      result.setAttribute('aria-live', 'polite');
      result.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere';
      const details = el('details');
      const sample = el('pre', JSON.stringify(example, null, 2));
      sample.style.cssText = 'white-space:pre-wrap;max-height:220px;overflow:auto';
      const useExample = button('Copy example into draft', 'regional_weather-example');
      details.append(el('summary', 'Schema and disabled example'),
        el('p', 'Version 1 accepts enabled, seed and up to 32 regions. Regions have unique IDs, names, explicit rooms and public shelters. No custom world is enabled automatically. Each severe-prone outdoor room needs a real shelter route within 12 steps.'),
        el('p', 'Optional regional fields: latitude, seasonal_weights (all four seasons, weights for sunny, partly cloudy, rain, wind and thunderstorm), duration_minutes [30,360], warning_minutes 15–60, severe_chance 0–0.1, tornado_chance 0–0.05, severe_cooldown_minutes 1500–30000, exposure room-to-0–1, and at most eight tornado_rooms.'),
        el('p', 'Shelters must be actual indoor rooms marked weather_shelter=true, not rentable or private properties. Cold rain becomes snow after local temperature is calculated. Warning periods precede severe conditions. Consequences are bounded character exposure, not building destruction. Setting consequences=false disables exposure damage, not weather or refuge behavior.'),
        el('p', 'The disabled example uses placeholders. Replace every room ID and explicitly mark real public shelters before saving. Save preserves unrelated world metadata; Apply remains separate. See docs/REGIONAL-WEATHER.txt.'), sample, useExample);
      const rooms = el('details');
      rooms.append(el('summary', 'Saved room IDs (' + current.room_ids.length + ')'), el('pre', current.room_ids.join('\n') || 'No saved rooms.'));
      const controls = el('div');
      controls.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin-top:16px';
      const validate = button('Validate draft', 'regional_weather-validate');
      const save = button('Save weather', 'regional_weather-save');
      const reload = button('Reload saved', 'regional_weather-reload');
      const cancel = button('Cancel', 'regional_weather-cancel');
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
        if (ed.gameSlug !== slug || !config.editor_enabled) throw Error('The selected world or creator permissions changed. Close this dialog and reopen Weather settings.');
      };
      input.oninput = () => status(input.value === baseline ? 'No draft changes.' : 'Draft changes only. Nothing has been saved or applied.');
      useExample.onclick = () => {
        if (input.value !== baseline && !confirm('Replace this unsaved weather draft with the example?')) return;
        input.value = JSON.stringify(example, null, 2);
        status('Disabled example copied into the draft. Replace placeholder room IDs before validating or saving.');
      };
      const submit = async validateOnly => {
        if (busy) return;
        try {
          stillSelected();
          const value = JSON.parse(input.value);
          if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Weather must be a JSON object.');
          setBusy(true);
          status(validateOnly ? 'Validating draft…' : 'Saving weather…');
          const response = await apiPost(path, {regional_weather_json: input.value, validate_only: validateOnly, revision});
          if (response.error) throw Error(response.error);
          if (!activeDialog.isConnected) return;
          if (!validateOnly) {
            revision = response.revision;
            baseline = response.regional_weather_json;
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
        if (input.value !== baseline && !confirm('Discard the unsaved weather draft and reload saved settings?')) return;
        try {
          stillSelected(); setBusy(true);
          const response = await apiGet(path);
          if (response.error) throw Error(response.error);
          if (!activeDialog.isConnected) return;
          revision = response.revision;
          baseline = response.regional_weather_json;
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
