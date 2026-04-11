#!/usr/bin/env python3

from __future__ import annotations

import html
import re


def escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def render_badge(label: str, tone: str) -> str:
    return f'<span class="badge badge-{escape(tone)}">{escape(label)}</span>'


def render_external_link(href: str, label: str) -> str:
    return f'<a class="chip-link" href="{escape(href)}" target="_blank" rel="noreferrer">{escape(label)}</a>'


ROBOTS_META_CONTENT = "noindex, nofollow"


def _render_help_sections(sections: list[dict[str, str]]) -> str:
    if not sections:
        return ""
    items = []
    for item in sections:
        items.append(
            '<li class="contextual-help-list-item">'
            f'<a href="{escape(item["href"])}">{escape(item["label"])}</a>'
            f"<span>{escape(item['summary'])}</span>"
            "</li>"
        )
    return (
        '<section class="contextual-help-block">'
        '<h2 class="contextual-help-title">Page Focus</h2>'
        f'<ul class="contextual-help-list">{"".join(items)}</ul>'
        "</section>"
    )


def _render_help_glossary(glossary: list[dict[str, str]]) -> str:
    if not glossary:
        return ""
    items = []
    for item in glossary:
        items.append(
            '<li class="contextual-help-list-item">'
            f"<strong>{escape(item['term'])}</strong>"
            f"<span>{escape(item['definition'])}</span>"
            "</li>"
        )
    return (
        '<section class="contextual-help-block">'
        '<h2 class="contextual-help-title">Glossary</h2>'
        f'<ul class="contextual-help-list">{"".join(items)}</ul>'
        "</section>"
    )


def _render_help_references(references: list[dict[str, str]]) -> str:
    if not references:
        return ""
    links = []
    for item in references:
        links.append(
            '<li class="contextual-help-link-row">'
            f'<a href="{escape(item["href"])}" target="_blank" rel="noreferrer">{escape(item["label"])}</a>'
            f"<span>{escape(item['kind'])}</span>"
            "</li>"
        )
    return (
        '<section class="contextual-help-block">'
        '<h2 class="contextual-help-title">Canonical Links</h2>'
        f'<ul class="contextual-help-links">{"".join(links)}</ul>'
        "</section>"
    )


def _render_help_escalation(escalation: dict[str, object] | None) -> str:
    if not escalation:
        return ""
    runbook = escalation.get("runbook")
    runbook_html = ""
    if isinstance(runbook, dict):
        runbook_html = (
            '<div class="contextual-help-escalation-row">'
            "<strong>Owning runbook</strong>"
            f'<a href="{escape(runbook.get("href", ""))}" target="_blank" rel="noreferrer">{escape(runbook.get("label", "Runbook"))}</a>'
            "</div>"
        )
    return (
        '<section class="contextual-help-block contextual-help-block-accent">'
        '<h2 class="contextual-help-title">Escalation Path</h2>'
        '<div class="contextual-help-escalation-row">'
        "<strong>Back out safely</strong>"
        f"<span>{escape(escalation.get('backout', ''))}</span>"
        "</div>"
        f"{runbook_html}"
        '<div class="contextual-help-escalation-row">'
        "<strong>Handoff</strong>"
        f"<span>{escape(escalation.get('handoff', ''))}</span>"
        "</div>"
        "</section>"
    )


def render_contextual_help(contextual_help: dict[str, object] | None) -> str:
    if not contextual_help:
        return ""
    audience = contextual_help.get("audience")
    audience_html = ""
    if isinstance(audience, list) and audience:
        chips = "".join(f'<span class="tag">{escape(item)}</span>' for item in audience)
        audience_html = (
            f'<div class="contextual-help-audience"><strong>Audience</strong><div class="chip-row">{chips}</div></div>'
        )
    sections = contextual_help.get("sections")
    glossary = contextual_help.get("glossary")
    references = contextual_help.get("references")
    return (
        '<div class="contextual-help-shell">'
        '<button class="contextual-help-toggle" type="button" aria-expanded="false" aria-controls="contextual-help-drawer" data-contextual-help-toggle>'
        "Contextual Help"
        "</button>"
        '<div class="contextual-help-overlay" data-contextual-help-dismiss hidden></div>'
        '<aside class="contextual-help-drawer" id="contextual-help-drawer" hidden>'
        '<div class="contextual-help-header">'
        f'<div><p class="eyebrow">Need help in this page?</p><h2>{escape(contextual_help.get("title", "Contextual Help"))}</h2></div>'
        '<button class="contextual-help-close" type="button" aria-label="Close contextual help" data-contextual-help-dismiss>Close</button>'
        "</div>"
        f'<p class="subtitle">{escape(contextual_help.get("summary", ""))}</p>'
        f"{audience_html}"
        f"{_render_help_sections(sections if isinstance(sections, list) else [])}"
        f"{_render_help_glossary(glossary if isinstance(glossary, list) else [])}"
        f"{_render_help_references(references if isinstance(references, list) else [])}"
        f"{_render_help_escalation(contextual_help.get('escalation') if isinstance(contextual_help.get('escalation'), dict) else None)}"
        "</aside>"
        "</div>"
    )


def page_template(
    *,
    title: str,
    subtitle: str,
    nav_items: list[tuple[str, str, bool]],
    body: str,
    page_path: str,
    contextual_help: dict[str, object] | None = None,
) -> str:
    nav_html = []
    for href, label, active in nav_items:
        classes = "nav-link nav-link-active" if active else "nav-link"
        nav_html.append(f'<a class="{classes}" href="{escape(href)}">{escape(label)}</a>')

    help_html = render_contextual_help(contextual_help)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="{ROBOTS_META_CONTENT}">
    <title>{escape(title)} | LV3 Platform</title>
    <link rel="stylesheet" href="{escape(page_path)}styles.css">
  </head>
  <body>
    <div class="page-shell">
      <header class="hero">
        <p class="eyebrow">LV3 Platform</p>
        <h1>{escape(title)}</h1>
        <p class="subtitle">{escape(subtitle)}</p>
        {help_html}
      </header>
      <nav class="nav-bar">
        {"".join(nav_html)}
      </nav>
      <main class="page-content">
        {body}
      </main>
    </div>
    <script>
      (() => {{
        const body = document.body;
        const toggle = document.querySelector("[data-contextual-help-toggle]");
        const drawer = document.getElementById("contextual-help-drawer");
        const dismissButtons = document.querySelectorAll("[data-contextual-help-dismiss]");
        if (!toggle || !drawer) {{
          return;
        }}
        function setOpen(isOpen) {{
          toggle.setAttribute("aria-expanded", String(isOpen));
          drawer.hidden = !isOpen;
          dismissButtons.forEach((button) => {{
            if (button instanceof HTMLElement && button.classList.contains("contextual-help-overlay")) {{
              button.hidden = !isOpen;
            }}
          }});
          body.classList.toggle("contextual-help-open", isOpen);
        }}
        toggle.addEventListener("click", () => setOpen(toggle.getAttribute("aria-expanded") !== "true"));
        dismissButtons.forEach((button) => {{
          button.addEventListener("click", () => setOpen(false));
        }});
        document.addEventListener("keydown", (event) => {{
          if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {{
            setOpen(false);
            toggle.focus();
          }}
        }});
      }})();
    </script>
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

.contextual-help-shell {
  margin-top: 18px;
}

.contextual-help-toggle,
.contextual-help-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.88);
  color: var(--ink);
  font: inherit;
  cursor: pointer;
}

.contextual-help-overlay {
  position: fixed;
  inset: 0;
  background: rgba(31, 37, 32, 0.3);
  z-index: 18;
}

.contextual-help-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(28rem, 92vw);
  padding: 24px 20px 28px;
  border-left: 1px solid var(--line);
  background: rgba(255, 251, 244, 0.98);
  box-shadow: var(--shadow);
  overflow-y: auto;
  z-index: 19;
}

.contextual-help-header,
.contextual-help-escalation-row,
.contextual-help-link-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.contextual-help-header {
  align-items: start;
}

.contextual-help-audience,
.contextual-help-block {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.contextual-help-block-accent {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid var(--line);
  background: rgba(20, 90, 74, 0.06);
}

.contextual-help-title {
  margin: 0;
  font-size: 1.15rem;
}

.contextual-help-list,
.contextual-help-links {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}

.contextual-help-list-item,
.contextual-help-link-row {
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: var(--panel-strong);
}

.contextual-help-list-item {
  display: grid;
  gap: 6px;
}

.contextual-help-list-item a,
.contextual-help-link-row a {
  font-weight: bold;
}

.contextual-help-link-row {
  align-items: center;
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
