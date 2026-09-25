/**
 * Protótipo da fila de saque: monta o cartão no navegador, sem backend, para mostrar o desenho da tela.
 *
 * Os números vêm de SCENES (fictícios). A formatação e a animação são as mesmas da tela real — os textos de
 * posição/avanço seguem frontend/providers.py e a animação segue static/frontend/js/withdraw.js — para o
 * protótipo mostrar exatamente o que o app mostra quando recebe estes mesmos números do /acoes/saque/fila.
 */
(function () {
  'use strict';

  var SCENES = [
    { label: 'Fim da fila', amount: 'R$ 250,00', entry: 3001, base: 3001, requested: '25/09 às 14:32' },
    { label: 'Meio da fila', amount: 'R$ 45,25', entry: 7, base: 3, requested: '25/09 às 14:32' },
    { label: 'Primeiro da fila', amount: 'R$ 90,00', entry: 1, base: 1, requested: '25/09 às 14:32' },
    { label: 'Saiu da fila', amount: null, entry: null, base: null, requested: null }
  ];

  var DRIVE_MS = 1500;  // igual à transição da faixa no CSS (1400ms) + folga
  var MOVED_MS = 6000;  // tempo do selo "A fila andou"

  var scene = SCENES[0];
  var moved = 0;        // quantas posições a fila andou desde que a cena foi aberta

  function position() { return scene.base === null ? null : Math.max(1, scene.base - moved); }

  /* --- texto da tela: as mesmas contas de frontend/providers.py (get_withdraw_queue) --- */

  function thousands(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }

  function aheadLabel(position) {
    var ahead = position - 1;
    if (ahead === 0) return 'Ninguém na sua frente. Você é o próximo.';
    if (ahead === 1) return '1 pessoa na sua frente';
    return thousands(ahead) + ' pessoas na sua frente';
  }

  function progress(position) {
    var total = scene.entry - 1;
    return {
      pct: total === 0 ? 100 : Math.floor((scene.entry - position) * 100 / total),
      cleared: total === 0 ? 'Você entrou na fila como o primeiro.'
                           : thousands(scene.entry - position) + ' de ' + thousands(total) +
                             ' saques que estavam na sua frente já saíram da fila.'
    };
  }

  /* --- cartão: a mesma marcação de _withdraw_queue.html --- */

  var TRACTOR = '<svg viewBox="0 0 36 28">' +
      '<rect x="17" y="12" width="15" height="7" rx="2" fill="#2F6F4E"/>' +
      '<rect x="27" y="6" width="2.4" height="7" rx="1" fill="#173F35"/>' +
      '<path d="M8 19V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v13z" fill="#D6A94E"/>' +
      '<rect x="10.5" y="6.5" width="6" height="6" rx="1" fill="#FFFEFA" opacity="0.9"/>' +
      '<g class="wq-wheel" style="transform-origin: 11px 20px"><circle cx="11" cy="20" r="7" fill="#173F35"/>' +
      '<circle cx="11" cy="20" r="2.6" fill="#D6A94E"/><path d="M11 13.6v12.8M4.6 20h12.8" stroke="#2F6F4E" ' +
      'stroke-width="1.4"/></g>' +
      '<g class="wq-wheel" style="transform-origin: 28px 22.5px"><circle cx="28" cy="22.5" r="4.5" fill="#173F35"/>' +
      '<circle cx="28" cy="22.5" r="1.6" fill="#D6A94E"/><path d="M28 18.5v8M24 22.5h8" stroke="#2F6F4E" ' +
      'stroke-width="1.2"/></g></svg>';

  var FLAG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" ' +
      'stroke-linejoin="round"><path d="M5 22V3"/><path d="M5 4h12l-2.5 4L17 12H5"/></svg>';

  function cardHtml() {
    var at = position();
    if (at === null) {
      return '<section class="wd-card"><h2>Nenhum saque na fila</h2>' +
             '<p>Quando não há saque aguardando, o cartão não aparece: é o que a tela mostra depois do pagamento.</p></section>';
    }
    var bar = progress(at);
    return '<section class="wq" data-withdraw-queue data-position="' + at + '">' +
      '<div class="wq-head"><span class="wq-live" aria-hidden="true"></span>' +
      '<div class="wq-head-text"><h2>Seu saque está na fila</h2>' +
      '<p>Pedido em ' + scene.requested + '</p></div>' +
      '<p class="wq-amount">' + scene.amount + '</p></div>' +
      '<div class="wq-spot"><p class="wq-spot-label">Sua posição</p>' +
      '<p class="wq-spot-value"><span class="wq-num" data-queue-position>' + thousands(at) +
      '</span><span class="wq-ord">º</span></p>' +
      '<p class="wq-ahead"><span data-queue-ahead>' + aheadLabel(at) + '</span> ' +
      '<span class="wq-moved" data-queue-moved hidden></span></p></div>' +
      '<div class="wq-track-wrap" data-queue-track><div class="wq-track" role="progressbar" ' +
      'aria-label="Avanço da fila à sua frente" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + bar.pct +
      '" data-queue-progress style="--wq-pct: ' + bar.pct + '">' +
      '<span class="wq-harvested" aria-hidden="true"></span>' +
      '<span class="wq-tractor" aria-hidden="true">' + TRACTOR + '</span>' +
      '<span class="wq-flag" aria-hidden="true">' + FLAG + '</span></div>' +
      '<p class="wq-cleared" data-queue-cleared>' + bar.cleared + '</p></div>' +
      '<p class="wq-foot"><span data-queue-updated>Atualizado agora</span>' +
      '<span class="wq-foot-note">A posição atualiza sozinha e só anda quando um saque à sua frente é pago.</span></p>' +
      '<p class="demo-seal">Demonstração - fila fictícia, sem pagamento real</p>' +
      '<p class="visually-hidden" aria-live="polite" data-queue-announce></p></section>';
  }

  /* --- animação: a mesma de withdraw.js (renderQueue) --- */

  function rollNumber(el, text) {
    el.classList.remove('is-rolling');
    void el.offsetWidth; // reinicia a animação se a fila andar duas vezes seguidas
    el.classList.add('is-rolling');
    setTimeout(function () { el.textContent = text; }, 320);
    setTimeout(function () { el.classList.remove('is-rolling'); }, 720);
  }

  function clockLabel() {
    var d = new Date();
    return 'Atualizado às ' + ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }

  /** Queue andou: número rola, trator avança, selo e anúncio para leitor de tela. */
  function render() {
    var el = document.querySelector('[data-withdraw-queue]');
    var at = position();
    if (!el || at === null) return;
    var previous = parseInt(el.getAttribute('data-position'), 10);
    if (previous === at) return;

    el.setAttribute('data-position', String(at));
    el.querySelector('[data-queue-updated]').textContent = clockLabel();
    var bar = progress(at);
    var track = el.querySelector('[data-queue-progress]');
    el.querySelector('[data-queue-ahead]').textContent = aheadLabel(at);
    el.querySelector('[data-queue-cleared]').textContent = bar.cleared;
    track.style.setProperty('--wq-pct', String(bar.pct));
    track.setAttribute('aria-valuenow', String(bar.pct));
    rollNumber(el.querySelector('[data-queue-position]'), thousands(at));
    track.classList.add('is-driving');
    setTimeout(function () { track.classList.remove('is-driving'); }, DRIVE_MS);

    var howMany = previous - at;
    var chip = el.querySelector('[data-queue-moved]');
    chip.textContent = howMany === 1 ? 'A fila andou 1 posição' : 'A fila andou ' + howMany + ' posições';
    chip.hidden = false;
    clearTimeout(chip._hideTimer);
    chip._hideTimer = setTimeout(function () { chip.hidden = true; }, MOVED_MS);
    el.querySelector('[data-queue-announce]').textContent =
      'Sua posição agora é ' + thousands(at) + '. ' + aheadLabel(at);
  }

  function show() {
    document.querySelector('[data-queue-slot]').innerHTML = cardHtml();
  }

  function markButtons() {
    document.querySelectorAll('[data-scenes] .pt-btn').forEach(function (btn) {
      btn.classList.toggle('is-on', btn._scene === scene);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var bar = document.querySelector('[data-scenes]');

    SCENES.forEach(function (item) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'pt-btn';
      btn.textContent = item.label;
      btn._scene = item;
      btn.addEventListener('click', function () {
        scene = item;
        moved = 0;
        show();
        markButtons();
      });
      bar.appendChild(btn);
    });

    var advance = document.createElement('button');
    advance.type = 'button';
    advance.className = 'pt-btn';
    advance.textContent = 'Simular: a fila andou';
    advance.addEventListener('click', function () {
      if (position() === null || position() <= 1) return;
      moved += 1;
      render();
    });
    bar.appendChild(advance);

    show();
    markButtons();
  });
})();
