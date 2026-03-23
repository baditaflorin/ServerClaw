from __future__ import annotations

from ansible.errors import AnsibleFilterError


def _ensure_mapping(value, label):
    if not isinstance(value, dict):
        raise AnsibleFilterError(f"{label} must be a mapping")
    return value


def platform_service(catalog, service_id):
    catalog = _ensure_mapping(catalog, "platform service catalog")
    if service_id not in catalog:
        raise AnsibleFilterError(f"unknown platform service id: {service_id}")
    service = _ensure_mapping(catalog[service_id], f"platform service {service_id!r}")
    merged = dict(service)
    merged.setdefault("service_id", service_id)
    return merged


def platform_service_url(catalog, service_id, url_key):
    service = platform_service(catalog, service_id)
    urls = _ensure_mapping(service.get("urls", {}), f"platform service {service_id!r}.urls")
    if url_key not in urls:
        raise AnsibleFilterError(f"service {service_id!r} does not define url {url_key!r}")
    return urls[url_key]


def platform_service_port(catalog, service_id, port_key):
    service = platform_service(catalog, service_id)
    ports = _ensure_mapping(service.get("ports", {}), f"platform service {service_id!r}.ports")
    if port_key not in ports:
        raise AnsibleFilterError(f"service {service_id!r} does not define port {port_key!r}")
    return ports[port_key]


def platform_service_host(catalog, service_id):
    service = platform_service(catalog, service_id)
    if not service.get("private_ip"):
        raise AnsibleFilterError(f"service {service_id!r} does not define private_ip")
    return service["private_ip"]


def platform_guest(catalog, guest_name):
    catalog = _ensure_mapping(catalog, "platform guest catalog")
    if guest_name not in catalog:
        raise AnsibleFilterError(f"unknown platform guest: {guest_name}")
    return _ensure_mapping(catalog[guest_name], f"platform guest {guest_name!r}")


def platform_guest_attr(catalog, guest_name, attribute):
    guest = platform_guest(catalog, guest_name)
    if attribute not in guest:
        raise AnsibleFilterError(f"guest {guest_name!r} does not define attribute {attribute!r}")
    return guest[attribute]


class FilterModule(object):
    def filters(self):
        return {
            "platform_service": platform_service,
            "platform_service_url": platform_service_url,
            "platform_service_port": platform_service_port,
            "platform_service_host": platform_service_host,
            "platform_guest": platform_guest,
            "platform_guest_attr": platform_guest_attr,
        }
