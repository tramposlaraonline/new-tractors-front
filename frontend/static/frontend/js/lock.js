/**
 * New Tractors — Áreas bloqueadas temporariamente (FRONTEND_ONLY_HOME, FRONTEND_BALANCE_RECALC).
 *
 * Toque em [data-locked] (abas, menu lateral, atalhos do Início) abre o aviso #areaLockedModal
 * em vez de navegar ou abrir o modal. [data-locked="idDoModal"] abre outro aviso (ex.: recalcLockedModal). Escuta na fase de captura do window, então roda antes do
 * app.js (SPA), home.js e statement.js, que escutam no document, e impede que eles recebam o clique.
 * O servidor também recusa as telas/ações bloqueadas: isto é só a camada visual.
 */
(function () {
  'use strict';

  window.addEventListener('click', function (e) {
    var el = e.target.closest ? e.target.closest('[data-locked]') : null;
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    var id = el.getAttribute('data-locked') || 'areaLockedModal';
    document.dispatchEvent(new CustomEvent('wl:open', { detail: { id: id } }));
  }, true);
})();
