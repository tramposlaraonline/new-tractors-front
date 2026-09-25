/**
 * New Tractors — Solicitar Saque Pix (/withdraw).
 *
 * Valores em centavos inteiros (sem erro de ponto flutuante). O servidor revalida tudo:
 * a tela só evita pedidos que certamente seriam recusados.
 * Usa os utilitários expostos pelo home.js (window.NT) e delegação de eventos (funciona após troca SPA).
 */
(function () {
  'use strict';

  var pendingKey = null; // mantida entre tentativas após falha de rede, para o backend não processar duas vezes

  function root() { return document.querySelector('[data-withdraw]'); }

  function num(el, attr) { return parseInt(el.getAttribute(attr), 10) || 0; }

  function brl(cents) {
    var abs = Math.abs(cents);
    var int = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return (cents < 0 ? '-' : '') + 'R$ ' + int + ',' + ('0' + (abs % 100)).slice(-2);
  }

  function amountCents(page) {
    var raw = page.querySelector('[data-withdraw-amount]').value;
    if (!raw) return 0;
    var value = Number(String(raw).replace(',', '.'));
    if (!isFinite(value) || value <= 0) return 0;
    return Math.round(value * 100);
  }

  /** Recalcula líquido, rótulo e estado do botão. Retorna {cents, valid}. */
  function update(page) {
    var cents = amountCents(page);
    var balance = num(page, 'data-balance-cents');
    var min = num(page, 'data-min-cents');
    var feeBp = num(page, 'data-fee-bp');
    var hasKey = page.getAttribute('data-has-key') === '1';
    var net = cents > 0 ? cents - Math.round(cents * feeBp / 10000) : 0;

    page.querySelector('[data-withdraw-net]').textContent = brl(Math.max(0, net));
    page.querySelector('[data-withdraw-submit-label]').textContent =
      cents > 0 ? 'Confirmar Saque Pix (' + brl(cents) + ')' : 'Confirmar Saque Pix';

    var error = '';
    if (cents > 0 && cents < min) error = 'O valor mínimo para saque é ' + brl(min) + '.';
    else if (cents > balance) error = 'Valor acima do saldo disponível para saque.';
    var errorEl = page.querySelector('[data-withdraw-error]');
    errorEl.textContent = error;
    errorEl.hidden = !error;

    var valid = hasKey && cents >= min && cents <= balance && cents > 0;
    var btn = page.querySelector('[data-withdraw-submit]');
    if (!btn.getAttribute('aria-busy')) btn.disabled = !valid;
    return { cents: cents, valid: valid };
  }

  function openDialog(id, message, selector) {
    var modal = document.getElementById(id);
    if (message && selector) modal.querySelector(selector).textContent = message;
    window.NT.openModal(id);
  }

  function submit(page) {
    var state = update(page);
    if (!state.valid) return;
    var btn = page.querySelector('[data-withdraw-submit]');
    var label = page.querySelector('[data-withdraw-submit-label]');
    if (!pendingKey || pendingKey.cents !== state.cents) pendingKey = { key: window.NT.newKey(), cents: state.cents };

    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    label.textContent = 'Processando Saque...';

    var body = new FormData();
    body.append('amount', (state.cents / 100).toFixed(2));
    window.NT.postAction(page.getAttribute('data-withdraw-url'), body, { 'X-Idempotency-Key': pendingKey.key })
      .then(function (data) {
        if (!data.networkError) pendingKey = null;
        btn.removeAttribute('aria-busy');
        if (!data.ok) {
          update(page);
          openDialog('withdrawError', data.message, '[data-withdraw-error-message]');
          return;
        }
        window.NT.applyBalances(data);
        if (typeof data.withdraw_balance_cents === 'number') {
          page.setAttribute('data-balance-cents', String(data.withdraw_balance_cents));
        }
        if (typeof data.recent_html === 'string') page.querySelector('[data-withdraw-recent]').innerHTML = data.recent_html;
        if (typeof data.queue_html === 'string') {
          page.querySelector('[data-withdraw-queue-slot]').innerHTML = data.queue_html;
          scheduleQueue();
        }
        page.querySelector('[data-withdraw-amount]').value = '';
        update(page);
        openDialog('withdrawSuccess', data.message, '[data-withdraw-success-message]');
      });
  }

  document.addEventListener('input', function (e) {
    if (e.target.matches && e.target.matches('[data-withdraw-amount]')) update(e.target.closest('[data-withdraw]'));
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.matches && e.target.matches('[data-withdraw-amount]')) {
      e.preventDefault();
      e.target.closest('[data-withdraw]').querySelector('[data-withdraw-submit]').click();
    }
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var page = root();
    if (!page) return;
    var el;
    if ((el = e.target.closest('[data-withdraw-all]'))) {
      page.querySelector('[data-withdraw-amount]').value = (num(page, 'data-balance-cents') / 100).toFixed(2);
      update(page);
      return;
    }
    if ((el = e.target.closest('[data-withdraw-submit]'))) {
      var state = update(page);
      if (!state.valid) {
        var amountInput = page.querySelector('[data-withdraw-amount]');
        if (amountInput) amountInput.focus();
        return;
      }
      var confirmAmount = document.querySelector('[data-withdraw-confirm-amount]');
      if (!confirmAmount || !window.NT) return;
      confirmAmount.textContent = brl(state.cents);
      window.NT.openModal('withdrawConfirm');
      return;
    }
    if ((el = e.target.closest('[data-withdraw-confirm]'))) {
      if (!window.NT) return;
      window.NT.closeModal(document.getElementById('withdrawConfirm'), false);
      submit(page);
    }
  });

  document.addEventListener('app:page', function () {
    var page = root();
    if (page) {
      pendingKey = null;
      update(page);
    }
    // Entrando na tela de saque: atualiza a fila na hora (não espera 15s).
    if (queueCard() && !document.hidden) {
      pollQueue();
    } else {
      scheduleQueue();
    }
  });

  // -----------------------------------------------------------------------
  // Fila de saque: consulta o backend enquanto o cartão está na tela e a aba visível.
  // A tela nunca calcula posição: só mostra o que /acoes/saque/fila devolve.
  // -----------------------------------------------------------------------
  var QUEUE_POLL_MS = 15000;
  var DRIVE_MS = 1500;   // igual à transição da faixa no CSS (1400ms) + folga
  var MOVED_MS = 6000;   // tempo do selo "A fila andou"
  var queueTimer = null;
  var queueBusy = false;

  function queueCard() { return document.querySelector('[data-withdraw-queue]'); }

  function scheduleQueue() {
    clearTimeout(queueTimer);
    queueTimer = null;
    if (queueCard() && !document.hidden) queueTimer = setTimeout(pollQueue, QUEUE_POLL_MS);
  }

  function clockLabel() {
    var d = new Date();
    return 'Atualizado às ' + ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }

  function setStale(card, stale) {
    card.classList.toggle('is-stale', stale);
    card.querySelector('[data-queue-updated]').textContent =
      stale ? 'Sem conexão com a fila. Tentando de novo...' : clockLabel();
  }

  /** Troca o número no meio da rolagem (com movimento reduzido, a animação não roda e a troca é imediata). */
  function rollNumber(el, text) {
    el.classList.remove('is-rolling');
    void el.offsetWidth; // reinicia a animação se a fila andar duas vezes seguidas
    el.classList.add('is-rolling');
    setTimeout(function () { el.textContent = text; }, 320);
    setTimeout(function () { el.classList.remove('is-rolling'); }, 720);
  }

  function renderQueue(card, q) {
    var previous = parseInt(card.getAttribute('data-position'), 10) || q.position;
    var numEl = card.querySelector('[data-queue-position]');
    card.setAttribute('data-position', String(q.position));
    card.querySelector('[data-queue-ahead]').textContent = q.ahead_label;

    var trackWrap = card.querySelector('[data-queue-track]');
    var track = card.querySelector('[data-queue-progress]');
    var hasProgress = typeof q.progress_pct === 'number';
    trackWrap.hidden = !hasProgress;
    if (hasProgress) {
      track.style.setProperty('--wq-pct', String(q.progress_pct));
      track.setAttribute('aria-valuenow', String(q.progress_pct));
      card.querySelector('[data-queue-cleared]').textContent = q.cleared_label;
    }

    if (q.position >= previous) { numEl.textContent = q.position_display; return; }

    // A fila andou: número rola, trator avança, selo e anúncio para leitor de tela.
    var moved = previous - q.position;
    rollNumber(numEl, q.position_display);
    if (hasProgress) {
      track.classList.add('is-driving');
      setTimeout(function () { track.classList.remove('is-driving'); }, DRIVE_MS);
    }
    var chip = card.querySelector('[data-queue-moved]');
    chip.textContent = moved === 1 ? 'A fila andou 1 posição' : 'A fila andou ' + moved + ' posições';
    chip.hidden = false;
    clearTimeout(chip._hideTimer);
    chip._hideTimer = setTimeout(function () { chip.hidden = true; }, MOVED_MS);
    card.querySelector('[data-queue-announce]').textContent =
      'Sua posição agora é ' + q.position_display + '. ' + q.ahead_label;
  }

  function pollQueue() {
    var card = queueCard();
    if (!card || queueBusy) return;
    queueBusy = true;
    window.NT.postAction(card.getAttribute('data-queue-url')).then(function (data) {
      queueBusy = false;
      if (queueCard() !== card) return;   // saiu da tela no meio da consulta
      if (data.locked) return;            // área fechada pelo bloqueio: para de consultar
      if (!data.ok) { setStale(card, true); scheduleQueue(); return; }
      if (!data.queue) {
        // Saiu da fila (pago ou recusado): recarrega a tela para mostrar status e saldo reais.
        window.NTApp.navigate(location.href, { replace: true });
        return;
      }
      setStale(card, false);
      renderQueue(card, data.queue);
      scheduleQueue();
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { clearTimeout(queueTimer); queueTimer = null; return; }
    if (queueCard()) pollQueue(); // voltou para a aba: atualiza na hora em vez de esperar o próximo ciclo
  });

  // -----------------------------------------------------------------------
  // Cadastro da chave Pix (usa window.NTForm do deposit.js)
  // -----------------------------------------------------------------------
  var KEY_TYPES = {
    cpf: { placeholder: '000.000.000-00', inputmode: 'numeric', maxlength: 14 },
    cnpj: { placeholder: '00.000.000/0000-00', inputmode: 'numeric', maxlength: 18 },
    phone: { placeholder: '(00) 00000-0000', inputmode: 'numeric', maxlength: 15 },
    email: { placeholder: 'voce@email.com', inputmode: 'email', maxlength: 77 },
    random: { placeholder: '00000000-0000-0000-0000-000000000000', inputmode: 'text', maxlength: 36 }
  };

  function maskPhone(v) {
    var d = window.NTForm.digits(v);
    if (d.indexOf('55') === 0 && d.length > 11) d = d.slice(2);
    d = d.slice(0, 11);
    if (d.length > 7) return '(' + d.slice(0, 2) + ') ' + d.slice(2, 7) + '-' + d.slice(7);
    if (d.length > 2) return '(' + d.slice(0, 2) + ') ' + d.slice(2);
    return d ? '(' + d : '';
  }

  function maskCnpj(v) {
    var d = window.NTForm.digits(v).slice(0, 14);
    if (d.length > 12) return d.slice(0, 2) + '.' + d.slice(2, 5) + '.' + d.slice(5, 8) + '/' + d.slice(8, 12) + '-' + d.slice(12);
    if (d.length > 8) return d.slice(0, 2) + '.' + d.slice(2, 5) + '.' + d.slice(5, 8) + '/' + d.slice(8);
    if (d.length > 5) return d.slice(0, 2) + '.' + d.slice(2, 5) + '.' + d.slice(5);
    if (d.length > 2) return d.slice(0, 2) + '.' + d.slice(2);
    return d;
  }

  function cnpjValid(v) {
    var d = window.NTForm.digits(v);
    if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false;
    for (var size = 12; size <= 13; size++) {
      var weights = size === 12 ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
      var total = 0;
      for (var i = 0; i < size; i++) total += parseInt(d[i], 10) * weights[i];
      var check = total % 11 < 2 ? 0 : 11 - total % 11;
      if (check !== parseInt(d[size], 10)) return false;
    }
    return true;
  }

  function keyType(form) {
    var checked = form.querySelector('input[name="key_type"]:checked');
    return checked ? checked.value : '';
  }

  function applyKeyType(form) {
    var cfg = KEY_TYPES[keyType(form)] || KEY_TYPES.cpf;
    var input = form.querySelector('[data-pix-key-input]');
    input.value = '';
    input.placeholder = cfg.placeholder;
    input.setAttribute('inputmode', cfg.inputmode);
    input.maxLength = cfg.maxlength;
    input.classList.toggle('fm-mono', keyType(form) !== 'email');
    window.NTForm.setFieldError(form, 'key', '');
  }

  function keyError(type, value) {
    var F = window.NTForm;
    var d = F.digits(value);
    if (type === 'cpf') return F.cpfValid(value) ? '' : 'CPF inválido. Confira os números.';
    if (type === 'cnpj') return cnpjValid(value) ? '' : 'CNPJ inválido. Confira os números.';
    if (type === 'phone') return d.length === 11 ? '' : 'Telefone deve ter DDD + 9 dígitos.';
    if (type === 'email') return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim()) ? '' : 'E-mail inválido.';
    if (type === 'random') {
      return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.trim()) ? ''
        : 'Chave aleatória inválida (formato 00000000-0000-0000-0000-000000000000).';
    }
    return 'Selecione o tipo de chave.';
  }

  document.addEventListener('change', function (e) {
    if (e.target.matches && e.target.matches('[data-pix-key-form] input[name="key_type"]')) applyKeyType(e.target.form);
  });

  document.addEventListener('input', function (e) {
    if (!e.target.matches || !e.target.matches('[data-pix-key-input]')) return;
    var form = e.target.form;
    var type = keyType(form);
    if (type === 'cpf') e.target.value = window.NTForm.maskCpf(e.target.value);
    else if (type === 'cnpj') e.target.value = maskCnpj(e.target.value);
    else if (type === 'phone') e.target.value = maskPhone(e.target.value);
    else if (type === 'random') e.target.value = e.target.value.replace(/\s+/g, '').toLowerCase();
  });

  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('[data-register-pix]')) {
      var form = document.querySelector('[data-pix-key-form]');
      form.reset();
      window.NTForm.clearErrors(form);
      applyKeyType(form);
      window.NT.openModal('pixKeyModal');
    }
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('[data-pix-key-form]')) return;
    e.preventDefault();
    var F = window.NTForm;
    F.clearErrors(form);
    var error = keyError(keyType(form), form.elements.key.value);
    if (error) { F.setFieldError(form, 'key', error); form.elements.key.focus(); return; }

    var btn = form.querySelector('[data-pix-key-submit]');
    F.busy(btn, 'Salvando chave...');
    window.NT.postAction(form.getAttribute('action'), new FormData(form)).then(function (data) {
      F.idle(btn);
      if (!data.ok) { F.showServerErrors(form, data); return; }
      window.NT.closeModal(document.getElementById('pixKeyModal'), false);
      // Recarrega só o conteúdo da tela (SPA) para mostrar a chave vinculada.
      F.flash('pixKeySuccess', 1600, function () { window.NTApp.navigate(location.href, { replace: true }); });
    });
  });

  // Carga direta de /withdraw: o app:page inicial do app.js dispara antes deste script.
  if (root()) update(root());
  if (queueCard() && !document.hidden) {
    pollQueue();
  } else {
    scheduleQueue();
  }
})();
