/**
 * Тендер PRO — Избранные тендеры
 * Хранение в localStorage
 */

const favResults = document.getElementById("fav-results");
const favToolbar = document.getElementById("fav-toolbar");
const favCount = document.getElementById("fav-count");
const btnExport = document.getElementById("btn-export-fav");
const btnClear = document.getElementById("btn-clear-fav");

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

function getFavorites() {
  try { return JSON.parse(localStorage.getItem("podryad_favorites") || "[]"); }
  catch { return []; }
}

function saveFavorites(list) {
  try {
    localStorage.setItem("podryad_favorites", JSON.stringify(list));
  } catch (e) {
    /* storage blocked (private mode / WebView) */
  }
}

function removeFavorite(id) {
  const favs = getFavorites().filter(f => f.id !== id);
  saveFavorites(favs);
  render();
}

function exportCSV(items) {
  const BOM = "\uFEFF";
  const header = "Название;Заказчик;Регион;НМЦК;Тип закона;Площадка;Дедлайн;Ссылка\n";
  const rows = items.map(t => {
    return [
      (t.title || "").replace(/;/g, ","),
      (t.customer_name || "").replace(/;/g, ","),
      (t.customer_region || "").replace(/;/g, ","),
      t.nmck || "",
      t.law_type || "",
      t.source_platform || "",
      (t.submission_deadline || "").slice(0, 10),
      t.original_url || "",
    ].join(";");
  }).join("\n");

  const blob = new Blob([BOM + header + rows], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "favorites_podryad_pro.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function render() {
  const favs = getFavorites();

  if (!favs.length) {
    favToolbar.classList.add("hidden");
    favResults.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
        </div>
        <p>Нет сохранённых тендеров. Найдите интересные закупки в <a href="/web/">поиске</a> и нажмите на сердечко.</p>
      </div>`;
    return;
  }

  favToolbar.classList.remove("hidden");
  favCount.innerHTML = `Сохранено: <span>${favs.length}</span>`;

  favResults.innerHTML = "";
  for (const t of favs) {
    const url = t.original_url || "";
    const div = document.createElement("div");
    div.className = "tender-card glass";
    div.innerHTML = `
      <div class="tender-card-header">
        <div class="tender-title">${esc(t.title || "Без названия")}</div>
        <button type="button" class="btn-fav active" data-id="${esc(t.id)}" title="Убрать из избранного">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
        </button>
      </div>
      <div class="tender-body">
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          <span class="tender-nmck">${esc(fmtMoney(t.nmck))}</span>
        </div>
        <div class="tender-field">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18"/><path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16"/></svg>
          ${esc(t.customer_name || "\u2014")}
        </div>
      </div>
      ${url ? `<div class="tender-footer"><a class="tender-link" href="${esc(url)}" target="_blank" rel="noopener">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
        Открыть на площадке</a></div>` : ""}
    `;
    favResults.appendChild(div);
  }

  favResults.querySelectorAll(".btn-fav").forEach(btn => {
    btn.addEventListener("click", () => removeFavorite(btn.dataset.id));
  });
}

if (btnExport) {
  btnExport.addEventListener("click", () => exportCSV(getFavorites()));
}
if (btnClear) {
  btnClear.addEventListener("click", () => {
    if (confirm("Удалить все сохранённые тендеры?")) {
      saveFavorites([]);
      render();
    }
  });
}

render();
