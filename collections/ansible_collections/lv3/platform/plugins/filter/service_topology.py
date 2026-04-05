from __future__ import annotations

from ansible.errors import AnsibleFilterError


def _ensure_catalog(catalog):
    if not isinstance(catalog, dict):
        raise AnsibleFilterError(
            "service topology catalog must be a mapping keyed by service id"
        )
    return catalog


def _service_with_id(service_id, service_data):
    if not isinstance(service_data, dict):
        raise AnsibleFilterError(
            f"service topology entry {service_id!r} must be a mapping"
        )
    merged = dict(service_data)
    merged.setdefault("service_id", service_id)
    return merged


def service_topology_get(catalog, service_id):
    catalog = _ensure_catalog(catalog)
    if service_id not in catalog:
        raise AnsibleFilterError(f"unknown service topology id: {service_id}")
    return _service_with_id(service_id, catalog[service_id])


def service_topology_edge_certificate_domains(catalog):
    domains = []
    for service_id, service_data in _ensure_catalog(catalog).items():
        service = _service_with_id(service_id, service_data)
        edge = service.get("edge", {})
        if edge.get("enabled") and edge.get("tls", True) and service.get(
            "public_hostname"
        ):
            domains.extend(edge.get("aliases", []))
            domains.append(service["public_hostname"])
    return domains


def service_topology_edge_sites(catalog):
    sites = []
    for service_id, service_data in _ensure_catalog(catalog).items():
        service = _service_with_id(service_id, service_data)
        edge = service.get("edge", {})
        if not edge.get("enabled"):
            continue

        kind = edge.get("kind")
        hostname = service.get("public_hostname")
        if not hostname:
            raise AnsibleFilterError(
                f"service {service_id} enables edge publication without public_hostname"
            )

        site = {
            "hostname": hostname,
            "kind": kind,
        }
        if "noindex" in edge:
            site["noindex"] = edge["noindex"]
        if kind == "static":
            site["slug"] = edge["slug"]
        elif kind == "proxy":
            site["upstream"] = edge["upstream"]
            for optional_field in (
                "aliases",
                "blocked_exact_paths",
                "chunked_transfer_encoding",
                "client_max_body_size",
                "crawl_policy_enabled",
                "exact_redirects",
                "preserve_upstream_security_headers",
                "prefix_proxy_routes",
                "preserve_upstream_security_headers",
                "proxy_hide_headers",
                "proxy_read_timeout_seconds",
                "proxy_request_buffering",
                "proxy_send_timeout_seconds",
                "root_proxy_path",
                "security_headers_enabled",
                "server_sent_events",
                "upstream_ssl_verify",
            ):
                if optional_field in edge:
                    site[optional_field] = edge[optional_field]
        else:
            raise AnsibleFilterError(
                f"service {service_id} has unsupported edge kind: {kind}"
            )

        sites.append(site)
    return sites


def service_topology_edge_static_sites(catalog):
    static_sites = []
    for service_id, service_data in _ensure_catalog(catalog).items():
        service = _service_with_id(service_id, service_data)
        edge = service.get("edge", {})
        if not edge.get("enabled") or edge.get("kind") != "static":
            continue

        static_site = {
            "slug": edge["slug"],
            "hostname": service["public_hostname"],
            "title": edge["title"],
            "description": edge["description"],
            "meta": edge["meta"],
        }
        if "action_url" in edge:
            static_site["action_url"] = edge["action_url"]
        if "action_label" in edge:
            static_site["action_label"] = edge["action_label"]
        static_sites.append(static_site)
    return static_sites


def service_topology_dns_records(catalog, visibility=None):
    records = []
    for service_id, service_data in _ensure_catalog(catalog).items():
        service = _service_with_id(service_id, service_data)
        dns = service.get("dns", {})
        if not dns.get("managed"):
            continue
        if visibility is not None and dns.get("visibility") != visibility:
            continue

        if not dns.get("name"):
            raise AnsibleFilterError(
                f"service {service_id} manages DNS without dns.name"
            )
        if not dns.get("target"):
            raise AnsibleFilterError(
                f"service {service_id} manages DNS without dns.target"
            )

        records.append(
            {
                "name": dns["name"],
                "type": dns.get("type", "A"),
                "value": dns["target"],
                "ttl": dns.get("ttl", 60),
            }
        )
        for extra_record in dns.get("additional_records", []):
            if not isinstance(extra_record, dict):
                raise AnsibleFilterError(
                    f"service {service_id} declares a non-mapping dns.additional_records entry"
                )
            if not extra_record.get("name"):
                raise AnsibleFilterError(
                    f"service {service_id} manages additional DNS without dns.additional_records[].name"
                )
            if not extra_record.get("target"):
                raise AnsibleFilterError(
                    f"service {service_id} manages additional DNS without dns.additional_records[].target"
                )
            records.append(
                {
                    "name": extra_record["name"],
                    "type": extra_record.get("type", dns.get("type", "A")),
                    "value": extra_record["target"],
                    "ttl": extra_record.get("ttl", dns.get("ttl", 60)),
                }
            )
    return records


class FilterModule(object):
    def filters(self):
        return {
            "service_topology_get": service_topology_get,
            "service_topology_edge_certificate_domains": (
                service_topology_edge_certificate_domains
            ),
            "service_topology_edge_sites": service_topology_edge_sites,
            "service_topology_edge_static_sites": service_topology_edge_static_sites,
            "service_topology_dns_records": service_topology_dns_records,
        }
