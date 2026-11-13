/* Explicit cohort authoring. Preview is read-only; Apply stages, never saves. */
(() => {
  'use strict';
  const toolbar = document.getElementById('ed-save')?.parentElement;
  if (!toolbar) return;
  const node = (tag, text) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const button = (id, text) => {
    const b = node('button', text);
    b.id = id; b.type = 'button'; b.className = 'ed-btn';
    return b;
  };
  const open = button('ed-population', 'Resident population');
  open.title = 'Preview a new opt-in resident cohort without changing existing people';
  toolbar.append(open);
  let dialog = null, opening = false;
  function permission() {
    open.hidden = !config.editor_enabled;
    open.disabled = opening || !!dialog || !config.editor_enabled || !ed.gameSlug;
    if (dialog && (!config.editor_enabled || ed.gameSlug !== dialog.dataset.world)) dialog.close();
  }
  const priorToolbar = updateToolbar;
  updateToolbar = function () { priorToolbar(); permission(); };
  const editorTab = document.querySelector('header nav button[data-tab="editor"]');
  if (editorTab) new MutationObserver(permission).observe(editorTab, {attributes:true, attributeFilter:['disabled']});
  permission();

  function report(container, response) {
    container.replaceChildren(node('h3', response.no_op ? 'Already installed: original cohort report' : 'Preview: target and generated cohort'));
    const s = response.summary || {}, pop = s.population || {};
    container.append(node('p', 'Requested: ' + (pop.requested ?? s.count ?? '?') +
      '; generated: ' + (pop.generated ?? s.count ?? '?') +
      '; existing NPC definitions: ' + (pop.existing_npc_definitions ?? pop.existing ?? 'see detail') +
      '. Existing-count basis: ' + (pop.existing_basis || 'authored NPC definitions, including creatures; not a living-resident total') +
      '. Denominator: ' + (pop.denominator || 'new cohort only') + '.'));
    if (Array.isArray(s.age_bins)) {
      const table = node('table'), header = node('tr');
      table.style.cssText = 'width:100%;text-align:left;border-collapse:collapse';
      for (const label of ['Local age range', 'Weight', 'Target', 'Actual']) header.append(node('th', label));
      const head = node('thead'); head.append(header); table.append(head);
      const body = node('tbody');
      for (const bin of s.age_bins) {
        const row = node('tr');
        for (const value of [bin.min + '–' + bin.max, bin.weight, bin.target_count, bin.actual_count]) row.append(node('td', String(value ?? '')));
        body.append(row);
      }
      table.append(body); container.append(table);
    }
    const households = s.households || {};
    container.append(node('p', 'Households: ' + (households.count ?? '?') +
      ' generated. Target: ' + (households.target || 'no statistical household quota; fictional composition constrained by adult care and authored capacity') + '.'));
    container.append(node('p', 'Local species: ' + (s.species || 'see detail') +
      '; target ' + (pop.requested ?? s.count ?? '?') + '; actual ' + (pop.generated ?? s.count ?? '?') +
      '. This cohort has one authored species; other local species and existing residents are outside its denominator.'));
    const details = node('details');
    const full = node('pre', JSON.stringify(s, null, 2));
    full.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:280px;overflow:auto';
    details.append(node('summary', 'Exact ages, household types, local species and learning detail'), full);
    container.append(details);
    for (const message of new Set([...(s.caveats || []), ...(response.warnings || [])])) container.append(node('p', String(message)));
  }

  open.onclick = async () => {
    if (!config.editor_enabled || !ed.gameSlug || dialog || opening) return;
    const slug = ed.gameSlug, name = ed.gameName || slug;
    const path = 'games/' + encodeURIComponent(slug) + '/population';
    opening = true; permission();
    try {
      const current = await apiGet(path);
      if (current.error) throw Error(current.error);
      if (slug !== ed.gameSlug || !config.editor_enabled) return;
      const active = node('dialog');
      dialog = active; active.id = 'population-dialog'; active.dataset.world = slug;
      active.setAttribute('aria-labelledby', 'population-heading');
      active.style.cssText = 'box-sizing:border-box;width:min(820px,94vw);max-height:90vh;overflow:auto;background:#161c24;color:#e2e8ed;border:1px solid #607c72;border-radius:10px;padding:22px';
      const heading = node('h2', 'Resident population · ' + name + ' (' + slug + ')'); heading.id = 'population-heading';
      const intro = node('p', 'Create a new cohort only when you choose. Opening, editing and Preview change no definitions or saves. Apply adds new editable NPC definitions and a manifest to this world’s Editor draft. Existing residents are never silently rebalanced.');
      const workflow = node('p', 'Preview includes current Editor drafts. After Apply, review NPC fields, Save, then Apply to running game using the main toolbar. Living rules must already be enabled separately. Cancel before Apply discards this configuration only.');
      const label = node('label', 'Population configuration (JSON): seed, age bins, species, homes/capacity, learning, work, leisure, faction and fictional health');
      label.htmlFor = 'population-json';
      const input = node('textarea'); input.id = 'population-json'; input.rows = 17; input.spellcheck = false;
      input.value = current.population_json;
      input.style.cssText = 'box-sizing:border-box;display:block;width:100%;min-height:260px;resize:vertical;background:#0d1218;color:#def1e9;border:1px solid #53675f;padding:10px;font:13px/1.45 monospace';
      const help = node('details');
      help.append(node('summary', 'Configuration, local years and calibration scope'),
        node('p', 'All ages use the Expanse calendar directly: 25 hours/day, 26 days/month and 8 months/year. No Earth-year conversion. The humanlike_fictional preset supplies editable local age bins; use species_authored with explicit age_bins for another species. Mage is an occupation or class, not a species.'),
        node('p', 'Use a unique cohort id, a nonnegative integer seed, count, race, species and group. homes is an explicit list of {room, capacity}; no room is auto-selected as housing. Use school_rooms or community_learning_rooms for the matching learning choice. workplaces uses {room, occupation, slots}; leisure_rooms is a list of real room IDs. Read the preview warnings about routes and capacity.'),
        node('p', 'Age bins use {min, max, weight}. Species life_stages is edited in the main species Editor as structured JSON, with fictional:true, infancy_end_years, school_start_years, adolescence_start_years, adulthood_years, work_start_years and elder_years. Adult relationships and adult work require age at least 18 plus species adulthood. Elders are not automatically retired.'),
        node('p', 'health.enabled is false by default. The fictional preset and exact-ID species_profiles are author choices, not medical facts. Optional adult_reference calibration describes an adult-only, ten-condition survey scope; it does not estimate child, all-age, nonhuman or fantasy prevalence. See docs/POPULATION-HEALTH.md for source year and limitations. Chronic profiles and support preferences do not alter acute injury, disease, ability or retirement.'),
        node('p', 'Example health settings: {"enabled":true,"preset":"fictional"}. Custom age_bands use {min_age_years,max_age_years,count_weights:[P0,P1,P2plus]}; the final maximum may be null. multi_count_weights chooses the exact fictional number within 2+. All health and species thresholds remain ordinary creator-editable data.'));
      const refs = node('details'), refText = node('pre', JSON.stringify(current.references || {}, null, 2));
      refText.style.cssText = 'white-space:pre-wrap;max-height:220px;overflow:auto';
      refs.append(node('summary', 'Current room, faction, race and species IDs / life-stage settings'), refText);
      const manifest = node('details'), manifestText = node('pre', JSON.stringify(current.manifest || {}, null, 2));
      manifestText.style.cssText = 'white-space:pre-wrap;max-height:220px;overflow:auto';
      manifest.append(node('summary', 'Existing generation manifest' + (current.pending ? ' (staged)' : '')), manifestText);
      const status = node('p', current.living_world_enabled ? 'Draft only. Choose explicit homes and settings, then Preview.' : 'Living rules are disabled. This dialog will not enable them. Enable them separately before generating a cohort.');
      status.id = 'population-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
      status.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere';
      const summary = node('section'); summary.id = 'population-preview'; summary.hidden = true;
      const consentLabel = node('label'), consent = node('input'); consent.type = 'checkbox'; consent.id = 'population-reviewed';
      consentLabel.append(consent, node('span', ' I reviewed this exact preview. Add this new cohort to the Editor draft.'));
      const controls = node('div'); controls.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;margin-top:16px';
      const preview = button('population-generate-preview', 'Preview cohort');
      const apply = button('population-apply', 'Apply preview to Editor draft');
      const cancel = button('population-cancel', 'Cancel');
      controls.append(preview, apply, cancel);
      let busy = '', handle = null, previewText = '', completed = false;
      const isCurrent = () => active.isConnected && active.open && dialog === active && ed.gameSlug === slug && config.editor_enabled;
      function sync() {
        input.disabled = !!busy || completed;
        preview.disabled = !!busy || completed;
        consent.disabled = !!busy || !handle || completed;
        apply.disabled = !!busy || !handle || !consent.checked || input.value !== previewText || completed;
        cancel.disabled = busy === 'apply';
      }
      function say(text, error = false) { status.textContent = text; status.style.color = error ? '#ffba9d' : '#badacb'; }
      input.oninput = () => {
        handle = null; consent.checked = false; summary.hidden = true; sync();
        say('Draft changed. Preview again before applying. Nothing saved or applied.');
      };
      consent.onchange = sync;
      preview.onclick = async () => {
        if (busy || completed || !isCurrent()) return;
        const text = input.value;
        handle = null; consent.checked = false; summary.hidden = true;
        try {
          const parsed = JSON.parse(text);
          if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw Error('Population configuration must be an object.');
          busy = 'preview'; sync(); say('Checking this cohort against current Editor content…');
          const response = await apiPost(path, {action:'preview', population_json:text});
          if (!isCurrent()) return;
          if (response.error) throw Error(response.error);
          handle = response.no_op ? null : response.preview_token; previewText = text;
          report(summary, response); summary.hidden = false;
          say(response.no_op ? 'This cohort is already recorded. The report describes its original generation. No definitions will be added, repaired or restored. Use a new cohort id for an additive population.' : response.text + ' Review the exact denominator, ages, households and local species, then check the review box.');
        } catch (error) { if (isCurrent()) say(error.message, true); }
        finally { busy = ''; if (isCurrent()) sync(); }
      };
      apply.onclick = async () => {
        if (busy || completed || !handle || !consent.checked || input.value !== previewText || !isCurrent()) return;
        busy = 'apply'; sync(); say('Staging this exact preview. Wait for the result before closing.');
        try {
          const response = await apiPost(path, {action:'apply', population_json:previewText, preview_token:handle});
          if (!isCurrent()) return;
          if (response.error) { handle = null; consent.checked = false; throw Error(response.error); }
          completed = true; cancel.textContent = 'Close'; say(response.text); setStatus(response.text, 'ok');
          // Refresh only the pinned world's visible Editor lists after success.
          if (ed.type) await refreshEntries();
          if (isCurrent()) await refreshEntriesCache();
        } catch (error) {
          if (isCurrent()) say(completed ? 'Population staging is confirmed. The Editor list could not refresh: ' + error.message + ' Close this dialog and reopen the NPC list to inspect the staged definitions.' : error.message + (handle ? ' The outcome may be uncertain. Retry Apply with this same preview to check safely; do not generate a new cohort.' : ' Preview again after reviewing current content.'), true);
        } finally { busy = ''; if (isCurrent()) sync(); }
      };
      cancel.onclick = () => { if (busy !== 'apply') active.close(); };
      active.addEventListener('cancel', event => { if (busy === 'apply') event.preventDefault(); });
      // With all controls disabled during Apply, native Qt WebEngine may move
      // keyboard focus outside the dialog. Guard Escape at document capture too.
      const guardEscape = event => {
        if (active.open && busy === 'apply' && event.key === 'Escape') {
          event.preventDefault(); event.stopImmediatePropagation();
        }
      };
      document.addEventListener('keydown', guardEscape, true);
      active.addEventListener('close', () => {
        document.removeEventListener('keydown', guardEscape, true);
        active.remove(); if (dialog === active) dialog = null;
        permission(); if (!open.hidden) open.focus();
      });
      active.append(heading, intro, workflow, label, input, help, refs, manifest, status, summary, consentLabel, controls);
      document.body.append(active); active.showModal(); sync(); input.focus(); permission();
    } catch (error) { if (ed.gameSlug === slug && config.editor_enabled) setStatus(error.message, 'warn'); }
    finally { opening = false; permission(); }
  };
})();
