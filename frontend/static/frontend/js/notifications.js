/**
 * New Tractors — Painel de notificações (sino do cabeçalho).
 * Carrega a lista sempre que abre; "Marcar todas como lidas" chama o backend e atualiza a tela e o ponto do sino.
 */
(function () {
  'use strict';

  var TIMEOUT_MS = 15000;
  var READ_LABEL = 'Marcar todas como lidas';
  var DONE_LABEL = 'Todas as notificações marcadas como lidas';

  function panel() { return document.getElementById('notifModal'); }

  function setBellDot(on) {
    document.querySelectorAll('.app-header-btn-bell').forEach(function (bell) {
      var dot = bell.querySelector('.app-header-dot');
      if (on && !dot) {
        dot = document.createElement('span');
        dot.className = 'app-header-dot';
        dot.setAttribute('aria-hidden', 'true');
        bell.appendChild(dot);
      } else if (!on && dot) {
        dot.remove();
      }
      bell.setAttribute('aria-label', on ? 'Notificações (há novas)' : 'Notificações');
    });
  }

  function setReadButton(p, allRead) {
    var btn = p.querySelector('[data-notif-read]');
    btn.disabled = allRead;
    btn.classList.toggle('is-done', allRead);
    p.querySelector('[data-notif-read-label]').textContent = allRead ? DONE_LABEL : READ_LABEL;
  }

  function load() {
    var p = panel();
    var list = p.querySelector('[data-notif-list]');
    var loading = p.querySelector('[data-notif-loading]');
    var error = p.querySelector('[data-notif-error]');
    list.innerHTML = '';
    loading.hidden = false;
    error.hidden = true;
    var controller = window.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, TIMEOUT_MS) : null;
    fetch(p.getAttribute('data-notif-url'), { credentials: 'same-origin', signal: controller ? controller.signal : undefined,
                                               headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (res) {
        if (res.status === 401) { window.location.assign('/login?next=' + encodeURIComponent(location.pathname)); return null; }
        return res.json();
      })
      .then(function (data) {
        if (timer) clearTimeout(timer);
        loading.hidden = true;
        if (!data) return;
        if (!data.ok) { error.textContent = data.message || 'Não foi possível carregar as notificações.'; error.hidden = false; return; }
        list.innerHTML = data.html;
        setReadButton(p, data.unread === 0);
        setBellDot(data.unread > 0);
      })
      .catch(function () {
        if (timer) clearTimeout(timer);
        loading.hidden = true;
        error.textContent = 'Sem conexão. Verifique sua internet.';
        error.hidden = false;
      });
  }

  function markAllRead(btn) {
    var p = panel();
    btn.disabled = true;
    window.NT.postAction(p.getAttribute('data-notif-read-url')).then(function (data) {
      if (!data.ok) {
        btn.disabled = false;
        var error = p.querySelector('[data-notif-error]');
        error.textContent = data.message || 'Não foi possível marcar como lidas agora.';
        error.hidden = false;
        return;
      }
      p.querySelectorAll('.nf-item.is-unread').forEach(function (li) { li.classList.remove('is-unread'); });
      setReadButton(p, true);
      setBellDot(false);
    });
  }

  document.addEventListener('click', function (e) {
    if (!e.target.closest || !panel()) return;
    if (e.target.closest('[data-open-notifications]')) {
      window.NT.openModal('notifModal');
      load();
      return;
    }
    var btn = e.target.closest('[data-notif-read]');
    if (btn && !btn.disabled) markAllRead(btn);
  });
})();
