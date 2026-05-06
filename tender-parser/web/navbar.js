/**
 * NavBar — Custom Element (Web Component)
 * Внедряет навигацию на все страницы. Использование: <nav-bar active="tenders"></nav-bar>
 * active: tenders | auctions | grants | social-contract | favorites | subscribe | stats
 */

const NAV_LINKS = [
  { id: "tenders",         href: "/web/",                      label: "Тендеры",         svg: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>' },
  { id: "auctions",        href: "/web/auctions.html",          label: "Аукционы",        svg: '<path d="M18 15l-6-3.5L6 15"/><path d="M18 9l-6-3.5L6 9"/><path d="M6 15v4l6 3 6-3v-4"/>' },
  { id: "grants",          href: "/web/grants.html",            label: "Финансирование",  svg: '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>' },
  { id: "social-contract", href: "/web/social-contract.html",   label: "Соц. контракт",   svg: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>' },
  { id: "favorites",       href: "/web/favorites.html",         label: "Избранное",       svg: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>' },
  { id: "subscribe",       href: "/web/subscribe.html",         label: "Подписки",        svg: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>' },
  { id: "stats",           href: "/web/stats.html",             label: "Аналитика",       svg: '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>' },
];

class NavBar extends HTMLElement {
  connectedCallback() {
    const active = this.getAttribute("active") || "tenders";
    const isMain = active === "tenders";

    const backLink = isMain ? "" : `
      <a href="/web/" class="nav-back-link" title="Вернуться к поиску тендеров">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        <span>Назад</span>
      </a>
    `;

    const linksClass = `navbar-links${isMain ? ' always-visible' : ''}`;

    this.innerHTML = `
      <div class="navbar-brand">
        ${backLink}
        <span>Тендер PRO</span>
        <a href="https://podryadpro.ru/" class="nav-podryad" title="Платформа Подряд PRO" style="margin-left:10px;font-size:11px;font-weight:500;color:var(--text-muted);opacity:0.5;transition:opacity 0.2s;white-space:nowrap;text-decoration:none" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.5">← Подряд PRO</a>
      </div>
      <button class="navbar-burger${isMain ? ' hidden-on-main' : ''}" id="navbar-burger" aria-label="Меню" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>
      <div class="${linksClass}">
        ${NAV_LINKS.map(l => `
          <a href="${l.href}" class="nav-link${l.id === active ? ' active' : ''}">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${l.svg}</svg>
            <span>${l.label}</span>
          </a>
        `).join("")}
      </div>
    `;

    this.setupEvents();
  }

  setupEvents() {
    // Hamburger menu toggle
    const burger = this.querySelector("#navbar-burger");
    const links = this.querySelector(".navbar-links");
    if (burger && links) {
      burger.addEventListener("click", () => {
        const open = links.classList.toggle("open");
        burger.classList.toggle("active", open);
        burger.setAttribute("aria-expanded", String(open));
      });
    }

    // Close menu on outside click
    document.addEventListener("click", (e) => {
      if (burger && links && !burger.contains(e.target) && !links.contains(e.target)) {
        links.classList.remove("open");
        burger.classList.remove("active");
        burger.setAttribute("aria-expanded", "false");
      }
    });

    // Prefetch pages on hover for instant navigation
    this.querySelectorAll("a.nav-link").forEach(a => {
      a.addEventListener("mouseenter", () => {
        const href = a.getAttribute("href");
        if (href && !document.querySelector(`link[href="${href}"]`)) {
          const link = document.createElement("link");
          link.rel = "prefetch";
          link.href = href;
          document.head.appendChild(link);
        }
      }, { once: true });
    });
  }
}

customElements.define("nav-bar", NavBar);
