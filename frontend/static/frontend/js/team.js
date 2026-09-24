/**
 * New Tractors — Equipe (/equipe): troca "Minha equipe"/"Metas", filtro de membros por nível e cópia do convite.
 * Tudo no cliente (os dados já vêm no HTML); a aba escolhida vai para a URL (?aba=metas) sem recarregar.
 */
(function () {
  'use strict';

  function root() { return document.querySelector('[data-team]'); }

  function showSection(page, section, updateUrl) {
    page.querySelectorAll('[data-team-tab]').forEach(function (btn) {
      var on = btn.getAttribute('data-team-tab') === section;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', String(on));
    });
    page.querySelectorAll('[data-team-panel]').forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-team-panel') !== section;
    });
    if (updateUrl && window.history.replaceState) {
      var url = new URL(location.href);
      if (section === 'goals') url.searchParams.set('aba', 'metas'); else url.searchParams.delete('aba');
      history.replaceState(history.state, '', url.pathname + url.search);
    }
  }

  function filterMembers(page, level) {
    page.querySelectorAll('[data-member-filter]').forEach(function (btn) {
      var on = btn.getAttribute('data-member-filter') === level;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-pressed', String(on));
      if (on && btn.scrollIntoView) btn.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
    var visible = 0;
    page.querySelectorAll('.tm-member').forEach(function (li) {
      var show = level === 'all' || li.getAttribute('data-level') === level;
      li.hidden = !show;
      if (show) visible++;
    });
    var empty = page.querySelector('[data-member-empty]');
    if (empty) empty.hidden = visible > 0 || !page.querySelector('.tm-member');
  }

  function copyText(text, done) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallback(text)); });
    } else {
      done(fallback(text));
    }
  }

  function fallback(text) {
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

  document.addEventListener('click', function (e) {
    var page = root();
    if (!page || !e.target.closest) return;
    var el;
    if ((el = e.target.closest('[data-team-tab]'))) { showSection(page, el.getAttribute('data-team-tab'), true); return; }
    if ((el = e.target.closest('[data-member-filter]'))) { filterMembers(page, el.getAttribute('data-member-filter')); return; }
    if ((el = e.target.closest('[data-copy-invite]'))) {
      var label = el.querySelector('[data-copy-invite-label]');
      copyText(page.querySelector('[data-invite-url]').textContent.trim(), function (ok) {
        label.textContent = ok ? 'Link copiado!' : 'Copie o link acima';
        el.classList.toggle('is-copied', ok);
        setTimeout(function () { label.textContent = 'Copiar Link'; el.classList.remove('is-copied'); }, 2500);
      });
    }
  });
})();
