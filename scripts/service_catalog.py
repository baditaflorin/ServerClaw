#!/usr/bin/env python3

import argparse
import sys
from typing import Any, Final

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from environment_topology import ALLOWED_BINDING_STATUSES, ALLOWED_ENVIRONMENTS

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


SERVICE_CATALOG_PATH: Final = repo_path("config", "service-capability-catalog.json")
SERVICE_CATALOG_SCHEMA_PATH: Final = repo_path(
    "docs", "schema", "service-capability-catalog.schema.json"
)
HOST_VARS_PATH: Final = repo_path("inventory", "host_vars", "proxmox_florin.yml")
STACK_PATH: Final = repo_path("versions", "stack.yaml")
UPTIME_MONITORS_PATH: Final = repo_path("config", "uptime-kuma", "monitors.json")
HEALTH_PROBE_CATALOG_PATH: Final = repo_path("config", "health-probe-catalog.json")
IMAGE_CATALOG_PATH: Final = repo_path("config", "image-catalog.json")
SECRET_CATALOG_PATH: Final = repo_path("config", "secret-catalog.json")

ALLOWED_CATEGORIES = {
    "observability",
    "security",
    "automation",
    "data",
    "communication",
    "access",
    "infrastructure",
}
ALLOWED_LIFECYCLE_STATES = {"active", "planned", "retiring"}
ALLOWED_EXPOSURES = {
    "edge-static",
    "edge-published",
    "informational-only",
    "private-only",
}
ALLOWED_DEPENDENCY_TYPES = {"hard", "soft", "optional"}


def require_environment_bindings(
    value: Any,
    path: str,
    *,
    public_url: str | None,
    internal_url: str | None,
    subdomain: str | None,
) -> dict[str, dict[str, str]]:
    bindings = require_mapping(value, path)
    if "production" not in bindings:
        raise ValueError(f"{path} must declare a production binding")

    normalized: dict[str, dict[str, str]] = {}
    for env_id, binding in bindings.items():
        if env_id not in ALLOWED_ENVIRONMENTS:
            raise ValueError(f"{path}.{env_id} must be one of {sorted(ALLOWED_ENVIRONMENTS)}")
        binding = require_mapping(binding, f"{path}.{env_id}")
        status = require_str(binding.get("status"), f"{path}.{env_id}.status")
        if status not in ALLOWED_BINDING_STATUSES:
            raise ValueError(
                f"{path}.{env_id}.status must be one of {sorted(ALLOWED_BINDING_STATUSES)}"
            )
        url = require_str(binding.get("url"), f"{path}.{env_id}.url")
        normalized_binding: dict[str, str] = {"status": status, "url": url}
        if "subdomain" in binding:
            normalized_binding["subdomain"] = require_str(
                binding.get("subdomain"), f"{path}.{env_id}.subdomain"
            )
        if "notes" in binding:
            normalized_binding["notes"] = require_str(binding.get("notes"), f"{path}.{env_id}.notes")

        if env_id == "production":
            expected_url = public_url or internal_url
            if expected_url and url != expected_url:
                raise ValueError(
                    f"{path}.production.url must match the service primary URL '{expected_url}'"
                )
            if subdomain is not None and normalized_binding.get("subdomain") != subdomain:
                raise ValueError(
                    f"{path}.production.subdomain must match the service subdomain '{subdomain}'"
                )

        normalized[env_id] = normalized_binding

    return normalized


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_int(value: Any, path: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    result = []
    for index, item in enumerate(items):
        result.append(require_str(item, f"{path}[{index}]"))
    if len(result) != len(set(result)):
        raise ValueError(f"{path} must not contain duplicates")
    return result


def require_degradation_modes(value: Any, path: str) -> list[dict[str, Any]]:
    modes = require_list(value, path)
    normalized: list[dict[str, Any]] = []
    seen_dependencies: set[str] = set()
    for index, mode in enumerate(modes):
        mode = require_mapping(mode, f"{path}[{index}]")
        dependency = require_str(mode.get("dependency"), f"{path}[{index}].dependency")
        if dependency in seen_dependencies:
            raise ValueError(f"{path} must not declare duplicate dependency '{dependency}'")
        seen_dependencies.add(dependency)
        dependency_type = require_str(mode.get("dependency_type"), f"{path}[{index}].dependency_type")
        if dependency_type not in ALLOWED_DEPENDENCY_TYPES:
            raise ValueError(
                f"{path}[{index}].dependency_type must be one of {sorted(ALLOWED_DEPENDENCY_TYPES)}"
            )
        degraded_behaviour = require_str(
            mode.get("degraded_behaviour"),
            f"{path}[{index}].degraded_behaviour",
        )
        degraded_for_seconds_max = require_int(
            mode.get("degraded_for_seconds_max"),
            f"{path}[{index}].degraded_for_seconds_max",
            minimum=-1,
        )
        recovery_signal = require_str(mode.get("recovery_signal"), f"{path}[{index}].recovery_signal")
        tested_by = require_str(mode.get("tested_by"), f"{path}[{index}].tested_by")
        if not tested_by.startswith("fault:"):
            raise ValueError(f"{path}[{index}].tested_by must start with 'fault:'")
        normalized.append(
            {
                "dependency": dependency,
                "dependency_type": dependency_type,
                "degraded_behaviour": degraded_behaviour,
                "degraded_for_seconds_max": degraded_for_seconds_max,
                "recovery_signal": recovery_signal,
                "tested_by": tested_by,
            }
        )
    return normalized


def load_service_catalog() -> dict[str, Any]:
    return load_json(SERVICE_CATALOG_PATH)


def health_probe_service_ids() -> set[str]:
    probe_catalog = require_mapping(load_json(HEALTH_PROBE_CATALOG_PATH), "health-probe-catalog")
    require_str(probe_catalog.get("schema_version"), "health-probe-catalog.schema_version")
    services = require_mapping(probe_catalog.get("services"), "health-probe-catalog.services")
    return {require_str(service_id, f"health-probe-catalog service id '{service_id}'") for service_id in services}


def image_catalog_ids() -> set[str]:
    image_catalog = require_mapping(load_json(IMAGE_CATALOG_PATH), "image-catalog")
    require_str(image_catalog.get("schema_version"), "image-catalog.schema_version")
    images = image_catalog.get("images")
    ids: set[str] = set()
    if isinstance(images, dict):
        for image_id, image in images.items():
            require_str(image_id, f"image-catalog.images key '{image_id}'")
            require_mapping(image, f"image-catalog.images.{image_id}")
            ids.add(image_id)
        return ids
    if isinstance(images, list):
        for index, image in enumerate(images):
            image = require_mapping(image, f"image-catalog.images[{index}]")
            ids.add(require_str(image.get("id"), f"image-catalog.images[{index}].id"))
        return ids
    raise ValueError("image-catalog.images must be a list or object")


def secret_catalog_ids() -> set[str]:
    secret_catalog = require_mapping(load_json(SECRET_CATALOG_PATH), "secret-catalog")
    require_str(secret_catalog.get("schema_version"), "secret-catalog.schema_version")
    secrets = require_list(secret_catalog.get("secrets"), "secret-catalog.secrets")
    ids: set[str] = set()
    for index, secret in enumerate(secrets):
        secret = require_mapping(secret, f"secret-catalog.secrets[{index}]")
        ids.add(require_str(secret.get("id"), f"secret-catalog.secrets[{index}].id"))
    return ids


def validate_service_catalog(catalog: dict[str, Any]) -> None:
    jsonschema.validate(
        instance=catalog,
        schema=load_json(SERVICE_CATALOG_SCHEMA_PATH),
    )

    services = require_list(catalog.get("services"), "services")
    if not services:
        raise ValueError("services must not be empty")

    host_vars = load_yaml(HOST_VARS_PATH)
    stack = load_yaml(STACK_PATH)
    monitor_catalog = load_json(UPTIME_MONITORS_PATH)
    topology = require_mapping(host_vars.get("lv3_service_topology"), "lv3_service_topology")
    guest_vmids = {
        guest["name"]: guest["vmid"]
        for guest in require_list(host_vars.get("proxmox_guests"), "proxmox_guests")
    }
    observed_guests = {
        guest["name"]
        for guest in require_list(
            stack["observed_state"]["guests"]["instances"],
            "observed_state.guests.instances",
        )
    }
    monitor_names = {monitor["name"] for monitor in monitor_catalog}
    probe_service_ids = health_probe_service_ids()
    known_image_ids = image_catalog_ids()
    known_secret_ids = secret_catalog_ids()

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    active_service_ids: set[str] = set()
    declared_probe_service_ids: set[str] = set()

    for index, service in enumerate(services):
        service = require_mapping(service, f"services[{index}]")
        service_id = require_str(service.get("id"), f"services[{index}].id")
        if service_id in seen_ids:
            raise ValueError(f"duplicate service id: {service_id}")
        seen_ids.add(service_id)

        name = require_str(service.get("name"), f"services[{index}].name")
        if name in seen_names:
            raise ValueError(f"duplicate service name: {name}")
        seen_names.add(name)

        require_str(service.get("description"), f"services[{index}].description")

        category = require_str(service.get("category"), f"services[{index}].category")
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"services[{index}].category must be one of {sorted(ALLOWED_CATEGORIES)}")

        lifecycle_status = require_str(
            service.get("lifecycle_status"),
            f"services[{index}].lifecycle_status",
        )
        if lifecycle_status not in ALLOWED_LIFECYCLE_STATES:
            raise ValueError(
                f"services[{index}].lifecycle_status must be one of {sorted(ALLOWED_LIFECYCLE_STATES)}"
            )

        vm = require_str(service.get("vm"), f"services[{index}].vm")
        vmid = service.get("vmid")
        if vmid is not None:
            vmid = require_int(vmid, f"services[{index}].vmid")
            if vm in guest_vmids and guest_vmids[vm] != vmid:
                raise ValueError(
                    f"services[{index}].vmid must match inventory vmid {guest_vmids[vm]} for {vm}"
                )

        exposure = require_str(service.get("exposure"), f"services[{index}].exposure")
        if exposure not in ALLOWED_EXPOSURES:
            raise ValueError(f"services[{index}].exposure must be one of {sorted(ALLOWED_EXPOSURES)}")

        internal_url = None
        public_url = None
        subdomain = None
        for field in ("internal_url", "public_url", "subdomain", "dashboard_url", "runbook", "adr"):
            if field in service:
                value = require_str(service.get(field), f"services[{index}].{field}")
                if field == "internal_url":
                    internal_url = value
                if field == "public_url":
                    public_url = value
                if field == "subdomain":
                    subdomain = value

        require_environment_bindings(
            service.get("environments"),
            f"services[{index}].environments",
            public_url=public_url,
            internal_url=internal_url,
            subdomain=subdomain,
        )

        runbook = service.get("runbook")
        if runbook is not None and not repo_path(runbook).exists():
            raise ValueError(f"services[{index}].runbook references missing path {runbook}")

        if "uptime_monitor_name" in service:
            monitor_name = require_str(
                service.get("uptime_monitor_name"),
                f"services[{index}].uptime_monitor_name",
            )
            if monitor_name not in monitor_names:
                raise ValueError(
                    f"services[{index}].uptime_monitor_name references unknown monitor '{monitor_name}'"
                )

        if "health_probe_id" in service:
            health_probe_id = require_str(
                service.get("health_probe_id"),
                f"services[{index}].health_probe_id",
            )
            declared_probe_service_ids.add(service_id)
            if health_probe_id not in probe_service_ids:
                raise ValueError(
                    f"services[{index}].health_probe_id references unknown health probe '{health_probe_id}'"
                )

        for image_id in require_string_list(
            service.get("image_catalog_ids", []),
            f"services[{index}].image_catalog_ids",
        ):
            if image_id not in known_image_ids:
                raise ValueError(
                    f"services[{index}].image_catalog_ids references unknown image '{image_id}'"
                )

        for secret_id in require_string_list(
            service.get("secret_catalog_ids", []),
            f"services[{index}].secret_catalog_ids",
        ):
            if secret_id not in known_secret_ids:
                raise ValueError(
                    f"services[{index}].secret_catalog_ids references unknown secret '{secret_id}'"
                )

        if "tags" in service:
            require_string_list(service.get("tags"), f"services[{index}].tags")

        if "degradation_modes" in service:
            require_degradation_modes(
                service.get("degradation_modes"),
                f"services[{index}].degradation_modes",
            )

        if lifecycle_status == "active":
            active_service_ids.add(service_id)
            if vm != "proxmox_florin" and vm not in observed_guests:
                raise ValueError(
                    f"active service '{service_id}' must reference an observed guest or host surface"
                )
            if service_id in topology:
                topology_entry = topology[service_id]
                if topology_entry.get("owning_vm") != vm:
                    raise ValueError(
                        f"service '{service_id}' vm '{vm}' does not match topology owning_vm "
                        f"'{topology_entry.get('owning_vm')}'"
                    )
                if topology_entry.get("exposure_model") != exposure:
                    raise ValueError(
                        f"service '{service_id}' exposure '{exposure}' does not match topology exposure "
                        f"'{topology_entry.get('exposure_model')}'"
                    )

    if declared_probe_service_ids != probe_service_ids:
        missing = sorted(probe_service_ids - declared_probe_service_ids)
        extra = sorted(declared_probe_service_ids - probe_service_ids)
        details = []
        if missing:
            details.append(f"missing services: {', '.join(missing)}")
        if extra:
            details.append(f"extra services: {', '.join(extra)}")
        raise ValueError(
            "service capability catalog entries that declare health probes must cover exactly the health-probe catalog services: "
            + "; ".join(details)
        )


def list_services(catalog: dict[str, Any]) -> int:
    print(f"Service catalog: {SERVICE_CATALOG_PATH}")
    print("Available services:")
    for service in sorted(catalog["services"], key=lambda item: item["id"]):
        print(
            f"  - {service['id']} [{service['category']}, {service['exposure']}]: "
            f"{service.get('internal_url', 'n/a')}"
        )
    return 0


def show_service(catalog: dict[str, Any], service_id: str) -> int:
    for service in catalog["services"]:
        if service["id"] != service_id:
            continue
        print(f"Service: {service['id']}")
        print(f"Name: {service['name']}")
        print(f"Lifecycle: {service['lifecycle_status']}")
        print(f"Category: {service['category']}")
        print(f"VM: {service['vm']}" + (f" (VMID {service['vmid']})" if "vmid" in service else ""))
        print(f"Exposure: {service['exposure']}")
        print(f"Description: {service['description']}")
        if "internal_url" in service:
            print(f"Internal URL: {service['internal_url']}")
        if "public_url" in service:
            print(f"Public URL: {service['public_url']}")
        if "subdomain" in service:
            print(f"Subdomain: {service['subdomain']}")
        if "uptime_monitor_name" in service:
            print(f"Health monitor: {service['uptime_monitor_name']}")
        if "health_probe_id" in service:
            print(f"Health probe: {service['health_probe_id']}")
        if service.get("image_catalog_ids"):
            print("Images:")
            for image_id in service["image_catalog_ids"]:
                print(f"  - {image_id}")
        if service.get("secret_catalog_ids"):
            print("Secrets:")
            for secret_id in service["secret_catalog_ids"]:
                print(f"  - {secret_id}")
        if "runbook" in service:
            print(f"Runbook: {service['runbook']}")
        if "dashboard_url" in service:
            print(f"Dashboard: {service['dashboard_url']}")
        if "adr" in service:
            print(f"ADR: {service['adr']}")
        if service.get("degradation_modes"):
            print("Degradation modes:")
            for mode in service["degradation_modes"]:
                duration = mode["degraded_for_seconds_max"]
                duration_text = "indefinite" if duration == -1 else f"{duration}s"
                print(
                    "  - "
                    f"{mode['dependency']} [{mode['dependency_type']}] "
                    f"max={duration_text} tested_by={mode['tested_by']}"
                )
                print(f"    behaviour: {mode['degraded_behaviour']}")
                print(f"    recovery: {mode['recovery_signal']}")
        environments = service.get("environments", {})
        if environments:
            print("Environments:")
            for env_id in sorted(environments):
                binding = environments[env_id]
                subdomain = f" [{binding['subdomain']}]" if "subdomain" in binding else ""
                print(
                    f"  - {env_id}: {binding['status']} -> {binding['url']}{subdomain}"
                )
        tags = service.get("tags", [])
        if tags:
            print("Tags:")
            for tag in tags:
                print(f"  - {tag}")
        return 0

    print(f"Unknown service: {service_id}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate the service capability catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and exit.")
    parser.add_argument("--list", action="store_true", help="List available services.")
    parser.add_argument("--service", help="Print a readable summary for one service id.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog = load_service_catalog()
        validate_service_catalog(catalog)
        if args.validate:
            print(f"Service catalog OK: {SERVICE_CATALOG_PATH}")
            return 0
        if args.service:
            return show_service(catalog, args.service)
        return list_services(catalog)
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("Service catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
