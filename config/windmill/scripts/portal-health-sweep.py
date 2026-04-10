#!/usr/bin/env python3
"""Windmill workflow: Portal Health Sweep (ADR 0399 Tier 3).

Fetches each portal's live URL and checks for expected content.  For
the homepage specifically, compares live service tiles against the
service-capability-catalog to detect content-level drift (active
services missing, removed services still present).

Posts drift alerts to ntfy and optionally to Mattermost.

Schedule: every 60 minutes (recommended).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

# Portal internal endpoints and how to check them.
# check_path is fetched via HTTP GET; the response is examined for
# service-level assertions where applicable.
PORTALS: dict[str, dict[str, str]] = {
    "homepage": {
        "url": "http://10.10.10.91:3090",
        "check_path": "/api/services",
    },
    "ops": {
        "url": "http://10.10.10.20:8092",
        "check_path": "/",
    },
    "docs": {
        "url": "https://docs.lv3.org",
        "check_path": "/",
    },
    "changelog": {
        "url": "https://changelog.lv3.org",
        "check_path": "/",
    },
}


def _http_get(url: str, timeout: int = 15) -> tuple[int, str]:
    """Perform a simple GET and return (status_code, body)."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def _post_ntfy(ntfy_url: str, title: str, message: str, priority: str = "default") -> None:
    """Post an alert to ntfy."""
    payload = json.dumps({
        "topic": ntfy_url.rsplit("/", 1)[-1] if "/" in ntfy_url else "platform-reconciliation",
        "title": title,
        "message": message,
        "priority": priority,
    }).encode("utf-8")
    request = urllib.request.Request(
        ntfy_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"ntfy post failed: {exc}\n")


def _post_mattermost(webhook_url: str, markdown: str) -> None:
    """Post a message to Mattermost via incoming webhook."""
    payload = json.dumps({"text": markdown}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Mattermost webhook failed: {exc}\n")


def _load_catalog(repo_root: Path) -> list[dict[str, Any]]:
    """Load the service-capability-catalog and return the services list."""
    catalog_path = repo_root / "config" / "service-capability-catalog.json"
    if not catalog_path.exists():
        return []
    with open(catalog_path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("services", [])


def _check_portal_reachability(name: str, portal: dict[str, str]) -> dict[str, Any]:
    """Check that a portal responds with HTTP 2xx."""
    url = portal["url"].rstrip("/") + portal["check_path"]
    status_code, body = _http_get(url)
    reachable = 200 <= status_code < 300
    return {
        "portal": name,
        "url": url,
        "reachable": reachable,
        "status_code": status_code,
        "body_length": len(body),
        "issues": [] if reachable else [f"HTTP {status_code} from {url}"],
    }


def _check_homepage_services(
    portal_url: str,
    catalog_services: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare homepage /api/services against the canonical catalog.

    Active services should appear in the homepage response.
    Non-active services (removed, deprecated) should NOT appear.
    """
    api_url = portal_url.rstrip("/") + "/api/services"
    status_code, body = _http_get(api_url)
    result: dict[str, Any] = {
        "api_url": api_url,
        "status_code": status_code,
        "issues": [],
        "missing_active": [],
        "stale_removed": [],
    }

    if status_code < 200 or status_code >= 300:
        result["issues"].append(f"Homepage API returned HTTP {status_code}")
        return result

    # Attempt to parse the API response body.  The homepage API may return
    # JSON or HTML depending on the dashboard implementation.  We search for
    # service IDs/names in the body text as a fallback when JSON parsing fails.
    body_lower = body.lower()

    active_services = [
        s for s in catalog_services if s.get("lifecycle_status") == "active"
    ]
    removed_services = [
        s for s in catalog_services if s.get("lifecycle_status") != "active"
    ]

    for svc in active_services:
        svc_id = svc.get("id", "")
        svc_name = svc.get("name", "")
        # Only check services that are expected to appear on the homepage
        # (those with a subdomain or public_url — internal-only services
        # may not be listed on the dashboard).
        if not svc.get("subdomain") and not svc.get("public_url"):
            continue
        if svc_id.lower() not in body_lower and svc_name.lower() not in body_lower:
            result["missing_active"].append({"id": svc_id, "name": svc_name})

    for svc in removed_services:
        svc_id = svc.get("id", "")
        svc_name = svc.get("name", "")
        if svc_id.lower() in body_lower or svc_name.lower() in body_lower:
            result["stale_removed"].append({"id": svc_id, "name": svc_name})

    if result["missing_active"]:
        count = len(result["missing_active"])
        result["issues"].append(
            f"{count} active service(s) missing from homepage"
        )
    if result["stale_removed"]:
        count = len(result["stale_removed"])
        result["issues"].append(
            f"{count} removed service(s) still appearing on homepage"
        )

    return result


def _build_markdown(health_results: list[dict[str, Any]], homepage_check: dict[str, Any] | None) -> str:
    """Build a Mattermost-friendly markdown summary."""
    lines: list[str] = ["#### Portal Health Sweep", ""]

    all_ok = True
    for r in health_results:
        icon = ":white_check_mark:" if r["reachable"] else ":x:"
        lines.append(f"- {icon} **{r['portal']}**: HTTP {r['status_code']}")
        if not r["reachable"]:
            all_ok = False

    if homepage_check:
        if homepage_check.get("missing_active"):
            all_ok = False
            lines.append("")
            lines.append(f"**Missing active services on homepage** ({len(homepage_check['missing_active'])}):")
            for svc in homepage_check["missing_active"][:10]:
                lines.append(f"  - `{svc['id']}` ({svc['name']})")
            if len(homepage_check["missing_active"]) > 10:
                lines.append(f"  - _...and {len(homepage_check['missing_active']) - 10} more_")

        if homepage_check.get("stale_removed"):
            all_ok = False
            lines.append("")
            lines.append(f"**Stale removed services on homepage** ({len(homepage_check['stale_removed'])}):")
            for svc in homepage_check["stale_removed"][:10]:
                lines.append(f"  - `{svc['id']}` ({svc['name']})")

    if all_ok:
        lines.append("")
        lines.append("All portals healthy and content aligned with catalog.")

    return "\n".join(lines)


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    ntfy_url: str = "http://10.10.10.92:8075/platform-reconciliation",
    mattermost_webhook: str = "",
) -> dict[str, Any]:
    """Health sweep: verify live portal content matches canonical catalogs.

    Intended to run on a 60-minute cron schedule via Windmill.
    """
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    catalog_services = _load_catalog(repo_root)

    # Step 1: Check reachability of all portals
    health_results: list[dict[str, Any]] = []
    for name, portal in PORTALS.items():
        health_results.append(_check_portal_reachability(name, portal))

    # Step 2: For homepage, run deep content comparison against catalog
    homepage_check: dict[str, Any] | None = None
    homepage_health = next(
        (r for r in health_results if r["portal"] == "homepage"), None
    )
    if homepage_health and homepage_health["reachable"] and catalog_services:
        homepage_check = _check_homepage_services(
            PORTALS["homepage"]["url"],
            catalog_services,
        )

    # Collect all issues across portals
    all_issues: list[str] = []
    for r in health_results:
        all_issues.extend(r.get("issues", []))
    if homepage_check:
        all_issues.extend(homepage_check.get("issues", []))

    has_issues = len(all_issues) > 0

    # Step 3: Post ntfy alert if issues found
    ntfy_target = ntfy_url or os.environ.get("LV3_NTFY_URL", "")
    if ntfy_target and has_issues:
        _post_ntfy(
            ntfy_target,
            title="Portal Health Sweep: drift detected",
            message="\n".join(all_issues),
            priority="high" if any(not r["reachable"] for r in health_results) else "default",
        )

    # Step 4: Post Mattermost summary if webhook provided and issues found
    markdown = _build_markdown(health_results, homepage_check)
    webhook = mattermost_webhook or os.environ.get("LV3_MATTERMOST_WEBHOOK", "")
    if webhook and has_issues:
        _post_mattermost(webhook, markdown)

    return {
        "status": "alert" if has_issues else "ok",
        "channel": "#platform-ops",
        "portals_checked": len(health_results),
        "portals_reachable": sum(1 for r in health_results if r["reachable"]),
        "portals_unreachable": sum(1 for r in health_results if not r["reachable"]),
        "issue_count": len(all_issues),
        "issues": all_issues,
        "health_results": health_results,
        "homepage_check": homepage_check,
        "markdown": markdown,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Portal health sweep: verify live content against catalogs (ADR 0399 Tier 3).",
    )
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--ntfy-url", default="http://10.10.10.92:8075/platform-reconciliation")
    parser.add_argument("--mattermost-webhook", default="")
    args = parser.parse_args()
    result = main(
        repo_path=args.repo_path,
        ntfy_url=args.ntfy_url,
        mattermost_webhook=args.mattermost_webhook,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
