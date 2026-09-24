/**
 * New Tractors — Modais automáticos ao carregar a página ([data-autoshow="ordem"]).
 * Mostra um por vez, na ordem; ao fechar um, abre o próximo. Esc, clique fora e botões [data-wl-close] fecham.
 * Autocontido (não depende do home.js): roda também nas telas de login/cadastro.
 */
(function () {
  'use strict';

  var queue = Array.prototype.slice.call(document.querySelectorAll('[data-autoshow]'))
    .sort(function (a, b) { return (+a.getAttribute('data-autoshow')) - (+b.getAttribute('data-autoshow')); });
  var current = null;
  var lastFocus = null;

  function open(modal) {
    current = modal;
    lastFocus = lastFocus || document.activeElement;
    modal.hidden = false;
    void modal.offsetWidth; // força o layout para a transição de entrada
    modal.classList.add('is-open');
    document.documentElement.classList.add('wl-lock');
    var card = modal.querySelector('.wl-card, .wl-banner');
    if (card) card.focus({ preventScroll: true });
  }

  function next() {
    var modal = queue.shift();
    if (modal) { open(modal); return; }
    current = null;
    document.documentElement.classList.remove('wl-lock');
    if (lastFocus && document.contains(lastFocus) && lastFocus.focus) lastFocus.focus({ preventScroll: true });
    lastFocus = null;
  }

  function close() {
    if (!current) return;
    var modal = current;
    current = null;
    modal.classList.remove('is-open');
    setTimeout(function () {
      modal.hidden = true;
      next();
    }, 230);
  }

  document.addEventListener('click', function (e) {
    if (!current || !e.target.closest) return;
    var el;
    if ((el = e.target.closest('[data-wl-close]')) && current.contains(el)) {
      // Links (ex.: "Ver minha equipe") seguem para o app.js; aqui só fecha.
      if (el.tagName !== 'A') e.preventDefault();
      close();
      return;
    }
    if ((el = e.target.closest('[data-wl-copy]')) && current.contains(el)) {
      var text = current.querySelector('[data-wl-invite]').textContent.trim();
      var label = el.querySelector('[data-wl-copy-label]');
      var done = function (ok) {
        label.textContent = ok ? 'Link copiado!' : 'Copie o link acima';
        el.classList.toggle('is-copied', ok);
        setTimeout(function () { label.textContent = 'Copiar Link'; el.classList.remove('is-copied'); }, 2500);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
      } else {
        var area = document.createElement('textarea');
        area.value = text;
        area.style.cssText = 'position:fixed;top:-1000px;opacity:0';
        document.body.appendChild(area);
        area.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
        document.body.removeChild(area);
        done(ok);
      }
    }
  });

  // Abertura sob demanda (ex.: auth.js ao receber a trava de login/cadastro):
  // document.dispatchEvent(new CustomEvent('wl:open', { detail: { id: 'idDoModal' } })).
  document.addEventListener('wl:open', function (e) {
    var modal = e.detail && document.getElementById(e.detail.id);
    if (!modal || modal === current || queue.indexOf(modal) !== -1) return;
    if (current) { queue.unshift(modal); return; }
    open(modal);
  });

  document.addEventListener('keydown', function (e) {
    if (!current) return;
    if (e.key === 'Escape') { close(); return; }
    if (e.key !== 'Tab') return;
    var focusables = current.querySelectorAll('a[href], button:not([disabled])');
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  next();
})();
