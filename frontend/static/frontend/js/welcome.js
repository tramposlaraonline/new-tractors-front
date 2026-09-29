/**
 * New Tractors — Modais automáticos ao carregar a página ([data-autoshow="ordem"]).
 * Mostra um por vez, na ordem; ao fechar um, abre o próximo. Esc, clique fora e botões [data-wl-close] fecham.
 * Modal de vídeo (data-wl-video-once): na 1ª vez exige assistir até o fim antes de liberar o fechamento.
 * Autocontido (não depende do home.js): roda também nas telas de login/cadastro.
 */
(function () {
  'use strict';

  var queue = Array.prototype.slice.call(document.querySelectorAll('[data-autoshow]'))
    .sort(function (a, b) { return (+a.getAttribute('data-autoshow')) - (+b.getAttribute('data-autoshow')); });
  var current = null;
  var lastFocus = null;
  var videoLocked = false;

  function storageGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function storageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }

  function isVideoSeen(modal) {
    var key = modal.getAttribute('data-wl-video-once');
    return key ? storageGet(key) === '1' : true;
  }

  function markVideoSeen(modal) {
    var key = modal.getAttribute('data-wl-video-once');
    if (key) storageSet(key, '1');
  }

  function setVideoCloseVisible(modal, visible) {
    var nodes = modal.querySelectorAll('.wl-video-close, .wl-video-done');
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].hidden = !visible;
    }
    var hint = modal.querySelector('[data-wl-video-hint]');
    if (hint) hint.hidden = visible;
  }

  function unlockVideo(modal) {
    if (!videoLocked || current !== modal) return;
    videoLocked = false;
    modal.classList.remove('is-video-locked');
    markVideoSeen(modal);
    setVideoCloseVisible(modal, true);
  }

  function setupVideoModal(modal) {
    var video = modal.querySelector('[data-wl-video]');
    if (!video) return;

    var seen = isVideoSeen(modal);
    videoLocked = !seen;
    modal.classList.toggle('is-video-locked', videoLocked);
    setVideoCloseVisible(modal, seen);

    // Reinicia e tenta autoplay (muted primeiro para passar na política do browser; depois tenta com som).
    try {
      video.pause();
      video.currentTime = 0;
    } catch (e) { /* ignore */ }

    video.muted = true;
    var playPromise = video.play();
    if (playPromise && playPromise.then) {
      playPromise.then(function () {
        // Já está tocando mudo; usuário pode ligar o som nos controles.
      }).catch(function () {
        // Autoplay bloqueado: controles bastam.
      });
    }

    video.onended = function () {
      unlockVideo(modal);
    };
  }

  function teardownVideo(modal) {
    var video = modal && modal.querySelector('[data-wl-video]');
    if (!video) return;
    try {
      video.pause();
      video.onended = null;
    } catch (e) { /* ignore */ }
  }

  function open(modal) {
    current = modal;
    lastFocus = lastFocus || document.activeElement;
    modal.hidden = false;
    void modal.offsetWidth;
    modal.classList.add('is-open');
    document.documentElement.classList.add('wl-lock');

    if (modal.hasAttribute('data-wl-video-once')) {
      setupVideoModal(modal);
    }

    var card = modal.querySelector('.wl-card, .wl-banner, .wl-video-card');
    if (card) card.focus({ preventScroll: true });
  }

  function next() {
    var modal = queue.shift();
    if (modal) { open(modal); return; }
    current = null;
    videoLocked = false;
    document.documentElement.classList.remove('wl-lock');
    if (lastFocus && document.contains(lastFocus) && lastFocus.focus) lastFocus.focus({ preventScroll: true });
    lastFocus = null;
  }

  function close() {
    if (!current) return;
    if (videoLocked) return;
    var modal = current;
    current = null;
    teardownVideo(modal);
    modal.classList.remove('is-open');
    modal.classList.remove('is-video-locked');
    setTimeout(function () {
      modal.hidden = true;
      next();
    }, 230);
  }

  document.addEventListener('click', function (e) {
    if (!current || !e.target.closest) return;
    var el;
    if ((el = e.target.closest('[data-wl-close]')) && current.contains(el)) {
      if (videoLocked) {
        e.preventDefault();
        return;
      }
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

  document.addEventListener('wl:open', function (e) {
    var modal = e.detail && document.getElementById(e.detail.id);
    if (!modal || modal === current || queue.indexOf(modal) !== -1) return;
    if (current) { queue.unshift(modal); return; }
    open(modal);
  });

  document.addEventListener('keydown', function (e) {
    if (!current) return;
    if (e.key === 'Escape') {
      if (videoLocked) { e.preventDefault(); return; }
      close();
      return;
    }
    if (e.key !== 'Tab') return;
    var focusables = current.querySelectorAll('a[href], button:not([disabled]):not([hidden]), video');
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  next();
})();