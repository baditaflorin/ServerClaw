#!/usr/bin/env python3

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

loaded_platform = sys.modules.get("platform")
if loaded_platform is not None and not hasattr(loaded_platform, "__path__"):
    loaded_platform_file = getattr(loaded_platform, "__file__", "")
    if not str(loaded_platform_file).startswith(str(REPO_ROOT / "platform")):
        sys.modules.pop("platform", None)

from platform.repo import TOPOLOGY_HOST, TOPOLOGY_HOST_VARS_PATH

from validation_toolkit import (
    apply_identity_domain_overlay,
    require_bool,
    require_int,
    require_list,
    require_mapping,
    require_str,
)

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from environment_catalog import configured_environment_ids
from environment_topology import ALLOWED_BINDING_STATUSES
from stage_smoke import DEFAULT_SUITE_ID, DEFAULT_SUITE_NAME, declared_smoke_suites

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


SERVICE_CATALOG_PATH: Final = repo_path("config", "service-capability-catalog.json")
SERVICE_CATALOG_SCHEMA_PATH: Final = repo_path("docs", "schema", "service-capability-catalog.schema.json")
ADR_DIR: Final = repo_path("docs", "adr")
SERVICE_BUNDLE_ROOT: Final = repo_path("catalog", "services")
STACK_PATH: Final = repo_path("versions", "stack.yaml")
WORKSTREAMS_PATH: Final = repo_path("workstreams.yaml")
UPTIME_MONITORS_PATH: Final = repo_path("config", "uptime-kuma", "monitors.json")
HEALTH_PROBE_CATALOG_PATH: Final = repo_path("config", "health-probe-catalog.json")
IMAGE_CATALOG_PATH: Final = repo_path("config", "image-catalog.json")
SECRET_CATALOG_PATH: Final = repo_path("config", "secret-catalog.json")
ALLOWED_ENVIRONMENTS = set(configured_environment_ids())

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


def current_git_branch() -> str:
    try:
        branch = subprocess.check_output(
            ["git", "-C", str(repo_path()), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "HEAD"
    return branch or "HEAD"


def service_catalog_enforces_observed_guest_surfaces() -> bool:
    registry = load_yaml(WORKSTREAMS_PATH)
    if not isinstance(registry, dict):
        return True
    release_policy = registry.get("release_policy")
    if not isinstance(release_policy, dict):
        return True
    branch_policy = release_policy.get("versions_stack_branch_policy")
    if branch_policy != "main_only":
        return True
    return current_git_branch() == "main"


def validate_smoke_suites(value: Any, path: str) -> list[dict[str, Any]]:
    suites = require_list(value, path)
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, suite in enumerate(suites):
        suite = require_mapping(suite, f"{path}[{index}]")
        suite_id = require_str(suite.get("id"), f"{path}[{index}].id")
        if suite_id in seen_ids:
            raise ValueError(f"{path} must not declare duplicate smoke suite '{suite_id}'")
        seen_ids.add(suite_id)
        name = require_str(suite.get("name"), f"{path}[{index}].name")
        description = require_str(suite.get("description"), f"{path}[{index}].description")
        required_receipt_keywords = unique_string_list(
            suite.get("required_receipt_keywords", []),
            f"{path}[{index}].required_receipt_keywords",
        )
        required_verification_checks = unique_string_list(
            suite.get("required_verification_checks", []),
            f"{path}[{index}].required_verification_checks",
        )
        if not required_receipt_keywords and not required_verification_checks:
            raise ValueError(f"{path}[{index}] must declare at least one receipt keyword or verification check token")
        normalized.append(
            {
                "id": suite_id,
                "name": name,
                "description": description,
                "required_receipt_keywords": required_receipt_keywords,
                "required_verification_checks": required_verification_checks,
            }
        )
    return normalized


def validate_environment_bindings(
    value: Any,
    path: str,
    *,
    public_url: str | None,
    internal_url: str | None,
    subdomain: str | None,
) -> dict[str, dict[str, Any]]:
    bindings = require_mapping(value, path)
    if "production" not in bindings:
        raise ValueError(f"{path} must declare a production binding")

    normalized: dict[str, dict[str, Any]] = {}
    for env_id, binding in bindings.items():
        if env_id not in ALLOWED_ENVIRONMENTS:
            raise ValueError(f"{path}.{env_id} must be one of {sorted(ALLOWED_ENVIRONMENTS)}")
        binding = require_mapping(binding, f"{path}.{env_id}")
        status = require_str(binding.get("status"), f"{path}.{env_id}.status")
        if status not in ALLOWED_BINDING_STATUSES:
            raise ValueError(f"{path}.{env_id}.status must be one of {sorted(ALLOWED_BINDING_STATUSES)}")
        url = require_str(binding.get("url"), f"{path}.{env_id}.url")
        normalized_binding: dict[str, str] = {"status": status, "url": url}
        if "subdomain" in binding:
            normalized_binding["subdomain"] = require_str(binding.get("subdomain"), f"{path}.{env_id}.subdomain")
        if "stage_ready" in binding:
            normalized_binding["stage_ready"] = require_bool(
                binding.get("stage_ready"),
                f"{path}.{env_id}.stage_ready",
            )
        if "smoke_suite_ids" in binding:
            normalized_binding["smoke_suite_ids"] = unique_string_list(
                binding.get("smoke_suite_ids"),
                f"{path}.{env_id}.smoke_suite_ids",
            )
        if "notes" in binding:
            normalized_binding["notes"] = require_str(binding.get("notes"), f"{path}.{env_id}.notes")
        if "smoke_suites" in binding:
            normalized_binding["smoke_suites"] = validate_smoke_suites(
                binding.get("smoke_suites"),
                f"{path}.{env_id}.smoke_suites",
            )

        if normalized_binding.get("stage_ready") and status != "active":
            raise ValueError(f"{path}.{env_id}.stage_ready requires an active environment binding")
        if normalized_binding.get("stage_ready") and not normalized_binding.get("smoke_suite_ids"):
            raise ValueError(f"{path}.{env_id}.stage_ready requires at least one smoke suite id")

        if env_id == "production":
            expected_url = public_url or internal_url
            if expected_url and url != expected_url:
                raise ValueError(f"{path}.production.url must match the service primary URL '{expected_url}'")
            if subdomain is not None and normalized_binding.get("subdomain") != subdomain:
                raise ValueError(f"{path}.production.subdomain must match the service subdomain '{subdomain}'")

        normalized[env_id] = normalized_binding

    return normalized


def unique_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    result = []
    for index, item in enumerate(items):
        result.append(require_str(item, f"{path}[{index}]"))
    if len(result) != len(set(result)):
        raise ValueError(f"{path} must not contain duplicates")
    return result


def validate_degradation_modes(value: Any, path: str) -> list[dict[str, Any]]:
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
            raise ValueError(f"{path}[{index}].dependency_type must be one of {sorted(ALLOWED_DEPENDENCY_TYPES)}")
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
    return apply_identity_domain_overlay(load_json(SERVICE_CATALOG_PATH))


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


def uptime_monitor_names() -> tuple[set[str], bool]:
    if not UPTIME_MONITORS_PATH.exists():
        return set(), False

    monitor_catalog = require_list(load_json(UPTIME_MONITORS_PATH), "uptime-kuma.monitors")
    names: set[str] = set()
    for index, monitor in enumerate(monitor_catalog):
        monitor = require_mapping(monitor, f"uptime-kuma.monitors[{index}]")
        names.add(require_str(monitor.get("name"), f"uptime-kuma.monitors[{index}].name"))
    return names, True


def validate_service_catalog(catalog: dict[str, Any]) -> None:
    from standby_capacity import validate_catalog_standby_policies

    jsonschema.validate(
        instance=catalog,
        schema=load_json(SERVICE_CATALOG_SCHEMA_PATH),
    )

    services = require_list(catalog.get("services"), "services")
    if not services:
        raise ValueError("services must not be empty")

    host_vars = load_yaml(TOPOLOGY_HOST_VARS_PATH)
    stack = load_yaml(STACK_PATH)
    topology = require_mapping(host_vars.get("lv3_service_topology"), "lv3_service_topology")
    guest_vmids = {
        guest["name"]: guest["vmid"] for guest in require_list(host_vars.get("proxmox_guests"), "proxmox_guests")
    }
    observed_guests = {
        guest["name"]
        for guest in require_list(
            stack["observed_state"]["guests"]["instances"],
            "observed_state.guests.instances",
        )
    }
    allowed_service_surfaces = set(observed_guests)
    if not service_catalog_enforces_observed_guest_surfaces():
        allowed_service_surfaces.update(guest_vmids.keys())
    monitor_names, has_monitor_catalog = uptime_monitor_names()
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
            raise ValueError(f"services[{index}].lifecycle_status must be one of {sorted(ALLOWED_LIFECYCLE_STATES)}")

        vm = require_str(service.get("vm"), f"services[{index}].vm")
        vmid = service.get("vmid")
        if vmid is not None:
            vmid = require_int(vmid, f"services[{index}].vmid", minimum=1)
            if vm in guest_vmids and guest_vmids[vm] != vmid:
                raise ValueError(f"services[{index}].vmid must match inventory vmid {guest_vmids[vm]} for {vm}")

        exposure = require_str(service.get("exposure"), f"services[{index}].exposure")
        if exposure not in ALLOWED_EXPOSURES:
            raise ValueError(f"services[{index}].exposure must be one of {sorted(ALLOWED_EXPOSURES)}")

        internal_url = None
        public_url = None
        subdomain = None
        adr = None
        for field in ("internal_url", "public_url", "subdomain", "dashboard_url", "runbook", "adr"):
            if field in service:
                value = require_str(service.get(field), f"services[{index}].{field}")
                if field == "internal_url":
                    internal_url = value
                if field == "public_url":
                    public_url = value
                if field == "subdomain":
                    subdomain = value
                if field == "adr":
                    adr = value

        adr_file = None
        if "adr_file" in service:
            adr_file = require_str(service.get("adr_file"), f"services[{index}].adr_file")
            adr_path = repo_path(adr_file)
            if not adr_path.exists():
                raise ValueError(f"services[{index}].adr_file references missing path {adr_file}")
            try:
                adr_path.relative_to(ADR_DIR)
            except ValueError as exc:
                raise ValueError(f"services[{index}].adr_file must stay under docs/adr/") from exc
            if adr is None:
                raise ValueError(f"services[{index}].adr_file requires services[{index}].adr")
            if adr_path.name.split("-", 1)[0] != adr:
                raise ValueError(f"services[{index}].adr_file must match ADR {adr}")
        if adr is not None:
            adr_matches = sorted(ADR_DIR.glob(f"{adr}-*.md"))
            if not adr_matches:
                raise ValueError(f"services[{index}].adr references unknown ADR '{adr}'")
            if len(adr_matches) > 1 and adr_file is None:
                raise ValueError(f"services[{index}].adr_file is required because ADR {adr} resolves to multiple files")

        validate_environment_bindings(
            service.get("environments"),
            f"services[{index}].environments",
            public_url=public_url,
            internal_url=internal_url,
            subdomain=subdomain,
        )
        active_environment_ids = [
            env_id
            for env_id, binding in service.get("environments", {}).items()
            if isinstance(binding, dict) and binding.get("status") == "active"
        ]
        for env_id in active_environment_ids:
            if not declared_smoke_suites(service, env_id):
                raise ValueError(f"services[{index}].environments.{env_id} must resolve at least one stage smoke suite")

        runbook = service.get("runbook")
        if runbook is not None and not repo_path(runbook).exists():
            raise ValueError(f"services[{index}].runbook references missing path {runbook}")

        if "uptime_monitor_name" in service:
            monitor_name = require_str(
                service.get("uptime_monitor_name"),
                f"services[{index}].uptime_monitor_name",
            )
            if has_monitor_catalog and monitor_name not in monitor_names:
                raise ValueError(f"services[{index}].uptime_monitor_name references unknown monitor '{monitor_name}'")

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

        for image_id in unique_string_list(
            service.get("image_catalog_ids", []),
            f"services[{index}].image_catalog_ids",
        ):
            if image_id not in known_image_ids:
                raise ValueError(f"services[{index}].image_catalog_ids references unknown image '{image_id}'")

        for secret_id in unique_string_list(
            service.get("secret_catalog_ids", []),
            f"services[{index}].secret_catalog_ids",
        ):
            if secret_id not in known_secret_ids:
                raise ValueError(f"services[{index}].secret_catalog_ids references unknown secret '{secret_id}'")

        if "tags" in service:
            unique_string_list(service.get("tags"), f"services[{index}].tags")

        if "degradation_modes" in service:
            validate_degradation_modes(
                service.get("degradation_modes"),
                f"services[{index}].degradation_modes",
            )

        if lifecycle_status == "active":
            active_service_ids.add(service_id)
            if vm != TOPOLOGY_HOST and vm not in allowed_service_surfaces:
                raise ValueError(f"active service '{service_id}' must reference an observed guest or host surface")
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

    validate_catalog_standby_policies(catalog)


def list_services(catalog: dict[str, Any]) -> int:
    print(f"Service catalog: {SERVICE_CATALOG_PATH}")
    print("Available services:")
    for service in sorted(catalog["services"], key=lambda item: item["id"]):
        print(
            f"  - {service['id']} [{service['category']}, {service['exposure']}]: {service.get('internal_url', 'n/a')}"
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
        bundle_path = SERVICE_BUNDLE_ROOT / service["id"] / "service.yaml"
        if bundle_path.exists():
            print(f"Source bundle: {bundle_path.relative_to(repo_path())}")
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
                print(f"  - {env_id}: {binding['status']} -> {binding['url']}{subdomain}")
                smoke_suites = declared_smoke_suites(service, env_id) if binding.get("status") == "active" else []
                if smoke_suites:
                    explicit = isinstance(binding.get("smoke_suites"), list)
                    qualifier = "declared" if explicit else "inherited"
                    print(f"    smoke suites ({qualifier}):")
                    for suite in smoke_suites:
                        print(f"      - {suite['id']}: {suite['name']}")
                elif binding.get("status") == "active":
                    print(f"    smoke suites: {DEFAULT_SUITE_ID} ({DEFAULT_SUITE_NAME})")
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
    except Exception as exc:
        return emit_cli_error("Service catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
