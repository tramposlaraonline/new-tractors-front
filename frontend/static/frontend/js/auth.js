/**
 * New Tractors — Comportamento das telas de autenticação
 * Replica o agrofarm-auth.js original (máscara, validação, mensagens, "Verificando..." /
 * "Criando conta...", modal de sucesso de 3,5s com barra de progresso, código de convite
 * preservado entre URL e sessionStorage), falando com as views Django via JSON.
 * Sem fetch (ou resposta HTML inesperada) o form faz POST normal e o Django renderiza os erros.
 */
document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  var REQUEST_TIMEOUT_MS = 15000;
  var SUCCESS_MODAL_MS = 3500;
  var INVITE_STORAGE_KEY = 'new_tractor_pending_invite_code';

  // Máscara de celular BR (remove 55 extra quando colado)
  function phoneDigits(val) {
    var digits = (val || '').replace(/\D/g, '');
    if (digits.indexOf('55') === 0 && (digits.length === 12 || digits.length === 13)) {
      digits = digits.slice(2);
    }
    return digits.slice(0, 11);
  }

  function maskPhone(val) {
    var digits = phoneDigits(val);
    if (!digits) return '';
    if (digits.length <= 2) return '(' + digits;
    if (digits.length <= 6) return '(' + digits.slice(0, 2) + ') ' + digits.slice(2);
    if (digits.length <= 10) return '(' + digits.slice(0, 2) + ') ' + digits.slice(2, 6) + '-' + digits.slice(6);
    return '(' + digits.slice(0, 2) + ') ' + digits.slice(2, 7) + '-' + digits.slice(7, 11);
  }

  function storageGet(key) {
    try { return window.sessionStorage.getItem(key) || ''; } catch (e) { return ''; }
  }

  function storageSet(key, value) {
    try { window.sessionStorage.setItem(key, value); } catch (e) { /* modo privado / bloqueado */ }
  }

  // Código de convite vindo da URL fica guardado para a tela de cadastro (como no original)
  var urlParams = new URLSearchParams(window.location.search);
  var codeInUrl = urlParams.get('code') || urlParams.get('register_code') || urlParams.get('invitationCode');
  if (codeInUrl) storageSet(INVITE_STORAGE_KEY, codeInUrl.replace(/\s+/g, '').toUpperCase());

  // Mostrar/ocultar senha (mesmo feedback do original: opacidade do ícone)
  document.querySelectorAll('[data-toggle-password]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById(btn.getAttribute('data-toggle-password'));
      if (!input) return;
      var isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      btn.setAttribute('aria-pressed', String(isPassword));
      btn.setAttribute('aria-label', isPassword ? 'Ocultar senha' : 'Exibir senha');
      var icon = btn.querySelector('svg');
      if (icon) icon.style.opacity = isPassword ? '1' : '0.6';
    });
  });

  function safeRedirect(url) {
    try {
      var target = new URL(url || '/', window.location.href);
      if (target.origin === window.location.origin) return target.href;
    } catch (e) { /* URL inválida: usa a raiz */ }
    return '/';
  }

  // Modal de sucesso com barra de progresso animada
  function triggerSuccessModal(onComplete, durationMs) {
    var modal = document.getElementById('authSuccessModal');
    var bar = document.getElementById('authProgressBar');
    if (!modal) { onComplete(); return; }

    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    var card = modal.querySelector('.auth-modal-card');
    if (card) card.focus();

    if (!bar) { setTimeout(onComplete, durationMs); return; }

    bar.style.width = '0%';
    var startTime = performance.now();
    function step(now) {
      var elapsed = now - startTime;
      bar.style.width = Math.min(100, (elapsed / durationMs) * 100) + '%';
      if (elapsed < durationMs) {
        requestAnimationFrame(step);
      } else {
        bar.style.width = '100%';
        setTimeout(onComplete, 200);
      }
    }
    requestAnimationFrame(step);
  }

  function setFieldError(input, message, errorId) {
    var errorEl = document.getElementById(errorId || input.id + '-error');
    if (message) {
      if (errorEl) { errorEl.textContent = message; errorEl.hidden = false; }
      input.classList.add('is-invalid');
      input.setAttribute('aria-invalid', 'true');
      if (errorEl) input.setAttribute('aria-describedby', errorEl.id);
    } else {
      if (errorEl) { errorEl.textContent = ''; errorEl.hidden = true; }
      input.classList.remove('is-invalid');
      input.removeAttribute('aria-invalid');
      input.removeAttribute('aria-describedby');
    }
  }

  /**
   * Liga um form de autenticação ao fluxo comum: validação local -> fetch JSON -> modal -> redirect.
   * opts.fields: { nomeDoCampoNoDjango: { input, errorId } } na ordem de foco.
   * opts.validate(): retorna true se pode enviar (já marca os erros).
   */
  function bindAuthForm(form, opts) {
    var submitBtn = opts.submitBtn;
    var generalAlert = document.getElementById('generalAlert');
    var originalBtnHtml = submitBtn.innerHTML;

    function showAlert(message) {
      if (!generalAlert) return;
      generalAlert.textContent = message || '';
      generalAlert.hidden = !message;
    }

    function resetButton() {
      submitBtn.disabled = false;
      submitBtn.removeAttribute('aria-busy');
      submitBtn.innerHTML = originalBtnHtml;
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (submitBtn.disabled) return;
      if (!opts.validate()) return;

      if (!window.fetch || !window.AbortController || !window.FormData) {
        form.submit();
        return;
      }

      submitBtn.disabled = true;
      submitBtn.setAttribute('aria-busy', 'true');
      submitBtn.innerHTML = '<span>' + opts.busyLabel + '</span>';
      showAlert('');

      var controller = new AbortController();
      var timer = setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS);

      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        signal: controller.signal
      })
        .then(function (res) {
          var contentType = res.headers.get('Content-Type') || '';
          if (contentType.indexOf('application/json') === -1) {
            if (res.status >= 500) throw new Error('server');
            // Resposta HTML inesperada (ex.: falha de CSRF): deixa o Django renderizar pelo fluxo normal.
            return { fallback: true };
          }
          return res.json();
        })
        .then(function (data) {
          clearTimeout(timer);
          if (data.fallback) {
            form.submit();
            return;
          }
          if (data.ok) {
            // Botão continua desabilitado até o redirect.
            if (opts.onSuccess) opts.onSuccess();
            triggerSuccessModal(function () {
              window.location.replace(safeRedirect(data.redirect));
            }, SUCCESS_MODAL_MS);
            return;
          }
          resetButton();
          if (data.locked) {
            // Trava temporária (FRONTEND_AUTH_LOCKED): aviso em modal, com os botões das comunidades.
            // Só cai no alerta do card se o modal não estiver na página (ex.: trava ligada depois do carregamento).
            if (document.getElementById('authLockedModal')) {
              document.dispatchEvent(new CustomEvent('wl:open', { detail: { id: 'authLockedModal' } }));
            } else {
              showAlert(data.message || opts.fallbackError);
            }
            return;
          }
          var errors = data.errors || {};
          var firstInvalid = null;
          var hasFieldError = false;
          Object.keys(opts.fields).forEach(function (name) {
            var field = opts.fields[name];
            if (errors[name]) {
              setFieldError(field.input, errors[name][0], field.errorId);
              hasFieldError = true;
              if (!firstInvalid) firstInvalid = field.input;
            }
          });
          if (firstInvalid) firstInvalid.focus();
          if (data.message || !hasFieldError) showAlert(data.message || opts.fallbackError);
        })
        .catch(function () {
          clearTimeout(timer);
          resetButton();
          showAlert(opts.networkError);
        });
    });

    return { showAlert: showAlert };
  }

  // ==========================================
  // LOGIN FORM
  // ==========================================
  var loginForm = document.getElementById('loginForm');
  if (loginForm) {
    var mobileInput = document.getElementById('mobile');
    var loginPassInput = document.getElementById('password');

    var login = bindAuthForm(loginForm, {
      submitBtn: document.getElementById('btn-login-submit'),
      busyLabel: 'Verificando...',
      fallbackError: 'Credenciais inválidas.',
      networkError: 'Erro ao conectar ao servidor.',
      fields: { mobile: { input: mobileInput }, password: { input: loginPassInput } },
      validate: function () {
        var valid = true;
        var digits = phoneDigits(mobileInput.value);
        var pass = loginPassInput.value || '';

        if (!digits) {
          setFieldError(mobileInput, 'Informe seu número de telefone.');
          mobileInput.focus();
          valid = false;
        } else if (digits.length < 8) {
          setFieldError(mobileInput, 'Telefone deve ter entre 8 e 11 dígitos.');
          mobileInput.focus();
          valid = false;
        }

        if (!pass) {
          setFieldError(loginPassInput, 'Informe sua senha de acesso.');
          if (valid) loginPassInput.focus();
          valid = false;
        } else if (pass.length < 6) {
          setFieldError(loginPassInput, 'A senha deve ter pelo menos 6 caracteres.');
          if (valid) loginPassInput.focus();
          valid = false;
        }
        return valid;
      }
    });

    if (mobileInput.value) mobileInput.value = maskPhone(mobileInput.value);

    mobileInput.addEventListener('input', function (e) {
      e.target.value = maskPhone(e.target.value);
      setFieldError(mobileInput, '');
      login.showAlert('');
    });

    loginPassInput.addEventListener('input', function () {
      setFieldError(loginPassInput, '');
      login.showAlert('');
    });
  }

  // ==========================================
  // REGISTER FORM
  // ==========================================
  var regForm = document.getElementById('registerForm');
  if (regForm) {
    var fullNameInput = document.getElementById('fullName');
    var phoneInput = document.getElementById('phone');
    var regPassInput = document.getElementById('password');
    var passConfirmInput = document.getElementById('passwordConfirmation');
    var inviteInput = document.getElementById('invitationCode');
    var CONFIRM_ERROR_ID = 'confirmation-error';

    function normalizeInvite(val) {
      return (val || '').replace(/\s+/g, '').toUpperCase();
    }

    var register = bindAuthForm(regForm, {
      submitBtn: document.getElementById('btn-register-submit'),
      busyLabel: 'Criando conta...',
      fallbackError: 'Não foi possível cadastrar.',
      networkError: 'Erro ao processar cadastro no servidor.',
      fields: {
        full_name: { input: fullNameInput },
        phone: { input: phoneInput },
        password: { input: regPassInput },
        password_confirmation: { input: passConfirmInput, errorId: CONFIRM_ERROR_ID },
        invitation_code: { input: inviteInput }
      },
      onSuccess: function () {
        // Convite já usado: não deve reaparecer num próximo cadastro nesta aba.
        try { window.sessionStorage.removeItem(INVITE_STORAGE_KEY); } catch (e) { /* ignora */ }
      },
      validate: function () {
        var valid = true;
        var name = (fullNameInput.value || '').trim();
        var digits = phoneDigits(phoneInput.value);
        var pass = regPassInput.value || '';
        var passConf = passConfirmInput.value || '';
        inviteInput.value = normalizeInvite(inviteInput.value);

        if (!name || name.length < 3) {
          setFieldError(fullNameInput, 'Informe seu nome e sobrenome.');
          fullNameInput.focus();
          valid = false;
        }

        if (digits.length !== 11) {
          setFieldError(phoneInput, 'Telefone deve ter 11 dígitos com DDD.');
          if (valid) phoneInput.focus();
          valid = false;
        }

        if (pass.length < 6) {
          setFieldError(regPassInput, 'A senha deve ter no mínimo 6 caracteres.');
          if (valid) regPassInput.focus();
          valid = false;
        }

        if (!passConf) {
          setFieldError(passConfirmInput, 'Confirme sua senha.', CONFIRM_ERROR_ID);
          if (valid) passConfirmInput.focus();
          valid = false;
        } else if (pass !== passConf) {
          setFieldError(passConfirmInput, 'As senhas não coincidem.', CONFIRM_ERROR_ID);
          if (valid) passConfirmInput.focus();
          valid = false;
        }
        return valid;
      }
    });

    // Preenche o convite a partir da URL/sessionStorage, sem sobrescrever o que o servidor devolveu
    var storedInvite = storageGet(INVITE_STORAGE_KEY);
    if (storedInvite && !inviteInput.value) inviteInput.value = normalizeInvite(storedInvite);

    if (phoneInput.value) phoneInput.value = maskPhone(phoneInput.value);

    function checkPasswordsMatch() {
      var p = regPassInput.value || '';
      var c = passConfirmInput.value || '';
      if (p && c) {
        setFieldError(passConfirmInput, p === c ? '' : 'As senhas não coincidem.', CONFIRM_ERROR_ID);
      }
    }

    fullNameInput.addEventListener('input', function () {
      setFieldError(fullNameInput, '');
      register.showAlert('');
    });

    phoneInput.addEventListener('input', function (e) {
      e.target.value = maskPhone(e.target.value);
      setFieldError(phoneInput, '');
      register.showAlert('');
    });

    regPassInput.addEventListener('input', function () {
      setFieldError(regPassInput, '');
      register.showAlert('');
      checkPasswordsMatch();
    });

    passConfirmInput.addEventListener('input', function () {
      checkPasswordsMatch();
      register.showAlert('');
    });

    inviteInput.addEventListener('input', function (e) {
      e.target.value = normalizeInvite(e.target.value);
      storageSet(INVITE_STORAGE_KEY, e.target.value);
    });
  }
});
