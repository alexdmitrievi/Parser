/**
 * Тендер PRO — Аукционы банкротов
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

const PROP_NAMES = {
  real_estate: "\u041d\u0435\u0434\u0432\u0438\u0436\u0438\u043c\u043e\u0441\u0442\u044c",
  land: "\u0417\u0435\u043c\u043b\u044f",
  vehicles: "\u0422\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442",
  special_equipment: "\u0421\u043f\u0435\u0446\u0442\u0435\u0445\u043d\u0438\u043a\u0430",
  equipment: "\u041e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u0435",
  other_assets: "\u041f\u0440\u043e\u0447\u0435\u0435",
};

function propBadge(tags) {
  if (!tags || !tags.length) return "";
  return tags.map(t => `<span class="badge badge-auction">${esc(PROP_NAMES[t] || t)}</span>`).join("");
}

function platformBadge(p) {
  if (!p) return "";
  const names = { lot_online: "\u0420\u0410\u0414" };
  return `<span class="badge badge-platform">${esc(names[p] || p)}</span>`;
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

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
  const header = "\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435;\u0422\u0438\u043f;\u0426\u0435\u043d\u0430;\u0420\u0435\u0433\u0438\u043e\u043d;\u041f\u043b\u043e\u0449\u0430\u0434\u043a\u0430;\u0421\u0441\u044b\u043b\u043a\u0430\n";
  const rows = items.map(t => [(t.title||"").replace(/;/g,","),(t.niche_tags||[]).map(n=>PROP_NAMES[n]||n).join(","),t.nmck||"",t.customer_region||"",t.source_platform||"",t.original_url||""].join(";")).join("\n");
  const blob = new Blob([BOM + header + rows], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "auctions.csv"; a.click();
}
if (btnExportEl) btnExportEl.addEventListener("click", () => exportCSV(_lastItems));

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

  params.set("law_type", "auction"); // КЛЮЧЕВОЕ ОТЛИЧИЕ от app.js
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
    resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon"><svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="m8 11 6 0"/></svg></div><p>\u041b\u043e\u0442\u043e\u0432 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e. \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u0435 \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0441\u043b\u043e\u0432\u0430 \u0438\u043b\u0438 \u0444\u0438\u043b\u044c\u0442\u0440\u044b.</p></div>`;
    return;
  }
  _lastItems = items;
  for (const t of items) {
    const url = t.original_url || "";
    const div = document.createElement("div");
    div.className = "tender-card glass";
    div.innerHTML = `
      <div class="tender-card-header">
        <div class="tender-title">${esc(t.title || "\u0411\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f")}</div>
        <div class="tender-badges">
          ${propBadge(t.niche_tags)}
          ${platformBadge(t.source_platform)}
        </div>
      </div>
      <div class="tender-body">
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          <span class="tender-nmck">${esc(fmtMoney(t.nmck))}</span>
        </div>
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
          ${esc(t.customer_region || "\u2014")}
        </div>
      </div>
      ${url ? `<div class="tender-footer"><a class="tender-link" href="${esc(url)}" target="_blank" rel="noopener"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg> \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0435</a></div>` : ""}
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

    resultsCountEl.innerHTML = `\u041d\u0430\u0439\u0434\u0435\u043d\u043e: <span>${total.toLocaleString("ru-RU")}</span> \u043b\u043e\u0442\u043e\u0432`;
    resultsToolbar.classList.remove("hidden");
    renderCards(data.items || []);

    if (total > 0) {
      pageInfo.textContent = `${page} / ${pages}`;
      btnPrev.disabled = page <= 1;
      btnNext.disabled = page >= pages;
      pagerEl.classList.remove("hidden");
    }
    setStatus("", false);
  } catch (e) {
    console.error(e);
    setStatus("\u041e\u0448\u0438\u0431\u043a\u0430: " + (e.message || "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0441\u0435\u0442\u044c."), true);
    resultsEl.innerHTML = "";
    resultsToolbar.classList.add("hidden");
  }
}

/* ── Events ── */

form.addEventListener("submit", ev => { ev.preventDefault(); pageInput.value = "1"; runSearch(); });
btnReset.addEventListener("click", () => { form.reset(); pageInput.value = "1"; sortSelect.value = "created_at"; setStatus(""); resultsToolbar.classList.add("hidden"); resultsEl.innerHTML = ""; pagerEl.classList.add("hidden"); });
btnPrev.addEventListener("click", () => { pageInput.value = String(Math.max(1, parseInt(pageInput.value, 10) - 1)); runSearch(); });
btnNext.addEventListener("click", () => { pageInput.value = String(parseInt(pageInput.value, 10) + 1); runSearch(); });
sortSelect.addEventListener("change", () => { pageInput.value = "1"; runSearch(); });
