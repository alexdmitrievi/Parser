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

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function showSummary(total, page, pages, perPage) {
  summaryEl.textContent =
    `Найдено: ${total} · стр. ${page}/${pages} · по ${perPage} на странице`;
  summaryEl.classList.remove("hidden");
}

function renderCards(cards) {
  resultsEl.innerHTML = "";
  if (!cards || cards.length === 0) {
    const p = document.createElement("p");
    p.className = "card";
    p.textContent =
      "Ничего не найдено. Уточните запрос или проверьте подключение к базе.";
    resultsEl.appendChild(p);
    return;
  }
  for (const text of cards) {
    const div = document.createElement("div");
    div.className = "card";
    div.textContent = text;
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
  setStatus("Загрузка…", false);
  resultsEl.innerHTML = "";
  summaryEl.classList.add("hidden");
  pagerEl.classList.add("hidden");

  const qs = buildQueryString();
  const url = `${apiBase()}/api/search/tenders?${qs}`;

  try {
    const res = await fetch(url, { method: "GET", headers: { Accept: "application/json" } });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `HTTP ${res.status}`);
    }
    const data = await res.json();
    const total = data.total ?? 0;
    const page = data.page ?? 1;
    const pages = data.pages ?? 1;
    const perPage = data.per_page ?? 5;
    const cards = data.cards || [];

    showSummary(total, page, pages, perPage);
    renderCards(cards);
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
