/**
 * Поиск тендеров: вызов GET /api/search/tenders (как логика бота).
 */

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const summaryEl = document.getElementById("summary");
const resultsEl = document.getElementById("results");
const pagerEl = document.getElementById("pager");
const pageInput = document.getElementById("page");
const btnPrev = document.getElementById("btn-prev");
const btnNext = document.getElementById("btn-next");
const pageInfo = document.getElementById("page-info");
const btnReset = document.getElementById("btn-reset");

function apiBase() {
  return "";
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

function fmtMoney(n) {
  if (n == null) return "\u2014";
  try {
    return Number(n).toLocaleString("ru-RU") + " \u20BD";
  } catch {
    return String(n);
  }
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function showSummary(total, page, pages, perPage) {
  summaryEl.textContent =
    `Найдено: ${total} \u00b7 стр. ${page}/${pages} \u00b7 по ${perPage} на странице`;
  summaryEl.classList.remove("hidden");
}

function renderCards(items) {
  resultsEl.innerHTML = "";
  if (!items || items.length === 0) {
    const p = document.createElement("p");
    p.className = "card";
    p.textContent =
      "Ничего не найдено. Уточните запрос или проверьте подключение к базе.";
    resultsEl.appendChild(p);
    return;
  }
  for (const t of items) {
    const div = document.createElement("div");
    div.className = "card";

    const url = t.original_url || "";
    const tags = (t.niche_tags || []).map((s) => esc(s)).join(", ") || "\u2014";
    const deadline = t.submission_deadline
      ? new Date(t.submission_deadline).toLocaleDateString("ru-RU")
      : "\u2014";

    div.innerHTML = `
      <div class="card-title">${esc(t.title || "Без названия")}</div>
      <div class="card-row"><span class="card-label">НМЦК:</span> ${esc(fmtMoney(t.nmck))} \u00b7 ${esc(t.law_type || "\u2014")}</div>
      <div class="card-row"><span class="card-label">Заказчик:</span> ${esc(t.customer_name || "\u2014")}</div>
      <div class="card-row"><span class="card-label">Регион:</span> ${esc(t.customer_region || "\u2014")}</div>
      <div class="card-row"><span class="card-label">Дедлайн:</span> ${esc(deadline)}</div>
      <div class="card-row"><span class="card-label">Теги:</span> ${tags}</div>
      ${url ? `<a class="card-link" href="${esc(url)}" target="_blank" rel="noopener">Открыть на площадке</a>` : ""}
    `;
    resultsEl.appendChild(div);
  }
}

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
  params.set("status", "active");
  params.set("page", pageInput.value || "1");
  params.set("per_page", fd.get("per_page") || "5");
  return params.toString();
}

async function runSearch() {
  setStatus("Загрузка\u2026", false);
  resultsEl.innerHTML = "";
  summaryEl.classList.add("hidden");
  pagerEl.classList.add("hidden");

  const qs = buildQueryString();
  const url = `${apiBase()}/api/search/tenders?${qs}`;

  try {
    const res = await fetch(url, { method: "GET", headers: { Accept: "application/json" } });
    const raw = await res.text();
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = JSON.parse(raw);
        if (j.detail) {
          msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        }
      } catch {
        if (raw) msg = raw;
      }
      throw new Error(msg);
    }
    const data = JSON.parse(raw);
    const total = data.total ?? 0;
    const page = data.page ?? 1;
    const pages = data.pages ?? 1;
    const perPage = data.per_page ?? 5;
    const items = data.items || [];

    showSummary(total, page, pages, perPage);
    renderCards(items);
    if (total > 0) {
      pageInfo.textContent = `${page} / ${pages}`;
      btnPrev.disabled = page <= 1;
      btnNext.disabled = page >= pages;
      pagerEl.classList.remove("hidden");
    }
    setStatus("", false);
  } catch (e) {
    console.error(e);
    setStatus("Ошибка загрузки данных. Проверьте сеть и настройки API.", true);
    resultsEl.innerHTML = "";
  }
}

form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  pageInput.value = "1";
  runSearch();
});

btnReset.addEventListener("click", () => {
  form.reset();
  document.getElementById("per_page").value = "5";
  pageInput.value = "1";
  setStatus("");
  summaryEl.classList.add("hidden");
  resultsEl.innerHTML = "";
  pagerEl.classList.add("hidden");
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
