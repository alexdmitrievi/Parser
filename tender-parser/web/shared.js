/**
 * TenderPars — Shared Utilities v2
 * Mobile-first: dynamic bottom nav, scroll-to-top FAB, pull-to-refresh, touch optimizations
 */
'use strict';

/* ── Dynamic Mobile Bottom Navigation (injected on all pages) ── */
(function injectMobileNav() {
  if (document.getElementById('mobile-nav')) return; // already injected

  const path = window.location.pathname;

  const navItems = [
    { href: '/web/',               label: 'Тендеры',     svg: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>' },
    { href: '/web/auctions.html',  label: 'Аукционы',    svg: '<path d="M18 15l-6-3.5L6 15"/><path d="M18 9l-6-3.5L6 9"/><path d="M6 15v4l6 3 6-3v-4"/>' },
    { href: '/web/grants.html',    label: 'Гранты',      svg: '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>' },
    { href: '/web/favorites.html', label: 'Избранное',    svg: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>' },
  ];

  function isActive(href) {
    if (href === '/web/') return path === '/' || path === '/web/' || path.endsWith('/web/index.html');
    return path.endsWith(href) || path.endsWith(href.replace('/web/', '/'));
  }

  const itemsHTML = navItems.map(item => `
    <a href="${item.href}" class="mobile-nav-item${isActive(item.href) ? ' active' : ''}">
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${item.svg}</svg>
      <span>${item.label}</span>
    </a>
  `).join('');

  const nav = document.createElement('nav');
  nav.className = 'mobile-nav';
  nav.id = 'mobile-nav';
  nav.setAttribute('aria-label', 'Мобильная навигация');
  nav.innerHTML = `<div class="mobile-nav-inner">${itemsHTML}</div>`;
  document.body.appendChild(nav);
})();

/* ── Dynamic Scroll-to-Top FAB ── */
(function injectScrollTop() {
  if (document.getElementById('scroll-top')) return;

  const btn = document.createElement('button');
  btn.className = 'scroll-top';
  btn.id = 'scroll-top';
  btn.setAttribute('aria-label', 'Наверх');
  btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6"/></svg>';
  document.body.appendChild(btn);

  let ticking = false;
  function onScroll() {
    if (!ticking) {
      requestAnimationFrame(() => {
        btn.classList.toggle('visible', window.scrollY > 400);
        ticking = false;
      });
      ticking = true;
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
})();

/* ── Toast ── */
function showToast(msg) {
  let c = document.querySelector('.toast-container');
  if (!c) { c = document.createElement('div'); c.className = 'toast-container'; document.body.appendChild(c); }
  const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; c.appendChild(t);
  setTimeout(() => { t.classList.add('fade-out'); t.addEventListener('animationend', () => t.remove()); }, 2500);
}

/* ── Escape HTML ── */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s ?? '');
  return d.innerHTML;
}

/* ── Format money ── */
function fmtMoney(n) {
  if (n == null) return '\u2014';
  try { return Number(n).toLocaleString('ru-RU') + ' \u20BD'; }
  catch { return String(n); }
}

/* ── Format date ── */
function fmtDate(iso) {
  if (!iso) return '\u2014';
  try { return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return String(iso).slice(0, 10); }
}

/* ── Dark mode ── */
(function initTheme() {
  const saved = localStorage.getItem('tenderpro-theme');
  if (saved === 'dark') document.body.classList.add('dark');
  window.toggleTheme = function () {
    const isDark = document.body.classList.toggle('dark');
    localStorage.setItem('tenderpro-theme', isDark ? 'dark' : 'light');
  };
})();

/* ── fetch with timeout ── */
function fetchWithTimeout(url, opts = {}, timeoutMs = 8000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  const merged = { ...opts, signal: opts.signal || ctrl.signal };
  return fetch(url, merged).finally(() => clearTimeout(t));
}

/* ── Status message ── */
function setStatus(el, text, isError) {
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('error', !!isError);
}

/* ── Autocomplete ── */
function setupAutocomplete(inputEl, dropdownEl, fetchFn) {
  let timer = null, idx = -1, items = [], abort = null;

  function show(results) {
    items = results; idx = -1;
    if (!results.length) { dropdownEl.classList.add('hidden'); dropdownEl.innerHTML = ''; return; }
    dropdownEl.innerHTML = results
      .map((t, i) => `<div class="autocomplete-item" data-index="${i}">${esc(t)}</div>`)
      .join('');
    dropdownEl.classList.remove('hidden');
  }

  function pick(i) {
    if (i >= 0 && i < items.length) {
      inputEl.value = items[i];
      dropdownEl.classList.add('hidden');
      items = []; idx = -1;
    }
  }

  function highlight() {
    dropdownEl.querySelectorAll('.autocomplete-item').forEach((el, i) => {
      el.classList.toggle('active', i === idx);
      if (i === idx) el.scrollIntoView({ block: 'nearest' });
    });
  }

  inputEl.addEventListener('input', () => {
    clearTimeout(timer);
    if (abort) abort.abort();
    const q = inputEl.value.trim();
    if (q.length < 1) { dropdownEl.classList.add('hidden'); return; }
    timer = setTimeout(async () => {
      try {
        abort = new AbortController();
        show(await fetchFn(q, abort.signal));
      } catch { dropdownEl.classList.add('hidden'); }
    }, 250);
  });

  inputEl.addEventListener('keydown', e => {
    if (dropdownEl.classList.contains('hidden')) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); highlight(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, 0); highlight(); }
    else if (e.key === 'Enter' && idx >= 0) { e.preventDefault(); pick(idx); }
    else if (e.key === 'Escape') { dropdownEl.classList.add('hidden'); }
  });

  dropdownEl.addEventListener('click', e => {
    const item = e.target.closest('.autocomplete-item');
    if (item) pick(parseInt(item.dataset.index, 10));
  });

  document.addEventListener('click', e => {
    if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) dropdownEl.classList.add('hidden');
  });
}

async function fetchRegionSuggestions(q, signal) {
  const res = await fetchWithTimeout(`/api/suggest/regions?q=${encodeURIComponent(q)}`, signal ? { signal } : {}, 4000);
  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}

/* ── Pull-to-refresh hint ── */
(function initPullToRefresh() {
  if (!('ontouchstart' in window)) return;
  let startY = 0, pulling = false;
  const hint = document.createElement('div');
  hint.style.cssText = 'position:fixed;top:0;left:0;right:0;height:0;background:var(--brand);z-index:9999;transition:height .2s ease;display:flex;align-items:center;justify-content:center;color:#fff;font-size:.75rem;font-weight:600;overflow:hidden';
  document.body.prepend(hint);

  document.addEventListener('touchstart', e => {
    if (window.scrollY > 10) return;
    startY = e.touches[0].clientY;
  }, { passive: true });

  document.addEventListener('touchmove', e => {
    if (window.scrollY > 10) { pulling = false; hint.style.height = '0'; return; }
    const delta = e.touches[0].clientY - startY;
    if (delta > 20 && !pulling) {
      pulling = true;
      hint.style.height = Math.min(delta / 2, 48) + 'px';
      hint.textContent = delta > 60 ? 'Отпустите для обновления' : 'Потяните для обновления';
    }
  }, { passive: true });

  document.addEventListener('touchend', () => {
    if (pulling && hint.style.height && parseInt(hint.style.height) > 44) {
      hint.textContent = 'Обновление...';
      setTimeout(() => { hint.style.height = '0'; window.location.reload(); }, 150);
    } else {
      hint.style.height = '0';
    }
    pulling = false;
  }, { passive: true });
})();

/* ── Service Worker ── */
if ('serviceWorker' in navigator) {
  const hadController = !!navigator.serviceWorker.controller;
  const register = () => {
    navigator.serviceWorker.register('/web/sw.js', { scope: '/' }).then((reg) => {
      reg.addEventListener('updatefound', () => {
        const nw = reg.installing;
        if (!nw) return;
        nw.addEventListener('statechange', () => {
          if (nw.state === 'installed' && navigator.serviceWorker.controller) {
            try { nw.postMessage('skipWaiting'); } catch {}
          }
        });
      });
    }).catch(() => {});
  };
  if ('requestIdleCallback' in window) {
    window.addEventListener('load', () => requestIdleCallback(register, { timeout: 3000 }));
  } else {
    window.addEventListener('load', () => setTimeout(register, 1500));
  }

  let _reloaded = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController || _reloaded) return;
    _reloaded = true;
    window.location.reload();
  });
}

/* ── Touch micro-interaction ── */
(function initTouchFeedback() {
  if (!('ontouchstart' in window)) return;
  document.addEventListener('pointerdown', e => {
    const el = e.target.closest('.btn, .chip, .mobile-nav-item, .auction-tab');
    if (!el) return;
    el.style.transform = 'scale(.96)';
    el.style.transition = 'transform .1s ease';
  }, { passive: true });
  document.addEventListener('pointerup', e => {
    const el = e.target.closest('.btn, .chip, .mobile-nav-item, .auction-tab');
    if (!el) return;
    el.style.transform = '';
    el.style.transition = '';
  }, { passive: true });
  document.addEventListener('pointercancel', () => {
    document.querySelectorAll('.btn:active, .chip:active, .mobile-nav-item:active').forEach(el => {
      el.style.transform = '';
      el.style.transition = '';
    });
  }, { passive: true });
})();
