#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from api_publication import load_api_publication_catalog
from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path


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
OPENAPI_DEFAULT_URL = "https://api.lv3.org/v1/openapi.json"
REPO_ROOT = repo_path()
LINK_PATTERN = re.compile(r"(!?\[[^\]]*])\(([^)]+)\)")


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
    return Path(
        *(
            [".."] * len(current.parent.parts)
            + list(destination.parts)
        )
    ).as_posix()


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


def adr_lookup() -> dict[str, Path]:
    return {
        path.name.split("-", 1)[0]: path
        for path in ADR_DIR.glob("*.md")
    }


def subdomains_by_service(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["service_id"]].append(entry)
    return grouped


def secret_lookup() -> dict[str, dict[str, Any]]:
    return {
        secret["id"]: secret
        for secret in load_json(SECRET_CATALOG_PATH)["secrets"]
    }


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
    adr_paths: dict[str, Path],
    service_subdomains: list[dict[str, Any]],
    secrets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    adr_link = None
    if service.get("adr") in adr_paths:
        adr_link = relative_site_link(
            Path("services") / f"{service['id']}.md",
            site_path_for_repo_path(adr_paths[service["adr"]]) or Path(),
        )

    runbook_link = None
    runbook_title = None
    runbook_path = repo_path(service["runbook"]) if service.get("runbook") else None
    if runbook_path and runbook_path.exists():
        mapped = site_path_for_repo_path(runbook_path)
        if mapped is not None:
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
    adr_paths: dict[str, Path],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    totals = {
        "services": len(services),
        "public_services": sum(1 for service in services if service.get("public_url")),
        "private_services": sum(1 for service in services if service["exposure"] == "private-only"),
    }

    for service in services:
        grouped[service["category"]].append(
            {
                **service,
                "link": f"{service['id']}.md",
                "primary_url": service.get("public_url") or service.get("internal_url"),
                "adr_link": (
                    relative_site_link(
                        Path("services/index.md"),
                        site_path_for_repo_path(adr_paths[service["adr"]]) or Path(),
                    )
                    if service.get("adr") in adr_paths
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

    for path in sorted(RUNBOOK_DIR.glob("*.md")):
        target = Path("runbooks", path.name)
        copy_transformed_markdown(output_dir, path, target)
        item = {"title": read_h1(path), "link": path.name, "stem": path.stem}
        runbook_items.append(item)
        if path.stem in featured_stems:
            featured.append({"title": item["title"], "link": item["link"]})

    runbook_items.sort(key=lambda item: item["title"])
    featured.sort(key=lambda item: item["title"])
    write_generated(
        output_dir,
        "runbooks/index.md",
        render_template("runbooks-index.md.j2", featured=featured, runbooks=runbook_items),
    )
    return runbook_items


def render_adr_pages(output_dir: Path) -> list[dict[str, str]]:
    entries = []
    for path in sorted(ADR_DIR.glob("*.md")):
        target = Path("architecture", "decisions", path.name)
        copy_transformed_markdown(output_dir, path, target)
        metadata = parse_metadata_block(path)
        entries.append(
            {
                "id": path.name.split("-", 1)[0],
                "title": read_h1(path).split(": ", 1)[-1],
                "status": metadata.get("Status", "unknown"),
                "implementation_status": metadata.get("Implementation Status", "unknown"),
                "link": f"decisions/{path.name}",
            }
        )

    totals = {
        "total": len(entries),
        "implemented": sum(1 for entry in entries if entry["implementation_status"] == "Implemented"),
        "proposed": sum(1 for entry in entries if entry["status"] == "Proposed"),
    }
    write_generated(
        output_dir,
        "architecture/index.md",
        render_template("architecture-index.md.j2", totals=totals, adrs=entries),
    )
    return entries


def render_release_notes(output_dir: Path) -> list[dict[str, str]]:
    releases = []
    readme_path = RELEASE_NOTES_DIR / "README.md"
    if readme_path.exists():
        copy_transformed_markdown(output_dir, readme_path, Path("releases", "index-source.md"))

    for path in sorted(RELEASE_NOTES_DIR.glob("[0-9]*.md"), key=version_key, reverse=True):
        target = Path("releases", path.name)
        copy_transformed_markdown(output_dir, path, target)
        date = "unknown"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- Date: "):
                date = line.removeprefix("- Date: ").strip()
                break
        releases.append({"version": path.stem, "date": date, "link": path.name})

    write_generated(
        output_dir,
        "releases/index.md",
        render_template("releases-index.md.j2", releases=releases),
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
    write_generated(output_dir, "reference/index.md", render_template("reference-index.md.j2"))

    subdomains_index = subdomains_by_service(subdomains)
    port_rows = []
    for service in sorted(services, key=lambda item: (min((row["port"] for row in service_port_rows(item, subdomains_index.get(item["id"], []))), default=0), item["name"])):
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
    write_generated(output_dir, "reference/ports.md", render_template("reference-ports.md.j2", rows=port_rows))

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
                "target": entry["target"],
                "target_port": entry["target_port"],
                "tls_provider": entry["tls"]["provider"],
            }
        )
    write_generated(
        output_dir,
        "reference/subdomains.md",
        render_template("reference-subdomains.md.j2", rows=subdomain_rows),
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
        render_template("reference-identities.md.j2", classes=classes, identities=identities),
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
        render_template("reference-secrets.md.j2", secrets=secret_rows),
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
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
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
            "servers": [{"url": "https://api.lv3.org"}],
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
        render_template(
            "api-index.md.j2",
            catalog_missing=api_gateway_catalog_missing,
            surfaces=surface_rows,
            openapi_source=source,
        ),
    )
    write_generated(output_dir, "api/openapi.md", render_template("openapi-page.md.j2"))


def render_changelog_page(output_dir: Path, releases: list[dict[str, str]]) -> None:
    changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")
    write_generated(
        output_dir,
        "changelog.md",
        render_template(
            "changelog.md.j2",
            current_version=VERSION_PATH.read_text(encoding="utf-8").strip(),
            releases=releases,
            unreleased=extract_unreleased_section(changelog_text),
        ),
    )


def render_home_and_upgrade(output_dir: Path) -> None:
    for path in SITE_SOURCE_DOCS:
        copy_transformed_markdown(output_dir, path, site_path_for_repo_path(path) or Path(path.name))


def render_services(output_dir: Path) -> None:
    services = load_json(SERVICE_CATALOG_PATH)["services"]
    adr_paths = adr_lookup()
    subdomains = load_json(SUBDOMAIN_CATALOG_PATH)["subdomains"]
    secrets = secret_lookup()
    grouped_subdomains = subdomains_by_service(subdomains)

    for service in sorted(services, key=lambda item: item["name"]):
        context = build_service_page_context(
            service,
            adr_paths=adr_paths,
            service_subdomains=grouped_subdomains.get(service["id"], []),
            secrets=secrets,
        )
        write_generated(
            output_dir,
            Path("services", f"{service['id']}.md"),
            render_template("service-page.md.j2", service=context),
        )

    write_generated(
        output_dir,
        "services/index.md",
        render_template(
            "services-index.md.j2",
            **build_services_index_context(services, adr_paths=adr_paths),
        ),
    )
    render_reference_pages(output_dir, services=services, subdomains=subdomains, secrets=secrets)


def render_site(output_dir: Path, *, openapi_url: str | None = OPENAPI_DEFAULT_URL) -> None:
    reset_generated_dir(output_dir)
    render_home_and_upgrade(output_dir)
    render_runbook_pages(output_dir)
    render_adr_pages(output_dir)
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
        output_dir / "reference" / "ports.md",
        output_dir / "api" / "index.md",
        output_dir / "api" / "openapi.md",
        output_dir / "api" / "openapi.json",
        output_dir / "releases" / "index.md",
        output_dir / "changelog.md",
    ]
    for path in expected:
        if not path.exists():
            raise ValueError(f"missing generated docs artifact: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the MkDocs source tree for docs.lv3.org.")
    parser.add_argument("--write", action="store_true", help="Write generated site source into docs/site-generated.")
    parser.add_argument("--check", action="store_true", help="Generate into a temp dir and validate the expected artifacts.")
    parser.add_argument("--openapi-url", default=OPENAPI_DEFAULT_URL, help="OpenAPI schema URL to snapshot before build.")
    args = parser.parse_args()

    if not args.write and not args.check:
        parser.error("choose --write or --check")

    try:
        if args.write:
            render_site(SITE_GENERATED_DIR, openapi_url=args.openapi_url)
            validate_site(SITE_GENERATED_DIR)
            print(f"Generated docs site source: {SITE_GENERATED_DIR}")
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
