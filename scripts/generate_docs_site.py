#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from adr_catalog import resolve_service_adr_path
from api_publication import load_api_publication_catalog
from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from dependency_graph import load_dependency_graph, render_dependency_page
from ops_portal.contextual_help import build_docs_page_help, glossary_reference_rows, site_path_to_browser_href


SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
SECRET_CATALOG_PATH = repo_path("config", "secret-catalog.json")
VERSIONS_STACK_PATH = repo_path("versions", "stack.yaml")
CHANGELOG_PATH = repo_path("changelog.md")
VERSION_PATH = repo_path("VERSION")
ADR_DIR = repo_path("docs", "adr")
RUNBOOK_DIR = repo_path("docs", "runbooks")
RELEASE_NOTES_DIR = repo_path("docs", "release-notes")
SITE_SOURCE_DOCS = {
    repo_path("docs", "index.md"),
    repo_path("docs", "upgrade", "v1.md"),
}
SITE_GENERATED_DIR = repo_path("docs", "site-generated")
TEMPLATE_DIR = repo_path("docs", "templates")
OPENAPI_DEFAULT_URL = "https://api.localhost/v1/openapi.json"
REPO_ROOT = repo_path()
LINK_PATTERN = re.compile(r"(!?\[[^\]]*])\(([^)]+)\)")
SENSITIVITY_LEVELS = ("PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL")
DEFAULT_SENSITIVITY = "INTERNAL"
SOURCE_ONLY_SENSITIVITY = {"CONFIDENTIAL"}


@dataclass(frozen=True)
class PortalDocument:
    source_path: Path
    title: str
    metadata: dict[str, str]
    content: str
    sensitivity: str
    portal_summary: str
    justification: str | None
    portal_display: str
    publish_in_portal: bool


def build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )


def render_template(template_name: str, **context: Any) -> str:
    return build_env().get_template(template_name).render(**context).strip() + "\n"


def read_h1(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").title()


def parse_metadata_block(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            if metadata:
                break
            continue
        key, _, value = line[2:].partition(":")
        if not value:
            continue
        metadata[key.strip()] = value.strip()
    return metadata


def split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---\n"):
        return {}, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}, content

    metadata: dict[str, str] = {}
    for line in content[4:end].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        if not value:
            continue
        metadata[key.strip().lower()] = value.strip().strip("'\"")
    return metadata, content[end + 5 :]


def strip_leading_metadata_block(content: str) -> str:
    lines = content.splitlines()
    heading_index = next((index for index, line in enumerate(lines) if line.startswith("# ")), None)
    if heading_index is None:
        return content

    index = heading_index + 1
    while index < len(lines) and not lines[index].strip():
        index += 1

    block_start = index
    while index < len(lines) and lines[index].startswith("- "):
        index += 1
    if index == block_start:
        return content

    while index < len(lines) and not lines[index].strip():
        index += 1

    stripped_lines = lines[:block_start] + lines[index:]
    stripped = "\n".join(stripped_lines)
    if content.endswith("\n"):
        stripped += "\n"
    return stripped


def normalize_sensitivity(raw_value: str | None) -> str:
    if not raw_value:
        return DEFAULT_SENSITIVITY
    candidate = raw_value.strip().upper()
    if candidate not in SENSITIVITY_LEVELS:
        raise ValueError(f"unsupported sensitivity classification: {raw_value}")
    return candidate


def metadata_value(frontmatter: dict[str, str], metadata: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if frontmatter.get(key):
            return frontmatter[key]
        if metadata.get(key):
            return metadata[key]
    return None


def first_content_paragraph(content: str) -> str:
    paragraphs = re.split(r"\n\s*\n", strip_leading_metadata_block(content).strip())
    for paragraph in paragraphs:
        candidate = " ".join(paragraph.strip().split())
        if not candidate or candidate.startswith("#"):
            continue
        return candidate
    return ""


def default_portal_summary(path: Path, title: str, sensitivity: str) -> str:
    if sensitivity == "RESTRICTED":
        doc_type = "runbook" if path.parent.name == "runbooks" else "architecture decision"
        return f"Sensitive {doc_type} summary for {title}. Full content is reserved for platform administrators."
    if sensitivity == "CONFIDENTIAL":
        return (
            f"{title} is classified as confidential and is intentionally excluded from the published developer portal."
        )
    return ""


def pagefind_section(target_path: Path) -> str:
    if target_path == Path("index.md"):
        return "home"
    if target_path == Path("changelog.md"):
        return "changelog"
    if not target_path.parts:
        return "home"
    if target_path.parts[0] == "upgrade":
        return "upgrade"
    return target_path.parts[0]


def pagefind_audiences(target_path: Path) -> list[str]:
    section = pagefind_section(target_path)
    audiences = {
        "api": ["integrators", "operators"],
        "architecture": ["contributors", "operators"],
        "changelog": ["operators", "contributors"],
        "home": ["operators", "contributors"],
        "reference": ["operators", "contributors"],
        "releases": ["operators", "contributors"],
        "runbooks": ["operators"],
        "services": ["operators", "contributors"],
        "upgrade": ["operators"],
    }
    return audiences.get(section, ["operators"])


def pagefind_metadata(
    target_path: Path,
    *,
    service: str | None = None,
    capabilities: list[str] | None = None,
) -> dict[str, str | list[str]]:
    metadata: dict[str, str | list[str]] = {
        "pagefind_section": pagefind_section(target_path),
        "pagefind_audience": pagefind_audiences(target_path),
    }
    if service:
        metadata["pagefind_service"] = service
    if capabilities:
        metadata["pagefind_capability"] = capabilities
    return metadata


def build_portal_document(path: Path) -> PortalDocument:
    raw_content = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(raw_content)
    metadata = parse_metadata_block(path)
    title = read_h1(path)
    sensitivity = normalize_sensitivity(metadata_value(frontmatter, metadata, "sensitivity", "Sensitivity"))
    justification = metadata_value(frontmatter, metadata, "justification", "Justification")
    portal_summary = metadata_value(
        frontmatter,
        metadata,
        "portal_summary",
        "summary",
        "Portal Summary",
        "Summary",
    )
    if portal_summary is None and sensitivity in {"PUBLIC", "INTERNAL"}:
        portal_summary = first_content_paragraph(body)
    if not portal_summary:
        portal_summary = default_portal_summary(path, title, sensitivity)

    portal_display = "full"
    publish_in_portal = True
    if sensitivity == "RESTRICTED":
        portal_display = "summary"
    elif sensitivity == "CONFIDENTIAL":
        portal_display = "hidden"
        publish_in_portal = False

    return PortalDocument(
        source_path=path,
        title=title,
        metadata=metadata,
        content=body,
        sensitivity=sensitivity,
        portal_summary=portal_summary,
        justification=justification,
        portal_display=portal_display,
        publish_in_portal=publish_in_portal,
    )


def build_page_frontmatter(
    *,
    sensitivity: str,
    portal_display: str,
    tags: list[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    search_exclude: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "sensitivity": sensitivity,
        "portal_display": portal_display,
    }
    if tags:
        payload["tags"] = tags
    if extra_metadata:
        payload.update(extra_metadata)
    if search_exclude:
        payload["search"] = {"exclude": True}
    rendered = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{rendered}\n---\n\n"


def portal_notice(document: PortalDocument) -> str:
    if document.sensitivity == "PUBLIC":
        return (
            '!!! note "Sensitivity: PUBLIC"\n'
            "    This page is safe to share externally and is fully visible in the developer portal.\n"
        )
    if document.sensitivity == "INTERNAL":
        return (
            '!!! note "Sensitivity: INTERNAL"\n'
            "    This page is intended for authenticated operators and internal collaborators.\n"
        )
    if document.sensitivity == "RESTRICTED":
        lines = [
            '!!! warning "Sensitivity: RESTRICTED"',
            "    The developer portal publishes only a summary for this document.",
            "    Request temporary platform-admin access through `#platform-admin` when the full source is needed.",
        ]
        if document.justification:
            lines.append(f"    Justification: {document.justification}")
        return "\n".join(lines) + "\n"
    return (
        '!!! danger "Sensitivity: CONFIDENTIAL"\n'
        "    This document is intentionally excluded from the published developer portal.\n"
    )


def render_portal_document(document: PortalDocument, target_path: Path) -> str:
    section = pagefind_section(target_path)
    frontmatter = build_page_frontmatter(
        sensitivity=document.sensitivity,
        portal_display=document.portal_display,
        tags=[document.sensitivity.lower(), section],
        extra_metadata={
            **pagefind_metadata(target_path),
            "contextual_help": build_docs_page_help(target_path=target_path, title=document.title),
        },
        search_exclude=document.sensitivity == "CONFIDENTIAL",
    )
    notice = portal_notice(document)

    if document.portal_display == "summary":
        summary = document.portal_summary or default_portal_summary(
            document.source_path,
            document.title,
            document.sensitivity,
        )
        body = f"# {document.title}\n\n{notice}\n## Portal Summary\n\n{summary}\n"
        return frontmatter + body

    rewritten = rewrite_markdown_links(document.content, document.source_path, target_path)
    return frontmatter + notice + "\n" + rewritten.lstrip()


def wrap_generated_page(
    content: str,
    *,
    target_path: Path,
    sensitivity: str,
    portal_display: str = "full",
    tags: list[str] | None = None,
    pagefind_service: str | None = None,
    pagefind_capabilities: list[str] | None = None,
    contextual_help: dict[str, Any] | None = None,
) -> str:
    normalized_content = content.lstrip()
    normalized_content = re.sub(r"\A---\n.*?\n---\n+", "", normalized_content, count=1, flags=re.DOTALL)
    normalized_content = re.sub(
        r'\A!!! (?:note|warning|danger) "Sensitivity: [^"]+"\n(?: {4}.*\n)+\n*',
        "",
        normalized_content,
        count=1,
    )
    frontmatter = build_page_frontmatter(
        sensitivity=sensitivity,
        portal_display=portal_display,
        tags=tags,
        extra_metadata={
            **pagefind_metadata(
                target_path,
                service=pagefind_service,
                capabilities=pagefind_capabilities,
            ),
            "contextual_help": contextual_help
            or build_docs_page_help(target_path=target_path, title=target_path.stem.replace("-", " ").title()),
        },
    )
    notice = portal_notice(
        PortalDocument(
            source_path=REPO_ROOT,
            title="Generated page",
            metadata={},
            content=content,
            sensitivity=sensitivity,
            portal_summary="",
            justification=None,
            portal_display=portal_display,
            publish_in_portal=True,
        )
    )
    return frontmatter + notice + "\n" + normalized_content.lstrip()


@lru_cache(maxsize=1)
def repo_remote_url() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    remote = result.stdout.strip()
    if remote.startswith("git@github.com:"):
        return "https://github.com/" + remote.removeprefix("git@github.com:").removesuffix(".git")
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    return ""


@lru_cache(maxsize=1)
def known_repo_roots() -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    roots = {REPO_ROOT}
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            roots.add(Path(line.removeprefix("worktree ").strip()))
    return tuple(sorted(roots))


def repo_view_link(path: Path) -> str:
    remote = repo_remote_url()
    if remote:
        try:
            relative = path.relative_to(REPO_ROOT)
        except ValueError:
            return str(path)
        return f"{remote}/blob/main/{relative.as_posix()}"
    return str(path)


def site_path_for_repo_path(path: Path) -> Path | None:
    try:
        relative = path.relative_to(REPO_ROOT)
    except ValueError:
        return None

    if relative == Path("changelog.md"):
        return Path("changelog.md")
    if relative == Path("docs/index.md"):
        return Path("index.md")
    if relative == Path("docs/upgrade/v1.md"):
        return Path("upgrade/v1.md")
    if relative == Path("docs/adr"):
        return Path("architecture", "index.md")
    if relative == Path("docs/runbooks"):
        return Path("runbooks", "index.md")
    if relative == Path("docs/release-notes"):
        return Path("releases", "index.md")
    if relative.parts[:2] == ("docs", "adr"):
        return Path("architecture", "decisions", relative.name)
    if relative.parts[:2] == ("docs", "runbooks"):
        if len(relative.parts) == 2:
            return Path("runbooks", "index.md")
        return Path("runbooks", relative.name)
    if relative.parts[:2] == ("docs", "release-notes"):
        if len(relative.parts) == 2:
            return Path("releases", "index.md")
        if relative.name == "README.md":
            return Path("releases", "index.md")
        return Path("releases", relative.name)
    return None


def relative_site_link(current: Path, destination: Path) -> str:
    return Path(*([".."] * len(current.parent.parts) + list(destination.parts))).as_posix()


def resolve_repo_target(source_path: Path, raw_target: str) -> Path | None:
    if raw_target.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return None
    candidate = raw_target
    candidate_path = Path(raw_target)
    for root in known_repo_roots():
        try:
            return REPO_ROOT / candidate_path.relative_to(root)
        except ValueError:
            continue
    if raw_target.startswith("/"):
        return None
    path = (source_path.parent / candidate).resolve()
    try:
        path.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return path


def rewrite_markdown_links(content: str, source_path: Path, target_site_path: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        label, raw_link = match.groups()
        link = raw_link.strip()
        if link.startswith(("http://", "https://", "mailto:", "tel:", "#")):
            return match.group(0)
        if any(marker in link for marker in ("{{", "}}", "{%", "%}")):
            return match.group(0)

        target, anchor = (link.split("#", 1) + [""])[:2]
        resolved = resolve_repo_target(source_path, target)
        if resolved is None and target.startswith(str(REPO_ROOT)):
            resolved = Path(target)
        if resolved is None:
            return match.group(0)

        mapped = site_path_for_repo_path(resolved)
        if mapped is not None:
            rewritten = relative_site_link(target_site_path, mapped)
            if anchor:
                rewritten = f"{rewritten}#{anchor}"
            return f"{label}({rewritten})"

        rewritten = repo_view_link(resolved)
        if anchor:
            rewritten = f"{rewritten}#{anchor}"
        return f"{label}({rewritten})"

    return LINK_PATTERN.sub(replace, content)


def reset_generated_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def write_generated(output_dir: Path, relative_path: str | Path, content: str) -> None:
    target = output_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def copy_transformed_markdown(output_dir: Path, source_path: Path, target_path: Path) -> None:
    content = source_path.read_text(encoding="utf-8")
    rewritten = rewrite_markdown_links(content, source_path, target_path)
    write_generated(output_dir, target_path, rewritten)


def version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in path.stem.split("."))


def default_port_for_scheme(scheme: str) -> int | None:
    return {
        "http": 80,
        "https": 443,
        "ssh": 22,
        "postgres": 5432,
    }.get(scheme)


def port_from_url(url: str) -> int | None:
    parsed = urlparse(url)
    if parsed.port is not None:
        return parsed.port
    return default_port_for_scheme(parsed.scheme)


def portal_document_lookup(directory: Path) -> dict[Path, PortalDocument]:
    return {path: build_portal_document(path) for path in sorted(directory.glob("*.md"))}


def subdomains_by_service(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["service_id"]].append(entry)
    return grouped


def secret_lookup() -> dict[str, dict[str, Any]]:
    return {secret["id"]: secret for secret in load_json(SECRET_CATALOG_PATH)["secrets"]}


def service_port_rows(
    service: dict[str, Any],
    service_subdomains: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for surface_name, url in (
        ("public", service.get("public_url")),
        ("internal", service.get("internal_url")),
    ):
        if not url:
            continue
        port = port_from_url(url)
        if port is None or (surface_name, port) in seen:
            continue
        seen.add((surface_name, port))
        rows.append(
            {
                "surface": surface_name,
                "port": port,
                "endpoint": url,
                "source": "service-capability-catalog",
            }
        )

    for entry in sorted(service_subdomains, key=lambda item: item["fqdn"]):
        port = entry.get("target_port")
        if not isinstance(port, int) or ("subdomain", port) in seen:
            continue
        seen.add(("subdomain", port))
        rows.append(
            {
                "surface": entry["fqdn"],
                "port": port,
                "endpoint": f"{entry['target']}:{port}",
                "source": "subdomain-catalog",
            }
        )
    return rows


def build_service_page_context(
    service: dict[str, Any],
    *,
    adr_documents: dict[Path, PortalDocument],
    service_subdomains: list[dict[str, Any]],
    secrets: dict[str, dict[str, Any]],
    runbook_documents: dict[Path, PortalDocument],
) -> dict[str, Any]:
    adr_link = None
    adr_path = resolve_service_adr_path(service)
    if adr_path is not None:
        if adr_documents.get(adr_path, build_portal_document(adr_path)).publish_in_portal:
            adr_link = relative_site_link(
                Path("services") / f"{service['id']}.md",
                site_path_for_repo_path(adr_path) or Path(),
            )

    runbook_link = None
    runbook_title = None
    runbook_path = repo_path(service["runbook"]) if service.get("runbook") else None
    if runbook_path and runbook_path.exists():
        document = runbook_documents.get(runbook_path, build_portal_document(runbook_path))
        mapped = site_path_for_repo_path(runbook_path)
        if mapped is not None and document.publish_in_portal:
            runbook_link = relative_site_link(Path("services") / f"{service['id']}.md", mapped)
            runbook_title = read_h1(runbook_path)

    secret_refs = []
    for secret_id in service.get("secret_catalog_ids", []):
        secret = secrets.get(secret_id)
        if not secret:
            continue
        rotation_days = secret.get("rotation_period_days")
        rotation_summary = f"every {rotation_days} days" if rotation_days else secret.get("rotation_mode", "n/a")
        secret_refs.append(
            {
                "id": secret["id"],
                "storage_contract": secret.get("storage_contract", "n/a"),
                "rotation_summary": rotation_summary,
            }
        )

    environments = []
    for environment, binding in sorted(service.get("environments", {}).items()):
        environments.append(
            {
                "environment": environment,
                "status": binding["status"],
                "url": binding.get("url"),
                "notes": binding.get("notes", "n/a"),
            }
        )

    subdomain_rows = [
        {
            "fqdn": item["fqdn"],
            "status": item["status"],
            "exposure": item["exposure"],
            "tls_provider": item["tls"]["provider"],
            "notes": item.get("notes", "n/a"),
        }
        for item in sorted(service_subdomains, key=lambda row: row["fqdn"])
    ]

    page_context = dict(service)
    page_context.update(
        {
            "adr_link": adr_link,
            "runbook_link": runbook_link,
            "runbook_title": runbook_title,
            "secret_refs": secret_refs,
            "environments": environments,
            "subdomains": subdomain_rows,
            "ports": service_port_rows(service, service_subdomains),
        }
    )
    return page_context


def build_services_index_context(
    services: list[dict[str, Any]],
    *,
    adr_documents: dict[Path, PortalDocument],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    totals = {
        "services": len(services),
        "public_services": sum(1 for service in services if service.get("public_url")),
        "private_services": sum(1 for service in services if service["exposure"] == "private-only"),
    }

    for service in services:
        adr_path = resolve_service_adr_path(service)
        grouped[service["category"]].append(
            {
                **service,
                "link": f"{service['id']}.md",
                "primary_url": service.get("public_url") or service.get("internal_url"),
                "adr_link": (
                    relative_site_link(
                        Path("services/index.md"),
                        site_path_for_repo_path(adr_path) or Path(),
                    )
                    if (
                        adr_path is not None
                        and adr_documents.get(adr_path, build_portal_document(adr_path)).publish_in_portal
                    )
                    else None
                ),
            }
        )

    categories = [
        {
            "name": category.replace("_", " ").title(),
            "services": sorted(items, key=lambda item: item["name"]),
        }
        for category, items in sorted(grouped.items())
    ]
    return {"totals": totals, "categories": categories}


def render_runbook_pages(output_dir: Path) -> list[dict[str, str]]:
    runbook_items = []
    featured_stems = {
        "deploy-a-service",
        "rotate-certificates",
        "add-a-new-service",
        "break-glass-recovery",
    }
    featured = []

    for path, document in portal_document_lookup(RUNBOOK_DIR).items():
        if not document.publish_in_portal:
            continue
        target = Path("runbooks", path.name)
        write_generated(output_dir, target, render_portal_document(document, target))
        item = {
            "title": document.title,
            "link": path.name,
            "stem": path.stem,
            "sensitivity": document.sensitivity,
            "portal_display": document.portal_display,
        }
        runbook_items.append(item)
        if path.stem in featured_stems:
            featured.append(
                {
                    "title": item["title"],
                    "link": item["link"],
                    "sensitivity": item["sensitivity"],
                    "portal_display": item["portal_display"],
                }
            )

    runbook_items.sort(key=lambda item: item["title"])
    featured.sort(key=lambda item: item["title"])
    write_generated(
        output_dir,
        "runbooks/index.md",
        wrap_generated_page(
            render_template("runbooks-index.md.j2", featured=featured, runbooks=runbook_items),
            target_path=Path("runbooks", "index.md"),
            sensitivity="INTERNAL",
            tags=["runbooks", "index"],
        ),
    )
    return runbook_items


def render_adr_pages(output_dir: Path) -> list[dict[str, str]]:
    entries = []
    sensitivity_totals = {level: 0 for level in SENSITIVITY_LEVELS}
    for path, document in portal_document_lookup(ADR_DIR).items():
        sensitivity_totals[document.sensitivity] += 1
        if not document.publish_in_portal:
            continue
        target = Path("architecture", "decisions", path.name)
        write_generated(output_dir, target, render_portal_document(document, target))
        metadata = document.metadata
        entries.append(
            {
                "id": path.name.split("-", 1)[0],
                "title": document.title.split(": ", 1)[-1],
                "status": metadata.get("Status", "unknown"),
                "implementation_status": metadata.get("Implementation Status", "unknown"),
                "sensitivity": document.sensitivity,
                "portal_display": document.portal_display,
                "link": f"decisions/{path.name}",
            }
        )

    totals = {
        "total": len(entries),
        "implemented": sum(1 for entry in entries if entry["implementation_status"] == "Implemented"),
        "proposed": sum(1 for entry in entries if entry["status"] == "Proposed"),
        "public": sensitivity_totals["PUBLIC"],
        "internal": sensitivity_totals["INTERNAL"],
        "restricted": sensitivity_totals["RESTRICTED"],
        "confidential": sensitivity_totals["CONFIDENTIAL"],
    }
    write_generated(
        output_dir,
        "architecture/index.md",
        wrap_generated_page(
            render_template(
                "architecture-index.md.j2",
                totals=totals,
                adrs=entries,
                generated_pages=[
                    {
                        "title": "Service Dependency Graph",
                        "description": "Recovery tiers and Mermaid service-dependency diagram generated from config/dependency-graph.json.",
                        "link": "dependency-graph.md",
                    }
                ],
            ),
            target_path=Path("architecture", "index.md"),
            sensitivity="INTERNAL",
            tags=["architecture", "index"],
        ),
    )
    return entries


def render_dependency_graph_page(output_dir: Path) -> None:
    graph = load_dependency_graph(validate_schema=True)
    write_generated(
        output_dir,
        Path("architecture", "dependency-graph.md"),
        wrap_generated_page(
            render_dependency_page(graph),
            target_path=Path("architecture", "dependency-graph.md"),
            sensitivity="INTERNAL",
            tags=["architecture", "dependency-graph"],
        ),
    )


def render_release_notes(output_dir: Path) -> list[dict[str, str]]:
    releases = []
    readme_path = RELEASE_NOTES_DIR / "README.md"
    if readme_path.exists():
        content = rewrite_markdown_links(
            readme_path.read_text(encoding="utf-8"),
            readme_path,
            Path("releases", "index-source.md"),
        )
        write_generated(
            output_dir,
            Path("releases", "index-source.md"),
            wrap_generated_page(
                content,
                target_path=Path("releases", "index-source.md"),
                sensitivity="INTERNAL",
                tags=["releases", "source"],
            ),
        )

    for path in sorted(RELEASE_NOTES_DIR.glob("[0-9]*.md"), key=version_key, reverse=True):
        target = Path("releases", path.name)
        content = rewrite_markdown_links(path.read_text(encoding="utf-8"), path, target)
        write_generated(
            output_dir,
            target,
            wrap_generated_page(
                content,
                target_path=target,
                sensitivity="INTERNAL",
                tags=["releases"],
            ),
        )
        date = "unknown"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- Date: "):
                date = line.removeprefix("- Date: ").strip()
                break
        releases.append({"version": path.stem, "date": date, "link": path.name})

    write_generated(
        output_dir,
        "releases/index.md",
        wrap_generated_page(
            render_template("releases-index.md.j2", releases=releases),
            target_path=Path("releases", "index.md"),
            sensitivity="INTERNAL",
            tags=["releases", "index"],
        ),
    )
    stale_readme = output_dir / "releases" / "index-source.md"
    if stale_readme.exists():
        stale_readme.unlink()
    return releases


def render_reference_pages(
    output_dir: Path,
    *,
    services: list[dict[str, Any]],
    subdomains: list[dict[str, Any]],
    secrets: dict[str, dict[str, Any]],
) -> None:
    write_generated(
        output_dir,
        "reference/index.md",
        wrap_generated_page(
            render_template("reference-index.md.j2"),
            target_path=Path("reference", "index.md"),
            sensitivity="INTERNAL",
            tags=["reference", "index"],
        ),
    )

    write_generated(
        output_dir,
        "reference/glossary.md",
        wrap_generated_page(
            render_template("reference-glossary.md.j2", rows=glossary_reference_rows()),
            target_path=Path("reference", "glossary.md"),
            sensitivity="INTERNAL",
            tags=["reference", "glossary"],
            contextual_help=build_docs_page_help(target_path=Path("reference", "glossary.md"), title="Glossary"),
        ),
    )

    subdomains_index = subdomains_by_service(subdomains)
    port_rows = []
    for service in sorted(
        services,
        key=lambda item: (
            min((row["port"] for row in service_port_rows(item, subdomains_index.get(item["id"], []))), default=0),
            item["name"],
        ),
    ):
        for row in service_port_rows(service, subdomains_index.get(service["id"], [])):
            port_rows.append(
                {
                    "service_name": service["name"],
                    "service_link": f"../services/{service['id']}.md",
                    "surface": row["surface"],
                    "port": row["port"],
                    "endpoint": row["endpoint"],
                }
            )
    port_rows.sort(key=lambda row: (row["port"], row["service_name"], row["surface"]))
    write_generated(
        output_dir,
        "reference/ports.md",
        wrap_generated_page(
            render_template("reference-ports.md.j2", rows=port_rows),
            target_path=Path("reference", "ports.md"),
            sensitivity="INTERNAL",
            tags=["reference", "ports"],
        ),
    )

    service_names = {service["id"]: service["name"] for service in services}
    subdomain_rows = []
    for entry in sorted(subdomains, key=lambda item: item["fqdn"]):
        service_id = entry["service_id"]
        subdomain_rows.append(
            {
                "fqdn": entry["fqdn"],
                "service_name": service_names.get(service_id, service_id),
                "service_link": f"../services/{service_id}.md" if service_id in service_names else None,
                "status": entry["status"],
                "exposure": entry["exposure"],
                "auth_requirement": entry["auth_requirement"],
                "target": entry["target"],
                "target_port": entry["target_port"],
                "tls_provider": entry["tls"]["provider"],
            }
        )
    write_generated(
        output_dir,
        "reference/subdomains.md",
        wrap_generated_page(
            render_template("reference-subdomains.md.j2", rows=subdomain_rows),
            target_path=Path("reference", "subdomains.md"),
            sensitivity="INTERNAL",
            tags=["reference", "subdomains"],
        ),
    )

    identity_taxonomy = load_yaml(VERSIONS_STACK_PATH)["desired_state"]["identity_taxonomy"]
    classes = []
    for class_id, item in sorted(identity_taxonomy["classes"].items()):
        classes.append(
            {
                "id": class_id,
                "interactive_use": item["interactive_use"],
                "automation_use": item["automation_use"],
                "description": item["description"],
            }
        )
    identities = []
    for item in identity_taxonomy["managed_identities"]:
        identities.append(
            {
                "id": item["id"],
                "principal": item["principal"],
                "class": item["class"],
                "owner": item["owner"],
                "purpose": item["purpose"],
            }
        )
    write_generated(
        output_dir,
        "reference/identities.md",
        wrap_generated_page(
            render_template("reference-identities.md.j2", classes=classes, identities=identities),
            target_path=Path("reference", "identities.md"),
            sensitivity="INTERNAL",
            tags=["reference", "identities"],
        ),
    )

    secret_rows = []
    for secret in sorted(secrets.values(), key=lambda item: item["id"]):
        rotation_days = secret.get("rotation_period_days")
        rotation_summary = f"every {rotation_days} days" if rotation_days else secret.get("rotation_mode", "n/a")
        secret_rows.append(
            {
                "id": secret["id"],
                "owner_service": secret.get("owner_service", "n/a"),
                "storage_contract": secret.get("storage_contract", "n/a"),
                "rotation_summary": rotation_summary,
            }
        )
    write_generated(
        output_dir,
        "reference/secrets.md",
        wrap_generated_page(
            render_template("reference-secrets.md.j2", secrets=secret_rows),
            target_path=Path("reference", "secrets.md"),
            sensitivity="INTERNAL",
            tags=["reference", "secrets"],
        ),
    )


def extract_unreleased_section(changelog_text: str) -> str:
    match = re.search(r"^## Unreleased\n(?P<body>.*?)(?:\n## |\Z)", changelog_text, re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return match.group("body").strip()


def fetch_openapi_snapshot(url: str | None, *, timeout: float = 5.0) -> tuple[dict[str, Any], str]:
    if url:
        try:
            request = Request(url, headers={"User-Agent": "lv3-docs-generator"})
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload, url
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            pass

    _catalog, _tiers, surfaces = load_api_publication_catalog()
    paths = {}
    for surface in surfaces:
        if not surface["endpoint"].startswith("/"):
            continue
        paths.setdefault(
            surface["endpoint"],
            {
                "get": {
                    "summary": surface["title"],
                    "responses": {
                        "200": {"description": "Successful response."},
                    },
                }
            },
        )
    return (
        {
            "openapi": "3.1.0",
            "info": {
                "title": "LV3 Platform API",
                "version": VERSION_PATH.read_text(encoding="utf-8").strip(),
                "description": "Fallback OpenAPI snapshot generated from the API publication catalog.",
            },
            "servers": [{"url": "https://api.localhost"}],
            "paths": paths,
        },
        "fallback:config/api-publication.json",
    )


def render_api_pages(output_dir: Path, openapi_url: str | None) -> None:
    api_gateway_catalog_missing = not repo_path("config", "api-gateway-catalog.json").exists()
    _catalog, _tiers, surfaces = load_api_publication_catalog()
    snapshot, source = fetch_openapi_snapshot(openapi_url)

    output_path = output_dir / "api" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    surface_rows = []
    for surface in surfaces:
        surface_rows.append(
            {
                "id": surface["id"],
                "publication_tier": surface["publication_tier"],
                "lane": surface["lane"],
                "endpoint": surface["endpoint"],
                "public_hostnames": ", ".join(surface["public_hostnames"]) if surface["public_hostnames"] else "n/a",
            }
        )

    write_generated(
        output_dir,
        "api/index.md",
        wrap_generated_page(
            render_template(
                "api-index.md.j2",
                catalog_missing=api_gateway_catalog_missing,
                surfaces=surface_rows,
                openapi_source=source,
            ),
            target_path=Path("api", "index.md"),
            sensitivity="PUBLIC",
            tags=["api", "index"],
        ),
    )
    write_generated(
        output_dir,
        "api/openapi.md",
        wrap_generated_page(
            render_template("openapi-page.md.j2"),
            target_path=Path("api", "openapi.md"),
            sensitivity="PUBLIC",
            tags=["api", "openapi"],
        ),
    )


def render_changelog_page(output_dir: Path, releases: list[dict[str, str]]) -> None:
    changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")
    write_generated(
        output_dir,
        "changelog.md",
        wrap_generated_page(
            render_template(
                "changelog.md.j2",
                current_version=VERSION_PATH.read_text(encoding="utf-8").strip(),
                releases=releases,
                unreleased=extract_unreleased_section(changelog_text),
            ),
            target_path=Path("changelog.md"),
            sensitivity="INTERNAL",
            tags=["releases", "changelog"],
        ),
    )


def render_home_and_upgrade(output_dir: Path) -> None:
    for path in SITE_SOURCE_DOCS:
        target_path = site_path_for_repo_path(path) or Path(path.name)
        content = rewrite_markdown_links(path.read_text(encoding="utf-8"), path, target_path)
        write_generated(
            output_dir,
            target_path,
            wrap_generated_page(
                content,
                target_path=target_path,
                sensitivity="INTERNAL",
                tags=[pagefind_section(target_path)],
            ),
        )


def render_services(output_dir: Path) -> None:
    services = load_json(SERVICE_CATALOG_PATH)["services"]
    adr_documents = portal_document_lookup(ADR_DIR)
    runbook_documents = portal_document_lookup(RUNBOOK_DIR)
    subdomains = load_json(SUBDOMAIN_CATALOG_PATH)["subdomains"]
    secrets = secret_lookup()
    grouped_subdomains = subdomains_by_service(subdomains)

    for service in sorted(services, key=lambda item: item["name"]):
        context = build_service_page_context(
            service,
            adr_documents=adr_documents,
            service_subdomains=grouped_subdomains.get(service["id"], []),
            secrets=secrets,
            runbook_documents=runbook_documents,
        )
        write_generated(
            output_dir,
            Path("services", f"{service['id']}.md"),
            wrap_generated_page(
                render_template("service-page.md.j2", service=context),
                target_path=Path("services", f"{service['id']}.md"),
                sensitivity="INTERNAL",
                tags=["services", service["id"]],
                pagefind_service=service["id"],
                pagefind_capabilities=service.get("tags", []),
                contextual_help=build_docs_page_help(
                    target_path=Path("services", f"{service['id']}.md"),
                    title=str(service.get("name", service["id"])),
                    service=context,
                    runbook_href=(
                        site_path_to_browser_href("", site_path_for_repo_path(repo_path(service["runbook"])))
                        if service.get("runbook") and site_path_for_repo_path(repo_path(service["runbook"])) is not None
                        else None
                    ),
                    runbook_title=context.get("runbook_title"),
                    adr_href=(
                        site_path_to_browser_href("", site_path_for_repo_path(resolve_service_adr_path(service)))
                        if resolve_service_adr_path(service) is not None
                        and site_path_for_repo_path(resolve_service_adr_path(service)) is not None
                        else None
                    ),
                    adr_id=str(service.get("adr")) if service.get("adr") else None,
                ),
            ),
        )

    write_generated(
        output_dir,
        "services/index.md",
        wrap_generated_page(
            render_template(
                "services-index.md.j2",
                **build_services_index_context(services, adr_documents=adr_documents),
            ),
            target_path=Path("services", "index.md"),
            sensitivity="INTERNAL",
            tags=["services", "index"],
        ),
    )
    render_reference_pages(output_dir, services=services, subdomains=subdomains, secrets=secrets)


def render_site(output_dir: Path, *, openapi_url: str | None = OPENAPI_DEFAULT_URL) -> None:
    reset_generated_dir(output_dir)
    render_home_and_upgrade(output_dir)
    render_runbook_pages(output_dir)
    render_adr_pages(output_dir)
    render_dependency_graph_page(output_dir)
    releases = render_release_notes(output_dir)
    render_services(output_dir)
    render_api_pages(output_dir, openapi_url)
    render_changelog_page(output_dir, releases)


def validate_site(output_dir: Path) -> None:
    expected = [
        output_dir / "index.md",
        output_dir / "services" / "index.md",
        output_dir / "services" / "keycloak.md",
        output_dir / "runbooks" / "index.md",
        output_dir / "architecture" / "index.md",
        output_dir / "architecture" / "dependency-graph.md",
        output_dir / "reference" / "ports.md",
        output_dir / "reference" / "glossary.md",
        output_dir / "api" / "index.md",
        output_dir / "api" / "openapi.md",
        output_dir / "api" / "openapi.json",
        output_dir / "releases" / "index.md",
        output_dir / "changelog.md",
    ]
    for path in expected:
        if not path.exists():
            raise ValueError(f"missing generated docs artifact: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the MkDocs source tree for docs.localhost.")
    parser.add_argument("--write", action="store_true", help="Write generated site source into docs/site-generated.")
    parser.add_argument(
        "--check", action="store_true", help="Generate into a temp dir and validate the expected artifacts."
    )
    parser.add_argument(
        "--output-dir",
        help="Optional output directory to use with --write instead of docs/site-generated.",
    )
    parser.add_argument(
        "--openapi-url", default=OPENAPI_DEFAULT_URL, help="OpenAPI schema URL to snapshot before build."
    )
    args = parser.parse_args(argv)

    if not args.write and not args.check:
        parser.error("choose --write or --check")

    try:
        if args.write:
            output_dir = Path(args.output_dir).resolve() if args.output_dir else SITE_GENERATED_DIR
            render_site(output_dir, openapi_url=args.openapi_url)
            validate_site(output_dir)
            print(f"Generated docs site source: {output_dir}")
            return 0

        with tempfile.TemporaryDirectory(prefix="lv3-docs-site-") as temp_dir:
            output_dir = Path(temp_dir)
            render_site(output_dir, openapi_url=None if not args.openapi_url else args.openapi_url)
            validate_site(output_dir)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Docs site generation", exc)


if __name__ == "__main__":
    raise SystemExit(main())
