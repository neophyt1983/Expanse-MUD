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

  // Follow incoming messages only while the reader is already at the bottom.
  let following = true, unread = 0;
  const nearBottom = () => log.scrollHeight - log.clientHeight - log.scrollTop <= 48;
  function badge() {
    if (!latest) return;
    latest.hidden = unread === 0;
    latest.textContent = unread ? 'New messages (' + unread + ') ↓' : 'Latest messages ↓';
  }
  function jumpToLatest() {
    following = true;
    unread = 0;
    log.scrollTop = log.scrollHeight;
    badge();
  }
  function beforeAppend(force = false) {
    return { follow: force || (log.clientHeight ? nearBottom() : following), top: log.scrollTop };
  }
  function afterAppend(position) {
    if (!position || position.follow) { jumpToLatest(); return; }
    following = false;
    log.scrollTop = position.top;
    unread += 1;
    badge();
  }
  log.addEventListener('scroll', () => {
    if (!log.clientHeight) return;
    following = nearBottom();
    if (following) { unread = 0; badge(); }
  }, { passive: true });
  latest?.addEventListener('click', jumpToLatest);
  if (window.ResizeObserver) {
    new ResizeObserver(() => { if (following && log.clientHeight) jumpToLatest(); }).observe(log);
  }
  window.ExpanseTranscript = { beforeAppend, afterAppend, jumpToLatest };
})();
