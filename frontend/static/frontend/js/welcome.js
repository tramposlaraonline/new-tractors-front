/**
 * New Tractors — Modais automáticos ao carregar a página ([data-autoshow="ordem"]).
 * Mostra um por vez, na ordem; ao fechar um, abre o próximo. Esc, clique fora e botões [data-wl-close] fecham.
 * Modal de vídeo (data-wl-video-once): na 1ª vez exige assistir até o fim (sem adiantar) antes de liberar
 * o fechamento; o botão de baixo enche conforme o progresso. Depois de visto, pode pular a qualquer momento.
 * Se o vídeo não carregar, libera a saída sem marcar como visto (volta a aparecer no próximo carregamento).
 * Vídeo só inicia com áudio após clique do usuário (sem autoplay mudo).
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

  function formatClock(seconds) {
    var s = Math.max(0, Math.ceil(seconds || 0));
    return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }

  function formatDuration(seconds) {
    var s = Math.round(seconds || 0);
    if (!s) return 'Com som';
    var m = Math.floor(s / 60);
    var r = s % 60;
    return (m ? m + 'min' : '') + (r ? (m ? ('0' + r).slice(-2) : r) + 's' : '') + ', com som';
  }

  // Controla um modal de vídeo: estados locked | done | free | error.
  function createVideoController(modal) {
    var card = modal.querySelector('.wl-vcard');
    var video = modal.querySelector('[data-wl-video]');
    var play = modal.querySelector('[data-wl-video-play]');
    var playLabel = modal.querySelector('[data-wl-video-play-label]');
    var playHint = modal.querySelector('[data-wl-video-play-hint]');
    var status = modal.querySelector('[data-wl-video-status]');
    var closeBtn = modal.querySelector('.wl-vclose');
    var cta = modal.querySelector('[data-wl-video-continue]');
    var ctaLabel = modal.querySelector('[data-wl-video-cta-label]');
    var seenKey = modal.getAttribute('data-wl-video-once');

    var state = 'locked';
    var maxWatched = 0;

    function isSeen() {
      return seenKey ? storageGet(seenKey) === '1' : true;
    }

    function restart(el, cls) {
      el.classList.remove(cls);
      void el.offsetWidth;
      el.classList.add(cls);
    }

    function updateProgress() {
      var d = video.duration || 0;
      var p = d ? Math.min(1, maxWatched / d) : 0;
      cta.style.setProperty('--wl-progress', p.toFixed(4));
      if (state !== 'locked') return;
      ctaLabel.textContent = maxWatched ? 'Liberado em ' + formatClock(d - maxWatched) : 'Assista para liberar';
    }

    function setState(next) {
      state = next;
      videoLocked = next === 'locked';
      card.setAttribute('data-state', next);
      modal.classList.toggle('is-video-locked', videoLocked);
      closeBtn.hidden = videoLocked;
      cta.setAttribute('aria-disabled', videoLocked ? 'true' : 'false');

      if (next === 'locked') {
        status.textContent = 'Assista até o fim para continuar.';
        updateProgress();
      } else if (next === 'done') {
        status.textContent = 'Pronto, você assistiu tudo.';
        ctaLabel.textContent = 'Continuar';
        restart(cta, 'is-ready');
      } else if (next === 'free') {
        status.textContent = 'Você já assistiu. Pode pular.';
        ctaLabel.textContent = 'Continuar';
      } else if (next === 'error') {
        status.textContent = 'Não foi possível carregar o vídeo. Confira sua internet.';
        ctaLabel.textContent = 'Continuar sem assistir';
      }
    }

    function showPlay(label, hint, retry) {
      playLabel.textContent = label;
      playHint.textContent = hint;
      play.classList.toggle('is-retry', !!retry);
      play.setAttribute('aria-label', label);
      play.hidden = false;
    }

    // "Já assistido" só cresce tocando: saltos pra frente são barrados no 'seeking' abaixo.
    video.addEventListener('timeupdate', function () {
      if (!video.seeking && video.currentTime > maxWatched) maxWatched = video.currentTime;
      updateProgress();
    });

    // Na 1ª vez não deixa adiantar além do que já foi visto (voltar pode).
    video.addEventListener('seeking', function () {
      if (state === 'locked' && video.currentTime > maxWatched + 0.5) video.currentTime = maxWatched;
    });

    video.addEventListener('loadedmetadata', function () {
      if (!maxWatched && !play.hidden) playHint.textContent = formatDuration(video.duration);
      updateProgress();
    });

    video.addEventListener('ended', function () {
      maxWatched = video.duration || maxWatched;
      updateProgress();
      video.controls = false;
      if (state === 'locked') {
        if (seenKey) storageSet(seenKey, '1');
        setState('done');
      }
      showPlay('Assistir de novo', formatDuration(video.duration), true);
    });

    video.addEventListener('pause', function () {
      if (video.ended || state === 'error' || current !== modal) return;
      showPlay('Continuar assistindo', 'Faltam ' + formatClock((video.duration || 0) - video.currentTime), false);
    });

    video.addEventListener('playing', function () {
      play.hidden = true;
      updateProgress();
    });

    video.addEventListener('waiting', function () {
      if (state === 'locked') ctaLabel.textContent = 'Carregando vídeo…';
    });

    function fail() {
      video.controls = false;
      setState('error');
      showPlay('Tentar de novo', 'Verifique a conexão', true);
    }

    video.addEventListener('error', fail);

    // Sem controles nativos (1ª vez), tocar na tela pausa.
    video.addEventListener('click', function () {
      if (!video.controls && !video.paused) video.pause();
    });

    return {
      reset: function () {
        maxWatched = 0;
        try {
          video.pause();
          video.currentTime = 0;
        } catch (e) { /* ignore */ }
        video.muted = false;
        video.controls = false;
        // O preload pode ter falhado antes do modal abrir: não prende o usuário.
        if (video.error) { fail(); return; }
        setState(isSeen() ? 'free' : 'locked');
        showPlay('Assistir vídeo', formatDuration(video.duration), false);
      },

      start: function () {
        if (state === 'error') {
          setState(isSeen() ? 'free' : 'locked');
          video.load();
        }
        if (video.ended) {
          try { video.currentTime = 0; } catch (e) { /* ignore */ }
        }
        play.hidden = true;
        video.controls = state !== 'locked';
        video.muted = false;
        var p = video.play();
        if (p && p.then) {
          p.catch(function () {
            if (video.error) { fail(); return; }
            video.controls = false;
            showPlay('Assistir vídeo', formatDuration(video.duration), false);
          });
        }
      },

      // Tentou sair com o vídeo bloqueado: o botão balança em vez de nada acontecer.
      nudge: function () {
        restart(cta, 'is-nudge');
      },

      teardown: function () {
        try {
          video.pause();
          video.controls = false;
        } catch (e) { /* ignore */ }
      }
    };
  }

  function videoCtl(modal) {
    if (!modal || !modal.hasAttribute('data-wl-video-once')) return null;
    if (!modal._wlVideo) modal._wlVideo = createVideoController(modal);
    return modal._wlVideo;
  }

  function open(modal) {
    current = modal;
    lastFocus = lastFocus || document.activeElement;
    modal.hidden = false;
    void modal.offsetWidth;
    modal.classList.add('is-open');
    document.documentElement.classList.add('wl-lock');

    var ctl = videoCtl(modal);
    if (ctl) ctl.reset();

    var card = modal.querySelector('.wl-card, .wl-banner, .wl-vcard');
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
    if (videoLocked) {
      var locked = videoCtl(current);
      if (locked) locked.nudge();
      return;
    }
    var modal = current;
    current = null;
    var ctl = videoCtl(modal);
    if (ctl) ctl.teardown();
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

    // Play do vídeo (com áudio)
    if ((el = e.target.closest('[data-wl-video-play]')) && current.contains(el)) {
      e.preventDefault();
      videoCtl(current).start();
      return;
    }

    if ((el = e.target.closest('[data-wl-video-continue], [data-wl-close]')) && current.contains(el)) {
      if (el.tagName !== 'A' || videoLocked) e.preventDefault();
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
      if (videoLocked) e.preventDefault();
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
