/**
 * New Tractors — Interações da aba Início (modais, Roda da Sorte, check-in, bônus, compra).
 *
 * Tudo por delegação de eventos no document: funciona mesmo depois que o app.js troca o
 * conteúdo do #appView (o HTML do Início chega sem <script>).
 * As ações falam com as views Django por POST + JSON (CSRF do token da página).
 */
(function () {
  'use strict';

  var REQUEST_TIMEOUT_MS = 15000;
  var SEGMENTS = 7;
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var SPIN_MS = reduceMotion ? 0 : 5200;
  var NETWORK_ERROR = 'Sem conexão. Verifique sua internet e tente novamente.';
  var GENERIC_ERROR = 'Não foi possível concluir agora. Tente novamente em instantes.';

  var lastFocus = null;
  var spinning = false;

  // -----------------------------------------------------------------------
  // Utilitários
  // -----------------------------------------------------------------------
  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function newKey() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return 'k' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
  }

  /** POST que sempre resolve com {ok, ...}: nunca rejeita, para as telas tratarem um único formato. */
  function postAction(url, body, headers) {
    var controller = window.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS) : null;
    var allHeaders = { 'Accept': 'application/json', 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' };
    Object.keys(headers || {}).forEach(function (k) { allHeaders[k] = headers[k]; });

    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: allHeaders,
      body: body || new FormData(),
      signal: controller ? controller.signal : undefined
    })
      .then(function (res) {
        var isJson = (res.headers.get('Content-Type') || '').indexOf('application/json') !== -1;
        if (res.status === 401) {
          window.location.assign('/login?next=' + encodeURIComponent(location.pathname));
          return { ok: false, message: 'Sua sessão expirou. Entre novamente.', networkError: false };
        }
        if (!isJson) return { ok: false, message: GENERIC_ERROR };
        return res.json();
      })
      .catch(function () { return { ok: false, message: NETWORK_ERROR, networkError: true }; })
      .then(function (data) {
        if (timer) clearTimeout(timer);
        return data || { ok: false, message: GENERIC_ERROR };
      });
  }

  function applyBalances(data) {
    if (data.wallet) {
      Object.keys(data.wallet).forEach(function (key) {
        document.querySelectorAll('[data-wallet="' + key + '"]').forEach(function (el) { el.textContent = data.wallet[key]; });
      });
    }
    if (typeof data.invest_balance_cents === 'number') {
      document.querySelectorAll('[data-invest-cents]').forEach(function (el) {
        el.setAttribute('data-invest-cents', String(data.invest_balance_cents));
      });
    }
    if (typeof data.spins_available === 'number') {
      var modal = document.getElementById('rouletteModal');
      if (modal) {
        modal.setAttribute('data-spins', String(data.spins_available));
        if (!spinning) renderRoulette(modal);
      }
    }
  }

  function setBusy(btn, busy, label) {
    if (busy) {
      btn.dataset.idleHtml = btn.innerHTML;
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      if (label) btn.textContent = label;
    } else {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      if (btn.dataset.idleHtml) btn.innerHTML = btn.dataset.idleHtml;
    }
  }

  // -----------------------------------------------------------------------
  // Modais (foco preso, Esc fecha, trava a rolagem do fundo)
  // -----------------------------------------------------------------------
  function openModals() {
    return Array.prototype.slice.call(document.querySelectorAll('.nt-modal.is-open'));
  }

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    if (!openModals().length) lastFocus = document.activeElement;
    if (id === 'rouletteModal') resetRoulette(modal);
    modal.hidden = false;
    // Força o layout antes da classe para a transição de entrada acontecer.
    void modal.offsetWidth;
    modal.classList.add('is-open');
    document.documentElement.classList.add('nt-modal-open');
    var target = modal.querySelector('[data-autofocus], input:not([type=hidden])') || modal.querySelector('.nt-modal-card');
    if (target) target.focus({ preventScroll: true });
  }

  function closeModal(modal, restoreFocus) {
    if (!modal || !modal.classList.contains('is-open')) return;
    if (modal.id === 'rouletteModal' && spinning) return; // não fecha no meio do giro
    modal.classList.remove('is-open');
    setTimeout(function () { if (!modal.classList.contains('is-open')) modal.hidden = true; }, 220);
    if (!openModals().length) {
      document.documentElement.classList.remove('nt-modal-open');
      if (restoreFocus !== false && lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
    }
  }

  function trapFocus(e, modal) {
    var focusables = modal.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])');
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  document.addEventListener('keydown', function (e) {
    var modals = openModals();
    if (!modals.length) return;
    var top = modals[modals.length - 1];
    if (e.key === 'Escape') closeModal(top);
    else if (e.key === 'Tab') trapFocus(e, top);
  });

  function showError(message) {
    var modal = document.getElementById('actionErrorModal');
    if (!modal) { window.alert(message); return; }
    modal.querySelector('[data-error-message]').textContent = message || GENERIC_ERROR;
    openModal('actionErrorModal');
  }

  // -----------------------------------------------------------------------
  // Roda da Sorte
  // -----------------------------------------------------------------------
  function spinsOf(modal) {
    return Math.max(0, parseInt(modal.getAttribute('data-spins'), 10) || 0);
  }

  function renderRoulette(modal) {
    var spins = spinsOf(modal);
    modal.querySelector('[data-spins-label]').textContent =
      spins === 1 ? '1 giro disponível' : spins + ' giros disponíveis';
    var btn = modal.querySelector('[data-spin]');
    btn.disabled = spins < 1;
    btn.classList.toggle('is-ready', spins > 0);
    // Texto igual ao do site ("disponíveis" mesmo com 1 giro).
    modal.querySelector('[data-spin-label]').textContent =
      spins > 0 ? 'Girar Agora (' + spins + ' disponíveis)' : 'Sem giros disponíveis';
  }

  function resetRoulette(modal) {
    modal.querySelector('[data-result]').hidden = true;
    modal.querySelector('[data-error]').hidden = true;
    renderRoulette(modal);
  }

  function spin(modal) {
    if (spinning || spinsOf(modal) < 1) return;
    spinning = true;
    var btn = modal.querySelector('[data-spin]');
    var wheel = modal.querySelector('[data-wheel]');
    var error = modal.querySelector('[data-error]');
    btn.disabled = true;
    modal.querySelector('[data-spin-label]').textContent = 'Girando...';
    modal.querySelector('[data-result]').hidden = true;
    error.hidden = true;

    postAction(modal.getAttribute('data-spin-url')).then(function (data) {
      if (!data.ok) {
        spinning = false;
        error.textContent = data.message || GENERIC_ERROR;
        error.hidden = false;
        if (typeof data.spins_available === 'number') applyBalances(data);
        renderRoulette(modal);
        return;
      }

      // Para a fatia sorteada debaixo do ponteiro (topo). Fatia i vai de i*seg a (i+1)*seg, sentido horário.
      var seg = 360 / SEGMENTS;
      var current = parseFloat(wheel.dataset.rotation || '0');
      var jitter = (Math.random() - 0.5) * seg * 0.5;
      var target = (360 - (data.segment_index + 0.5) * seg + jitter) % 360;
      var delta = ((target - (current % 360)) + 360) % 360;
      var next = current + 360 * 6 + delta;
      wheel.dataset.rotation = String(next);
      wheel.style.transition = SPIN_MS ? 'transform ' + SPIN_MS + 'ms cubic-bezier(0.12, 0.72, 0.16, 1)' : 'none';
      wheel.style.transform = 'rotate(' + next + 'deg)';

      var finished = false;
      function finish() {
        if (finished) return;
        finished = true;
        spinning = false;
        modal.querySelector('[data-result-value]').textContent = data.prize_amount;
        modal.querySelector('[data-result]').hidden = false;
        applyBalances(data);
        renderRoulette(modal);
      }
      if (!SPIN_MS) { finish(); return; }
      wheel.addEventListener('transitionend', finish, { once: true });
      setTimeout(finish, SPIN_MS + 400); // garantia caso o transitionend não dispare (aba em segundo plano)
    });
  }

  // -----------------------------------------------------------------------
  // Check-in
  // -----------------------------------------------------------------------
  function checkin(btn) {
    setBusy(btn, true, 'Confirmando...');
    postAction(btn.getAttribute('data-checkin-url')).then(function (data) {
      if (!data.ok) {
        setBusy(btn, false);
        showError(data.message);
        return;
      }
      applyBalances(data);
      var amountEl = document.querySelector('#checkinSuccessModal [data-checkin-amount]');
      if (amountEl && data.amount) {
        amountEl.textContent = data.amount;
        openModal('checkinSuccessModal');
      }
      var done = document.createElement('p');
      done.className = 'home-checkin-btn is-done';
      done.setAttribute('role', 'status');
      done.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>Check-in realizado hoje';
      btn.replaceWith(done);
    });
  }

  // -----------------------------------------------------------------------
  // Código de bônus
  // -----------------------------------------------------------------------
  function normalizeCode(value) {
    return (value || '').replace(/\s+/g, '').toUpperCase();
  }

  document.addEventListener('change', function (e) {
    if (e.target.matches && e.target.matches('[data-act-agree]')) {
      document.querySelector('[data-act-confirm]').disabled = !e.target.checked;
    }
  });

  document.addEventListener('input', function (e) {
    if (!e.target.matches || !e.target.matches('#bonusCode')) return;
    var input = e.target;
    var pos = input.selectionStart;
    input.value = normalizeCode(input.value);
    try { input.setSelectionRange(pos, pos); } catch (err) { /* alguns tipos de input não suportam */ }
    var form = input.form;
    form.querySelector('[data-bonus-submit]').disabled = !input.value;
    form.querySelector('[data-error]').hidden = true;
    input.removeAttribute('aria-invalid');
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('[data-bonus-form]')) return;
    e.preventDefault();
    var input = form.querySelector('#bonusCode');
    var btn = form.querySelector('[data-bonus-submit]');
    var error = form.querySelector('[data-error]');
    var code = normalizeCode(input.value);
    if (!code || btn.disabled && btn.getAttribute('aria-busy')) return;

    setBusy(btn, true, 'Ativando...');
    var body = new FormData();
    body.append('code', code);
    postAction(form.getAttribute('action'), body).then(function (data) {
      setBusy(btn, false);
      if (!data.ok) {
        error.textContent = data.message || GENERIC_ERROR;
        error.hidden = false;
        input.setAttribute('aria-invalid', 'true');
        input.focus();
        return;
      }
      applyBalances(data);
      form.reset();
      btn.disabled = true;
      closeModal(document.getElementById('bonusModal'), false);
      document.querySelector('#bonusSuccessModal [data-bonus-amount]').textContent = data.amount;
      openModal('bonusSuccessModal');
    });
  });

  // -----------------------------------------------------------------------
  // Ativar equipamento
  // -----------------------------------------------------------------------
  function brlCents(cents) {
    var int = Math.floor(Math.abs(cents) / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return 'R$ ' + int + ',' + ('0' + (Math.abs(cents) % 100)).slice(-2);
  }

  /** Abre a confirmação com os dados do card e o saldo atual; troca o botão principal se faltar saldo. */
  function openActivation(productBtn) {
    var modal = document.getElementById('activateModal');
    var home = document.querySelector('[data-invest-cents]');
    if (!modal || !home) return;
    var num = function (attr) { return parseInt(productBtn.getAttribute(attr), 10) || 0; };
    var price = num('data-price-cents');
    var balance = parseInt(home.getAttribute('data-invest-cents'), 10) || 0;
    var missing = Math.max(0, price - balance);
    var set = function (sel, text) { modal.querySelector(sel).textContent = text; };

    modal.dataset.purchaseUrl = productBtn.getAttribute('data-purchase-url');
    set('[data-act-code]', productBtn.getAttribute('data-code'));
    set('[data-act-price]', brlCents(price));
    set('[data-act-daily]', '+' + brlCents(num('data-daily-cents')));
    set('[data-act-days]', num('data-days') + ' dias');
    set('[data-act-total]', brlCents(num('data-total-cents')));
    set('[data-act-balance]', brlCents(balance));
    set('[data-act-missing-value]', brlCents(missing));
    modal.querySelector('[data-act-missing]').hidden = !missing;
    modal.querySelector('[data-act-confirm]').hidden = !!missing;
    modal.querySelector('[data-act-deposit]').hidden = !missing;
    modal.querySelector('[data-act-cancel]').textContent = missing ? 'Voltar' : 'Cancelar';
    // "Fazer Depósito Pix" já chega na tela de depósito com o valor que falta.
    var depositUrl = modal.getAttribute('data-deposit-url') + '?valor=' + (missing / 100).toFixed(2);
    modal.querySelector('[data-act-deposit]').setAttribute('href', depositUrl);
    modal.querySelector('[data-act-deposit-link]').setAttribute('href', depositUrl);
    var agree = modal.querySelector('[data-act-agree]');
    agree.checked = true;
    modal.querySelector('[data-act-confirm]').disabled = false;
    delete modal.dataset.idemKey;
    openModal('activateModal');
  }

  function purchase(btn) {
    var modal = document.getElementById('activateModal');
    // Mesma chave em novas tentativas após falha de rede (o backend não cobra duas vezes);
    // chave nova depois de uma resposta definitiva.
    if (!modal.dataset.idemKey) modal.dataset.idemKey = newKey();
    setBusy(btn, true, 'Ativando...');
    postAction(modal.dataset.purchaseUrl, null, { 'X-Idempotency-Key': modal.dataset.idemKey })
      .then(function (data) {
        setBusy(btn, false);
        if (!data.networkError) delete modal.dataset.idemKey;
        if (!data.ok) { showError(data.message); return; }
        closeModal(modal, false);
        applyBalances(data);
        var spins = data.spins_awarded || 0;
        var pill = document.querySelector('#purchaseSuccessModal [data-purchase-spins]');
        pill.hidden = spins < 1;
        document.querySelector('#purchaseSuccessModal [data-purchase-spins-text]').textContent =
          spins === 1 ? '+1 giro liberado na Roleta' : '+' + spins + ' giros liberados na Roleta';
        openModal('purchaseSuccessModal');
      });
  }

  // -----------------------------------------------------------------------
  // Cliques
  // -----------------------------------------------------------------------
  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var el;
    if ((el = e.target.closest('[data-open-modal]'))) { e.preventDefault(); openModal(el.getAttribute('data-open-modal')); return; }
    if ((el = e.target.closest('[data-spin]'))) { spin(el.closest('.nt-modal')); return; }
    if ((el = e.target.closest('[data-checkin-url]'))) { if (!el.disabled) checkin(el); return; }
    if ((el = e.target.closest('[data-activate]'))) { openActivation(el); return; }
    if ((el = e.target.closest('[data-act-confirm]'))) { if (!el.disabled) purchase(el); return; }
    if ((el = e.target.closest('[data-close-modal]'))) {
      // Links (ex.: "Ver Minhas Compras") seguem para o app.js; aqui só fecha o modal.
      if (el.tagName !== 'A') e.preventDefault();
      closeModal(el.closest('.nt-modal'), el.tagName !== 'A');
    }
  });

  // -----------------------------------------------------------------------
  // Perfil: ocultar saldos (lembrado neste navegador) e instalar o app (PWA)
  // -----------------------------------------------------------------------
  var HIDE_KEY = 'nt_hide_balances';
  var installPrompt = null;

  function setMasked(hidden) {
    document.querySelectorAll('[data-wallet-box]').forEach(function (box) { box.classList.toggle('is-masked', hidden); });
    document.querySelectorAll('[data-toggle-balances]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(hidden));
      btn.setAttribute('aria-label', hidden ? 'Mostrar saldos' : 'Ocultar saldos');
    });
  }

  function applyBalanceVisibility() {
    var hidden = false;
    try { hidden = window.localStorage.getItem(HIDE_KEY) === '1'; } catch (err) { /* armazenamento bloqueado */ }
    setMasked(hidden);
  }

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    if (e.target.closest('[data-toggle-balances]')) {
      var box = document.querySelector('[data-wallet-box]');
      var hidden = !(box && box.classList.contains('is-masked'));
      setMasked(hidden);
      try { window.localStorage.setItem(HIDE_KEY, hidden ? '1' : '0'); } catch (err) { /* só nesta visita */ }
      return;
    }
    var install = e.target.closest('[data-install-app]');
    if (install) {
      if (installPrompt) {
        installPrompt.prompt();
        installPrompt.userChoice.then(function () { installPrompt = null; });
      } else {
        // Sem suporte ao prompt (iOS, desktop sem manifest): mostra como instalar pelo navegador.
        var hint = install.parentElement.querySelector('[data-install-hint]');
        if (hint) hint.hidden = false;
      }
    }
  });

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    installPrompt = e;
  });

  document.addEventListener('app:page', applyBalanceVisibility);

  // -----------------------------------------------------------------------
  // Saldo para saque de DEMONSTRAÇÃO (FRONTEND_DEMO_WITHDRAW): "Calculando..." e depois sobe a cada 3s.
  // O valor sai do tempo decorrido (não soma por tique), então fica certo mesmo com o timer atrasado em
  // segundo plano. "Meu Patrimônio", se visível, = saldo para investir (data-invest-cents) + demonstração.
  // -----------------------------------------------------------------------
  var DEMO_TICK_MS = 3000;
  var DEMO_CALC_MS = 1800;
  var demoTimer = null;

  function startDemoTicker() {
    clearInterval(demoTimer);
    demoTimer = null;
    var withdraw = document.querySelector('[data-demo-withdraw]');
    if (!withdraw) return;
    var total = document.querySelector('[data-demo-total]');
    var baseCents = parseInt(withdraw.getAttribute('data-cents'), 10) || 0;
    var centsPerMs = (parseInt(withdraw.getAttribute('data-rate-cents-per-hour'), 10) || 0) / 3600000;
    var t0 = performance.now();
    var last = null;

    function show(el, cents, grew) {
      el.querySelector('.demo-value').textContent = brlCents(cents);
      if (!grew) return;
      el.classList.remove('is-up');
      void el.offsetWidth; // reinicia a animação de "subiu"
      el.classList.add('is-up');
    }

    function render() {
      var cents = Math.floor(baseCents + centsPerMs * (performance.now() - t0));
      if (cents === last) return;
      var grew = last !== null;
      last = cents;
      show(withdraw, cents, grew);
      var home = document.querySelector('[data-invest-cents]');
      if (total && home) show(total, (parseInt(home.getAttribute('data-invest-cents'), 10) || 0) + cents, grew);
    }

    // "Calculando..." só termina com o card à vista: com um aviso por cima (ex.: "Bem-vindo", que abre a cada
    // carga completa), espera fechar e conta o tempo do "Calculando..." a partir daí.
    function overlayOpen() { return !!document.querySelector('.wl-overlay.is-open'); }

    function waitOverlay() {
      if (!document.contains(withdraw)) return; // saiu do Início
      if (overlayOpen()) { setTimeout(waitOverlay, 300); return; }
      setTimeout(tryReveal, DEMO_CALC_MS);
    }

    function tryReveal() {
      if (!document.contains(withdraw)) return;
      if (overlayOpen()) { waitOverlay(); return; }
      render();
      withdraw.classList.remove('is-calculating');
      if (total) total.classList.remove('is-calculating');
      demoTimer = setInterval(function () {
        if (!document.contains(withdraw)) { clearInterval(demoTimer); demoTimer = null; return; }
        render();
      }, DEMO_TICK_MS);
    }

    setTimeout(tryReveal, DEMO_CALC_MS);
  }

  // Carga inicial (o app.js já emitiu o app:page antes deste arquivo) e cada volta ao Início pelo SPA.
  startDemoTicker();
  document.addEventListener('app:page', function (e) {
    if (e.detail && e.detail.tab === 'home') startDemoTicker();
  });

  // Utilitários usados por outras telas (withdraw.js).
  window.NT = { postAction: postAction, openModal: openModal, closeModal: closeModal, newKey: newKey,
                applyBalances: applyBalances, showError: showError };

  // Troca de aba pelo SPA com modal aberto: libera a rolagem.
  document.addEventListener('app:page', function () {
    spinning = false;
    document.documentElement.classList.remove('nt-modal-open');
  });
})();
