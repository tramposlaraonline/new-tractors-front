/**
 * New Tractors — Plano VIP (/vip).
 * Arquivo estático na casca: script inline do fragmento NÃO roda no SPA.
 */
(function () {
  'use strict';

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function section() {
    return document.querySelector('[data-vip]');
  }

  function buyVip(btn) {
    var root = section();
    if (!root) return;
    var url = root.getAttribute('data-vip-url');
    if (!url) return;

    var errEl = document.getElementById('vipError');
    var idleLabel = btn.textContent;

    btn.disabled = true;
    btn.textContent = 'Gerando PIX...';
    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = '';
    }

    var headers = {
      'Accept': 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRFToken': csrfToken(),
      'X-Requested-With': 'XMLHttpRequest'
    };

    // Reusa postAction do home.js se existir (mesmo contrato de CSRF/erro).
    var post = (window.NT && window.NT.postAction)
      ? window.NT.postAction(url, new FormData())
      : fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: headers,
          body: ''
        }).then(function (res) {
          return res.json().catch(function () {
            return { ok: false, message: 'Erro ao gerar cobrança.' };
          });
        }).catch(function () {
          return { ok: false, message: 'Erro de conexão. Tente novamente.' };
        });

    post.then(function (data) {
      if (data && data.ok && data.redirect) {
        if (window.NTApp && window.NTApp.navigate) {
          window.NTApp.navigate(data.redirect);
        } else {
          window.location.href = data.redirect;
        }
        return;
      }
      if (errEl) {
        errEl.textContent = (data && data.message) || 'Erro ao gerar cobrança.';
        errEl.hidden = false;
      }
      btn.disabled = false;
      btn.textContent = idleLabel;
    });
  }

  // Delegação: funciona depois que o SPA troca o HTML de /vip.
  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var btn = e.target.closest('[data-vip-buy], #btnBuyVip');
    if (!btn) return;
    if (!section()) return;
    e.preventDefault();
    if (btn.disabled) return;
    buyVip(btn);
  });
})();