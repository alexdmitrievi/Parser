/**
 * Тендер PRO — Поиск тендеров
 * Autocomplete, advanced filters, dynamic niches, sorting
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
const advancedToggle = document.getElementById("advanced-toggle");
const advancedBody = document.getElementById("advanced-body");
const btnExportEl = document.getElementById("btn-export");

/* ── Toast ── */

function showToast(msg) {
  let c = document.querySelector(".toast-container");
  if (!c) { c = document.createElement("div"); c.className = "toast-container"; document.body.appendChild(c); }
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; c.appendChild(t);
  setTimeout(() => { t.classList.add("fade-out"); t.addEventListener("animationend", () => t.remove()); }, 2500);
}

/* ── Helpers ── */

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

function fmtMoney(n) {
  if (n == null) return "\u2014";
  try { return Number(n).toLocaleString("ru-RU") + " \u20BD"; }
  catch { return String(n); }
}

function fmtDate(iso) {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
  } catch { return String(iso).slice(0, 10); }
}

function lawBadge(law) {
  if (!law) return "";
  const map = {
    "44-fz": { cls: "badge-44fz", label: "44-\u0424\u0417" },
    "223-fz": { cls: "badge-223fz", label: "223-\u0424\u0417" },
    "commercial": { cls: "badge-commercial", label: "\u041a\u043e\u043c\u043c." },
  };
  const m = map[law];
  if (!m) return `<span class="badge">${esc(law)}</span>`;
  return `<span class="badge ${m.cls}">${m.label}</span>`;
}

function nicheBadges(tags) {
  if (!tags || !tags.length) return "";
  const map = {
    furniture: "\u041c\u0435\u0431\u0435\u043b\u044c",
    construction: "\u0421\u0442\u0440\u043e\u0439\u043a\u0430",
    it: "IT",
    security: "\u041e\u0445\u0440\u0430\u043d\u0430",
    cleaning: "\u041a\u043b\u0438\u043d\u0438\u043d\u0433",
    food: "\u041f\u0438\u0442\u0430\u043d\u0438\u0435",
    medical: "\u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0430",
    transport: "\u0422\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442",
  };
  return tags.map(t => `<span class="badge badge-niche">${esc(map[t] || t)}</span>`).join("");
}

function platformBadge(p) {
  if (!p) return "";
  const names = {
    eis: "\u0415\u0418\u0421", roseltorg: "\u0420\u043e\u0441\u044d\u043b\u0442\u043e\u0440\u0433", sberbank_ast: "\u0421\u0431\u0435\u0440\u0431\u0430\u043d\u043a-\u0410\u0421\u0422",
    rts_tender: "\u0420\u0422\u0421", b2b_center: "B2B-Center", tektorg: "\u0422\u042d\u041a-\u0422\u043e\u0440\u0433",
    tenderguru: "TenderGuru", fabrikant: "Fabrikant", tenderpro: "TenderPro",
    etpgpb: "\u042d\u0422\u041f \u0413\u041f\u0411", etp_ets: "\u042d\u0422\u041f \u0415\u0422\u0421",
    rostender: "\u0420\u043e\u0441\u0442\u0435\u043d\u0434\u0435\u0440",
  };
  return `<span class="badge badge-platform">${esc(names[p] || p)}</span>`;
}

function methodBadge(m) {
  if (!m) return "";
  const names = {
    AE: "\u0410\u0443\u043a\u0446\u0438\u043e\u043d", OK: "\u041a\u043e\u043d\u043a\u0443\u0440\u0441", ZK: "\u0417\u0430\u043f\u0440\u043e\u0441 \u043a\u043e\u0442\u0438\u0440\u043e\u0432\u043e\u043a",
    ZP: "\u0417\u0430\u043f\u0440\u043e\u0441 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439", EP: "\u0415\u0434. \u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a", OA: "\u041e\u0442\u043a\u0440. \u0430\u0443\u043a\u0446\u0438\u043e\u043d",
  };
  return `<span class="badge badge-method">${esc(names[m] || m)}</span>`;
}

function statusBadge(status, deadline) {
  if (!status) return "";
  // Если дедлайн истёк — показываем "Завершён" вместо "Приём заявок"
  let effectiveStatus = status;
  if (status === "active" && deadline) {
    try {
      if (new Date(deadline) < new Date()) effectiveStatus = "expired";
    } catch {}
  }
  const map = {
    active: { cls: "badge-status-active", label: "\u041f\u0440\u0438\u0451\u043c \u0437\u0430\u044f\u0432\u043e\u043a" },
    expired: { cls: "badge-status-expired", label: "\u0417\u0430\u0432\u0435\u0440\u0448\u0451\u043d" },
    cancelled: { cls: "badge-status-cancelled", label: "\u041e\u0442\u043c\u0435\u043d\u0451\u043d" },
    completed: { cls: "badge-status-completed", label: "\u0418\u0442\u043e\u0433\u0438 \u043f\u043e\u0434\u0432\u0435\u0434\u0435\u043d\u044b" },
  };
  const m = map[effectiveStatus];
  if (!m) return `<span class="badge">${esc(effectiveStatus)}</span>`;
  return `<span class="badge ${m.cls}">${m.label}</span>`;
}

function deadlineInfo(dl) {
  if (!dl) return { text: "\u2014", cls: "" };
  try {
    const d = new Date(dl);
    const now = new Date();
    const diff = (d - now) / (1000 * 60 * 60 * 24);
    const text = d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
    if (diff < 0) return { text: text + " (\u0438\u0441\u0442\u0451\u043a)", cls: "deadline-danger" };
    if (diff < 3) return { text, cls: "deadline-danger" };
    if (diff < 7) return { text, cls: "deadline-warning" };
    return { text, cls: "" };
  } catch { return { text: String(dl).slice(0, 10), cls: "" }; }
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

/* ── Favorites (localStorage) ── */

function getFavorites() {
  try { return JSON.parse(localStorage.getItem("podryad_favorites") || "[]"); }
  catch { return []; }
}

function saveFavorites(list) {
  try {
    localStorage.setItem("podryad_favorites", JSON.stringify(list));
  } catch (e) {
    /* H5: private mode / storage blocked on some WebViews */
  }
}

function isFavorite(id) {
  return getFavorites().some(f => f.id === id);
}

function toggleFavorite(tender) {
  let favs = getFavorites();
  const idx = favs.findIndex(f => f.id === tender.id);
  if (idx >= 0) {
    favs.splice(idx, 1);
  } else {
    favs.unshift(tender);
  }
  saveFavorites(favs);
}

/* ── CSV Export ── */

let _lastItems = [];

function exportCSV(items) {
  if (!items || !items.length) return;
  const BOM = "\uFEFF";
  const header = "Название;Заказчик;Регион;НМЦК;Тип закона;Площадка;Дедлайн;Ссылка\n";
  const rows = items.map(t => [
    (t.title || "").replace(/;/g, ","),
    (t.customer_name || "").replace(/;/g, ","),
    (t.customer_region || "").replace(/;/g, ","),
    t.nmck || "",
    t.law_type || "",
    t.source_platform || "",
    (t.submission_deadline || "").slice(0, 10),
    t.original_url || "",
  ].join(";")).join("\n");
  const blob = new Blob([BOM + header + rows], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tenders_podryad_pro.csv";
  a.click();
  URL.revokeObjectURL(url);
}

if (btnExportEl) {
  btnExportEl.addEventListener("click", () => { exportCSV(_lastItems); showToast("CSV скачан"); });
}

/* ── Autocomplete ── */

function setupAutocomplete(inputEl, dropdownEl, fetchFn) {
  let timer = null;
  let idx = -1;
  let items = [];

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
    const q = inputEl.value.trim();
    if (q.length < 1) { dropdownEl.classList.add("hidden"); return; }
    timer = setTimeout(async () => {
      try { show(await fetchFn(q)); } catch { dropdownEl.classList.add("hidden"); }
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

/* ── Region autocomplete ── */

async function fetchRegionSuggestions(q) {
  const res = await fetch(`/api/suggest/regions?q=${encodeURIComponent(q)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}

setupAutocomplete(
  document.getElementById("region"),
  document.getElementById("region-dropdown"),
  fetchRegionSuggestions
);

/* ── Dynamic niches ── */

const NICHE_NAMES = {
  furniture: "\u041c\u0435\u0431\u0435\u043b\u044c",
  construction: "\u0421\u0442\u0440\u043e\u0439\u043a\u0430 / \u0440\u0435\u043c\u043e\u043d\u0442",
  it: "IT-\u0443\u0441\u043b\u0443\u0433\u0438",
  security: "\u041e\u0445\u0440\u0430\u043d\u0430",
  cleaning: "\u041a\u043b\u0438\u043d\u0438\u043d\u0433",
  food: "\u041f\u0440\u043e\u0434\u0443\u043a\u0442\u044b \u043f\u0438\u0442\u0430\u043d\u0438\u044f",
  medical: "\u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0430",
  transport: "\u0422\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442",
};

async function loadNiches() {
  try {
    const res = await fetch("/api/niches", { headers: { Accept: "application/json" } });
    if (!res.ok) return;
    const data = await res.json();
    const sel = document.getElementById("niche");
    const niches = data.niches || [];
    for (const n of niches) {
      const opt = document.createElement("option");
      opt.value = n.name;
      opt.textContent = `${NICHE_NAMES[n.name] || n.name} (${n.count})`;
      sel.appendChild(opt);
    }
  } catch { /* silent */ }
}

/* ── Dynamic platforms & methods ── */

async function loadPlatforms() {
  try {
    const res = await fetch("/api/suggest/platforms");
    if (!res.ok) return;
    const data = await res.json();
    const sel = document.getElementById("source_platform");
    for (const p of data.items || []) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      sel.appendChild(opt);
    }
  } catch { /* silent */ }
}

async function loadMethods() {
  try {
    const res = await fetch("/api/suggest/purchase-methods");
    if (!res.ok) return;
    const data = await res.json();
    const sel = document.getElementById("purchase_method");
    for (const m of data.items || []) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.name;
      sel.appendChild(opt);
    }
  } catch { /* silent */ }
}

/* ── Advanced filters toggle ── */

if (advancedToggle && advancedBody) {
  advancedToggle.addEventListener("click", () => {
    advancedToggle.classList.toggle("open");
    advancedBody.classList.toggle("open");
  });
}

/* ── Sort ── */

sortSelect.addEventListener("change", () => {
  pageInput.value = "1";
  runSearch();
});

/* ── Build query ── */

function buildQueryString() {
  const fd = new FormData(form);
  const params = new URLSearchParams();

  const q = (fd.get("q") || "").trim();
  if (q) params.set("q", q);

  const region = (fd.get("region") || "").trim();
  if (region) params.set("region", region);

  const niche = (fd.get("niche") || "").trim();
  if (niche) params.set("niche", niche);

  const minNmck = fd.get("min_nmck");
  if (minNmck !== "" && minNmck != null) params.set("min_nmck", String(minNmck));

  const maxNmck = fd.get("max_nmck");
  if (maxNmck !== "" && maxNmck != null) params.set("max_nmck", String(maxNmck));

  const lawType = (fd.get("law_type") || "").trim();
  if (lawType) params.set("law_type", lawType);

  const purchaseMethod = (fd.get("purchase_method") || "").trim();
  if (purchaseMethod) params.set("purchase_method", purchaseMethod);

  const dateFrom = (fd.get("date_from") || "").trim();
  if (dateFrom) params.set("date_from", dateFrom);

  const dateTo = (fd.get("date_to") || "").trim();
  if (dateTo) params.set("date_to", dateTo);

  const sourcePlatform = (fd.get("source_platform") || "").trim();
  if (sourcePlatform) params.set("source_platform", sourcePlatform);

  params.set("sort", sortSelect.value || "created_at");
  params.set("status", "active");
  params.set("page", pageInput.value || "1");
  params.set("per_page", fd.get("per_page") || "10");
  return params.toString();
}

/* ── Render cards ── */

function renderCards(items) {
  resultsEl.innerHTML = "";
  if (!items || items.length === 0) {
    resultsEl.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="m8 11 6 0"/></svg>
        </div>
        <p>\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0441\u043b\u043e\u0432\u0430 \u0438\u043b\u0438 \u0440\u0430\u0441\u0448\u0438\u0440\u044c\u0442\u0435 \u0444\u0438\u043b\u044c\u0442\u0440\u044b.</p>
      </div>`;
    return;
  }

  _lastItems = items;

  for (const t of items) {
    const url = t.original_url || "";
    const dl = deadlineInfo(t.submission_deadline);
    const faved = isFavorite(t.id);
    const div = document.createElement("div");
    div.className = "tender-card glass";
    div.innerHTML = `
      <div class="tender-card-header">
        <div class="tender-title">${esc(t.title || "\u0411\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f")}</div>
        <div class="tender-header-actions">
          <button type="button" class="btn-fav ${faved ? "active" : ""}" data-id="${esc(t.id)}" title="${faved ? "Убрать из избранного" : "В избранное"}">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="${faved ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
          </button>
          <div class="tender-badges">
            ${statusBadge(t.status, t.submission_deadline)}
            ${lawBadge(t.law_type)}
            ${platformBadge(t.source_platform)}
            ${methodBadge(t.purchase_method)}
            ${nicheBadges(t.niche_tags)}
          </div>
        </div>
      </div>
      <div class="tender-body">
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          <span class="tender-nmck">${esc(fmtMoney(t.nmck))}</span>
        </div>
        <div class="tender-field ${dl.cls}">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
          ${esc(dl.text)}
        </div>
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18"/><path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16"/></svg>
          ${esc(t.customer_name || "\u2014")}
        </div>
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
          ${esc(t.customer_region || "\u2014")}
        </div>
      </div>
      ${url ? `
      <div class="tender-footer">
        <a class="tender-link" href="${esc(url)}" target="_blank" rel="noopener">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
          \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0435
        </a>
        <div class="tender-meta">
          ${t.publish_date ? `<span>\u041e\u043f\u0443\u0431\u043b.: ${esc(fmtDate(t.publish_date))}</span>` : ""}
        </div>
      </div>` : ""}
    `;
    resultsEl.appendChild(div);
  }

  // Wire favorite buttons
  resultsEl.querySelectorAll(".btn-fav").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const tender = items.find(t => t.id === id);
      if (tender) toggleFavorite(tender);
      const active = isFavorite(id);
      btn.classList.toggle("active", active);
      btn.querySelector("svg").setAttribute("fill", active ? "currentColor" : "none");
    });
  });
}

/* ── Skeleton loading ── */

function showSkeleton() {
  resultsEl.innerHTML = "";
  for (let i = 0; i < 3; i++) {
    const div = document.createElement("div");
    div.className = "skeleton skeleton-card";
    resultsEl.appendChild(div);
  }
}

/* ── Search ── */

async function runSearch() {
  const btnSearch = document.getElementById("btn-search");
  if (btnSearch) { btnSearch.disabled = true; btnSearch.classList.add("loading"); }
  setStatus("", false);
  showSkeleton();
  resultsToolbar.classList.add("hidden");
  pagerEl.classList.add("hidden");

  const qs = buildQueryString();
  const url = `/api/search/tenders?${qs}`;

  try {
    const res = await fetch(url, { method: "GET", headers: { Accept: "application/json" } });
    const raw = await res.text();
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = JSON.parse(raw); if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); }
      catch { if (raw) msg = raw; }
      throw new Error(msg);
    }
    const data = JSON.parse(raw);
    const total = data.total ?? 0;
    const page = data.page ?? 1;
    const pages = data.pages ?? 1;

    // Results toolbar
    resultsCountEl.innerHTML = `\u041d\u0430\u0439\u0434\u0435\u043d\u043e: <span>${total.toLocaleString("ru-RU")}</span> \u0442\u0435\u043d\u0434\u0435\u0440\u043e\u0432`;
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
    setStatus("\u041e\u0448\u0438\u0431\u043a\u0430: " + (e.message || "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0441\u0435\u0442\u044c."), true);
    resultsEl.innerHTML = "";
    resultsToolbar.classList.add("hidden");
  } finally {
    const btnSearch = document.getElementById("btn-search");
    if (btnSearch) { btnSearch.disabled = false; btnSearch.classList.remove("loading"); }
  }
}

/* ── Events ── */

form.addEventListener("submit", ev => {
  ev.preventDefault();
  pageInput.value = "1";
  runSearch();
});

btnReset.addEventListener("click", () => {
  form.reset();
  document.getElementById("per_page").value = "10";
  pageInput.value = "1";
  sortSelect.value = "created_at";
  setStatus("");
  resultsToolbar.classList.add("hidden");
  resultsEl.innerHTML = "";
  pagerEl.classList.add("hidden");
  // Close advanced if open
  if (advancedToggle) advancedToggle.classList.remove("open");
  if (advancedBody) advancedBody.classList.remove("open");
});

btnPrev.addEventListener("click", () => {
  const p = Math.max(1, parseInt(pageInput.value, 10) - 1);
  pageInput.value = String(p);
  runSearch();
});

btnNext.addEventListener("click", () => {
  const p = parseInt(pageInput.value, 10) + 1;
  pageInput.value = String(p);
  runSearch();
});

/* ── Init: load dynamic data ── */
loadNiches();
loadPlatforms();
loadMethods();

/* ── Hero Stats counter ── */
(async function loadHeroStats() {
  const el = document.getElementById("hero-stats");
  if (!el) return;
  try {
    const res = await fetch("/api/stats", { headers: { Accept: "application/json" } });
    if (!res.ok) return;
    const data = await res.json();
    const total = data.total ?? 0;
    const regions = Object.keys(data.by_region || {}).length;
    if (total > 0) {
      el.innerHTML = `<span>${total.toLocaleString("ru-RU")}</span> \u0442\u0435\u043d\u0434\u0435\u0440\u043e\u0432 \u0438\u0437 <span>6</span> \u043f\u043b\u043e\u0449\u0430\u0434\u043e\u043a \u0432 <span>${regions}</span> \u0440\u0435\u0433\u0438\u043e\u043d\u0430\u0445`;
    }
  } catch { /* silent */ }
})();
