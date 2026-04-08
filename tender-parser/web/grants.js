/* grants.js — Финансирование бизнеса: гранты, кредиты, субсидии */
"use strict";

const API = "/api/funding";

const BADGE_CLASSES = {
  grant: "badge-grant",
  loan: "badge-loan",
  microloan: "badge-microloan",
  subsidy: "badge-subsidy",
  guarantee: "badge-guarantee",
  compensation: "badge-compensation",
  leasing: "badge-leasing",
};

const CARD_ACCENTS = {
  grant: "linear-gradient(90deg,#10b981,#059669)",
  loan: "linear-gradient(90deg,#3b82f6,#2563eb)",
  microloan: "linear-gradient(90deg,#8b5cf6,#7c3aed)",
  subsidy: "linear-gradient(90deg,#f59e0b,#d97706)",
  guarantee: "linear-gradient(90deg,#ef4444,#dc2626)",
  compensation: "linear-gradient(90deg,#14b8a6,#0d9488)",
  leasing: "linear-gradient(90deg,#a855f7,#9333ea)",
};

const TYPE_ICONS = {
  grant: "&#127381;",
  loan: "&#128181;",
  microloan: "&#128176;",
  subsidy: "&#127873;",
  guarantee: "&#128274;",
  compensation: "&#9749;",
  leasing: "&#128664;",
};

// State
let state = {
  query: "",
  programType: "",
  platform: "",
  region: "",
  page: 1,
  pageSize: 12,
  total: 0,
};

// Format number as currency
function fmt(n, currency = "₽") {
  if (n == null) return "—";
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1).replace(".0", "") + " млрд " + currency;
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(".0", "") + " млн " + currency;
  if (n >= 1_000) return (n / 1_000).toFixed(0) + " тыс " + currency;
  return n.toLocaleString("ru") + " " + currency;
}

function fmtRate(r) {
  if (r == null) return "—";
  return r + "% год.";
}

function fmtTerm(t) {
  if (t == null) return "—";
  if (t % 12 === 0) return (t / 12) + " " + pluralize(t / 12, "год", "года", "лет");
  return t + " мес.";
}

function pluralize(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

function escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Build query params
function buildParams(extra = {}) {
  const p = new URLSearchParams();
  if (state.query) p.set("q", state.query);
  if (state.programType) p.set("program_type", state.programType);
  if (state.region) p.set("region", state.region);
  p.set("page", state.page);
  p.set("page_size", state.pageSize);
  Object.entries(extra).forEach(([k, v]) => v != null && p.set(k, v));
  return p;
}

// Render skeleton
function showSkeleton(n = 6) {
  const grid = document.getElementById("grants-grid");
  grid.innerHTML = Array.from({ length: n }, () =>
    `<div class="skeleton" style="height:260px;border-radius:16px;"></div>`
  ).join("");
}

// Render grant card
function renderCard(p) {
  const badgeClass = BADGE_CLASSES[p.program_type] || "badge-grant";
  const accent = CARD_ACCENTS[p.program_type] || CARD_ACCENTS.grant;
  const icon = TYPE_ICONS[p.program_type] || "";
  const typeLabel = p.program_type_label || p.program_type;
  const regions = p.regions && p.regions.length > 0
    ? p.regions.slice(0, 2).map(r => `<span class="region-tag">${escHtml(r)}</span>`).join("") +
      (p.regions.length > 2 ? `<span class="region-tag">+${p.regions.length - 2}</span>` : "")
    : `<span class="region-tag all-russia">Вся Россия</span>`;

  return `
  <div class="grant-card" data-id="${escHtml(p.id)}" style="--card-accent:${accent}" tabindex="0" role="button" aria-label="${escHtml(p.program_name)}">
    <div class="grant-card-header">
      <span class="grant-type-badge ${badgeClass}">${icon} ${escHtml(typeLabel)}</span>
    </div>
    <div>
      <div class="grant-title">${escHtml(p.program_name)}</div>
      <div class="grant-organizer">
        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="11" x="2" y="7" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><line x1="12" x2="12" y1="12" y2="12.01"/></svg>
        ${escHtml(p.organizer_name || p.platform_label || "")}
      </div>
    </div>
    <div class="grant-amounts">
      <div class="grant-amount-item">
        <div class="grant-amount-value">${fmt(p.amount_max)}</div>
        <div class="grant-amount-label">Макс. сумма</div>
      </div>
      <div class="grant-amount-item">
        <div class="grant-amount-value" style="${p.rate != null ? "color:var(--accent-blue)" : ""}">${fmtRate(p.rate)}</div>
        <div class="grant-amount-label">Ставка</div>
      </div>
      <div class="grant-amount-item">
        <div class="grant-amount-value" style="color:var(--text-secondary)">${fmtTerm(p.term_months)}</div>
        <div class="grant-amount-label">Срок</div>
      </div>
    </div>
    <div class="grant-desc">${escHtml(p.description || "")}</div>
    <div class="grant-footer">
      <div class="grant-platform">
        <span class="platform-dot"></span>
        ${escHtml(p.platform_label || p.source_platform)}
      </div>
      <button class="btn-apply" data-url="${escHtml(p.original_url)}" onclick="event.stopPropagation();openUrl(this.dataset.url)">
        Подать заявку
        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
      </button>
    </div>
  </div>`;
}

function openUrl(url) {
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

// Show detail modal
function showDetail(program) {
  const modal = document.getElementById("detail-modal");
  const content = document.getElementById("modal-content");

  const badgeClass = BADGE_CLASSES[program.program_type] || "badge-grant";
  const typeLabel = program.program_type_label || program.program_type;

  const regions = program.regions && program.regions.length > 0
    ? program.regions.map(r => `<span class="info-tag">${escHtml(r)}</span>`).join("")
    : `<span class="info-tag" style="color:var(--accent-green)">Вся Россия</span>`;

  const industries = program.industries && program.industries.length > 0
    ? program.industries.map(i => `<span class="info-tag">${escHtml(i)}</span>`).join("")
    : `<span class="info-tag">Все отрасли</span>`;

  content.innerHTML = `
    <div style="margin-bottom:1rem">
      <span class="grant-type-badge ${badgeClass}" style="margin-bottom:0.75rem;display:inline-flex">${escHtml(typeLabel)}</span>
      <h2 style="font-size:1.2rem;line-height:1.4;margin-bottom:0.4rem">${escHtml(program.program_name)}</h2>
      <div style="font-size:0.85rem;color:var(--text-muted)">${escHtml(program.organizer_name || program.platform_label || "")}</div>
    </div>

    <div class="modal-amounts">
      <div class="grant-amount-item">
        <div class="grant-amount-value">${fmt(program.amount_min)} — ${fmt(program.amount_max)}</div>
        <div class="grant-amount-label">Сумма финансирования</div>
      </div>
      <div class="grant-amount-item">
        <div class="grant-amount-value" style="${program.rate != null ? "color:var(--accent-blue)" : ""}">${fmtRate(program.rate)}</div>
        <div class="grant-amount-label">Процентная ставка</div>
      </div>
      <div class="grant-amount-item">
        <div class="grant-amount-value" style="color:var(--text-secondary)">${fmtTerm(program.term_months)}</div>
        <div class="grant-amount-label">Срок</div>
      </div>
    </div>

    <div class="modal-section">
      <div class="modal-label">Описание программы</div>
      <div class="modal-text">${escHtml(program.description || "Описание не указано")}</div>
    </div>

    ${program.requirements ? `
    <div class="modal-section">
      <div class="modal-label">Требования к получателю</div>
      <div class="modal-text">${escHtml(program.requirements)}</div>
    </div>` : ""}

    <div class="modal-section">
      <div class="modal-label">Регионы действия</div>
      <div>${regions}</div>
    </div>

    <div class="modal-section">
      <div class="modal-label">Отрасли</div>
      <div>${industries}</div>
    </div>

    <div style="margin-top:1.5rem;display:flex;gap:0.75rem;flex-wrap:wrap">
      <a href="${escHtml(program.original_url)}" target="_blank" rel="noopener noreferrer"
         class="btn btn-primary" style="display:inline-flex;align-items:center;gap:0.5rem;text-decoration:none">
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
        Перейти на сайт программы
      </a>
    </div>
  `;

  modal.classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  document.getElementById("detail-modal").classList.remove("open");
  document.body.style.overflow = "";
}

// Fetch and render programs
async function loadPrograms() {
  const grid = document.getElementById("grants-grid");
  const status = document.getElementById("g-status");
  const pager = document.getElementById("g-pager");

  showSkeleton(6);
  status.textContent = "";
  pager.classList.add("hidden");

  const params = buildParams();
  // Фильтр по платформе
  if (state.platform) params.set("source_platform", state.platform);

  try {
    const res = await fetch(`${API}?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    state.total = data.total || 0;
    const items = data.items || [];

    if (!items.length) {
      grid.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:3rem 1rem;color:var(--text-muted)">
          <div style="font-size:2.5rem;margin-bottom:1rem">🔍</div>
          <div style="font-size:1rem;margin-bottom:0.5rem;color:var(--text-secondary)">Программы не найдены</div>
          <div>Попробуйте изменить фильтры или <button class="btn btn-ghost btn-sm" onclick="resetFilters()">сбросить поиск</button></div>
        </div>`;
      return;
    }

    grid.innerHTML = items.map(renderCard).join("");

    // Attach card click
    grid.querySelectorAll(".grant-card").forEach(card => {
      card.addEventListener("click", () => {
        const program = items.find(p => p.id === card.dataset.id);
        if (program) showDetail(program);
      });
      card.addEventListener("keydown", e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          card.click();
        }
      });
    });

    // Pager
    const totalPages = Math.ceil(state.total / state.pageSize);
    if (totalPages > 1) {
      pager.classList.remove("hidden");
      document.getElementById("g-page-info").textContent = `стр. ${state.page} / ${totalPages} · ${state.total} программ`;
      document.getElementById("g-prev").disabled = state.page <= 1;
      document.getElementById("g-next").disabled = state.page >= totalPages;
    }

    status.textContent = `Найдено: ${state.total} программ`;
  } catch (err) {
    grid.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:2rem;color:var(--text-muted)">
        <div style="margin-bottom:0.5rem">Ошибка загрузки данных</div>
        <button class="btn btn-ghost btn-sm" onclick="loadPrograms()">Повторить</button>
      </div>`;
    status.textContent = "Ошибка загрузки";
    console.error("Funding API error:", err);
  }
}

// Load meta counters
async function loadMeta() {
  try {
    const res = await fetch("/api/funding/meta");
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("cnt-total").textContent = data.total_active || data.total || 0;
    document.getElementById("cnt-grants").textContent = (data.by_type && data.by_type.grant) || 0;
    document.getElementById("cnt-loans").textContent =
      ((data.by_type && data.by_type.loan) || 0) +
      ((data.by_type && data.by_type.microloan) || 0);
  } catch (_) {}
}

function resetFilters() {
  state.query = "";
  state.programType = "";
  state.platform = "";
  state.region = "";
  state.page = 1;
  document.getElementById("g-query").value = "";
  document.getElementById("g-region").value = "";
  document.querySelectorAll(".type-pill").forEach(p => p.classList.toggle("active", p.dataset.type === ""));
  document.querySelectorAll(".platform-card").forEach(c => c.classList.toggle("active", c.dataset.platform === ""));
  loadPrograms();
}

// Autocomplete for region
const REGIONS = [
  "Москва","Санкт-Петербург","Московская область","Краснодарский край",
  "Республика Татарстан","Свердловская область","Новосибирская область",
  "Омская область","Тюменская область","Ростовская область","Нижегородская область",
  "Самарская область","Красноярский край","Челябинская область",
  "Пермский край","Воронежская область","Ставропольский край",
  "Саратовская область","Башкортостан","Волгоградская область",
];

function setupRegionAutocomplete() {
  const input = document.getElementById("g-region");
  const dropdown = document.getElementById("region-dropdown");
  if (!input || !dropdown) return;

  input.addEventListener("input", () => {
    const val = input.value.trim().toLowerCase();
    if (!val) { dropdown.classList.add("hidden"); return; }
    const matches = REGIONS.filter(r => r.toLowerCase().includes(val)).slice(0, 8);
    if (!matches.length) { dropdown.classList.add("hidden"); return; }
    dropdown.innerHTML = matches
      .map(r => `<div class="autocomplete-item" tabindex="-1">${r}</div>`)
      .join("");
    dropdown.classList.remove("hidden");
    dropdown.querySelectorAll(".autocomplete-item").forEach(item => {
      item.addEventListener("mousedown", e => {
        e.preventDefault();
        input.value = item.textContent;
        state.region = item.textContent;
        dropdown.classList.add("hidden");
        state.page = 1;
        loadPrograms();
      });
    });
  });

  document.addEventListener("click", e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add("hidden");
    }
  });

  input.addEventListener("change", () => {
    state.region = input.value.trim();
  });
}

// Init
document.addEventListener("DOMContentLoaded", () => {
  loadMeta();
  loadPrograms();
  setupRegionAutocomplete();

  // Search input with debounce
  let debounce;
  document.getElementById("g-query").addEventListener("input", e => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.query = e.target.value.trim();
      state.page = 1;
      loadPrograms();
    }, 400);
  });

  // Type pills
  document.getElementById("type-filters").addEventListener("click", e => {
    const pill = e.target.closest(".type-pill");
    if (!pill) return;
    document.querySelectorAll(".type-pill").forEach(p => p.classList.remove("active"));
    pill.classList.add("active");
    state.programType = pill.dataset.type;
    state.page = 1;
    loadPrograms();
  });

  // Platform cards
  document.getElementById("platform-row").addEventListener("click", e => {
    const card = e.target.closest(".platform-card");
    if (!card) return;
    document.querySelectorAll(".platform-card").forEach(c => c.classList.remove("active"));
    card.classList.add("active");
    state.platform = card.dataset.platform;
    state.page = 1;
    loadPrograms();
  });

  // Pagination
  document.getElementById("g-prev").addEventListener("click", () => {
    if (state.page > 1) { state.page--; loadPrograms(); window.scrollTo({ top: 0, behavior: "smooth" }); }
  });
  document.getElementById("g-next").addEventListener("click", () => {
    const totalPages = Math.ceil(state.total / state.pageSize);
    if (state.page < totalPages) { state.page++; loadPrograms(); window.scrollTo({ top: 0, behavior: "smooth" }); }
  });

  // Modal close
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("detail-modal").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeModal();
  });
});
