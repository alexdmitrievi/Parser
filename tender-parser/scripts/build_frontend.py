"""Фронтенд-бандлинг: конкатенация JS в правильном порядке + минификация CSS.
Запускать перед деплоем: python scripts/build_frontend.py
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

PAGES = {
    "tenders":     {"html": "index.html",    "js": ["app.js"]},
    "auctions":    {"html": "auctions.html", "js": ["auctions.js"]},
    "grants":      {"html": "grants.html",   "js": ["grants.js"]},
    "favorites":   {"html": "favorites.html","js": ["favorites.js"]},
    "subscribe":   {"html": "subscribe.html","js": ["subscribe.js"]},
    "stats":       {"html": "stats.html",    "js": ["stats.js"]},
    "social":      {"html": "social-contract.html", "js": ["social-contract.js"]},
}

COMMON_JS = ["shared.js", "navbar.js"]
MIN_CSS = "styles.min.css"


def read_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def concat_js(files: list[str]) -> str:
    parts = []
    for fname in files:
        fpath = WEB_DIR / fname
        if fpath.exists():
            src = read_file(fpath)
            parts.append(f"/* {fname} */\n{src}\n")
        else:
            print(f"  WARN: {fname} not found, skipping")
    return "\n".join(parts)


def minify_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>+~()])\s*", r"\1", css)
    css = re.sub(r";}", "}", css)
    return css.strip()


def update_html(html_path: Path, bundle_name: str, extra_scripts: list[str] | None = None) -> None:
    content = read_file(html_path)

    scripts_to_use = [f"/web/{bundle_name}"]
    if extra_scripts:
        scripts_to_use.extend(extra_scripts)

    script_tags = "\n".join(f'  <script src="{s}" defer></script>' for s in scripts_to_use)

    # Захватываем серию <script>-тегов с любыми атрибутами (включая defer/async)
    pattern = r"(\s*<script\s+[^>]*src=\"[^\"]+\"[^>]*></script>\s*)+"
    content = re.sub(pattern, f"\n{script_tags}\n", content, count=1)

    if MIN_CSS not in content:
        content = content.replace(
            '<link rel="preload" href="/web/styles.css" as="style" />',
            f'<link rel="preload" href="/web/{MIN_CSS}" as="style" />'
        )
        content = content.replace(
            '<link rel="stylesheet" href="/web/styles.css" />',
            f'<link rel="stylesheet" href="/web/{MIN_CSS}" />'
        )

    write_file(html_path, content)
    print(f"  Updated: {html_path.name}")


def main():
    print("Building frontend bundles...")

    styles_src = read_file(WEB_DIR / "styles.css")
    styles_min = minify_css(styles_src)
    write_file(WEB_DIR / MIN_CSS, styles_min)
    print(f"  CSS: {len(styles_src):,} → {len(styles_min):,} bytes ({100 - len(styles_min) * 100 // max(len(styles_src), 1)}% smaller)")

    for page_name, cfg in PAGES.items():
        bundle_name = f"bundle-{page_name}.js"
        all_js = COMMON_JS + cfg["js"]
        bundled = concat_js(all_js)
        write_file(WEB_DIR / bundle_name, bundled)
        sizes = " + ".join(
            str(len(read_file(WEB_DIR / f))) if (WEB_DIR / f).exists() else "?"
            for f in all_js
        )
        print(f"  JS {page_name}: {sizes} → {len(bundled):,} bytes ({bundle_name})")

        html_path = WEB_DIR / cfg["html"]
        extra = None
        if page_name == "stats":
            extra = ["/web/vendor/chart.umd.min.js"]
        update_html(html_path, bundle_name, extra)

    about_html = WEB_DIR / "about.html"
    about_content = read_file(about_html)
    bundle_common = "bundle-common.js"
    common_bundled = concat_js(COMMON_JS)
    write_file(WEB_DIR / bundle_common, common_bundled)
    print(f"  JS about: {bundle_common} ({len(common_bundled):,} bytes)")

    about_pattern = r"(\s*<script\s+[^>]*src=\"[^\"]+\"[^>]*></script>\s*)+"
    about_content = re.sub(
        about_pattern,
        f'\n  <script src="/web/{bundle_common}" defer></script>\n',
        about_content, count=1
    )
    about_content = about_content.replace(
        '<link rel="preload" href="/web/styles.css" as="style" />',
        f'<link rel="preload" href="/web/{MIN_CSS}" as="style" />'
    )
    about_content = about_content.replace(
        '<link rel="stylesheet" href="/web/styles.css" />',
        f'<link rel="stylesheet" href="/web/{MIN_CSS}" />'
    )
    write_file(about_html, about_content)
    print(f"  Updated: about.html")

    print("\nDone. Run 'npm run dev' to test locally.")


if __name__ == "__main__":
    main()
