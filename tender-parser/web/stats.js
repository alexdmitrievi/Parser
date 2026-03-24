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
  return tag.charAt(0).toUpperCase() + tag.slice(1);
}

async function loadStats() {
  if (!statusEl) return;
  statusEl.innerHTML = '<span class="spinner"></span> \u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0438\u2026';

  if (typeof Chart === "undefined") {
    setStatus(
      "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0433\u0440\u0430\u0444\u0438\u043a\u0438. \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u0435 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0443.",
      true
    );
    return;
  }

  try {
    const res = await fetch("/api/stats", { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById("kpi-total").textContent = (data.total ?? 0).toLocaleString("ru-RU");
    document.getElementById("kpi-recent").textContent = (data.created_last_7_days ?? 0).toLocaleString("ru-RU");

    const niches = data.by_niche || {};
    const regions = data.by_region || {};
    document.getElementById("kpi-niches").textContent = Object.keys(niches).length;
    document.getElementById("kpi-regions").textContent = Object.keys(regions).length;

    // Niche doughnut chart
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

    // Top-10 regions bar chart
    const regionEntries = Object.entries(regions)
      .filter(([k]) => k !== "unknown" && k.trim() !== "")
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    const regionLabels = regionEntries.map(([k]) => k.length > 22 ? k.slice(0, 19) + "\u2026" : k);
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
          maintainAspectRatio: true,
          aspectRatio: 1.4,
          plugins: {
            legend: { display: false },
          },
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

    setStatus("", false);
  } catch (e) {
    console.error(e);
    setStatus("\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0438.", true);
  }
}

loadStats();
