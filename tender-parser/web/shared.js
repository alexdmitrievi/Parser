/**
 * Shared helpers — подключить на всех страницах:
 *   <script src="/web/shared.js"></script>
 */

/* ── Toast notification ── */
function showToast(msg) {
  let c = document.querySelector(".toast-container");
  if (!c) { c = document.createElement("div"); c.className = "toast-container"; document.body.appendChild(c); }
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; c.appendChild(t);
  setTimeout(() => { t.classList.add("fade-out"); t.addEventListener("animationend", () => t.remove()); }, 2500);
}

/* ── Escape HTML ── */
function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

/* ── Format money (RUB) ── */
function fmtMoney(n) {
  if (n == null) return "\u2014";
  try { return Number(n).toLocaleString("ru-RU") + " \u20BD"; }
  catch { return String(n); }
}

/* ── Dark mode toggle ── */
(function initTheme() {
  const saved = localStorage.getItem("tenderpro-theme");
  if (saved === "dark") {
    document.body.classList.add("dark");
  }
  window.toggleTheme = function () {
    const isDark = document.body.classList.toggle("dark");
    localStorage.setItem("tenderpro-theme", isDark ? "dark" : "light");
  };
})();

/* ── Service Worker ── */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/web/sw.js").catch(() => {});
  });
}
