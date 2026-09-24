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
      if (!state.valid) return;
      document.querySelector('[data-withdraw-confirm-amount]').textContent = brl(state.cents);
      window.NT.openModal('withdrawConfirm');
      return;
    }
    if ((el = e.target.closest('[data-withdraw-confirm]'))) {
      window.NT.closeModal(document.getElementById('withdrawConfirm'), false);
      submit(page);
    }
  });

  document.addEventListener('app:page', function () {
    var page = root();
    if (page) { pendingKey = null; update(page); }
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
})();
