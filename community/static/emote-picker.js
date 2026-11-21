(() => {
  'use strict';
  for (const picker of document.querySelectorAll('[data-forum-emotes]')) {
    const textarea = picker.closest('form')?.querySelector('textarea[name="body"]');
    if (!textarea || typeof textarea.setRangeText !== 'function') continue;
    const status = picker.querySelector('[data-emote-status]');
    picker.querySelector('[data-emote-help]').textContent =
      'Choose an Expanse emoji to insert it at the cursor.';
    for (const button of picker.querySelectorAll('button[data-emote]')) {
      button.addEventListener('click', () => {
        const start = textarea.selectionStart, end = textarea.selectionEnd;
        const code = button.dataset.emote;
        if (textarea.maxLength >= 0 && textarea.value.length - (end - start) + code.length > textarea.maxLength) {
          status.textContent = 'There is not enough room for this emoji. Shorten the message and try again.';
          return;
        }
        status.textContent = '';
        textarea.setRangeText(code, start, end, 'end');
        picker.open = false;
        textarea.focus();
      });
      button.hidden = false;
    }
    for (const code of picker.querySelectorAll('[data-emote-fallback]')) code.hidden = true;
  }
})();
