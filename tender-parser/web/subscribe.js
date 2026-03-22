/**
 * Подряд PRO — Подписки на тендеры
 */

const form = document.getElementById("sub-form");
const emailInput = document.getElementById("email");
const globalStatus = document.getElementById("global-status");
const btnList = document.getElementById("btn-list");
const listArea = document.getElementById("list-area");
const listEmpty = document.getElementById("list-empty");

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

function setStatus(text, kind = "neutral") {
  globalStatus.textContent = text;
  globalStatus.className = "status-msg";
  if (kind === "error") globalStatus.classList.add("error");
  if (kind === "ok") globalStatus.classList.add("ok");
}

function formatArr(a) {
  if (!a || !a.length) return "\u2014";
  return a.map((v) => esc(v)).join(", ");
}

function renderList(items) {
  listArea.innerHTML = "";
  if (!items || items.length === 0) {
    listArea.classList.add("hidden");
    listEmpty.classList.remove("hidden");
    return;
  }
  listEmpty.classList.add("hidden");
  listArea.classList.remove("hidden");

  for (const row of items) {
    const id = row.id;
    const card = document.createElement("article");
    card.className = "sub-card glass";
    card.innerHTML = `
      <div class="sub-head">
        <strong>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px; opacity: 0.6"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
          Подписка
        </strong>
        <button type="button" class="btn btn-danger btn-del" data-id="${esc(id)}">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
          Удалить
        </button>
      </div>
      <dl>
        <dt>Ключевые слова</dt><dd>${formatArr(row.keywords)}</dd>
        <dt>Регионы</dt><dd>${formatArr(row.regions)}</dd>
        <dt>Ниши</dt><dd>${formatArr(row.niche_tags)}</dd>
        <dt>НМЦК</dt><dd>${esc(row.min_nmck ?? "\u2014")} \u2014 ${esc(row.max_nmck ?? "\u2014")}</dd>
        <dt>Типы законов</dt><dd>${formatArr(row.law_types)}</dd>
        <dt>Создана</dt><dd>${esc(row.created_at ? new Date(row.created_at).toLocaleDateString("ru-RU") : "\u2014")}</dd>
      </dl>
    `;
    listArea.appendChild(card);
  }

  listArea.querySelectorAll(".btn-del").forEach((btn) => {
    btn.addEventListener("click", () => deleteOne(btn.getAttribute("data-id")));
  });
}

async function deleteOne(subscriptionId) {
  const email = (emailInput.value || "").trim();
  if (!email) {
    setStatus("\u0423\u043a\u0430\u0436\u0438\u0442\u0435 email.", "error");
    return;
  }
  if (!confirm("\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443? \u042d\u0442\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u043d\u0435\u043b\u044c\u0437\u044f \u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c.")) return;
  setStatus("\u0423\u0434\u0430\u043b\u0435\u043d\u0438\u0435\u2026", "neutral");
  const q = new URLSearchParams({ email });
  const url = `/api/subscriptions/${encodeURIComponent(subscriptionId)}?${q}`;
  try {
    const res = await fetch(url, { method: "DELETE", headers: { Accept: "application/json" } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);
    setStatus("\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0443\u0434\u0430\u043b\u0435\u043d\u0430", "ok");
    await loadList();
  } catch (e) {
    console.error(e);
    setStatus("\u041e\u0448\u0438\u0431\u043a\u0430: " + (e.message || "\u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c"), "error");
  }
}

async function loadList() {
  const email = (emailInput.value || "").trim();
  if (!email) {
    setStatus("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 email \u0434\u043b\u044f \u0441\u043f\u0438\u0441\u043a\u0430 \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a.", "error");
    return;
  }
  setStatus("\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430\u2026", "neutral");
  listArea.classList.add("hidden");
  listEmpty.classList.add("hidden");
  const q = new URLSearchParams({ email });
  const url = `/api/subscriptions/list?${q}`;
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const items = data.items || [];
    if (items.length) {
      setStatus(`\u0417\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043e \u043f\u043e\u0434\u043f\u0438\u0441\u043e\u043a: ${items.length}`, "ok");
    } else {
      setStatus("\u041f\u043e\u0434\u043f\u0438\u0441\u043e\u043a \u0441 \u044d\u0442\u0438\u043c email \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e", "neutral");
    }
    renderList(items);
  } catch (e) {
    console.error(e);
    setStatus("\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0434\u0430\u043d\u043d\u044b\u0445.", "error");
  }
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const fd = new FormData(form);
  const email = (fd.get("email") || "").trim();
  const niche = (fd.get("niche") || "").trim();
  const body = {
    email,
    keywords: fd.get("keywords") || "",
    region: (fd.get("region") || "").trim(),
    niche: niche || null,
    min_nmck: fd.get("min_nmck") ? Number(fd.get("min_nmck")) : null,
    max_nmck: fd.get("max_nmck") ? Number(fd.get("max_nmck")) : null,
    law_type: (fd.get("law_type") || "").trim() || null,
  };
  if (!email) {
    setStatus("\u0423\u043a\u0430\u0436\u0438\u0442\u0435 email.", "error");
    return;
  }
  setStatus("\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435\u2026", "neutral");
  try {
    const res = await fetch(`/api/subscriptions/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
      throw new Error(msg || `HTTP ${res.status}`);
    }
    setStatus("\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430!", "ok");
    await loadList();
  } catch (e) {
    console.error(e);
    setStatus("\u041e\u0448\u0438\u0431\u043a\u0430: " + (e.message || "\u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c"), "error");
  }
});

btnList.addEventListener("click", () => loadList());
