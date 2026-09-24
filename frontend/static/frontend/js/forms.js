/**
 * New Tractors — Formulários simples em modal (Alterar senha, Processo seletivo).
 * <form data-action-form action="..." data-success-modal="id">: valida no servidor, mostra erros por campo
 * ([data-field-error="nome"]) e, no sucesso, fecha o modal e abre o modal de sucesso.
 * Também liga os olhos de mostrar/ocultar senha ([data-toggle-password]) dentro da área logada.
 */
(function () {
  'use strict';

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('[data-action-form]')) return;
    e.preventDefault();
    var F = window.NTForm;
    var btn = form.querySelector('[type="submit"]');
    if (btn.disabled) return;
    F.clearErrors(form);
    F.busy(btn, btn.getAttribute('data-busy-label') || 'Enviando...');
    window.NT.postAction(form.getAttribute('action'), new FormData(form)).then(function (data) {
      F.idle(btn);
      if (!data.ok) { F.showServerErrors(form, data); return; }
      form.reset();
      window.NT.closeModal(form.closest('.nt-modal'), false);
      var success = form.getAttribute('data-success-modal');
      if (success) window.NT.openModal(success);
    });
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('#appView [data-toggle-password]');
    if (!btn) return;
    var input = document.getElementById(btn.getAttribute('data-toggle-password'));
    if (!input) return;
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-pressed', String(show));
    btn.setAttribute('aria-label', show ? 'Ocultar senha' : 'Exibir senha');
  });

  // Ao abrir um modal de formulário, limpa erros antigos.
  document.addEventListener('click', function (e) {
    var opener = e.target.closest && e.target.closest('[data-open-modal]');
    if (!opener || !window.NTForm) return;
    var modal = document.getElementById(opener.getAttribute('data-open-modal'));
    var form = modal && modal.querySelector('[data-action-form]');
    if (form) { form.reset(); window.NTForm.clearErrors(form); }
  }, true);
})();
