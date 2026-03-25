/**
 * Тендер PRO — Аукционы банкротов + СНГ (CAT)
 */

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsToolbar = document.getElementById("results-toolbar");
const resultsCountEl = document.getElementById("results-count");
const resultsEl = document.getElementById("results");
const pagerEl = document.getElementById("pager");
const pageInput = document.getElementById("page");
const btnPrev = document.getElementById("btn-prev");
const btnNext = document.getElementById("btn-next");
const pageInfo = document.getElementById("page-info");
const btnReset = document.getElementById("btn-reset");
const sortSelect = document.getElementById("sort-select");
const btnExportEl = document.getElementById("btn-export");

/* ── Toast ── */

function showToast(msg) {
  let c = document.querySelector(".toast-container");
  if (!c) { c = document.createElement("div"); c.className = "toast-container"; document.body.appendChild(c); }
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; c.appendChild(t);
  setTimeout(() => { t.classList.add("fade-out"); t.addEventListener("animationend", () => t.remove()); }, 2500);
}

/* ── Tab state ── */

let activeTab = "bankruptcy"; // "bankruptcy" | "cis_cat"

const TAB_CONFIG = {
  bankruptcy: {
    lawType: "auction",
    title: "Аукционы банкротов",
    subtitle: "Имущество банкротов: земля, недвижимость, транспорт, оборудование",
    showPropertyType: true,
    resultLabel: "лотов",
  },
  cis_cat: {
    lawType: "cis_cat",
    title: "СНГ (CAT) — Спецтехника",
    subtitle: "Б/у спецтехника Caterpillar: экскаваторы, бульдозеры, погрузчики по площадкам СНГ",
    showPropertyType: false,
    resultLabel: "объявлений",
  },
};

/* ── Helpers ── */

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

const CURRENCY_SYMBOLS = { RUB: "\u20BD", USD: "$", EUR: "\u20AC", KZT: "\u20B8" };

function fmtMoney(n, currency) {
  if (n == null) return "\u2014";
  try {
    const sym = CURRENCY_SYMBOLS[currency] || currency || "\u20BD";
    return Number(n).toLocaleString("ru-RU") + " " + sym;
  } catch { return String(n); }
}

const PROP_NAMES = {
  real_estate: "Недвижимость",
  land: "Земля",
  vehicles: "Транспорт",
  special_equipment: "Спецтехника",
  equipment: "Оборудование",
  other_assets: "Прочее",
};

function propBadge(tags) {
  if (!tags || !tags.length) return "";
  return tags.map(t => `<span class="badge badge-auction">${esc(PROP_NAMES[t] || t)}</span>`).join("");
}

const PLATFORM_NAMES = {
  lot_online: "РАД",
  mascus: "Mascus",
  machinerytrader: "Machinery Trader",
  catused: "CAT Used",
  avito_cat: "Avito",
  kolesa_kz: "Kolesa.kz",
};

function platformBadge(p) {
  if (!p) return "";
  return `<span class="badge badge-platform">${esc(PLATFORM_NAMES[p] || p)}</span>`;
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

/* ── Tab switching ── */

function switchTab(tab) {
  if (activeTab === tab) return;
  activeTab = tab;

  // Update tab buttons
  document.querySelectorAll(".auction-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });

  // Update header
  const cfg = TAB_CONFIG[tab];
  const titleEl = document.getElementById("page-title");
  const subtitleEl = document.getElementById("page-subtitle");
  if (titleEl) titleEl.textContent = cfg.title;
  if (subtitleEl) subtitleEl.textContent = cfg.subtitle;

  // Show/hide property type filter
  const propField = document.getElementById("property_type");
  if (propField) {
    const fieldWrap = propField.closest(".field");
    if (fieldWrap) fieldWrap.style.display = cfg.showPropertyType ? "" : "none";
  }

  // Reset and search
  pageInput.value = "1";
  runSearch();
}

// Init tabs
document.querySelectorAll(".auction-tab").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

/* ── Autocomplete ── */

function setupAutocomplete(inputEl, dropdownEl, fetchFn) {
  let timer = null, idx = -1, items = [];

  function show(results) {
    items = results; idx = -1;
    if (!results.length) { dropdownEl.classList.add("hidden"); return; }
    dropdownEl.innerHTML = results.map((t, i) => `<div class="autocomplete-item" data-index="${i}">${esc(t)}</div>`).join("");
    dropdownEl.classList.remove("hidden");
  }
  function pick(i) { if (i >= 0 && i < items.length) { inputEl.value = items[i]; dropdownEl.classList.add("hidden"); items = []; idx = -1; } }
  function highlight() { dropdownEl.querySelectorAll(".autocomplete-item").forEach((el, i) => { el.classList.toggle("active", i === idx); if (i === idx) el.scrollIntoView({ block: "nearest" }); }); }

  inputEl.addEventListener("input", () => { clearTimeout(timer); const q = inputEl.value.trim(); if (q.length < 1) { dropdownEl.classList.add("hidden"); return; } timer = setTimeout(async () => { try { show(await fetchFn(q)); } catch { dropdownEl.classList.add("hidden"); } }, 300); });
  inputEl.addEventListener("keydown", e => { if (dropdownEl.classList.contains("hidden")) return; if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); highlight(); } else if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(idx - 1, 0); highlight(); } else if (e.key === "Enter" && idx >= 0) { e.preventDefault(); pick(idx); } else if (e.key === "Escape") { dropdownEl.classList.add("hidden"); } });
  dropdownEl.addEventListener("click", e => { const item = e.target.closest(".autocomplete-item"); if (item) pick(parseInt(item.dataset.index, 10)); });
  document.addEventListener("click", e => { if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) dropdownEl.classList.add("hidden"); });
}

async function fetchRegionSuggestions(q) {
  const res = await fetch(`/api/suggest/regions?q=${encodeURIComponent(q)}`);
  if (!res.ok) return [];
  return (await res.json()).items || [];
}

setupAutocomplete(document.getElementById("region"), document.getElementById("region-dropdown"), fetchRegionSuggestions);

/* ── CSV Export ── */
let _lastItems = [];
function exportCSV(items) {
  if (!items || !items.length) return;
  const BOM = "\uFEFF";
  const header = "Название;Тип;Цена;Валюта;Регион;Площадка;Ссылка\n";
  const rows = items.map(t => [
    (t.title || "").replace(/;/g, ","),
    (t.niche_tags || []).map(n => PROP_NAMES[n] || n).join(","),
    t.nmck || "",
    t.currency || "RUB",
    t.customer_region || "",
    PLATFORM_NAMES[t.source_platform] || t.source_platform || "",
    t.original_url || "",
  ].join(";")).join("\n");
  const filename = activeTab === "cis_cat" ? "cat_equipment.csv" : "auctions.csv";
  const blob = new Blob([BOM + header + rows], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename; a.click();
}
if (btnExportEl) btnExportEl.addEventListener("click", () => { exportCSV(_lastItems); showToast("CSV скачан"); });

/* ── Build query ── */

function buildQueryString() {
  const fd = new FormData(form);
  const params = new URLSearchParams();
  const q = (fd.get("q") || "").trim();
  if (q) params.set("q", q);
  const region = (fd.get("region") || "").trim();
  if (region) params.set("region", region);

  // Property type filter only for bankruptcy tab
  if (activeTab === "bankruptcy") {
    const niche = (fd.get("niche") || "").trim();
    if (niche) params.set("niche", niche);
  }

  const minNmck = fd.get("min_nmck");
  if (minNmck !== "" && minNmck != null) params.set("min_nmck", String(minNmck));
  const maxNmck = fd.get("max_nmck");
  if (maxNmck !== "" && maxNmck != null) params.set("max_nmck", String(maxNmck));

  // law_type зависит от активного таба
  const cfg = TAB_CONFIG[activeTab];
  params.set("law_type", cfg.lawType);
  params.set("sort", sortSelect.value || "created_at");
  params.set("status", "active");
  params.set("page", pageInput.value || "1");
  params.set("per_page", "10");
  return params.toString();
}

/* ── Render ── */

function renderCards(items) {
  resultsEl.innerHTML = "";
  if (!items || items.length === 0) {
    resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon"><svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="m8 11 6 0"/></svg></div><p>Лотов не найдено. Измените ключевые слова или фильтры.</p></div>`;
    return;
  }
  _lastItems = items;
  for (const t of items) {
    const url = t.original_url || "";
    const div = document.createElement("div");
    div.className = "tender-card glass";
    div.innerHTML = `
      <div class="tender-card-header">
        <div class="tender-title">${esc(t.title || "Без названия")}</div>
        <div class="tender-badges">
          ${propBadge(t.niche_tags)}
          ${platformBadge(t.source_platform)}
        </div>
      </div>
      <div class="tender-body">
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          <span class="tender-nmck">${esc(fmtMoney(t.nmck, t.currency))}</span>
        </div>
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
          ${esc(t.customer_region || "\u2014")}
        </div>
      </div>
      ${url ? `<div class="tender-footer"><a class="tender-link" href="${esc(url)}" target="_blank" rel="noopener"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg> Открыть на площадке</a></div>` : ""}
    `;
    resultsEl.appendChild(div);
  }
}

function showSkeleton() {
  resultsEl.innerHTML = "";
  for (let i = 0; i < 3; i++) { const d = document.createElement("div"); d.className = "skeleton skeleton-card"; resultsEl.appendChild(d); }
}

/* ── Search ── */

async function runSearch() {
  const btnSearch = document.getElementById("btn-search");
  if (btnSearch) { btnSearch.disabled = true; btnSearch.classList.add("loading"); }
  setStatus("", false);
  showSkeleton();
  resultsToolbar.classList.add("hidden");
  pagerEl.classList.add("hidden");

  try {
    const res = await fetch(`/api/search/tenders?${buildQueryString()}`, { headers: { Accept: "application/json" } });
    const raw = await res.text();
    if (!res.ok) { let msg = `HTTP ${res.status}`; try { const j = JSON.parse(raw); if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {} throw new Error(msg); }
    const data = JSON.parse(raw);
    const total = data.total ?? 0;
    const page = data.page ?? 1;
    const pages = data.pages ?? 1;

    const cfg = TAB_CONFIG[activeTab];
    resultsCountEl.innerHTML = `Найдено: <span>${total.toLocaleString("ru-RU")}</span> ${cfg.resultLabel}`;
    resultsToolbar.classList.remove("hidden");
    renderCards(data.items || []);

    if (total > 0) {
      pageInfo.textContent = `${page} / ${pages}`;
      btnPrev.disabled = page <= 1;
      btnNext.disabled = page >= pages;
      pagerEl.classList.remove("hidden");
    }
    setStatus("", false);
    if (total > 0) resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    console.error(e);
    setStatus("Ошибка: " + (e.message || "Проверьте сеть."), true);
    resultsEl.innerHTML = "";
    resultsToolbar.classList.add("hidden");
  } finally {
    if (btnSearch) { btnSearch.disabled = false; btnSearch.classList.remove("loading"); }
  }
}

/* ── Events ── */

form.addEventListener("submit", ev => { ev.preventDefault(); pageInput.value = "1"; runSearch(); });
btnReset.addEventListener("click", () => { form.reset(); pageInput.value = "1"; sortSelect.value = "created_at"; setStatus(""); resultsToolbar.classList.add("hidden"); resultsEl.innerHTML = ""; pagerEl.classList.add("hidden"); });
btnPrev.addEventListener("click", () => { pageInput.value = String(Math.max(1, parseInt(pageInput.value, 10) - 1)); runSearch(); });
btnNext.addEventListener("click", () => { pageInput.value = String(parseInt(pageInput.value, 10) + 1); runSearch(); });
sortSelect.addEventListener("change", () => { pageInput.value = "1"; runSearch(); });
