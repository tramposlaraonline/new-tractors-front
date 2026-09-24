/**
 * New Tractors — Depósito Pix (/recharge), identificação do titular (CPF) e pagamento (/recharge/<id>).
 *
 * Também expõe window.NTForm (máscara/validação de CPF e erros de campo), usado pelo cadastro de chave Pix.
 * Valores em centavos inteiros; o servidor revalida tudo.
 */
(function () {
  'use strict';

  var POLL_MS = 5000;
  var pendingKey = null;
  var pollTimer = null;
  var countdownTimer = null;

  // -----------------------------------------------------------------------
  // Utilitários de formulário (compartilhados)
  // -----------------------------------------------------------------------
  function digits(v) { return String(v || '').replace(/\D/g, ''); }

  function maskCpf(v) {
    var d = digits(v).slice(0, 11);
    if (d.length > 9) return d.slice(0, 3) + '.' + d.slice(3, 6) + '.' + d.slice(6, 9) + '-' + d.slice(9);
    if (d.length > 6) return d.slice(0, 3) + '.' + d.slice(3, 6) + '.' + d.slice(6);
    if (d.length > 3) return d.slice(0, 3) + '.' + d.slice(3);
    return d;
  }

  function cpfValid(v) {
    var d = digits(v);
    if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
    for (var size = 9; size <= 10; size++) {
      var total = 0;
      for (var i = 0; i < size; i++) total += parseInt(d[i], 10) * (size + 1 - i);
      if ((total * 10) % 11 % 10 !== parseInt(d[size], 10)) return false;
    }
    return true;
  }

  function nameValid(v) {
    var name = String(v || '').trim().replace(/\s+/g, ' ');
    return name.length >= 5 && name.indexOf(' ') > 0 && /^[A-Za-zÀ-ÖØ-öø-ÿ' .-]+$/.test(name);
  }

  function setFieldError(form, field, message) {
    var el = form.querySelector('[data-field-error="' + field + '"]');
    var input = form.querySelector('[name="' + field + '"]');
    if (el) { el.textContent = message || ''; el.hidden = !message; }
    if (input && input.type !== 'radio') {
      if (message) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
    }
  }

  function clearErrors(form) {
    form.querySelectorAll('[data-field-error]').forEach(function (el) { el.textContent = ''; el.hidden = true; });
    form.querySelectorAll('[aria-invalid]').forEach(function (el) { el.removeAttribute('aria-invalid'); });
    var general = form.querySelector('[data-form-error]');
    if (general) { general.textContent = ''; general.hidden = true; }
  }

  function showServerErrors(form, data) {
    var errors = data.errors || {};
    var fields = Object.keys(errors);
    fields.forEach(function (f) { setFieldError(form, f, errors[f]); });
    if (!fields.length) {
      var general = form.querySelector('[data-form-error]');
      if (general) { general.textContent = data.message || 'Não foi possível salvar agora.'; general.hidden = false; }
    } else {
      var first = form.querySelector('[name="' + fields[0] + '"]');
      if (first && first.focus) first.focus();
    }
  }

  function busy(btn, label) {
    btn.dataset.idleHtml = btn.innerHTML;
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    btn.textContent = label;
  }

  function idle(btn) {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    if (btn.dataset.idleHtml) btn.innerHTML = btn.dataset.idleHtml;
  }

  /** Mostra um aviso de sucesso por alguns instantes e segue. */
  function flash(id, ms, then) {
    window.NT.openModal(id);
    setTimeout(function () {
      window.NT.closeModal(document.getElementById(id), false);
      if (then) then();
    }, ms);
  }

  window.NTForm = {
    digits: digits, maskCpf: maskCpf, cpfValid: cpfValid, nameValid: nameValid, setFieldError: setFieldError,
    clearErrors: clearErrors, showServerErrors: showServerErrors, busy: busy, idle: idle, flash: flash
  };

  document.addEventListener('input', function (e) {
    if (e.target.matches && e.target.matches('[data-mask="cpf"]')) {
      e.target.value = maskCpf(e.target.value);
      var form = e.target.form;
      if (form) setFieldError(form, e.target.name, '');
    } else if (e.target.form && e.target.form.matches && e.target.form.matches('[data-cpf-form], [data-pix-key-form]')) {
      setFieldError(e.target.form, e.target.name, '');
    }
  });

  // -----------------------------------------------------------------------
  // Tela de depósito
  // -----------------------------------------------------------------------
  function brl(cents) {
    var int = Math.floor(cents / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return 'R$ ' + int + ',' + ('0' + (cents % 100)).slice(-2);
  }

  function depositRoot() { return document.querySelector('[data-deposit]'); }

  function amountCents(page) {
    var raw = page.querySelector('[data-deposit-amount]').value;
    var value = Number(String(raw || '').replace(',', '.'));
    return isFinite(value) && value > 0 ? Math.round(value * 100) : 0;
  }

  function validationError(page, cents) {
    var min = parseInt(page.getAttribute('data-min-cents'), 10) || 0;
    var max = parseInt(page.getAttribute('data-max-cents'), 10) || Infinity;
    if (!cents) return 'Selecione ou digite o valor do depósito.';
    if (cents < min) return 'O valor mínimo para depósito é ' + brl(min) + '.';
    if (cents > max) return 'O valor máximo por depósito é ' + brl(max) + '.';
    return '';
  }

  function updateDeposit(page, showError) {
    var cents = amountCents(page);
    page.querySelector('[data-deposit-submit-label]').textContent =
      cents ? 'Gerar Chave Pix (' + brl(cents) + ')' : 'Gerar Chave Pix';
    page.querySelectorAll('[data-preset-cents]').forEach(function (btn) {
      var on = parseInt(btn.getAttribute('data-preset-cents'), 10) === cents;
      btn.classList.toggle('is-selected', on);
      btn.setAttribute('aria-pressed', String(on));
    });
    var errorEl = page.querySelector('[data-deposit-error]');
    var error = validationError(page, cents);
    if (showError || (!error && !errorEl.hidden)) {
      errorEl.textContent = error;
      errorEl.hidden = !error;
    }
    return { cents: cents, error: error };
  }

  function depositFail(message) {
    document.querySelector('[data-deposit-error-message]').textContent = message;
    window.NT.openModal('depositError');
  }

  function generateCharge(page) {
    var state = updateDeposit(page, true);
    if (state.error) return;
    var btn = page.querySelector('[data-deposit-submit]');
    if (!pendingKey || pendingKey.cents !== state.cents) pendingKey = { key: window.NT.newKey(), cents: state.cents };
    busy(btn, '⌛ Gerando Cobrança Pix...');
    var body = new FormData();
    body.append('amount', (state.cents / 100).toFixed(2));
    window.NT.postAction(page.getAttribute('data-deposit-url'), body, { 'X-Idempotency-Key': pendingKey.key })
      .then(function (data) {
        if (!data.networkError) pendingKey = null;
        if (data.ok && data.redirect) {
          window.NTApp.navigate(data.redirect);
          return;
        }
        idle(btn);
        updateDeposit(page, false);
        if (data.need_cpf) { openCpf(page, state.cents); return; }
        depositFail(data.message || 'Não foi possível gerar a cobrança agora.');
      });
  }

  function openCpf(page, cents) {
    var modal = document.getElementById('cpfModal');
    var wrap = modal.querySelector('[data-cpf-amount-wrap]');
    wrap.hidden = !cents;
    modal.querySelector('[data-cpf-amount]').textContent = cents ? brl(cents) : '';
    modal.dataset.continue = cents ? '1' : '0';
    clearErrors(modal.querySelector('form'));
    window.NT.openModal('cpfModal');
  }

  document.addEventListener('input', function (e) {
    if (e.target.matches && e.target.matches('[data-deposit-amount]')) updateDeposit(depositRoot(), false);
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('[data-cpf-form]')) return;
    e.preventDefault();
    var page = depositRoot();
    clearErrors(form);
    if (!cpfValid(form.elements.cpf.value)) {
      setFieldError(form, 'cpf', 'CPF inválido. Confira os números.');
      form.elements.cpf.focus();
      return;
    }

    var btn = form.querySelector('[data-cpf-submit]');
    busy(btn, 'Salvando identificação...');
    window.NT.postAction(page.getAttribute('data-cpf-url'), new FormData(form)).then(function (data) {
      idle(btn);
      if (!data.ok) { showServerErrors(form, data); return; }
      var modal = document.getElementById('cpfModal');
      var shouldContinue = modal.dataset.continue === '1';
      var cpf = digits(form.elements.cpf.value);
      form.reset();
      window.NT.closeModal(modal, false);
      page.setAttribute('data-cpf-registered', '1');
      page.querySelector('[data-cpf-box]').hidden = true;
      page.querySelector('[data-cpf-masked]').textContent = '***.' + cpf.slice(3, 6) + '.' + cpf.slice(6, 9) + '-**';
      page.querySelector('[data-cpf-ok]').hidden = false;
      flash('cpfSuccess', 1600, function () { if (shouldContinue) generateCharge(page); });
    });
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var page = depositRoot();
    var el;
    if (page && (el = e.target.closest('[data-preset-cents]'))) {
      page.querySelector('[data-deposit-amount]').value = (parseInt(el.getAttribute('data-preset-cents'), 10) / 100).toFixed(2);
      updateDeposit(page, false);
      return;
    }
    if (page && e.target.closest('[data-open-cpf]')) { openCpf(page, 0); return; }
    if (page && e.target.closest('[data-deposit-submit]')) {
      var state = updateDeposit(page, true);
      if (state.error) { page.querySelector('[data-deposit-amount]').focus(); return; }
      if (page.getAttribute('data-cpf-registered') !== '1') openCpf(page, state.cents);
      else generateCharge(page);
      return;
    }
    var pay = paymentRoot();
    if (pay && (el = e.target.closest('[data-copy-pix]'))) { copyCode(pay, el); return; }
    if (pay && (el = e.target.closest('[data-confirm-paid]'))) { checkStatus(pay, true, el); }
  });

  // -----------------------------------------------------------------------
  // Tela de pagamento
  // -----------------------------------------------------------------------
  function paymentRoot() { return document.querySelector('[data-payment]'); }

  function stopPayment() {
    clearInterval(pollTimer);
    clearInterval(countdownTimer);
    pollTimer = countdownTimer = null;
  }

  function setPayStatus(pay, text, tone) {
    var el = pay.querySelector('[data-pay-status]');
    el.className = 'dp-pay-status' + (tone ? ' is-' + tone : '');
    pay.querySelector('[data-pay-status-text]').textContent = text;
  }

  function finishPaid(pay, redirect) {
    stopPayment();
    pay.setAttribute('data-status', 'paid');
    setPayStatus(pay, '✓ Pagamento Confirmado! Redirecionando...', 'ok');
    pay.querySelector('[data-confirm-paid]').disabled = true;
    setTimeout(function () { if (paymentRoot() === pay) window.NTApp.navigate(redirect || '/my'); }, 1500);
  }

  function markExpired(pay) {
    stopPayment();
    pay.setAttribute('data-status', 'expired');
    pay.querySelector('[data-timer-text]').textContent = 'Expirado';
    pay.querySelector('[data-timer]').classList.add('is-expired');
    pay.querySelector('[data-confirm-paid]').disabled = true;
    setPayStatus(pay, 'Cobrança expirada. Gere um novo Pix em "Alterar valor".', 'bad');
  }

  function checkStatus(pay, manual, btn) {
    if (pay.getAttribute('data-status') !== 'pending' || pay.dataset.checking === '1') return;
    pay.dataset.checking = '1';
    if (btn) busy(btn, 'Verificando pagamento...');
    var body = new FormData();
    body.append('manual', manual ? '1' : '0');
    window.NT.postAction(pay.getAttribute('data-status-url'), body).then(function (data) {
      pay.dataset.checking = '0';
      if (btn) idle(btn);
      if (paymentRoot() !== pay) return;
      if (data.ok && data.status === 'paid') { window.NT.applyBalances(data); finishPaid(pay, data.redirect); return; }
      if (data.ok && data.status === 'expired') { markExpired(pay); return; }
      if (manual) {
        setPayStatus(pay, data.ok ? 'Pagamento ainda não identificado. Aguardando liquidação bancária...'
                                  : (data.message || 'Não foi possível verificar agora.'), data.ok ? '' : 'bad');
      }
    });
  }

  function startPayment(pay) {
    stopPayment();
    var status = pay.getAttribute('data-status');
    if (status === 'paid') { finishPaid(pay, '/my'); return; }
    if (status === 'expired') { markExpired(pay); return; }

    var expires = Date.parse(pay.getAttribute('data-expires'));
    function tick() {
      if (paymentRoot() !== pay) { stopPayment(); return; }
      if (!expires) { pay.querySelector('[data-timer-text]').textContent = 'Aguardando'; return; }
      var left = Math.max(0, Math.round((expires - Date.now()) / 1000));
      var mm = Math.floor(left / 60), ss = left % 60;
      pay.querySelector('[data-timer-text]').textContent = 'Expira em: ' + mm + ':' + ('0' + ss).slice(-2);
      if (!left) markExpired(pay);
    }
    tick();
    countdownTimer = setInterval(tick, 1000);
    pollTimer = setInterval(function () {
      if (paymentRoot() !== pay) { stopPayment(); return; }
      if (!document.hidden) checkStatus(pay, false);
    }, POLL_MS);
  }

  function copyCode(pay, btn) {
    var code = pay.querySelector('[data-pix-code]').textContent.trim();
    var label = btn.querySelector('[data-copy-label]');
    function done(ok) {
      label.textContent = ok ? 'Código copiado!' : 'Selecione e copie o código acima';
      btn.classList.toggle('is-copied', ok);
      setTimeout(function () { label.textContent = 'Copiar Código Pix Copia e Cola'; btn.classList.remove('is-copied'); }, 2500);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(code).then(function () { done(true); }, function () { done(fallbackCopy(code)); });
    } else {
      done(fallbackCopy(code));
    }
  }

  function fallbackCopy(text) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.cssText = 'position:fixed;top:-1000px;opacity:0';
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    document.body.removeChild(area);
    return ok;
  }

  // -----------------------------------------------------------------------
  // Ciclo de vida (troca SPA e carga direta)
  // -----------------------------------------------------------------------
  function onPage() {
    var page = depositRoot();
    if (page) {
      pendingKey = null;
      var wanted = Number(new URLSearchParams(location.search).get('valor'));
      if (isFinite(wanted) && wanted > 0) {
        var min = parseInt(page.getAttribute('data-min-cents'), 10) || 0;
        page.querySelector('[data-deposit-amount]').value = (Math.max(Math.round(wanted * 100), min) / 100).toFixed(2);
      }
      updateDeposit(page, false);
    }
    var pay = paymentRoot();
    if (pay) startPayment(pay); else stopPayment();
  }

  document.addEventListener('app:page', onPage);
  onPage();
})();
