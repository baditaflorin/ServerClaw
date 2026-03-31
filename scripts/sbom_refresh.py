#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, repo_path
from drift_lib import load_controller_context, nats_tunnel, publish_nats_events, resolve_nats_credentials
from platform_observation_tool import maybe_read_secret_path
from sbom_scanner import (
    CVE_RECEIPTS_DIR,
    SBOM_RECEIPTS_DIR,
    DEFAULT_GRYPE_DB_CACHE_DIR,
    DEFAULT_SYFT_CACHE_DIR,
    isoformat_utc,
    latest_cve_receipt_for_image,
    load_scanner_config,
    net_new_high_or_critical_findings,
    now_utc,
    relpath,
    scan_catalog_image,
)


IMAGE_CATALOG_PATH = repo_path("config", "image-catalog.json")


def load_image_catalog(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def publish_delta_events(events: list[dict[str, Any]], *, context: dict[str, Any], enabled: bool) -> None:
    if not enabled or not events:
        return
    nats_url = os.environ.get("LV3_NATS_URL", "").strip()
    credentials = resolve_nats_credentials(context)
    if nats_url:
        publish_nats_events(events, nats_url=nats_url, credentials=credentials)
        return
    with nats_tunnel(context) as local_port:
        publish_nats_events(events, nats_url=f"nats://127.0.0.1:{local_port}", credentials=credentials)


def ntfy_publish_url(config: dict[str, Any]) -> str:
    host = os.environ.get("LV3_NTFY_HOST", "").strip() or str(config["ntfy"]["host"])
    port = int(os.environ.get("LV3_NTFY_PORT", "").strip() or config["ntfy"]["port"])
    topic = os.environ.get("LV3_NTFY_TOPIC", "").strip() or str(config["ntfy"]["topic"])
    return f"http://{host}:{port}/{topic}"


def maybe_send_ntfy_alert(events: list[dict[str, Any]], *, context: dict[str, Any], config: dict[str, Any], enabled: bool) -> None:
    if not enabled or not events:
        return
    password = maybe_read_secret_path(context["secret_manifest"], "ntfy_alertmanager_password")
    if not password:
        raise RuntimeError("ntfy alert requested but ntfy_alertmanager_password is unavailable")
    message_lines = [
        f"ADR 0298 detected {len(events)} net-new HIGH/CRITICAL image findings.",
    ]
    for event in events[:10]:
        finding = event["finding"]
        package = finding.get("package", {})
        message_lines.append(
            f"- {event['image_id']}: {finding.get('severity')} {finding.get('vulnerability_id')} in "
            f"{package.get('name')} {package.get('version')}"
        )
    request = urllib.request.Request(
        ntfy_publish_url(config),
        data="\n".join(message_lines).encode("utf-8"),
        headers={
            "Authorization": "Basic "
            + base64.b64encode(
                f"{config['ntfy']['username']}:{password}".encode("utf-8")
            ).decode("ascii"),
            "Title": "Platform CVE delta",
            "Priority": "high",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to publish the ntfy CVE alert: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ADR 0298 Syft/Grype refresh across the managed platform image catalog."
    )
    parser.add_argument("--image-catalog", type=Path, default=IMAGE_CATALOG_PATH)
    parser.add_argument("--sbom-dir", type=Path, default=SBOM_RECEIPTS_DIR)
    parser.add_argument("--cve-dir", type=Path, default=CVE_RECEIPTS_DIR)
    parser.add_argument("--image-id", action="append", dest="image_ids", default=[])
    parser.add_argument("--publish-nats", action="store_true")
    parser.add_argument("--send-ntfy-alerts", action="store_true")
    parser.add_argument("--print-report-json", action="store_true")
    parser.add_argument("--skip-db-update", action="store_true")
    parser.add_argument("--skip-artifact-cache", action="store_true")
    parser.add_argument("--syft-cache-dir", type=Path, default=DEFAULT_SYFT_CACHE_DIR)
    parser.add_argument("--grype-db-cache-dir", type=Path, default=DEFAULT_GRYPE_DB_CACHE_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_scanner_config()
        catalog = load_image_catalog(args.image_catalog)
        scanned_at = now_utc()
        images = catalog.get("images", {})
        if not isinstance(images, dict) or not images:
            raise ValueError("config/image-catalog.json must define a non-empty images object")
        selected_ids = set(args.image_ids or images.keys())
        image_reports: list[dict[str, Any]] = []
        delta_events: list[dict[str, Any]] = []
        for image_id in sorted(selected_ids):
            entry = images.get(image_id)
            if not isinstance(entry, dict):
                raise ValueError(f"unknown image id '{image_id}'")
            previous = latest_cve_receipt_for_image(image_id, args.cve_dir)
            previous_payload = previous[1] if previous else None
            sbom_path, cve_path, cve_receipt = scan_catalog_image(
                image_id=image_id,
                image_ref=str(entry["ref"]),
                runtime_host=entry.get("runtime_host"),
                platform_name=str(entry.get("platform", "linux/amd64")),
                sbom_dir=args.sbom_dir,
                cve_dir=args.cve_dir,
                config=config,
                scanned_at=scanned_at,
                syft_cache_dir=args.syft_cache_dir,
                grype_db_cache_dir=args.grype_db_cache_dir,
                update_grype_db=not args.skip_db_update and not image_reports,
                use_artifact_cache=not args.skip_artifact_cache,
            )
            net_new = net_new_high_or_critical_findings(previous_payload, cve_receipt)
            for finding in net_new:
                delta_events.append(
                    {
                        "event": "platform.security.cve_delta",
                        "generated_at": isoformat_utc(scanned_at),
                        "image_id": image_id,
                        "image_ref": entry["ref"],
                        "runtime_host": entry.get("runtime_host"),
                        "finding": finding,
                    }
                )
            image_reports.append(
                {
                    "image_id": image_id,
                    "image_ref": entry["ref"],
                    "runtime_host": entry.get("runtime_host"),
                    "sbom_receipt": relpath(sbom_path),
                    "cve_receipt": relpath(cve_path),
                    "summary": cve_receipt["summary"],
                    "new_high_or_critical_findings": len(net_new),
                }
            )

        context = (
            load_controller_context()
            if delta_events and (args.publish_nats or args.send_ntfy_alerts)
            else {}
        )
        publish_delta_events(delta_events, context=context, enabled=args.publish_nats)
        maybe_send_ntfy_alert(delta_events, context=context, config=config, enabled=args.send_ntfy_alerts)

        report = {
            "schema_version": "1.0.0",
            "generated_at": isoformat_utc(scanned_at),
            "image_count": len(image_reports),
            "delta_event_count": len(delta_events),
            "images": image_reports,
        }
        print(f"Scanned {len(image_reports)} managed images")
        if args.print_report_json:
            print(f"REPORT_JSON={json.dumps(report, separators=(',', ':'))}")
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("SBOM refresh", exc)


if __name__ == "__main__":
    raise SystemExit(main())
