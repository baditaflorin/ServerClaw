#!/usr/bin/env python3
"""Run live health probes against every service in catalog/services/<svc>/service.yaml.

ADR 0463 — post-converge / on-demand health-probe runner. Reads each
service catalog file, extracts the `health.liveness` block (already
populated for every service per ADR 0205), executes the probe, and
writes the result to `receipts/health-probes/<service>-<timestamp>.json`.

The runner is intentionally a leaf: it does not orchestrate converges,
does not gate pushes, and does not block on missing services. It just
runs the probes you point it at and writes receipts. `make doctor`
(ADR 0450 / 0460) can read those receipts in a follow-up workstream.

Usage:

    python3 scripts/run_health_probes.py [--service <svc>...] [--all] [--json]
                                         [--timeout 5] [--receipts-dir <path>]

Without `--service` or `--all`, the script prints a usage message and
exits 2 — there is no "guess what to probe" mode, because choosing the
target set is operator policy.

Exit codes:
  0 — every probed service returned the expected status / TCP connect
  1 — at least one probe failed
  2 — usage / data error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = REPO_ROOT / "catalog" / "services"
DEFAULT_RECEIPTS_DIR = REPO_ROOT / "receipts" / "health-probes"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for run_health_probes.py") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text()) or {}


def _list_services() -> list[str]:
    if not CATALOG_DIR.is_dir():
        return []
    return sorted(p.name for p in CATALOG_DIR.iterdir() if p.is_dir() and (p / "service.yaml").is_file())


def _service_health_block(slug: str) -> dict:
    path = CATALOG_DIR / slug / "service.yaml"
    data = _load_yaml(path)
    return (data.get("health") or {}).get("liveness") or {}


def probe_http(probe: dict, timeout: float) -> tuple[bool, str]:
    """Run an HTTP probe. Returns (ok, detail)."""
    url = probe.get("url", "")
    method = (probe.get("method") or "GET").upper()
    expected = probe.get("expected_status") or [200]
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ok = status in expected
            return ok, f"HTTP {method} {url} → {status} (expected {expected})"
    except urllib.error.HTTPError as exc:
        # urlopen raises on non-2xx; surface the actual code so the catalog's
        # expected_status (which often includes 401/302) can match.
        ok = exc.code in expected
        return ok, f"HTTP {method} {url} → {exc.code} (expected {expected})"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"HTTP {method} {url} failed: {exc}"


def probe_tcp(probe: dict, timeout: float) -> tuple[bool, str]:
    host = probe.get("host", "")
    port = int(probe.get("port", 0))
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return True, f"TCP {host}:{port} connect OK"
    except OSError as exc:
        return False, f"TCP {host}:{port} failed: {exc}"


def run_probe(probe: dict, *, timeout: float | None = None) -> tuple[bool, str]:
    """Dispatch a probe by `kind`. Unknown kinds return (False, msg)."""
    kind = probe.get("kind", "")
    timeout = float(probe.get("timeout_seconds", timeout or 5.0))
    if kind == "http":
        return probe_http(probe, timeout)
    if kind == "tcp":
        return probe_tcp(probe, timeout)
    return False, f"unknown probe kind {kind!r}"


def write_probe_receipt(receipts_dir: Path, slug: str, probe: dict, ok: bool, detail: str) -> Path:
    """ADR 0463 — record one probe result.

    Atomic write per ADR 0461: tempfile + fsync + os.replace via the
    shared helper.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from check_receipt_freshness import write_receipt_atomic

    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    safe_ts = now.replace(":", "").replace("-", "").replace("+0000", "Z")
    receipt_path = receipts_dir / f"{slug}-{safe_ts}.json"
    payload = {
        "schema_version": "1.0.0",
        "service": slug,
        "probed_at": now,
        "kind": probe.get("kind"),
        "ok": ok,
        "detail": detail,
        "probe": probe,
    }
    write_receipt_atomic(receipt_path, payload)
    return receipt_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--service", action="append", default=[], help="Service slug. Repeatable.")
    parser.add_argument("--all", action="store_true", help="Probe every service in catalog/services/.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Default per-probe timeout seconds.")
    parser.add_argument(
        "--receipts-dir",
        type=Path,
        default=DEFAULT_RECEIPTS_DIR,
        help="Directory to write per-probe receipts.",
    )
    parser.add_argument("--json", action="store_true", dest="json_out", help="Emit JSON summary on stdout.")
    parser.add_argument(
        "--no-receipts",
        action="store_true",
        help="Skip receipt writing (useful for tests / dry-run).",
    )
    args = parser.parse_args(argv)

    services: list[str]
    if args.all:
        services = _list_services()
    elif args.service:
        services = list(args.service)
    else:
        parser.print_usage(sys.stderr)
        print(
            "run_health_probes: pass --service <slug> (repeatable) or --all.",
            file=sys.stderr,
        )
        return 2

    if not services:
        print("run_health_probes: no services to probe.", file=sys.stderr)
        return 2

    if not args.no_receipts:
        args.receipts_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for slug in services:
        try:
            probe = _service_health_block(slug)
        except FileNotFoundError:
            results.append({"service": slug, "ok": False, "detail": "service.yaml not found"})
            continue
        if not probe:
            results.append({"service": slug, "ok": False, "detail": "no health.liveness defined"})
            continue
        ok, detail = run_probe(probe, timeout=args.timeout)
        receipt_path = None
        if not args.no_receipts:
            receipt_path = write_probe_receipt(args.receipts_dir, slug, probe, ok, detail)
        results.append(
            {
                "service": slug,
                "ok": ok,
                "detail": detail,
                "receipt": str(receipt_path.relative_to(REPO_ROOT)) if receipt_path else None,
            }
        )

    if args.json_out:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for r in results:
            marker = "[ok] " if r["ok"] else "[FAIL]"
            print(f"{marker} {r['service']:<30} {r['detail']}")
        ok_count = sum(1 for r in results if r["ok"])
        print(f"\nrun_health_probes: {ok_count}/{len(results)} probes OK")

    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
