#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml


HOSTNAME_PORT_PATTERN = re.compile(r":(\d+)(?:/|$)")
TEMPLATE_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")
HOSTVARS_REF_PATTERN = re.compile(r"^hostvars\['proxmox_florin'\]\.([a-zA-Z0-9_]+)$")
GUEST_IP_EXPR_PATTERN = re.compile(
    r"^\(proxmox_guests \| selectattr\('name', 'equalto', '([^']+)'\) \| map\(attribute='ipv4'\) \| first\)$"
)


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "lv3"


def parse_endpoint_port(endpoint: str) -> int | None:
    match = HOSTNAME_PORT_PATTERN.search(endpoint.strip())
    if match:
        return int(match.group(1))
    return None


def compact_comments(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line).strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_inventory_vars(host_vars_path: Path) -> dict[str, Any]:
    inventory_root = host_vars_path.parent.parent
    merged: dict[str, Any] = {}
    group_vars_path = inventory_root / "group_vars" / "all.yml"
    if group_vars_path.exists():
        merged.update(load_yaml(group_vars_path))
    merged.update(load_yaml(host_vars_path))
    return merged


def resolve_expression(expression: str, context: dict[str, Any], guest_ips: dict[str, str]) -> Any:
    if expression in context:
        return context[expression]
    hostvars_ref = HOSTVARS_REF_PATTERN.match(expression)
    if hostvars_ref:
        return context.get(hostvars_ref.group(1), f"{{{{ {expression} }}}}")
    guest_ip_ref = GUEST_IP_EXPR_PATTERN.match(expression)
    if guest_ip_ref:
        return guest_ips.get(guest_ip_ref.group(1), f"{{{{ {expression} }}}}")
    return f"{{{{ {expression} }}}}"


def resolve_template_value(value: Any, context: dict[str, Any], guest_ips: dict[str, str]) -> Any:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return value

    resolved = value
    for _ in range(6):
        updated = TEMPLATE_PATTERN.sub(
            lambda match: str(resolve_expression(match.group(1).strip(), context, guest_ips)),
            resolved,
        )
        if updated == resolved:
            break
        resolved = updated

    if resolved.isdigit():
        return int(resolved)
    return resolved


class NetBoxClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.changed = False
        self.created = 0
        self.updated = 0
        self.max_attempts = 5
        self.retry_delay_seconds = 2

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query}"

        data = None
        headers = {
          "Accept": "application/json",
          "Authorization": f"Bearer {self.token}",
        }
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(request) as response:
                    raw = response.read().decode()
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode()
                last_error = RuntimeError(f"{method} {url} failed with {exc.code}: {body}")
                if exc.code >= 500 and attempt < self.max_attempts:
                    time.sleep(self.retry_delay_seconds)
                    continue
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"{method} {url} failed: {exc.reason}")
                if attempt < self.max_attempts:
                    time.sleep(self.retry_delay_seconds)
                    continue
                raise last_error from exc
        else:
            raise RuntimeError(f"{method} {url} failed after {self.max_attempts} attempts: {last_error}")

        if not raw:
            return {}
        return json.loads(raw)

    def list(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = self.request("GET", path, params=params)
        if isinstance(payload, dict) and "results" in payload:
            results = list(payload["results"])
            next_url = payload.get("next")
            while next_url:
                payload = self.request("GET", next_url.replace(self.base_url, ""))
                results.extend(payload["results"])
                next_url = payload.get("next")
            return results
        if isinstance(payload, list):
            return payload
        raise RuntimeError(f"Unexpected list payload from {path}: {payload!r}")

    def get_one(self, path: str, *, params: dict[str, Any]) -> dict[str, Any] | None:
        results = self.list(path, params=params)
        if not results:
            return None
        if len(results) > 1:
            raise RuntimeError(f"Expected one object at {path} with {params}, found {len(results)}")
        return results[0]

    @staticmethod
    def _normalize_existing(value: Any) -> Any:
        if isinstance(value, dict) and "id" in value:
            return value["id"]
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                if "id" in value[0]:
                    return [item["id"] for item in value]
                if "value" in value[0]:
                    return [item["value"] for item in value]
            return value
        return value

    def ensure(
        self,
        path: str,
        *,
        lookup: dict[str, Any],
        payload: dict[str, Any],
        update_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        existing = self.get_one(path, params=lookup)
        if existing is None:
            created = self.request("POST", path, payload=payload)
            self.changed = True
            self.created += 1
            return created

        update_fields = update_fields or list(payload.keys())
        patch: dict[str, Any] = {}
        for field in update_fields:
            desired = payload.get(field)
            observed = self._normalize_existing(existing.get(field))
            if observed != desired:
                patch[field] = desired

        if patch:
            updated = self.request("PATCH", f"{path}{existing['id']}/", payload=patch)
            self.changed = True
            self.updated += 1
            return updated
        return existing


def load_lane_catalog(path: Path) -> dict[str, Any]:
    return load_json(path)


def ensure_reference_inventory(
    client: NetBoxClient,
    host_vars: dict[str, Any],
    stack: dict[str, Any],
) -> dict[str, Any]:
    site = client.ensure(
        "/api/dcim/sites/",
        lookup={"slug": "lv3-hetzner"},
        payload={
            "name": "LV3 Hetzner",
            "slug": "lv3-hetzner",
            "status": "active",
            "description": "Single-site LV3 dedicated infrastructure hosted on Hetzner.",
        },
    )
    manufacturer = client.ensure(
        "/api/dcim/manufacturers/",
        lookup={"slug": "hetzner"},
        payload={"name": "Hetzner", "slug": "hetzner"},
    )
    device_role = client.ensure(
        "/api/dcim/device-roles/",
        lookup={"slug": "proxmox-hypervisor"},
        payload={
            "name": "Proxmox Hypervisor",
            "slug": "proxmox-hypervisor",
            "color": "607d8b",
            "vm_role": False,
        },
        update_fields=["name", "color", "vm_role"],
    )
    device_type = client.ensure(
        "/api/dcim/device-types/",
        lookup={"slug": "hetzner-dedicated-proxmox-host"},
        payload={
            "manufacturer": manufacturer["id"],
            "model": "Dedicated Proxmox Host",
            "slug": "hetzner-dedicated-proxmox-host",
            "u_height": 1,
        },
        update_fields=["manufacturer", "model", "u_height"],
    )
    platform = client.ensure(
        "/api/dcim/platforms/",
        lookup={"slug": "debian-13-proxmox-ve-9"},
        payload={
            "name": "Debian 13 + Proxmox VE 9",
            "slug": "debian-13-proxmox-ve-9",
            "description": "Managed Proxmox host platform for the LV3 single-node topology.",
        },
        update_fields=["name", "description"],
    )
    guest_platform = client.ensure(
        "/api/dcim/platforms/",
        lookup={"slug": "debian-13"},
        payload={
            "name": "Debian 13",
            "slug": "debian-13",
            "description": "Managed Debian 13 guest baseline.",
        },
        update_fields=["name", "description"],
    )
    cluster_type = client.ensure(
        "/api/virtualization/cluster-types/",
        lookup={"slug": "proxmox-ve"},
        payload={"name": "Proxmox VE", "slug": "proxmox-ve"},
    )
    cluster_group = client.ensure(
        "/api/virtualization/cluster-groups/",
        lookup={"slug": "lv3-control-plane"},
        payload={
            "name": "LV3 Control Plane",
            "slug": "lv3-control-plane",
            "description": "Single-node LV3 cluster grouping for repo-managed platform inventory.",
        },
        update_fields=["name", "description"],
    )
    cluster = client.ensure(
        "/api/virtualization/clusters/",
        lookup={"name": "proxmox-florin"},
        payload={
            "name": "proxmox-florin",
            "type": cluster_type["id"],
            "group": cluster_group["id"],
            "scope_type": "dcim.site",
            "scope_id": site["id"],
            "status": "active",
            "comments": "Single-node Proxmox VE cluster for the LV3 platform.",
        },
        update_fields=["type", "group", "scope_type", "scope_id", "status", "comments"],
    )
    device = client.ensure(
        "/api/dcim/devices/",
        lookup={"name": "proxmox_florin"},
        payload={
            "name": "proxmox_florin",
            "site": site["id"],
            "role": device_role["id"],
            "device_type": device_type["id"],
            "platform": platform["id"],
            "status": "active",
            "comments": compact_comments(
                [
                    "Repo-managed Proxmox host for the LV3 single-node platform.",
                    f"Management IPv4: {host_vars['management_ipv4']}",
                    f"Management Tailscale IPv4: {host_vars['management_tailscale_ipv4']}",
                    f"Observed Proxmox version: {stack['observed_state']['proxmox']['version']}",
                    f"Observed kernel: {stack['observed_state']['os']['kernel']}",
                ]
            ),
        },
        update_fields=["site", "role", "device_type", "platform", "status", "comments"],
    )
    return {
        "site": site,
        "manufacturer": manufacturer,
        "device_role": device_role,
        "device_type": device_type,
        "platform": platform,
        "guest_platform": guest_platform,
        "cluster": cluster,
        "device": device,
    }


def ensure_host_network_inventory(
    client: NetBoxClient,
    host_vars: dict[str, Any],
    references: dict[str, Any],
) -> dict[str, Any]:
    device = references["device"]
    site = references["site"]
    interfaces = {
        name: client.ensure(
            "/api/dcim/interfaces/",
            lookup={"device_id": device["id"], "name": name},
            payload={
                "device": device["id"],
                "name": name,
                "type": "other",
                "enabled": True,
                "description": description,
            },
            update_fields=["type", "enabled", "description"],
        )
        for name, description in {
            host_vars["management_interface"]: "Hetzner uplink interface",
            host_vars["proxmox_wan_bridge"]: "Public bridge carrying the routed uplink",
            host_vars["proxmox_internal_bridge"]: "Private bridge for managed guests",
            "tailscale0": "Host Tailscale management interface",
        }.items()
    }
    prefixes = {
        "public": client.ensure(
            "/api/ipam/prefixes/",
            lookup={"prefix": f"{host_vars['hetzner_ipv4_route_network']}/{host_vars['management_ipv4_cidr']}"},
            payload={
                "prefix": f"{host_vars['hetzner_ipv4_route_network']}/{host_vars['management_ipv4_cidr']}",
                "scope_type": "dcim.site",
                "scope_id": site["id"],
                "status": "active",
                "description": "Hetzner-routed public IPv4 subnet for the dedicated host.",
            },
            update_fields=["scope_type", "scope_id", "status", "description"],
        ),
        "internal": client.ensure(
            "/api/ipam/prefixes/",
            lookup={"prefix": host_vars["proxmox_internal_network"]},
            payload={
                "prefix": host_vars["proxmox_internal_network"],
                "scope_type": "dcim.site",
                "scope_id": site["id"],
                "status": "active",
                "description": "Private guest bridge network for the managed Proxmox guests.",
            },
            update_fields=["scope_type", "scope_id", "status", "description"],
        ),
    }
    public_ip = client.ensure(
        "/api/ipam/ip-addresses/",
        lookup={"address": f"{host_vars['management_ipv4']}/{host_vars['management_ipv4_cidr']}"},
        payload={
            "address": f"{host_vars['management_ipv4']}/{host_vars['management_ipv4_cidr']}",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interfaces[host_vars["proxmox_wan_bridge"]]["id"],
            "status": "active",
            "dns_name": "proxmox.lv3.org",
            "description": "Primary public IPv4 for the Proxmox host.",
        },
        update_fields=["assigned_object_type", "assigned_object_id", "status", "dns_name", "description"],
    )
    client.ensure(
        "/api/ipam/ip-addresses/",
        lookup={"address": f"{host_vars['proxmox_internal_ipv4']}/{host_vars['proxmox_internal_cidr']}"},
        payload={
            "address": f"{host_vars['proxmox_internal_ipv4']}/{host_vars['proxmox_internal_cidr']}",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interfaces[host_vars["proxmox_internal_bridge"]]["id"],
            "status": "active",
            "description": "Gateway address for the private guest bridge.",
        },
        update_fields=["assigned_object_type", "assigned_object_id", "status", "description"],
    )
    tailscale_ip = client.ensure(
        "/api/ipam/ip-addresses/",
        lookup={"address": f"{host_vars['management_tailscale_ipv4']}/32"},
        payload={
            "address": f"{host_vars['management_tailscale_ipv4']}/32",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interfaces["tailscale0"]["id"],
            "status": "active",
            "description": "Steady-state private management address for the Proxmox host.",
        },
        update_fields=["assigned_object_type", "assigned_object_id", "status", "description"],
    )
    client.ensure(
        "/api/dcim/devices/",
        lookup={"name": device["name"]},
        payload={"primary_ip4": tailscale_ip["id"]},
        update_fields=["primary_ip4"],
    )
    return {"interfaces": interfaces, "prefixes": prefixes, "primary_ip": public_ip}


def ensure_vm_inventory(
    client: NetBoxClient,
    host_vars: dict[str, Any],
    references: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    vm_roles: dict[str, dict[str, Any]] = {}
    vms: dict[str, dict[str, Any]] = {}
    interfaces: dict[str, dict[str, Any]] = {}
    for guest in host_vars["proxmox_guests"]:
        role_slug = slugify(guest["role"])
        if role_slug not in vm_roles:
            vm_roles[role_slug] = client.ensure(
                "/api/dcim/device-roles/",
                lookup={"slug": role_slug},
                payload={
                    "name": guest["role"].replace("-", " ").title(),
                    "slug": role_slug,
                    "color": "4caf50",
                    "vm_role": True,
                },
                update_fields=["name", "color", "vm_role"],
            )
        vm = client.ensure(
            "/api/virtualization/virtual-machines/",
            lookup={"name": guest["name"]},
            payload={
                "name": guest["name"],
                "cluster": references["cluster"]["id"],
                "role": vm_roles[role_slug]["id"],
                "platform": references["guest_platform"]["id"],
                "status": "active",
                "vcpus": guest["cores"],
                "memory": guest["memory_mb"],
                "disk": guest["disk_gb"] * 1024,
                "comments": compact_comments(
                    [
                        "Repo-managed Proxmox guest definition.",
                        f"VMID: {guest['vmid']}",
                        f"Role: {guest['role']}",
                        f"IPv4: {guest['ipv4']}/{guest['cidr']}",
                        f"Gateway: {guest['gateway4']}",
                        f"Tags: {', '.join(guest['tags'])}",
                    ]
                ),
            },
            update_fields=["cluster", "role", "platform", "status", "vcpus", "memory", "disk", "comments"],
        )
        vms[guest["name"]] = vm
        interfaces[guest["name"]] = client.ensure(
            "/api/virtualization/interfaces/",
            lookup={"virtual_machine_id": vm["id"], "name": "net0"},
            payload={
                "virtual_machine": vm["id"],
                "name": "net0",
                "enabled": True,
                "description": f"Primary interface on {host_vars['proxmox_internal_bridge']}",
            },
            update_fields=["enabled", "description"],
        )
        ip = client.ensure(
            "/api/ipam/ip-addresses/",
            lookup={"address": f"{guest['ipv4']}/{guest['cidr']}"},
            payload={
                "address": f"{guest['ipv4']}/{guest['cidr']}",
                "assigned_object_type": "virtualization.vminterface",
                "assigned_object_id": interfaces[guest["name"]]["id"],
                "status": "active",
                "description": f"Primary address for {guest['name']}.",
            },
            update_fields=["assigned_object_type", "assigned_object_id", "status", "description"],
        )
        client.ensure(
            "/api/virtualization/virtual-machines/",
            lookup={"name": guest["name"]},
            payload={"primary_ip4": ip["id"]},
            update_fields=["primary_ip4"],
        )
    return vms


def build_service_catalog(
    host_vars: dict[str, Any],
    stack: dict[str, Any],
    lane_catalog: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = {}
    topology = host_vars["lv3_service_topology"]
    guest_ips = {guest["name"]: guest["ipv4"] for guest in host_vars["proxmox_guests"]}
    tailscale_proxy_by_name = {
        normalize_key(proxy["name"]): proxy for proxy in host_vars.get("proxmox_tailscale_tcp_proxies", [])
    }
    public_ingress_by_target: dict[str, set[int]] = {}
    for forward in host_vars.get("proxmox_public_ingress_tcp_forwards", []):
        public_ingress_by_target.setdefault(forward["target_host"], set()).add(int(forward["target_port"]))

    for service_id, service in topology.items():
        owning_vm = service["owning_vm"]
        private_ip = resolve_template_value(service.get("private_ip", ""), host_vars, guest_ips)
        if owning_vm == "proxmox_florin":
            private_ip = host_vars["management_tailscale_ipv4"]
        elif not private_ip or "{{" in str(private_ip):
            private_ip = guest_ips.get(owning_vm, str(service.get("private_ip", "")))
        services[service_id] = {
            "service_id": service_id,
            "name": service["service_name"],
            "owning_vm": owning_vm,
            "ports": set(),
            "notes": [
                f"Exposure: {service['exposure_model']}",
                f"Private IP: {private_ip}",
            ],
        }
        if service.get("public_hostname"):
            services[service_id]["notes"].append(f"Public hostname: {service['public_hostname']}")

        proxy = None
        for candidate in (service_id, service["service_name"], owning_vm):
            proxy = tailscale_proxy_by_name.get(normalize_key(candidate))
            if proxy:
                break
        if proxy:
            listen_address = resolve_template_value(proxy["listen_address"], host_vars, guest_ips)
            listen_port = int(resolve_template_value(proxy["listen_port"], host_vars, guest_ips))
            upstream_host = resolve_template_value(proxy["upstream_host"], host_vars, guest_ips)
            upstream_port = int(resolve_template_value(proxy["upstream_port"], host_vars, guest_ips))
            services[service_id]["ports"].add(listen_port)
            services[service_id]["notes"].append(
                f"Tailscale proxy: {listen_address}:{listen_port} -> {upstream_host}:{upstream_port}"
            )

        access = service.get("access", {})
        if access.get("url"):
            access_url = str(resolve_template_value(access["url"], host_vars, guest_ips))
            port = parse_endpoint_port(access_url)
            if port:
                services[service_id]["ports"].add(port)
            services[service_id]["notes"].append(f"Access URL: {access_url}")
        edge = service.get("edge", {})
        if edge.get("upstream"):
            upstream = str(resolve_template_value(edge["upstream"], host_vars, guest_ips))
            port = parse_endpoint_port(upstream)
            if port:
                services[service_id]["ports"].add(port)
            services[service_id]["notes"].append(f"Upstream: {upstream}")

        if private_ip in public_ingress_by_target:
            published_ports = sorted(public_ingress_by_target[private_ip])
            services[service_id]["ports"].update(published_ports)
            services[service_id]["notes"].append(
                f"Published ingress ports: {', '.join(str(port) for port in published_ports)}"
            )

    for lane_id, lane in lane_catalog["lanes"].items():
        for surface in lane.get("current_surfaces", []):
            for service_id in surface.get("service_refs", []):
                if service_id not in services:
                    continue
                port = parse_endpoint_port(surface.get("endpoint", ""))
                if port:
                    services[service_id]["ports"].add(port)
                services[service_id]["notes"].append(
                    f"Governed surface [{lane_id}/{surface['id']}]: {surface['endpoint']}"
                )

    mail_ports = stack["desired_state"]["mail"]["published_ports"]
    for port in mail_ports:
        if "mail_platform" in services:
            services["mail_platform"]["ports"].add(port)

    return services


def ensure_service_inventory(
    client: NetBoxClient,
    service_catalog: dict[str, dict[str, Any]],
    references: dict[str, Any],
    vms: dict[str, dict[str, Any]],
) -> int:
    synced = 0
    for service in service_catalog.values():
        if not service["ports"]:
            continue
        payload = {
            "name": service["name"],
            "protocol": "tcp",
            "ports": sorted(service["ports"]),
            "description": "Repo-managed LV3 service inventory object.",
            "comments": compact_comments(
                [
                    "Repo-managed service inventory object.",
                    *service["notes"],
                ]
            ),
        }
        if service["owning_vm"] == "proxmox_florin":
            payload["parent_object_type"] = "dcim.device"
            payload["parent_object_id"] = references["device"]["id"]
            lookup = {
                "parent_object_type": "dcim.device",
                "parent_object_id": references["device"]["id"],
                "name": service["name"],
            }
        else:
            payload["parent_object_type"] = "virtualization.virtualmachine"
            payload["parent_object_id"] = vms[service["owning_vm"]]["id"]
            lookup = {
                "parent_object_type": "virtualization.virtualmachine",
                "parent_object_id": vms[service["owning_vm"]]["id"],
                "name": service["name"],
            }
        client.ensure(
            "/api/ipam/services/",
            lookup=lookup,
            payload=payload,
            update_fields=["protocol", "ports", "description", "comments", "parent_object_type", "parent_object_id"],
        )
        synced += 1
    return synced


def sync_inventory(
    *,
    api_url: str,
    api_token_file: Path,
    host_vars_path: Path,
    stack_path: Path,
    lane_catalog_path: Path,
) -> dict[str, Any]:
    token = api_token_file.read_text().strip()
    if not token:
        raise RuntimeError(f"{api_token_file} is empty")

    host_vars = load_inventory_vars(host_vars_path)
    stack = load_yaml(stack_path)
    lane_catalog = load_lane_catalog(lane_catalog_path)
    client = NetBoxClient(api_url, token)

    references = ensure_reference_inventory(client, host_vars, stack)
    network = ensure_host_network_inventory(client, host_vars, references)
    vms = ensure_vm_inventory(client, host_vars, references)
    service_catalog = build_service_catalog(host_vars, stack, lane_catalog)
    service_count = ensure_service_inventory(client, service_catalog, references, vms)

    return {
        "changed": client.changed,
        "created": client.created,
        "updated": client.updated,
        "site_name": references["site"]["name"],
        "device_name": references["device"]["name"],
        "vm_count": len(vms),
        "prefix_count": len(network["prefixes"]),
        "service_count": service_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize the canonical LV3 repo inventory and topology into NetBox."
    )
    parser.add_argument("--api-url", required=True, help="NetBox base URL, for example http://100.118.189.95:8004")
    parser.add_argument("--api-token-file", required=True, type=Path, help="Controller-local NetBox API token file.")
    parser.add_argument("--host-vars", required=True, type=Path, help="Canonical host vars path.")
    parser.add_argument("--stack", required=True, type=Path, help="Canonical stack state path.")
    parser.add_argument("--lane-catalog", required=True, type=Path, help="Canonical control-plane lane catalog path.")
    args = parser.parse_args()

    try:
        summary = sync_inventory(
            api_url=args.api_url,
            api_token_file=args.api_token_file,
            host_vars_path=args.host_vars,
            stack_path=args.stack,
            lane_catalog_path=args.lane_catalog,
        )
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        return emit_cli_error("NetBox sync", exc)

    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
