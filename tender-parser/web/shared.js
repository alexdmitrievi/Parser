/**
 * Shared helpers — подключить на всех страницах:
 *   <script src="/web/shared.js"></script>
 */

/* ── Toast notification ── */
function showToast(msg) {
  let c = document.querySelector(".toast-container");
  if (!c) { c = document.createElement("div"); c.className = "toast-container"; document.body.appendChild(c); }
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; c.appendChild(t);
  setTimeout(() => { t.classList.add("fade-out"); t.addEventListener("animationend", () => t.remove()); }, 2500);
}

/* ── Escape HTML ── */
function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

/* ── Format money (RUB) ── */
function fmtMoney(n) {
  if (n == null) return "\u2014";
  try { return Number(n).toLocaleString("ru-RU") + " \u20BD"; }
  catch { return String(n); }
}

/* ── Dark mode toggle ── */
(function initTheme() {
  const saved = localStorage.getItem("tenderpro-theme");
  if (saved === "dark") {
    document.body.classList.add("dark");
  }
  window.toggleTheme = function () {
    const isDark = document.body.classList.toggle("dark");
    localStorage.setItem("tenderpro-theme", isDark ? "dark" : "light");
  };
})();

/* ── Formatters ── */
function fmtDate(iso) {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
  } catch { return String(iso).slice(0, 10); }
}

/* ── Autocomplete (shared across all pages) ── */
function setupAutocomplete(inputEl, dropdownEl, fetchFn) {
  let timer = null;
  let idx = -1;
  let items = [];
  let abort = null;

  function show(results) {
    items = results;
    idx = -1;
    if (!results.length) { dropdownEl.classList.add("hidden"); dropdownEl.innerHTML = ""; return; }
    dropdownEl.innerHTML = results
      .map((t, i) => `<div class="autocomplete-item" data-index="${i}">${esc(t)}</div>`)
      .join("");
    dropdownEl.classList.remove("hidden");
  }

  function pick(i) {
    if (i >= 0 && i < items.length) {
      inputEl.value = items[i];
      dropdownEl.classList.add("hidden");
      items = [];
      idx = -1;
    }
  }

  function highlight() {
    dropdownEl.querySelectorAll(".autocomplete-item").forEach((el, i) => {
      el.classList.toggle("active", i === idx);
      if (i === idx) el.scrollIntoView({ block: "nearest" });
    });
  }

  inputEl.addEventListener("input", () => {
    clearTimeout(timer);
    if (abort) abort.abort();
    const q = inputEl.value.trim();
    if (q.length < 1) { dropdownEl.classList.add("hidden"); return; }
    timer = setTimeout(async () => {
      try {
        abort = new AbortController();
        const signal = abort.signal;
        show(await fetchFn(q, signal));
      } catch { dropdownEl.classList.add("hidden"); }
    }, 300);
  });

  inputEl.addEventListener("keydown", e => {
    if (dropdownEl.classList.contains("hidden")) return;
    if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); highlight(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(idx - 1, 0); highlight(); }
    else if (e.key === "Enter" && idx >= 0) { e.preventDefault(); pick(idx); }
    else if (e.key === "Escape") { dropdownEl.classList.add("hidden"); }
  });

  dropdownEl.addEventListener("click", e => {
    const item = e.target.closest(".autocomplete-item");
    if (item) pick(parseInt(item.dataset.index, 10));
  });

  document.addEventListener("click", e => {
    if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) dropdownEl.classList.add("hidden");
  });
}

async function fetchRegionSuggestions(q, signal) {
  const res = await fetchWithTimeout(`/api/suggest/regions?q=${encodeURIComponent(q)}`, signal ? { signal } : {}, 4000);
  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}

/* ── Status message ── */
function setStatus(el, text, isError) {
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("error", !!isError);
}
/* ── fetch с таймаутом и graceful fallback ── */
function fetchWithTimeout(url, opts = {}, timeoutMs = 8000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  const merged = { ...opts, signal: opts.signal || ctrl.signal };
  return fetch(url, merged).finally(() => clearTimeout(t));
}

/* ── Регистрация SW (отложенная, чтобы не блокировать первую отрисовку) ── */
if ("serviceWorker" in navigator) {
  // Запоминаем, был ли контроллер до регистрации.
  // Если был — значит, это обновление, и нужно перезагрузиться при смене SW,
  // чтобы взять свежий HTML/CSS/JS. Если не было — это первая установка, reload не нужен.
  const hadController = !!navigator.serviceWorker.controller;
  const register = () => {
    navigator.serviceWorker.register("/web/sw.js", { scope: "/" }).then((reg) => {
      reg.addEventListener("updatefound", () => {
        const nw = reg.installing;
        if (!nw) return;
        nw.addEventListener("statechange", () => {
          if (nw.state === "installed" && navigator.serviceWorker.controller) {
            try { nw.postMessage("skipWaiting"); } catch {}
          }
        });
      });
    }).catch(() => {});
  };
  if ("requestIdleCallback" in window) {
    window.addEventListener("load", () => requestIdleCallback(register, { timeout: 3000 }));
  } else {
    window.addEventListener("load", () => setTimeout(register, 1500));
  }

  let _reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController || _reloaded) return;
    _reloaded = true;
    window.location.reload();
  });
}
