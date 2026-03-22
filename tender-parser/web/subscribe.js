/**
 * Веб-подписки: POST /api/subscriptions/create, GET list, DELETE.
 */

const form = document.getElementById("sub-form");
const emailInput = document.getElementById("email");
const globalStatus = document.getElementById("global-status");
const btnList = document.getElementById("btn-list");
const listArea = document.getElementById("list-area");
const listEmpty = document.getElementById("list-empty");

function apiBase() {
  return "";
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

function setStatus(text, kind = "neutral") {
  globalStatus.textContent = text;
  globalStatus.classList.remove("error", "ok");
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
    card.className = "sub-card";
    card.innerHTML = `
      <div class="sub-head">
        <strong>Подписка</strong>
        <button type="button" class="btn danger btn-del" data-id="${esc(id)}">Удалить</button>
      </div>
      <dl>
        <dt>Ключевые слова</dt><dd>${formatArr(row.keywords)}</dd>
        <dt>Регионы</dt><dd>${formatArr(row.regions)}</dd>
        <dt>Ниши (теги)</dt><dd>${formatArr(row.niche_tags)}</dd>
        <dt>НМЦК</dt><dd>${esc(row.min_nmck ?? "\u2014")} \u2014 ${esc(row.max_nmck ?? "\u2014")}</dd>
        <dt>Типы законов</dt><dd>${formatArr(row.law_types)}</dd>
        <dt>Создана</dt><dd>${esc(row.created_at || "\u2014")}</dd>
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
    setStatus("Укажите email.", "error");
    return;
  }
  if (!confirm("Удалить подписку? Это действие нельзя отменить.")) {
    return;
  }
  setStatus("Удаление\u2026", "neutral");
  const q = new URLSearchParams({ email });
  const url = `${apiBase()}/api/subscriptions/${encodeURIComponent(subscriptionId)}?${q}`;
  try {
    const res = await fetch(url, { method: "DELETE", headers: { Accept: "application/json" } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || data.message || `HTTP ${res.status}`);
    }
    setStatus("Подписка удалена", "ok");
    await loadList();
  } catch (e) {
    console.error(e);
    setStatus("Ошибка: " + (e.message || "не удалось удалить"), "error");
  }
}

async function loadList() {
  const email = (emailInput.value || "").trim();
  if (!email) {
    setStatus("Введите email для списка подписок.", "error");
    return;
  }
  setStatus("Загрузка\u2026", "neutral");
  listArea.classList.add("hidden");
  listEmpty.classList.add("hidden");
  const q = new URLSearchParams({ email });
  const url = `${apiBase()}/api/subscriptions/list?${q}`;
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const items = data.items || [];
    if (items.length) {
      setStatus(`Загружено подписок: ${items.length}`, "ok");
    } else {
      setStatus("Подписок с этим email не найдено", "neutral");
    }
    renderList(items);
  } catch (e) {
    console.error(e);
    setStatus("Ошибка загрузки данных.", "error");
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
    setStatus("Укажите email.", "error");
    return;
  }
  setStatus("Сохранение\u2026", "neutral");
  try {
    const res = await fetch(`${apiBase()}/api/subscriptions/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
      throw new Error(msg || `HTTP ${res.status}`);
    }
    setStatus("Подписка активна", "ok");
    await loadList();
  } catch (e) {
    console.error(e);
    setStatus("Ошибка: " + (e.message || "не удалось сохранить"), "error");
  }
});

btnList.addEventListener("click", () => loadList());
