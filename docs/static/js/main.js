/* WebCoder project page — theme toggle, figure lightbox, BibTeX copy. */

(function () {
  'use strict';

  // ---- theme: OS by default, explicit choice wins and is remembered ----
  var root = document.documentElement;
  var KEY = 'webcoder-theme';

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function remember(v) {
    try { localStorage.setItem(KEY, v); } catch (e) { /* private mode */ }
  }
  function prefersDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function isDark() {
    var t = root.getAttribute('data-theme');
    if (t) return t === 'dark';
    return prefersDark();
  }
  function paint(btn) {
    var dark = isDark();
    btn.textContent = dark ? '☀' : '☾';       // sun when dark, moon when light
    btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
    btn.setAttribute('aria-pressed', String(dark));
  }

  var saved = stored();
  if (saved === 'dark' || saved === 'light') root.setAttribute('data-theme', saved);

  var toggle = document.querySelector('.theme-toggle');
  if (toggle) {
    paint(toggle);
    toggle.addEventListener('click', function () {
      var next = isDark() ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      remember(next);
      paint(toggle);
    });
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
        if (!root.getAttribute('data-theme')) paint(toggle);
      });
    }
  }

  // ---- lightbox: click any figure image to see it full width ----
  var box = document.querySelector('.lightbox');
  var boxImg = box && box.querySelector('img');
  var lastFocus = null;

  function openBox(src, alt) {
    if (!box || !boxImg) return;
    boxImg.src = src;
    boxImg.alt = alt || '';
    box.setAttribute('open', '');
    document.body.style.overflow = 'hidden';
    var close = box.querySelector('.lightbox-close');
    if (close) close.focus();
  }
  function closeBox() {
    if (!box) return;
    box.removeAttribute('open');
    document.body.style.overflow = '';
    if (boxImg) boxImg.removeAttribute('src');
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  Array.prototype.forEach.call(document.querySelectorAll('figure img'), function (img) {
    img.addEventListener('click', function () {
      lastFocus = img;
      openBox(img.getAttribute('src'), img.getAttribute('alt'));
    });
  });

  if (box) {
    box.addEventListener('click', function (e) {
      if (e.target === box || e.target.classList.contains('lightbox-close')) closeBox();
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeBox();
  });

  // ---- BibTeX copy ----
  // The async clipboard API is unavailable on file:// and can reject even where
  // it exists, so a selection-based fallback runs whenever it does not succeed.
  function legacyCopy(node) {
    var range = document.createRange();
    range.selectNodeContents(node);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    sel.removeAllRanges();
    return ok;
  }

  Array.prototype.forEach.call(document.querySelectorAll('.copy-btn'), function (btn) {
    btn.addEventListener('click', function () {
      var card = btn.closest('.code-card');
      var pre = card && card.querySelector('pre');
      if (!pre) return;

      var settle = function (ok) {
        var old = btn.dataset.label || btn.textContent;
        btn.dataset.label = old;
        btn.textContent = ok ? 'Copied' : 'Press Ctrl+C';
        setTimeout(function () { btn.textContent = old; }, 1800);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(pre.innerText).then(
          function () { settle(true); },
          function () { settle(legacyCopy(pre)); }
        );
      } else {
        settle(legacyCopy(pre));
      }
    });
  });
})();
