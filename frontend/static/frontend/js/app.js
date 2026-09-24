/**
 * New Tractors — Navegação SPA da área logada.
 *
 * A casca (navbar + botão de Chat) é carregada uma vez; ao clicar num link com [data-spa-link]
 * só o conteúdo de <main id="appView"> é trocado, com a URL atualizada via History API.
 * Voltar/avançar do navegador funcionam e cada aba tem URL própria (F5 ou link direto abrem a casca completa).
 *
 * Protocolo: GET na própria URL com o header "X-SPA-Request: 1" -> JSON {ok, tab, title, html}.
 *   401 {redirect} -> sessão expirou: vai para o login com carga completa.
 *   Qualquer outra falha (rede, timeout, 5xx, resposta não-JSON) -> carga completa da URL, nunca tela quebrada.
 *
 * Telas que precisarem de JS escutam o evento "app:page" (disparado a cada troca e na carga inicial):
 *   document.addEventListener('app:page', function (e) { if (e.detail.tab === 'home') { ... } });
 * <script> dentro do HTML trocado NÃO é executado.
 */
(function () {
  'use strict';

  var REQUEST_TIMEOUT_MS = 15000;
  var SPA_HEADER = 'X-SPA-Request';

  var view = document.getElementById('appView');
  if (!view || !window.fetch || !window.history || !window.history.pushState) return;

  var tabs = Array.prototype.slice.call(document.querySelectorAll('.app-tab[data-tab], .app-side-link[data-tab]'));
  var inFlight = null;

  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

  function setActiveTab(tabKey) {
    tabs.forEach(function (tab) {
      var active = tab.getAttribute('data-tab') === tabKey;
      tab.classList.toggle('is-active', active);
      if (active) tab.setAttribute('aria-current', 'page');
      else tab.removeAttribute('aria-current');
    });
  }

  function emitPage(tabKey) {
    document.dispatchEvent(new CustomEvent('app:page', { detail: { tab: tabKey, url: location.href } }));
  }

  function saveScroll() {
    var state = history.state || {};
    state.spa = true;
    state.scrollY = window.scrollY;
    history.replaceState(state, '');
  }

  function fullLoad(url) {
    window.location.assign(url);
  }

  function render(data, scrollY) {
    view.innerHTML = data.html;
    view.setAttribute('data-tab', data.tab);
    if (data.title) document.title = data.title;
    setActiveTab(data.tab);
    var anchor = !scrollY && location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    if (anchor) anchor.scrollIntoView();
    else window.scrollTo(0, scrollY || 0);
    // Leitor de tela anuncia a nova tela; preventScroll para não pular a rolagem restaurada.
    view.focus({ preventScroll: true });
    emitPage(data.tab);
  }

  /**
   * @param {string} url      destino (mesma origem)
   * @param {object} opts     push: cria entrada no histórico; scrollY: rolagem a restaurar; tab: aba otimista
   */
  function navigate(url, opts) {
    opts = opts || {};
    if (inFlight) inFlight.abort();
    var controller = new AbortController();
    inFlight = controller;
    var timedOut = false;
    var timer = setTimeout(function () { timedOut = true; controller.abort(); }, REQUEST_TIMEOUT_MS);

    // Feedback imediato no toque, antes da resposta chegar.
    if (opts.tab) setActiveTab(opts.tab);
    document.documentElement.setAttribute('aria-busy', 'true');

    var headers = { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
    headers[SPA_HEADER] = '1';

    fetch(url, { method: 'GET', credentials: 'same-origin', headers: headers, signal: controller.signal })
      .then(function (res) {
        var isJson = (res.headers.get('Content-Type') || '').indexOf('application/json') !== -1;
        if (res.status === 401 && isJson) {
          return res.json().then(function (data) { fullLoad(data.redirect || url); return null; });
        }
        if (!res.ok || !isJson || res.redirected) { fullLoad(url); return null; }
        return res.json();
      })
      .then(function (data) {
        if (!data) return;
        if (!data.ok || typeof data.html !== 'string') { fullLoad(url); return; }
        if (opts.push) {
          clearTimeout(scrollTimer);
          saveScroll();
          history.pushState({ spa: true, scrollY: 0 }, '', url);
        }
        render(data, opts.scrollY);
      })
      .catch(function (err) {
        // Abortado por uma navegação mais nova: não faz nada, a nova já está em andamento.
        if (err && err.name === 'AbortError' && !timedOut) return;
        fullLoad(url);
      })
      .then(function () {
        clearTimeout(timer);
        if (inFlight === controller) {
          inFlight = null;
          document.documentElement.removeAttribute('aria-busy');
        }
      });
  }

  function isSpaClick(e, link) {
    if (e.defaultPrevented || e.button !== 0) return false;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false; // nova aba/janela: deixa o navegador
    if (link.target && link.target !== '_self') return false;
    if (link.hasAttribute('download')) return false;
    return link.origin === location.origin;
  }

  document.addEventListener('click', function (e) {
    var link = e.target.closest ? e.target.closest('a[data-spa-link]') : null;
    if (!link || !isSpaClick(e, link)) return;
    e.preventDefault();
    if (link.href === location.href) return; // já está nessa aba
    navigate(link.href, { push: true, tab: link.getAttribute('data-tab') });
  });

  window.addEventListener('popstate', function (e) {
    clearTimeout(scrollTimer); // não gravar a rolagem da tela anterior na entrada para onde voltamos
    var state = e.state || {};
    navigate(location.href, { push: false, scrollY: state.scrollY || 0 });
  });

  // Rolagem guardada na entrada atual do histórico (com debounce: o Safari limita replaceState por segundo),
  // para voltar/avançar devolverem cada aba onde o usuário estava.
  var scrollTimer = null;
  window.addEventListener('scroll', function () {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(saveScroll, 150);
  }, { passive: true });

  // Navegação programática para outras telas (ex.: depósito -> pagamento -> perfil).
  window.NTApp = {
    navigate: function (url, opts) {
      opts = opts || {};
      navigate(new URL(url, location.href).href, { push: opts.replace ? false : true });
    }
  };

  // Entrada inicial no histórico, para o "voltar" até aqui restaurar a rolagem.
  history.replaceState({ spa: true, scrollY: window.scrollY }, '');
  emitPage(view.getAttribute('data-tab'));
})();
