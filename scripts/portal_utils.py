#!/usr/bin/env python3

from __future__ import annotations

import html
import re
from urllib.parse import quote


def escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def render_badge(label: str, tone: str) -> str:
    return f'<span class="badge badge-{escape(tone)}">{escape(label)}</span>'


def render_external_link(href: str, label: str) -> str:
    return (
        f'<a class="chip-link" href="{escape(href)}" target="_blank" rel="noreferrer">{escape(label)}</a>'
    )


def page_template(
    *,
    title: str,
    subtitle: str,
    nav_items: list[tuple[str, str, bool]],
    body: str,
    page_path: str,
) -> str:
    nav_html = []
    for href, label, active in nav_items:
        classes = "nav-link nav-link-active" if active else "nav-link"
        nav_html.append(f'<a class="{classes}" href="{escape(href)}">{escape(label)}</a>')

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)} | LV3 Platform</title>
    <link rel="stylesheet" href="{escape(page_path)}styles.css">
  </head>
  <body>
    <div class="page-shell">
      <header class="hero">
        <p class="eyebrow">LV3 Platform</p>
        <h1>{escape(title)}</h1>
        <p class="subtitle">{escape(subtitle)}</p>
      </header>
      <nav class="nav-bar">
        {''.join(nav_html)}
      </nav>
      <main class="page-content">
        {body}
      </main>
    </div>
  </body>
</html>
"""


PORTAL_STYLES = """
:root {
  --bg: #f2ede2;
  --panel: rgba(255, 251, 244, 0.9);
  --panel-strong: #fffaf0;
  --ink: #1f2520;
  --muted: #5d685e;
  --line: rgba(31, 37, 32, 0.12);
  --accent: #145a4a;
  --accent-soft: #d9efe7;
  --warn: #9b5b16;
  --warn-soft: #f8ead2;
  --danger: #8a2f2f;
  --danger-soft: #f7dede;
  --ok: #256542;
  --ok-soft: #d9efdf;
  --shadow: 0 18px 48px rgba(31, 37, 32, 0.08);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(20, 90, 74, 0.14), transparent 28%),
    radial-gradient(circle at top right, rgba(155, 91, 22, 0.12), transparent 24%),
    linear-gradient(180deg, #f9f5ee 0%, var(--bg) 100%);
}

a {
  color: inherit;
}

.page-shell {
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px 20px 72px;
}

.hero {
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: linear-gradient(140deg, rgba(255, 250, 240, 0.96), rgba(228, 241, 235, 0.92));
  box-shadow: var(--shadow);
}

.eyebrow {
  margin: 0 0 12px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 0.75rem;
  color: var(--muted);
}

.hero h1 {
  margin: 0;
  font-size: clamp(2rem, 4vw, 3.6rem);
  line-height: 0.95;
}

.subtitle {
  margin: 14px 0 0;
  max-width: 70ch;
  color: var(--muted);
  font-size: 1rem;
  line-height: 1.6;
}

.nav-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 18px 0 26px;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.7);
  text-decoration: none;
  color: var(--muted);
}

.nav-link-active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.page-content {
  display: grid;
  gap: 18px;
}

.summary-grid,
.card-grid,
.two-col-grid {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.card-grid {
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.two-col-grid {
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.panel,
.card {
  border: 1px solid var(--line);
  border-radius: 24px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.panel {
  padding: 20px;
}

.card {
  padding: 18px;
}

.section-title {
  margin: 0 0 12px;
  font-size: 1.3rem;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-label {
  color: var(--muted);
  font-size: 0.9rem;
}

.metric-value {
  font-size: 1.8rem;
  line-height: 1;
}

.card-head,
.row-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}

.card-head h3,
.row-head h3 {
  margin: 0;
  font-size: 1.25rem;
}

.card p,
.panel p {
  line-height: 1.55;
}

.muted {
  color: var(--muted);
}

.meta-list {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.meta-list div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 0.95rem;
}

.meta-list strong {
  min-width: 84px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.chip-link,
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--panel-strong);
  text-decoration: none;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 0.84rem;
  border: 1px solid transparent;
}

.badge-ok {
  background: var(--ok-soft);
  color: var(--ok);
}

.badge-warn {
  background: var(--warn-soft);
  color: var(--warn);
}

.badge-danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.badge-neutral {
  background: rgba(31, 37, 32, 0.08);
  color: var(--muted);
}

.table-scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  text-align: left;
  padding: 12px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}

th {
  color: var(--muted);
  font-size: 0.84rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.group-block {
  display: grid;
  gap: 14px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.group-header h2 {
  margin: 0;
  font-size: 1.4rem;
}

.search-box {
  width: 100%;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: var(--panel-strong);
  font: inherit;
}

.toolbar {
  display: grid;
  gap: 12px;
}

details summary {
  cursor: pointer;
  font-weight: bold;
}

@media (max-width: 720px) {
  .page-shell {
    padding: 18px 14px 48px;
  }

  .hero {
    padding: 18px;
  }

  .card,
  .panel {
    border-radius: 20px;
  }

  th,
  td {
    min-width: 120px;
  }
}
"""
