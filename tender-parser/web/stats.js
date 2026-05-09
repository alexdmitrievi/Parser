/**
 * Тендер PRO — Аналитика тендеров
 * Dark theme chart colors
 */

const statusEl = document.getElementById("status");

const COLORS = [
  "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#6366f1",
];

const COLORS_BG = COLORS.map(c => c + "33");

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function nicheLabel(tag) {
  const map = {
    furniture: "Мебель",
    construction: "Стройка / ремонт",
    it: "IT-услуги",
    security: "Охрана",
    cleaning: "Клининг",
    food: "Продукты питания",
    medical: "Медицина",
    transport: "Транспорт",
  };
  return map[tag] || tag.charAt(0).toUpperCase() + tag.slice(1);
}

// Кэш статистики в localStorage — живёт 10 минут.
// Пока ждём свежие данные, сразу показываем кэш — нет белой страницы.
const STATS_CACHE_KEY = "tenderpro-stats-cache";
const STATS_CACHE_TTL = 10 * 60 * 1000;

function readStatsCache() {
  try {
    const raw = localStorage.getItem(STATS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.ts || Date.now() - parsed.ts > STATS_CACHE_TTL) return null;
    return parsed.data;
  } catch { return null; }
}

function writeStatsCache(data) {
  try { localStorage.setItem(STATS_CACHE_KEY, JSON.stringify({ ts: Date.now(), data })); } catch {}
}

let _nicheChart = null;
let _regionChart = null;

function renderStats(data) {
  document.getElementById("kpi-total").textContent = (data.total ?? 0).toLocaleString("ru-RU");
  document.getElementById("kpi-recent").textContent = (data.created_last_7_days ?? 0).toLocaleString("ru-RU");

  const niches = data.by_niche || {};
  const regions = data.by_region || {};
  document.getElementById("kpi-niches").textContent = Object.keys(niches).length;
  document.getElementById("kpi-regions").textContent = Object.keys(regions).length;

  const nicheLabels = Object.keys(niches).map(nicheLabel);
  const nicheValues = Object.values(niches);

  if (nicheLabels.length > 0) {
    if (_nicheChart) _nicheChart.destroy();
    _nicheChart = new Chart(document.getElementById("chart-niches"), {
      type: "doughnut",
      data: {
        labels: nicheLabels,
        datasets: [{
          data: nicheValues,
          backgroundColor: COLORS.slice(0, nicheLabels.length),
          borderColor: "rgba(10,14,23,0.8)",
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: "#94a3b8",
              padding: 12,
              font: { family: "Inter, system-ui", size: 12 },
              boxWidth: 14,
            },
          },
        },
      },
    });
  }

  const regionEntries = Object.entries(regions)
    .filter(([k]) => k !== "unknown" && k.trim() !== "")
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  const regionLabels = regionEntries.map(([k]) => k.length > 22 ? k.slice(0, 19) + "…" : k);
  const regionValues = regionEntries.map(([, v]) => v);

  if (regionLabels.length > 0) {
    if (_regionChart) _regionChart.destroy();
    _regionChart = new Chart(document.getElementById("chart-regions"), {
      type: "bar",
      data: {
        labels: regionLabels,
        datasets: [{
          label: "Тендеров",
          data: regionValues,
          backgroundColor: COLORS_BG.slice(0, regionLabels.length),
          borderColor: COLORS.slice(0, regionLabels.length),
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: true,
        aspectRatio: 1.4,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: { color: "#64748b", font: { family: "Inter, system-ui", size: 11 } },
            grid: { color: "rgba(255,255,255,0.04)" },
          },
          y: {
            ticks: { color: "#94a3b8", font: { family: "Inter, system-ui", size: 11 } },
            grid: { display: false },
          },
        },
      },
    });
  }
}

async function loadStats() {
  if (!statusEl) return;

  if (typeof Chart === "undefined") {
    setStatus("Не удалось загрузить графики. Обновите страницу.", true);
    return;
  }

  // Показать кэш сразу — пользователь не видит пустой страницы
  const cached = readStatsCache();
  if (cached) {
    renderStats(cached);
    setStatus("", false);
  } else {
    statusEl.innerHTML = '<span class="spinner"></span> Загрузка аналитики…';
  }

  try {
    const res = await fetchWithTimeout("/api/stats", { headers: { Accept: "application/json" } }, 8000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    writeStatsCache(data);
    renderStats(data);
    setStatus("", false);
  } catch (e) {
    if (!cached) setStatus("Ошибка загрузки аналитики.", true);
  }
}

loadStats();
