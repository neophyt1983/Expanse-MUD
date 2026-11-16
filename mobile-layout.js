/* Fit the phone workspace to the visible viewport without touching game state. */
(() => {
  'use strict';
  const app = document.getElementById('app');
  const input = document.getElementById('input');
  const log = document.getElementById('log');
  const latest = document.getElementById('conversation-latest');
  const done = document.getElementById('command-done');
  const phone = window.matchMedia('(max-width:680px), (max-width:950px) and (max-height:500px) and (pointer:coarse)');
  if (!app || !input || !log) return;

  let baselineHeight = 0, baselineWidth = 0, queued = false;
  let keyboardOpen = false, keyboardHeight = 0;
  let composing = false, compositionEnter = false;
  const positive = (value, fallback) => Number.isFinite(value) && value > 0 ? value : fallback;
  const pixels = value => Math.round(value * 100) / 100 + 'px';
  function setKeyboard(open) {
    keyboardOpen = open;
    app.dataset.mobileKeyboard = String(open);
    if (done) done.hidden = !open;
  }
  function viewport() {
    const visible = window.visualViewport;
    const focused = document.activeElement === input;
    if (!focused || !phone.matches) setKeyboard(false);
    // Browser pinch zoom magnifies the existing layout; it must not rebuild it.
    if (visible && Math.abs((visible.scale || 1) - 1) > 0.01) return;
    const zoom = positive(parseFloat(getComputedStyle(document.documentElement).zoom), 1);
    const width = positive(visible?.width, window.innerWidth);
    const height = positive(visible?.height, window.innerHeight);
    const widthChanged = !baselineWidth || Math.abs(width - baselineWidth) > 80;
    if (widthChanged) {
      baselineWidth = width;
      baselineHeight = Math.max(height, window.innerHeight);
    } else if (!focused) {
      baselineHeight = Math.max(height, window.innerHeight);
    } else {
      baselineHeight = Math.max(baselineHeight, height, window.innerHeight);
    }
    const values = {
      height: height / zoom,
      width: width / zoom,
      top: Math.max(0, visible?.offsetTop || 0) / zoom,
      left: Math.max(0, visible?.offsetLeft || 0) / zoom
    };
    for (const [name, value] of Object.entries(values)) {
      const property = '--expanse-mobile-' + name, text = pixels(value);
      if (document.documentElement.style.getPropertyValue(property) !== text) {
        document.documentElement.style.setProperty(property, text);
      }
    }
    // Rotation must not put the full toolbar back into a keyboard-sized view.
    // A very short focused view also benefits from the compact typing layout.
    const compressed = baselineHeight - height > 120 || height < 420;
    const retained = keyboardOpen && height < keyboardHeight + 120;
    const keyboard = phone.matches && focused && (compressed || retained);
    if (keyboard && (!keyboardOpen || widthChanged)) keyboardHeight = height;
    setKeyboard(keyboard);
  }
  function refresh() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; viewport(); });
  }
  window.addEventListener('resize', refresh);
  window.addEventListener('orientationchange', refresh);
  window.addEventListener('expanse:display', refresh);
  window.visualViewport?.addEventListener('resize', refresh);
  window.visualViewport?.addEventListener('scroll', refresh);
  phone.addEventListener?.('change', refresh);
  input.addEventListener('focus', refresh);
  input.addEventListener('blur', refresh);
  document.getElementById('command-send')?.addEventListener('pointerdown', event => {
    // Keep the input and keyboard in place until the native submit click fires.
    if (document.activeElement === input && event.button === 0) event.preventDefault();
  });
  done?.addEventListener('click', () => { input.blur(); refresh(); });
  input.addEventListener('compositionstart', () => { composing = true; });
  input.addEventListener('compositionend', () => { composing = false; });
  input.addEventListener('keydown', event => {
    if ((event.key === 'Enter' || event.keyCode === 229) &&
        (event.isComposing || composing || event.keyCode === 229)) {
      compositionEnter = true;
      setTimeout(() => { compositionEnter = false; }, 0);
    }
  });
  window.ExpanseMobileLayout = {
    refresh,
    isComposing: () => composing || compositionEnter,
    version: '1.9.4'
  };
  app.dataset.mobileLayout = '1.9.4';
  refresh();

  // Retain the reader's intent across wrapping, keyboard changes and panel moves.
  // Measuring the gap after a resize mistakes a shortened viewport for someone
  // scrolling into history, especially when combat messages arrive that frame.
  let following = true, unread = 0, anchorQueued = false;
  let readingTop = log.scrollTop, pointerActive = false, touchY = null;
  const metrics = () => ({top: log.scrollTop, height: log.clientHeight, content: log.scrollHeight});
  let previous = metrics();
  function badge() {
    if (!latest) return;
    latest.hidden = unread === 0;
    latest.textContent = unread ? 'New messages (' + unread + ') ↓' : 'Latest messages ↓';
  }
  function anchor() {
    // Hidden/tabbed panels can report scrollTop=0. Keep their reading position.
    if (!log.clientHeight) return;
    log.scrollTop = following ? log.scrollHeight : readingTop;
    previous = metrics();
  }
  function settle() {
    if (anchorQueued) return;
    anchorQueued = true;
    requestAnimationFrame(() => {
      anchorQueued = false;
      // A reader can scroll up between append and this frame; respect that.
      anchor();
    });
  }
  function jumpToLatest() {
    following = true;
    unread = 0;
    anchor();
    settle();
    badge();
  }
  function beforeAppend(force = false) {
    return {follow: force || following, top: log.clientHeight ? log.scrollTop : readingTop};
  }
  function afterAppend(position) {
    watchTail();
    if (!position || position.follow) { jumpToLatest(); return; }
    following = false;
    readingTop = position.top;
    anchor();
    settle();
    unread += 1;
    badge();
  }
  function readHistory() {
    if (!log.clientHeight || log.scrollTop <= 0) return;
    following = false;
    readingTop = log.scrollTop;
    previous = metrics();
  }
  log.addEventListener('scroll', () => {
    const current = metrics();
    if (!current.height) return;
    const resized = current.height !== previous.height || current.content !== previous.content;
    const up = current.top < previous.top - 1, down = current.top > previous.top + 1;
    // Native focus/scroll restoration can move the viewport after our last
    // anchor, without changing its dimensions. That is not a request to stop
    // following. Wheel/touch/key gestures pause before their scroll event;
    // scrollbar dragging is the remaining direct reading gesture here.
    if (up && (!resized || pointerActive) && (!following || pointerActive)) {
      following = false;
      readingTop = current.top;
    } else if (!following && down && current.content - current.height - current.top <= 2) {
      following = true;
      unread = 0;
      badge();
    } else if (!following && (up || down) && (!resized || pointerActive)) {
      readingTop = current.top;
    }
    previous = current;
    if (resized || (following && current.content - current.height - current.top > 2)) settle();
  }, {passive: true});
  log.addEventListener('wheel', event => {
    if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.deltaY < 0) readHistory();
  }, {passive: true});
  log.addEventListener('pointerdown', event => {
    // Clicking an inline action can restore focus and scroll; it is not a drag.
    pointerActive = event.button !== 2 && !event.target?.closest?.('button, a, input, textarea, select, summary');
    if (event.button === 1) readHistory(); // Middle-button autoscroll is deliberate.
  }, {passive: true});
  const releasePointer = () => {
    // A scrollbar can move before its queued scroll event is delivered. Record
    // that deliberate reading position even if pointerup/cancel arrives first.
    if (pointerActive) {
      const current = metrics();
      if (current.height && current.top < previous.top - 1) {
        following = false;
        readingTop = current.top;
        previous = current;
      }
    }
    pointerActive = false;
  };
  window.addEventListener('pointerup', releasePointer, {passive: true});
  window.addEventListener('pointercancel', releasePointer, {passive: true});
  log.addEventListener('touchstart', event => { touchY = event.touches?.[0]?.clientY ?? null; }, {passive: true});
  log.addEventListener('touchmove', event => {
    const y = event.touches?.[0]?.clientY;
    if (touchY !== null && y > touchY) readHistory();
    touchY = y ?? null;
  }, {passive: true});
  log.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.isComposing ||
        event.target?.closest?.('input, textarea, select, [contenteditable="true"], [role="textbox"]')) return;
    if (['ArrowUp', 'PageUp', 'Home'].includes(event.key) || (event.key === ' ' && event.shiftKey)) readHistory();
  });
  latest?.addEventListener('click', jumpToLatest);
  let tail = null, tailObserver = null;
  function watchTail() {
    const next = log.lastElementChild;
    if (!tailObserver || next === tail) return;
    tail = next;
    tailObserver.disconnect();
    if (tail) tailObserver.observe(tail);
  }
  if (window.ResizeObserver) {
    const resized = () => { anchor(); settle(); };
    const observer = new ResizeObserver(resized);
    observer.observe(log);
    const form = document.getElementById('input-form');
    if (form) observer.observe(form);
    tailObserver = new ResizeObserver(resized);
    watchTail();
  }
  if (window.MutationObserver) {
    new MutationObserver(() => { watchTail(); settle(); }).observe(log, {
      childList: true, subtree: true, characterData: true,
      attributes: true, attributeFilter: ['class', 'style', 'hidden']
    });
    // Docking reparents the panel; restoring it can reset its scroll position
    // even when the final dimensions are unchanged. Repair before scroll events.
    new MutationObserver(records => {
      if (records.some(record => record.type === 'attributes'
        ? record.target !== log && record.target.contains(log)
        : [...record.addedNodes, ...record.removedNodes].some(node => node.contains?.(log)))) {
        anchor();
        settle();
      }
    }).observe(app, {childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style', 'hidden']});
  }
  log.addEventListener('load', settle, true);
  document.fonts?.ready?.then(settle);
  document.fonts?.addEventListener?.('loadingdone', settle);
  window.ExpanseTranscript = { beforeAppend, afterAppend, jumpToLatest, version: '1.9.8' };
})();
