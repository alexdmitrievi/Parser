/**
 * Подряд PRO — Аналитика тендеров
 * Light theme chart colors
 */

const statusEl = document.getElementById("status");

const COLORS = [
  "#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626",
  "#0891b2", "#db2777", "#0d9488", "#ea580c", "#4f46e5",
];

const COLORS_BG = COLORS.map(c => c + "18");

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function nicheLabel(tag) {
  return tag.charAt(0).toUpperCase() + tag.slice(1);
}

async function loadStats() {
  statusEl.innerHTML = '<span class="spinner"></span> \u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0438\u2026';

  try {
    const res = await fetch("/api/stats", { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // KPI
    document.getElementById("kpi-total").textContent = (data.total ?? 0).toLocaleString("ru-RU");
    document.getElementById("kpi-recent").textContent = (data.created_last_7_days ?? 0).toLocaleString("ru-RU");

    const niches = data.by_niche || {};
    const regions = data.by_region || {};
    document.getElementById("kpi-niches").textContent = Object.keys(niches).length;
    document.getElementById("kpi-regions").textContent = Object.keys(regions).length;

    // Niche chart
    const nicheLabels = Object.keys(niches).map(nicheLabel);
    const nicheValues = Object.values(niches);

    if (nicheLabels.length > 0) {
      new Chart(document.getElementById("chart-niches"), {
        type: "doughnut",
        data: {
          labels: nicheLabels,
          datasets: [{
            data: nicheValues,
            backgroundColor: COLORS.slice(0, nicheLabels.length),
            borderColor: "#ffffff",
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: {
                color: "#475569",
                padding: 16,
                font: { family: "Inter, system-ui", size: 13 },
              },
            },
          },
        },
      });
    }

    // Regions chart — top 10
    const regionEntries = Object.entries(regions)
      .filter(([k]) => k !== "unknown")
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    const regionLabels = regionEntries.map(([k]) => k.length > 25 ? k.slice(0, 22) + "\u2026" : k);
    const regionValues = regionEntries.map(([, v]) => v);

    if (regionLabels.length > 0) {
      new Chart(document.getElementById("chart-regions"), {
        type: "bar",
        data: {
          labels: regionLabels,
          datasets: [{
            label: "\u0422\u0435\u043d\u0434\u0435\u0440\u043e\u0432",
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
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
          },
          scales: {
            x: {
              ticks: { color: "#94a3b8", font: { family: "Inter, system-ui" } },
              grid: { color: "rgba(0,0,0,0.04)" },
            },
            y: {
              ticks: { color: "#475569", font: { family: "Inter, system-ui", size: 12 } },
              grid: { display: false },
            },
          },
        },
      });
    }

    setStatus("", false);
  } catch (e) {
    console.error(e);
    setStatus("\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0438.", true);
  }
}

loadStats();
