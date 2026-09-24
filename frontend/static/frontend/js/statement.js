/**
 * New Tractors — Extrato de movimentações (modal global e página /extrato) e filtros do Histórico de Saques.
 *
 * Modal: aberto por [data-open-statement="<filtro>"]. Página: qualquer [data-statement-root] no conteúdo.
 * Ambos carregam 20 lançamentos por vez do mesmo endpoint e buscam mais ao chegar no fim (rolagem infinita).
 * Trocar de filtro cancela o carregamento anterior.
 */
(function () {
  'use strict';

  var TIMEOUT_MS = 15000;
  var states = new WeakMap();

  function modal() { return document.getElementById('statementModal'); }

  function stateOf(root) {
    var s = states.get(root);
    if (!s) {
      s = { filter: 'all', offset: 0, hasMore: true, loading: false, controller: null, observer: null };
      states.set(root, s);
    }
    return s;
  }

  function scrollBox(root) { return root.querySelector('[data-statement-scroll]'); }

  function showFoot(root, loading, error) {
    root.querySelector('[data-statement-foot]').hidden = !loading;
    root.querySelector('[data-statement-error]').hidden = !error;
    if (error) root.querySelector('[data-statement-error-text]').textContent = error;
  }

  function load(root) {
    var s = stateOf(root);
    if (s.loading || !s.hasMore) return;
    s.loading = true;
    showFoot(root, true, '');
    var controller = window.AbortController ? new AbortController() : null;
    s.controller = controller;
    var timer = controller ? setTimeout(function () { controller.abort(); }, TIMEOUT_MS) : null;
    var url = root.getAttribute('data-statement-url') + '?filtro=' + encodeURIComponent(s.filter) + '&offset=' + s.offset +
      (root.getAttribute('data-layout') === 'page' ? '&layout=page' : '');

    fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                 signal: controller ? controller.signal : undefined })
      .then(function (res) {
        if (res.status === 401) { window.location.assign('/login?next=' + encodeURIComponent(location.pathname)); return null; }
        return res.json();
      })
      .then(function (data) {
        if (timer) clearTimeout(timer);
        if (s.controller !== controller) return; // resposta de um filtro antigo
        s.loading = false;
        if (!data) return;
        if (!data.ok) { showFoot(root, false, data.message || 'Não foi possível carregar o extrato.'); return; }
        root.querySelector('[data-statement-list]').insertAdjacentHTML('beforeend', data.html);
        s.offset = data.next_offset;
        s.hasMore = !!data.has_more;
        showFoot(root, false, '');
        // Pouca coisa na tela: busca a próxima página sem esperar rolagem.
        var box = scrollBox(root);
        var short = box ? box.scrollHeight <= box.clientHeight + 40
                        : root.getBoundingClientRect().bottom < window.innerHeight + 40;
        if (s.hasMore && short) load(root);
      })
      .catch(function () {
        if (timer) clearTimeout(timer);
        if (s.controller !== controller) return;
        s.loading = false;
        showFoot(root, false, 'Sem conexão. Verifique sua internet.');
      });
  }

  function setFilter(root, filter) {
    var s = stateOf(root);
    if (s.controller) s.controller.abort();
    s.filter = filter;
    s.offset = 0;
    s.hasMore = true;
    s.loading = false;
    s.controller = null;
    root.querySelectorAll('[data-statement-filter]').forEach(function (chip) {
      var on = chip.getAttribute('data-statement-filter') === filter;
      chip.classList.toggle('is-active', on);
      chip.setAttribute('aria-pressed', String(on));
      if (on && chip.scrollIntoView) chip.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
    root.querySelector('[data-statement-list]').innerHTML = '';
    var box = scrollBox(root);
    if (box) box.scrollTop = 0;
    ensureObserver(root);
    load(root);
  }

  function ensureObserver(root) {
    var s = stateOf(root);
    if (s.observer) return;
    var box = scrollBox(root);
    if (!window.IntersectionObserver) {
      var target = box || window;
      s.observer = true;
      target.addEventListener('scroll', function () {
        var nearEnd = box ? box.scrollTop + box.clientHeight >= box.scrollHeight - 120
                          : window.innerHeight + window.scrollY >= document.body.scrollHeight - 200;
        if (s.hasMore && nearEnd) load(root);
      }, { passive: true });
      return;
    }
    s.observer = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting && s.hasMore) load(root);
    }, { root: box || null, rootMargin: '160px' });
    s.observer.observe(root.querySelector('[data-statement-sentinel]'));
  }

  // Histórico de Saques: filtro local (todos os saques já vêm no HTML).
  function filterHistory(box, group) {
    box.querySelectorAll('[data-history-filter]').forEach(function (chip) {
      var on = chip.getAttribute('data-history-filter') === group;
      chip.classList.toggle('is-active', on);
      chip.setAttribute('aria-pressed', String(on));
      if (on && chip.scrollIntoView) chip.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
    var visible = 0;
    box.querySelectorAll('[data-group]').forEach(function (li) {
      li.hidden = group !== 'all' && li.getAttribute('data-group') !== group;
      if (!li.hidden) visible++;
    });
    var empty = box.querySelector('[data-history-empty]');
    if (empty) empty.hidden = visible > 0 || !box.querySelector('[data-group]');
  }

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var el;
    if ((el = e.target.closest('[data-open-statement]')) && modal()) {
      e.preventDefault();
      window.NT.openModal('statementModal');
      setFilter(modal(), el.getAttribute('data-open-statement') || 'all');
      return;
    }
    if ((el = e.target.closest('[data-statement-filter]'))) {
      setFilter(el.closest('[data-statement-root]'), el.getAttribute('data-statement-filter'));
      return;
    }
    if ((el = e.target.closest('[data-statement-retry]'))) { load(el.closest('[data-statement-root]')); return; }
    if ((el = e.target.closest('[data-history-filter]'))) {
      filterHistory(el.closest('[data-history]'), el.getAttribute('data-history-filter'));
    }
  });

  // Página /extrato: carrega a primeira página ao entrar (troca SPA ou carga direta).
  function onPage() {
    document.querySelectorAll('#appView [data-statement-root]').forEach(function (root) { setFilter(root, 'all'); });
  }
  document.addEventListener('app:page', onPage);
  onPage();
})();
