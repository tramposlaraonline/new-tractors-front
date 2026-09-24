/**
 * New Tractors — Minhas Compras (/record): mantém a contagem "Próximo Crédito" atualizada.
 * O servidor já entrega o texto pronto; aqui só recalculamos a cada 30s a partir do horário (data-next-credit).
 */
(function () {
  'use strict';

  var timer = null;

  function label(target) {
    var seconds = Math.max(0, Math.floor((target - Date.now()) / 1000));
    var h = Math.floor(seconds / 3600);
    var m = Math.floor(seconds % 3600 / 60);
    return h + 'h ' + ('0' + m).slice(-2) + 'min';
  }

  function tick() {
    var cells = document.querySelectorAll('[data-next-credit]');
    if (!cells.length) { clearInterval(timer); timer = null; return; }
    cells.forEach(function (el) {
      var target = Date.parse(el.getAttribute('data-next-credit'));
      if (target) el.textContent = label(target);
    });
  }

  function start() {
    clearInterval(timer);
    timer = null;
    if (!document.querySelector('[data-next-credit]')) return;
    tick();
    timer = setInterval(tick, 30000);
  }

  document.addEventListener('app:page', start);
  start();
})();
