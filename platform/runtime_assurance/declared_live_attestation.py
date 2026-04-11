from __future__ import annotations

import concurrent.futures
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platform.repo import TOPOLOGY_HOST
from platform.world_state.client import StaleDataError, SurfaceNotFoundError, WorldStateClient, WorldStateUnavailable
from platform.world_state.materializer import SQLITE_CURRENT_VIEW_NAME, SQLITE_SNAPSHOTS_TABLE_NAME


PASS_HTTP_MAX_STATUS = 499
PROBE_ACCEPTED_SCHEMES = {"http", "https", "postgres", "ssh", "tcp"}
EDGE_ROUTE_EXPOSURES = {"edge-published", "edge-static", "informational-only"}
HEALTHY_VM_STATUSES = {"running", "started", "up"}


class ServiceAttestationNotFoundError(RuntimeError):
    def __init__(self, service_id: str, environment: str):
        super().__init__(f"Declared-live attestation for service '{service_id}' in environment '{environment}' was not found")
        self.service_id = service_id
        self.environment = environment


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("PyYAML is required for declared-live attestation.") from exc
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def is_loopback_host(value: str | None) -> bool:
    return value in {"127.0.0.1", "localhost", "::1"}


def is_template_value(value: str | None) -> bool:
    return not value or "{{" in value or "}}" in value


def parse_url(url: str | None) -> urllib.parse.ParseResult | None:
    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        return None
    return parsed


def service_catalog_path(repo_root: Path) -> Path:
    return repo_root / "config" / "service-capability-catalog.json"


def health_probe_catalog_path(repo_root: Path) -> Path:
    return repo_root / "config" / "health-probe-catalog.json"


def platform_vars_path(repo_root: Path) -> Path:
    return repo_root / "inventory" / "group_vars" / "platform.yml"


def stack_path(repo_root: Path) -> Path:
    return repo_root / "versions" / "stack.yaml"


def receipts_dir(repo_root: Path) -> Path:
    return repo_root / "receipts" / "live-applies"


def load_service_catalog(repo_root: Path) -> list[dict[str, Any]]:
    payload = load_json(service_catalog_path(repo_root), {"services": []})
    services = payload.get("services")
    return services if isinstance(services, list) else []


def load_health_probe_catalog(repo_root: Path) -> dict[str, Any]:
    payload = load_json(health_probe_catalog_path(repo_root), {"services": {}})
    services = payload.get("services")
    return services if isinstance(services, dict) else {}


def load_platform_topology(repo_root: Path) -> dict[str, Any]:
    payload = load_yaml(platform_vars_path(repo_root))
    topology = payload.get("platform_service_topology")
    return topology if isinstance(topology, dict) else {}


def load_stack(repo_root: Path) -> dict[str, Any]:
    return load_yaml(stack_path(repo_root))


def world_state_client(repo_root: Path, *, dsn: str | None = None) -> WorldStateClient:
    kwargs: dict[str, Any] = {"repo_root": repo_root, "dsn": dsn}
    if (dsn or "").startswith("sqlite:///"):
        kwargs["current_view_name"] = SQLITE_CURRENT_VIEW_NAME
        kwargs["snapshots_table_name"] = SQLITE_SNAPSHOTS_TABLE_NAME
    return WorldStateClient(**kwargs)


def load_proxmox_runtime_snapshot(repo_root: Path, *, world_state_dsn: str | None = None) -> list[dict[str, Any]]:
    try:
        payload = world_state_client(repo_root, dsn=world_state_dsn).get("proxmox_vms", allow_stale=True)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    except (SurfaceNotFoundError, WorldStateUnavailable, StaleDataError, OSError, RuntimeError):
        pass
    try:
        from platform.world_state.workers import collect_proxmox_vms

        return collect_proxmox_vms(repo_root)
    except Exception:  # noqa: BLE001
        return []


def vm_snapshot_index(snapshot: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    by_name: dict[str, dict[str, Any]] = {}
    by_vmid: dict[int, dict[str, Any]] = {}
    for item in snapshot:
        name = item.get("name")
        if isinstance(name, str) and name:
            by_name[name] = item
        vmid = item.get("vmid")
        if isinstance(vmid, int):
            by_vmid[vmid] = item
    return by_name, by_vmid


def active_bindings(service: dict[str, Any], requested_environment: str | None) -> list[tuple[str, dict[str, Any]]]:
    environments = service.get("environments")
    if not isinstance(environments, dict):
        return []
    bindings: list[tuple[str, dict[str, Any]]] = []
    for environment, binding in environments.items():
        if requested_environment and environment != requested_environment:
            continue
        if not isinstance(binding, dict):
            continue
        if binding.get("status") != "active":
            continue
        bindings.append((environment, binding))
    return bindings


def resolved_probe_host(service: dict[str, Any], topology: dict[str, Any]) -> str | None:
    urls = topology.get("urls")
    if isinstance(urls, dict):
        internal_url = urls.get("internal")
        parsed_internal = parse_url(internal_url if isinstance(internal_url, str) else None)
        if parsed_internal and parsed_internal.hostname and not is_loopback_host(parsed_internal.hostname):
            return parsed_internal.hostname

    private_ip = topology.get("private_ip")
    if isinstance(private_ip, str) and private_ip and not is_template_value(private_ip):
        return private_ip

    parsed_service_internal = parse_url(service.get("internal_url") if isinstance(service.get("internal_url"), str) else None)
    if parsed_service_internal and parsed_service_internal.hostname and not is_loopback_host(parsed_service_internal.hostname):
        return parsed_service_internal.hostname
    return None


def rewrite_probe_url(url: str, service: dict[str, Any], topology: dict[str, Any]) -> str:
    parsed = urllib.parse.urlparse(url)
    if not is_loopback_host(parsed.hostname):
        return url
    host = resolved_probe_host(service, topology)
    if not host:
        return url
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def rewrite_probe_host(host: str, service: dict[str, Any], topology: dict[str, Any]) -> str:
    if not is_loopback_host(host):
        return host
    return resolved_probe_host(service, topology) or host


def endpoint_probe_candidates(service: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    probes: list[tuple[str, dict[str, Any]]] = []
    for source in ("readiness", "liveness"):
        probe = contract.get(source)
        if isinstance(probe, dict):
            probes.append((source, probe))
    if probes:
        return probes
    url = None
    environments = service.get("environments")
    if isinstance(environments, dict):
        production = environments.get("production")
        if isinstance(production, dict):
            url = production.get("url")
    if not isinstance(url, str):
        url = service.get("internal_url") or service.get("public_url")
    if isinstance(url, str) and url:
        probes.append(
            (
                "fallback",
                {
                    "kind": "url",
                    "url": url,
                },
            )
        )
    return probes


def http_probe(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 5.0,
    accepted_statuses: set[int] | None = None,
    validate_tls: bool = True,
    accept_any_non_server_error: bool = False,
) -> dict[str, Any]:
    context = None
    if url.startswith("https://") and not validate_tls:
        context = ssl._create_unverified_context()  # noqa: SLF001
    request = urllib.request.Request(url, headers=headers or {}, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:  # noqa: S310
            status = getattr(response, "status", None)
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        status = exc.code
        final_url = exc.geturl()
        if accept_any_non_server_error and status < 500:
            return {
                "status": "pass",
                "observed": f"HTTP {status}",
                "http_status": status,
                "observed_target": final_url,
            }
        if accepted_statuses and status in accepted_statuses:
            return {
                "status": "pass",
                "observed": f"HTTP {status}",
                "http_status": status,
                "observed_target": final_url,
            }
        return {
            "status": "fail",
            "observed": f"HTTP {status}",
            "http_status": status,
            "observed_target": final_url,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "fail",
            "observed": str(exc),
            "http_status": None,
            "observed_target": url,
        }

    if accept_any_non_server_error and isinstance(status, int) and status <= PASS_HTTP_MAX_STATUS:
        return {
            "status": "pass",
            "observed": f"HTTP {status}",
            "http_status": status,
            "observed_target": final_url,
        }
    if accepted_statuses and status in accepted_statuses:
        return {
            "status": "pass",
            "observed": f"HTTP {status}",
            "http_status": status,
            "observed_target": final_url,
        }
    return {
        "status": "fail",
        "observed": f"HTTP {status}",
        "http_status": status,
        "observed_target": final_url,
    }


def tcp_probe(host: str, port: int, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {
                "status": "pass",
                "observed": f"TCP {host}:{port}",
                "http_status": None,
                "observed_target": f"{host}:{port}",
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "fail",
            "observed": str(exc),
            "http_status": None,
            "observed_target": f"{host}:{port}",
        }


def generic_url_probe(url: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in {"http", "https"}:
        return http_probe(
            url,
            method="GET",
            timeout_seconds=timeout_seconds,
            validate_tls=True,
            accept_any_non_server_error=True,
        )
    if scheme in {"ssh", "postgres", "tcp"} and parsed.hostname and parsed.port:
        return tcp_probe(parsed.hostname, parsed.port, timeout_seconds=timeout_seconds)
    return {
        "status": "skipped",
        "observed": f"unsupported scheme '{scheme}'",
        "http_status": None,
        "observed_target": url,
    }


def execute_contract_probe(
    service: dict[str, Any],
    topology: dict[str, Any],
    source: str,
    probe: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    kind = str(probe.get("kind", "unknown"))
    probe_timeout = min(float(probe.get("timeout_seconds", timeout_seconds)), timeout_seconds)
    if kind == "http":
        declared_url = str(probe.get("url", ""))
        url = rewrite_probe_url(declared_url, service, topology)
        headers = probe.get("headers") if isinstance(probe.get("headers"), dict) else {}
        expected_status = probe.get("expected_status")
        accepted = {
            int(item)
            for item in expected_status
            if isinstance(item, int)
        } if isinstance(expected_status, list) else None
        result = http_probe(
            url,
            method=str(probe.get("method", "GET")),
            headers={str(key): str(value) for key, value in headers.items()},
            timeout_seconds=probe_timeout,
            accepted_statuses=accepted,
            validate_tls=bool(probe.get("validate_tls", True)),
        )
        result.update(
            {
                "required": True,
                "source": f"health_probe_contract.{source}",
                "kind": kind,
                "declared_target": declared_url,
            }
        )
        return result

    if kind == "tcp":
        declared_host = str(probe.get("host", ""))
        port = int(probe.get("port", 0))
        host = rewrite_probe_host(declared_host, service, topology)
        result = tcp_probe(host, port, timeout_seconds=probe_timeout)
        result.update(
            {
                "required": True,
                "source": f"health_probe_contract.{source}",
                "kind": kind,
                "declared_target": f"{declared_host}:{port}",
            }
        )
        return result

    return {
        "status": "skipped",
        "required": True,
        "source": f"health_probe_contract.{source}",
        "kind": kind,
        "declared_target": str(probe.get("url") or probe.get("argv") or probe.get("unit") or kind),
        "observed_target": None,
        "http_status": None,
        "observed": f"unsupported probe kind '{kind}' from controller-safe attestation",
    }


def endpoint_proof_for_service(
    service: dict[str, Any],
    topology: dict[str, Any],
    contract: dict[str, Any],
    binding: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    candidates = endpoint_probe_candidates(service, contract)
    skipped: list[dict[str, Any]] = []
    for source, probe in candidates:
        if source == "fallback" and probe.get("kind") == "url":
            url = str(probe.get("url", ""))
            result = generic_url_probe(url, timeout_seconds=timeout_seconds)
            result.update(
                {
                    "required": True,
                    "source": "service_binding.url",
                    "kind": "url",
                    "declared_target": url,
                }
            )
        else:
            result = execute_contract_probe(service, topology, source, probe, timeout_seconds=timeout_seconds)
        if result["status"] == "pass":
            return result
        if result["status"] == "fail":
            return result
        skipped.append(result)

    if skipped:
        fallback = skipped[-1]
        fallback["observed"] = skipped[-1]["observed"]
        return fallback

    url = binding.get("url") or service.get("internal_url") or service.get("public_url")
    if isinstance(url, str) and url:
        result = generic_url_probe(url, timeout_seconds=timeout_seconds)
        result.update(
            {
                "required": True,
                "source": "service_binding.url",
                "kind": "url",
                "declared_target": url,
            }
        )
        return result

    return {
        "status": "fail",
        "required": True,
        "source": "service_binding.url",
        "kind": "missing",
        "declared_target": None,
        "observed_target": None,
        "http_status": None,
        "observed": "no declared endpoint available",
    }


def route_proof_required(service: dict[str, Any], binding: dict[str, Any]) -> bool:
    exposure = str(service.get("exposure", "")).strip()
    if exposure not in EDGE_ROUTE_EXPOSURES:
        return False
    url = binding.get("url") or service.get("public_url")
    parsed = parse_url(url if isinstance(url, str) else None)
    return bool(parsed and parsed.scheme in {"http", "https"})


def route_proof_for_service(service: dict[str, Any], binding: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    url = binding.get("url") or service.get("public_url")
    required = route_proof_required(service, binding)
    if not required:
        return {
            "status": "not_required",
            "required": False,
            "source": "declared_route_probe",
            "kind": "not_required",
            "declared_target": url if isinstance(url, str) and url else None,
            "observed_target": None,
            "http_status": None,
            "observed": "separate route proof is only required for declared edge or informational publications",
        }
    if not isinstance(url, str) or not url:
        return {
            "status": "skipped",
            "required": required,
            "source": "service_binding.url",
            "kind": "missing",
            "declared_target": None,
            "observed_target": None,
            "http_status": None,
            "observed": "no route-proof target declared",
        }

    result = generic_url_probe(url, timeout_seconds=timeout_seconds)
    result.update(
        {
            "required": required,
            "source": "declared_route_probe",
            "kind": "http",
            "declared_target": url,
        }
    )
    return result


def service_keywords(service: dict[str, Any], topology: dict[str, Any]) -> dict[str, set[str]]:
    strong = {
        normalize_text(str(service.get("id", ""))),
        normalize_text(str(service.get("name", ""))),
        normalize_text(str(service.get("subdomain", ""))),
        normalize_text(str(topology.get("public_hostname", ""))),
        normalize_text(str(topology.get("service_name", ""))),
    }
    weak = {
        normalize_text(str(service.get("vm", ""))),
        normalize_text(str(topology.get("owning_vm", ""))),
    }
    return {
        "strong": {item for item in strong if item},
        "weak": {item for item in weak if item},
    }


def receipt_match_score(receipt_text: str, keywords: dict[str, set[str]]) -> int:
    if any(keyword in receipt_text for keyword in keywords["strong"]):
        return 3
    if any(keyword in receipt_text for keyword in keywords["weak"]):
        return 1
    return 0


def latest_receipt_for_service(
    repo_root: Path,
    service: dict[str, Any],
    topology: dict[str, Any],
    *,
    environment: str,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = 0
    keywords = service_keywords(service, topology)
    for receipt_path in sorted(receipts_dir(repo_root).rglob("*.json"), reverse=True):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        receipt_environment = receipt.get("environment")
        if isinstance(receipt_environment, str) and receipt_environment != environment:
            continue
        receipt_text = normalize_text(
            " ".join(
                [
                    json.dumps(receipt.get("targets", []), sort_keys=True),
                    str(receipt.get("summary", "")),
                    str(receipt.get("workflow_id", "")),
                ]
            )
        )
        score = receipt_match_score(receipt_text, keywords)
        if score <= 0 or score < best_score:
            continue
        best = {
            "receipt_id": receipt.get("receipt_id", receipt_path.stem),
            "workflow_id": receipt.get("workflow_id"),
            "recorded_on": receipt.get("recorded_on") or receipt.get("applied_on"),
            "path": str(receipt_path.relative_to(repo_root)),
            "match_score": score,
            "summary": receipt.get("summary", ""),
        }
        best_score = score
        if best_score >= 3:
            break
    return best


def host_witness_for_service(
    service: dict[str, Any],
    snapshot_by_name: dict[str, dict[str, Any]],
    snapshot_by_vmid: dict[int, dict[str, Any]],
    stack: dict[str, Any],
) -> dict[str, Any]:
    declared_vm = str(service.get("vm", "")).strip()
    declared_vmid = service.get("vmid")

    if declared_vm == TOPOLOGY_HOST:
        observed_state = stack.get("observed_state", {})
        proxmox_state = observed_state.get("proxmox", {}) if isinstance(observed_state, dict) else {}
        installed = bool(proxmox_state.get("installed"))
        return {
            "status": "pass" if installed else "fail",
            "required": True,
            "source": "versions.stack.observed_state.proxmox",
            "declared_target": declared_vm,
            "observed_target": "host:proxmox-host",
            "observed": "host observed in canonical stack state" if installed else "host installation state missing",
            "vmid": None,
        }

    vm = None
    if isinstance(declared_vmid, int) and declared_vmid in snapshot_by_vmid:
        vm = snapshot_by_vmid[declared_vmid]
    elif declared_vm in snapshot_by_name:
        vm = snapshot_by_name[declared_vm]

    if not isinstance(vm, dict):
        return {
            "status": "fail",
            "required": True,
            "source": "world_state.proxmox_vms",
            "declared_target": declared_vm or declared_vmid,
            "observed_target": None,
            "observed": "declared VM not found in observed runtime inventory",
            "vmid": declared_vmid if isinstance(declared_vmid, int) else None,
        }

    status = str(vm.get("status", "")).lower()
    passed = status in HEALTHY_VM_STATUSES or vm.get("running") is True
    observed_name = str(vm.get("name", declared_vm or "unknown"))
    observed_vmid = vm.get("vmid") if isinstance(vm.get("vmid"), int) else declared_vmid
    return {
        "status": "pass" if passed else "fail",
        "required": True,
        "source": "world_state.proxmox_vms",
        "declared_target": declared_vm or declared_vmid,
        "observed_target": f"vm:{observed_name}/{observed_vmid}",
        "observed": f"VM status={status or 'unknown'}",
        "vmid": observed_vmid if isinstance(observed_vmid, int) else None,
    }


def runtime_identity_for_service(service: dict[str, Any], host_witness: dict[str, Any]) -> dict[str, Any]:
    if host_witness.get("status") != "pass":
        return {
            "status": "fail",
            "required": True,
            "source": host_witness.get("source"),
            "declared_target": service.get("vm"),
            "observed_target": host_witness.get("observed_target"),
            "observed": "runtime instance identity is unavailable because the declared host witness failed",
            "identity_type": "unknown",
        }

    declared_vm = str(service.get("vm", "")).strip()
    identity_type = "host_instance" if declared_vm == TOPOLOGY_HOST else "vm_instance"
    return {
        "status": "pass",
        "required": True,
        "source": host_witness.get("source"),
        "declared_target": declared_vm,
        "observed_target": host_witness.get("observed_target"),
        "observed": f"observed runtime identity {host_witness.get('observed_target')}",
        "identity_type": identity_type,
    }


def receipt_witness_for_service(
    repo_root: Path,
    service: dict[str, Any],
    topology: dict[str, Any],
    *,
    environment: str,
) -> dict[str, Any]:
    latest = latest_receipt_for_service(repo_root, service, topology, environment=environment)
    if not latest:
        return {
            "status": "fail",
            "required": True,
            "source": "receipts.live_applies",
            "declared_target": environment,
            "observed_target": None,
            "observed": f"no successful {environment} assurance receipt matched this service or host",
        }
    return {
        "status": "pass",
        "required": True,
        "source": "receipts.live_applies",
        "declared_target": environment,
        "observed_target": latest["receipt_id"],
        "observed": f"{latest['receipt_id']} recorded on {latest['recorded_on']}",
        "receipt": latest,
    }


def overall_attestation_status(
    host_witness: dict[str, Any],
    runtime_identity: dict[str, Any],
    endpoint_proof: dict[str, Any],
    route_proof: dict[str, Any],
    receipt_witness: dict[str, Any],
) -> str:
    required_items = [host_witness, runtime_identity, endpoint_proof, receipt_witness]
    if route_proof.get("required"):
        required_items.append(route_proof)
    if any(item.get("status") != "pass" for item in required_items):
        return "missing"
    return "attested"


def summarize_attestations(attestations: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(attestations),
        "attested": 0,
        "missing": 0,
        "route_required": 0,
        "route_failed": 0,
        "endpoint_failed": 0,
        "receipt_missing": 0,
        "host_failed": 0,
    }
    for item in attestations:
        status = item.get("status")
        if status == "attested":
            summary["attested"] += 1
        else:
            summary["missing"] += 1

        route_proof = item.get("route_proof", {})
        if route_proof.get("required"):
            summary["route_required"] += 1
            if route_proof.get("status") != "pass":
                summary["route_failed"] += 1

        if item.get("endpoint_proof", {}).get("status") != "pass":
            summary["endpoint_failed"] += 1
        if item.get("receipt_witness", {}).get("status") != "pass":
            summary["receipt_missing"] += 1
        if item.get("host_witness", {}).get("status") != "pass":
            summary["host_failed"] += 1
    return summary


def collect_one_service_attestation(
    repo_root: Path,
    service: dict[str, Any],
    environment: str,
    binding: dict[str, Any],
    topology: dict[str, Any],
    contract: dict[str, Any],
    snapshot_by_name: dict[str, dict[str, Any]],
    snapshot_by_vmid: dict[int, dict[str, Any]],
    stack: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    host_witness = host_witness_for_service(service, snapshot_by_name, snapshot_by_vmid, stack)
    runtime_identity = runtime_identity_for_service(service, host_witness)
    endpoint_proof = endpoint_proof_for_service(
        service,
        topology,
        contract,
        binding,
        timeout_seconds=timeout_seconds,
    )
    route_proof = route_proof_for_service(service, binding, timeout_seconds=timeout_seconds)
    receipt_witness = receipt_witness_for_service(repo_root, service, topology, environment=environment)
    status = overall_attestation_status(
        host_witness,
        runtime_identity,
        endpoint_proof,
        route_proof,
        receipt_witness,
    )
    return {
        "service_id": service["id"],
        "service_name": service.get("name", service["id"]),
        "environment": environment,
        "status": status,
        "declared": {
            "vm": service.get("vm"),
            "vmid": service.get("vmid"),
            "binding_url": binding.get("url"),
            "public_url": service.get("public_url"),
            "internal_url": service.get("internal_url"),
            "exposure": service.get("exposure"),
        },
        "host_witness": host_witness,
        "runtime_identity": runtime_identity,
        "endpoint_proof": endpoint_proof,
        "route_proof": route_proof,
        "receipt_witness": receipt_witness,
    }


def attestation_tasks(
    services: list[dict[str, Any]],
    topology_map: dict[str, Any],
    contracts: dict[str, Any],
    requested_environment: str | None,
    requested_service_id: str | None = None,
) -> list[tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    tasks: list[tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for service in services:
        if service.get("lifecycle_status") != "active":
            continue
        service_id = service.get("id")
        if not isinstance(service_id, str) or not service_id:
            continue
        if requested_service_id and service_id != requested_service_id:
            continue
        topology = topology_map.get(service_id, {})
        contract_id = str(service.get("health_probe_id") or service_id)
        contract = contracts.get(contract_id, {})
        for environment, binding in active_bindings(service, requested_environment):
            tasks.append((service, environment, binding, topology if isinstance(topology, dict) else {}, contract if isinstance(contract, dict) else {}))
    return tasks


def collect_declared_live_attestations(
    repo_root: Path | str | None = None,
    *,
    environment: str = "production",
    service_id: str | None = None,
    world_state_dsn: str | None = None,
    timeout_seconds: float = 5.0,
    max_workers: int = 16,
) -> dict[str, Any]:
    resolved_repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    services = load_service_catalog(resolved_repo_root)
    topology_map = load_platform_topology(resolved_repo_root)
    contracts = load_health_probe_catalog(resolved_repo_root)
    stack = load_stack(resolved_repo_root)
    snapshot = load_proxmox_runtime_snapshot(resolved_repo_root, world_state_dsn=world_state_dsn)
    snapshot_by_name, snapshot_by_vmid = vm_snapshot_index(snapshot)
    tasks = attestation_tasks(services, topology_map, contracts, environment, service_id)

    attestations: list[dict[str, Any]] = []
    worker_count = min(max_workers, len(tasks) or 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                collect_one_service_attestation,
                resolved_repo_root,
                service,
                binding_environment,
                binding,
                topology,
                contract,
                snapshot_by_name,
                snapshot_by_vmid,
                stack,
                timeout_seconds=timeout_seconds,
            )
            for service, binding_environment, binding, topology, contract in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            attestations.append(future.result())

    attestations.sort(key=lambda item: (item["environment"], item["service_id"]))
    return {
        "schema_version": "1.0.0",
        "environment": environment,
        "generated_at": isoformat(utc_now()),
        "summary": summarize_attestations(attestations),
        "services": attestations,
    }


def collect_declared_live_service_attestation(
    service_id: str,
    repo_root: Path | str | None = None,
    *,
    environment: str = "production",
    world_state_dsn: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    payload = collect_declared_live_attestations(
        repo_root,
        environment=environment,
        service_id=service_id,
        world_state_dsn=world_state_dsn,
        timeout_seconds=timeout_seconds,
    )
    for item in payload["services"]:
        if item["service_id"] == service_id and item["environment"] == environment:
            return item
    raise ServiceAttestationNotFoundError(service_id, environment)
