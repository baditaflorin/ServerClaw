#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from validation_toolkit import require_list, require_mapping, require_str

from controller_automation_toolkit import emit_cli_error


SAMPLE_CATALOG_PATH = REPO_ROOT / "reference-deployments" / "catalog.yaml"
PROVIDER_PROFILES_PATH = REPO_ROOT / "config" / "reference-provider-profiles.yaml"
SUPPORTED_SCHEMA_VERSION = "1.0.0"
TEMPLATE_PATTERN = re.compile(r"{{\s*([a-z0-9_]+)\s*}}")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
EXAMPLE_DOMAIN_SUFFIXES = (".example.test", ".example.invalid")
EXAMPLE_EMAIL_SUFFIXES = ("@example.test", "@example.com", "@example.invalid")
ALLOWED_EXAMPLE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)
REQUIRED_PROFILE_VALUE_KEYS = {
    "sample_ops_user",
    "sample_proxmox_host_label",
    "sample_proxmox_node_name",
    "sample_public_edge_guest_name",
    "sample_runtime_guest_name",
    "sample_proxmox_management_ipv4",
    "sample_proxmox_management_ipv4_cidr",
    "sample_proxmox_management_gateway4",
    "sample_proxmox_management_tailscale_ipv4",
    "sample_internal_gateway_ipv4",
    "sample_internal_cidr",
    "sample_internal_network_cidr",
    "sample_public_edge_ipv4",
    "sample_runtime_ipv4",
    "sample_public_base_domain",
    "sample_operator_base_domain",
    "sample_public_edge_hostname",
    "sample_proxmox_api_url",
    "sample_overlay_root",
    "sample_dns_provider",
    "sample_infrastructure_provider",
    "sample_requester_email",
}


def require_identifier(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{path} must use lowercase letters, numbers, and hyphens")
    return value


def require_repo_relative_path(value: Any, path: str) -> str:
    normalized = require_str(value, path).replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError(f"{path} must be repository-relative, not absolute")
    if re.match(r"^[A-Za-z]:/", normalized):
        raise ValueError(f"{path} must be repository-relative, not absolute")
    if ".." in Path(normalized).parts:
        raise ValueError(f"{path} must not escape the repository root")
    return normalized


def load_yaml_file(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return require_mapping(payload, str(path))


def load_sample_catalog(path: Path = SAMPLE_CATALOG_PATH) -> dict[str, Any]:
    return load_yaml_file(path)


def load_provider_profiles(path: Path = PROVIDER_PROFILES_PATH) -> dict[str, Any]:
    return load_yaml_file(path)


def _is_example_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(ip in network for network in ALLOWED_EXAMPLE_NETWORKS)


def _validate_example_scalar(key: str, value: str, path: str) -> None:
    if key.endswith("_overlay_root"):
        if not value.startswith(".local/"):
            raise ValueError(f"{path} must stay under .local/")
        return

    if key.endswith("_email"):
        if not value.endswith(EXAMPLE_EMAIL_SUFFIXES):
            raise ValueError(f"{path} must use an example email domain")
        return

    if key.endswith("_url"):
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"{path} must be a valid URL")
        host = parsed.hostname or ""
        if host and not (host.endswith(EXAMPLE_DOMAIN_SUFFIXES) or _is_example_ip(host)):
            raise ValueError(f"{path} must use an example hostname or address")
        return

    if key.endswith("_domain") or key.endswith("_hostname"):
        if not (value.endswith(EXAMPLE_DOMAIN_SUFFIXES) or _is_example_ip(value)):
            raise ValueError(f"{path} must use an example hostname or domain")
        return

    if key.endswith("_ipv4") or key.endswith("_gateway4"):
        if not _is_example_ip(value):
            raise ValueError(f"{path} must use a private or documentation IPv4 address")
        return

    if key.endswith("_network_cidr"):
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError(f"{path} must be a valid IPv4 CIDR") from exc
        if not any(network.subnet_of(allowed) or network == allowed for allowed in ALLOWED_EXAMPLE_NETWORKS):
            raise ValueError(f"{path} must use a private or documentation CIDR")
        return


def validate_provider_profile_catalog(
    payload: dict[str, Any],
    *,
    path: Path = PROVIDER_PROFILES_PATH,
) -> dict[str, dict[str, Any]]:
    if require_str(payload.get("schema_version"), f"{path}.schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}.schema_version must be {SUPPORTED_SCHEMA_VERSION}")

    profiles = require_list(payload.get("profiles"), f"{path}.profiles")
    if not profiles:
        raise ValueError(f"{path}.profiles must not be empty")

    index: dict[str, dict[str, Any]] = {}
    for profile_index, raw_profile in enumerate(profiles):
        profile_path = f"{path}.profiles[{profile_index}]"
        profile = require_mapping(raw_profile, profile_path)
        profile_id = require_identifier(profile.get("id"), f"{profile_path}.id")
        if profile_id in index:
            raise ValueError(f"{profile_path}.id duplicates '{profile_id}'")
        require_str(profile.get("title"), f"{profile_path}.title")
        require_str(profile.get("description"), f"{profile_path}.description")
        values = require_mapping(profile.get("values"), f"{profile_path}.values")

        missing = sorted(REQUIRED_PROFILE_VALUE_KEYS - set(values))
        if missing:
            raise ValueError(f"{profile_path}.values is missing required keys: {', '.join(missing)}")

        normalized_values: dict[str, str] = {}
        for key, raw_value in values.items():
            value_path = f"{profile_path}.values.{key}"
            normalized_key = require_str(key, value_path)
            normalized_value = require_str(raw_value, value_path)
            normalized_values[normalized_key] = normalized_value
            _validate_example_scalar(normalized_key, normalized_value, value_path)

        index[profile_id] = {
            "id": profile_id,
            "title": profile["title"],
            "description": profile["description"],
            "values": normalized_values,
        }

    return index


def _extract_placeholders(template_text: str) -> set[str]:
    return set(TEMPLATE_PATTERN.findall(template_text))


def validate_sample_catalog(
    payload: dict[str, Any],
    profile_index: dict[str, dict[str, Any]],
    *,
    path: Path = SAMPLE_CATALOG_PATH,
) -> list[dict[str, Any]]:
    if require_str(payload.get("schema_version"), f"{path}.schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}.schema_version must be {SUPPORTED_SCHEMA_VERSION}")

    samples = require_list(payload.get("samples"), f"{path}.samples")
    if not samples:
        raise ValueError(f"{path}.samples must not be empty")

    normalized_samples: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for sample_index, raw_sample in enumerate(samples):
        sample_path = f"{path}.samples[{sample_index}]"
        sample = require_mapping(raw_sample, sample_path)
        sample_id = require_identifier(sample.get("id"), f"{sample_path}.id")
        if sample_id in seen_ids:
            raise ValueError(f"{sample_path}.id duplicates '{sample_id}'")
        seen_ids.add(sample_id)

        title = require_str(sample.get("title"), f"{sample_path}.title")
        description = require_str(sample.get("description"), f"{sample_path}.description")

        canonical_examples: list[str] = []
        for example_index, raw_example in enumerate(
            require_list(sample.get("canonical_examples"), f"{sample_path}.canonical_examples")
        ):
            example_path = require_repo_relative_path(
                raw_example,
                f"{sample_path}.canonical_examples[{example_index}]",
            )
            if not (REPO_ROOT / example_path).is_file():
                raise ValueError(
                    f"{sample_path}.canonical_examples[{example_index}] references missing file '{example_path}'"
                )
            canonical_examples.append(example_path)

        provider_ids: list[str] = []
        for provider_index, raw_provider_id in enumerate(
            require_list(sample.get("supported_provider_profiles"), f"{sample_path}.supported_provider_profiles")
        ):
            provider_id = require_identifier(
                raw_provider_id,
                f"{sample_path}.supported_provider_profiles[{provider_index}]",
            )
            if provider_id not in profile_index:
                raise ValueError(
                    f"{sample_path}.supported_provider_profiles references unknown profile '{provider_id}'"
                )
            provider_ids.append(provider_id)

        render_files = require_list(sample.get("render_files"), f"{sample_path}.render_files")
        if not render_files:
            raise ValueError(f"{sample_path}.render_files must not be empty")

        normalized_render_files: list[dict[str, str]] = []
        seen_destinations: set[str] = set()
        destination_roots: set[str] = set()
        for render_index, raw_render_file in enumerate(render_files):
            render_path = f"{sample_path}.render_files[{render_index}]"
            render_file = require_mapping(raw_render_file, render_path)
            source = require_repo_relative_path(render_file.get("source"), f"{render_path}.source")
            destination = require_repo_relative_path(render_file.get("destination"), f"{render_path}.destination")
            description_text = require_str(render_file.get("description"), f"{render_path}.description")
            if destination in seen_destinations:
                raise ValueError(f"{render_path}.destination duplicates '{destination}'")
            seen_destinations.add(destination)
            destination_roots.add(Path(destination).parts[0])
            source_path = REPO_ROOT / source
            if not source_path.is_file():
                raise ValueError(f"{render_path}.source references missing template '{source}'")
            placeholders = _extract_placeholders(source_path.read_text(encoding="utf-8"))
            if not placeholders:
                raise ValueError(f"{render_path}.source must contain at least one placeholder")
            unknown_placeholders = sorted(
                placeholders - set(REQUIRED_PROFILE_VALUE_KEYS) - {"sample_id", "sample_title", "provider_profile_id"}
            )
            if unknown_placeholders:
                raise ValueError(f"{render_path}.source uses unknown placeholders: {', '.join(unknown_placeholders)}")
            normalized_render_files.append(
                {
                    "source": source,
                    "destination": destination,
                    "description": description_text,
                }
            )

        if {"inventory", "config", ".local"} - destination_roots:
            raise ValueError(f"{sample_path}.render_files must cover inventory/, config/, and .local/ starter outputs")

        normalized_samples.append(
            {
                "id": sample_id,
                "title": title,
                "description": description,
                "canonical_examples": canonical_examples,
                "supported_provider_profiles": provider_ids,
                "render_files": normalized_render_files,
            }
        )
    return normalized_samples


def _render_template(template_text: str, context: dict[str, str], template_path: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        try:
            return context[key]
        except KeyError as exc:
            raise ValueError(f"{template_path} uses undefined placeholder '{key}'") from exc

    rendered = TEMPLATE_PATTERN.sub(replace, template_text)
    unresolved = sorted(_extract_placeholders(rendered) - {"env"})
    if unresolved:
        raise ValueError(
            f"{template_path} left unresolved ADR 0339 placeholders in rendered output: {', '.join(unresolved)}"
        )
    return rendered


def _build_render_context(sample: dict[str, Any], profile: dict[str, Any]) -> dict[str, str]:
    context = dict(profile["values"])
    context["sample_id"] = sample["id"]
    context["sample_title"] = sample["title"]
    context["provider_profile_id"] = profile["id"]
    return context


def render_reference_deployment_sample(
    sample_id: str,
    profile_id: str,
    *,
    output_dir: Path,
    sample_catalog: dict[str, Any] | None = None,
    provider_profiles: dict[str, Any] | None = None,
) -> list[Path]:
    provider_payload = provider_profiles or load_provider_profiles()
    provider_index = validate_provider_profile_catalog(provider_payload)
    sample_payload = sample_catalog or load_sample_catalog()
    samples = validate_sample_catalog(sample_payload, provider_index)

    try:
        sample = next(item for item in samples if item["id"] == sample_id)
    except StopIteration as exc:
        raise ValueError(f"unknown sample '{sample_id}'") from exc
    if profile_id not in sample["supported_provider_profiles"]:
        raise ValueError(f"sample '{sample_id}' does not support profile '{profile_id}'")
    profile = provider_index[profile_id]

    context = _build_render_context(sample, profile)
    rendered_paths: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for render_file in sample["render_files"]:
        source_path = REPO_ROOT / render_file["source"]
        destination_path = output_dir / render_file["destination"]
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_text = _render_template(source_path.read_text(encoding="utf-8"), context, source_path)
        destination_path.write_text(rendered_text, encoding="utf-8")
        rendered_paths.append(destination_path)

    manifest_path = output_dir / ".reference-deployment-render.json"
    manifest_payload = {
        "sample_id": sample_id,
        "provider_profile_id": profile_id,
        "rendered_files": [path.relative_to(output_dir).as_posix() for path in rendered_paths],
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rendered_paths.append(manifest_path)
    return rendered_paths


def _validate_rendered_inventory(path: Path, profile: dict[str, Any]) -> None:
    payload = load_yaml_file(path)
    all_root = require_mapping(payload.get("all"), f"{path}.all")
    children = require_mapping(all_root.get("children"), f"{path}.all.children")
    production = require_mapping(children.get("production"), f"{path}.all.children.production")
    production_hosts = require_mapping(production.get("hosts"), f"{path}.all.children.production.hosts")
    proxmox_hosts = require_mapping(children.get("proxmox_hosts"), f"{path}.all.children.proxmox_hosts")
    lv3_guests = require_mapping(children.get("lv3_guests"), f"{path}.all.children.lv3_guests")

    expected_host = profile["values"]["sample_proxmox_host_label"]
    expected_edge = profile["values"]["sample_public_edge_guest_name"]
    expected_runtime = profile["values"]["sample_runtime_guest_name"]
    for host_name in (expected_host, expected_edge, expected_runtime):
        if host_name not in production_hosts:
            raise ValueError(f"{path} is missing rendered host '{host_name}'")

    proxmox_entries = require_mapping(proxmox_hosts.get("hosts"), f"{path}.all.children.proxmox_hosts.hosts")
    if expected_host not in proxmox_entries:
        raise ValueError(f"{path} is missing proxmox host '{expected_host}'")

    guest_entries = require_mapping(lv3_guests.get("hosts"), f"{path}.all.children.lv3_guests.hosts")
    for guest_name in (expected_edge, expected_runtime):
        if guest_name not in guest_entries:
            raise ValueError(f"{path} is missing guest '{guest_name}'")


def _validate_rendered_host_vars(path: Path, profile: dict[str, Any]) -> None:
    payload = load_yaml_file(path)
    if (
        require_str(payload.get("proxmox_node_name"), f"{path}.proxmox_node_name")
        != profile["values"]["sample_proxmox_node_name"]
    ):
        raise ValueError(f"{path}.proxmox_node_name does not match the provider profile")
    for key in (
        "management_ipv4",
        "management_tailscale_ipv4",
        "management_gateway4",
        "proxmox_internal_ipv4",
        "proxmox_internal_network",
        "proxmox_public_edge_ipv4",
    ):
        value = require_str(payload.get(key), f"{path}.{key}")
        mapped_key = {
            "management_ipv4": "sample_proxmox_management_ipv4",
            "management_tailscale_ipv4": "sample_proxmox_management_tailscale_ipv4",
            "management_gateway4": "sample_proxmox_management_gateway4",
            "proxmox_internal_ipv4": "sample_internal_gateway_ipv4",
            "proxmox_internal_network": "sample_internal_network_cidr",
            "proxmox_public_edge_ipv4": "sample_public_edge_ipv4",
        }[key]
        if value != profile["values"][mapped_key]:
            raise ValueError(f"{path}.{key} does not match the provider profile")


def _validate_rendered_api_publication(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}.schema_version must be {SUPPORTED_SCHEMA_VERSION}")
    if payload.get("default_publication_tier") != "internal-only":
        raise ValueError(f"{path}.default_publication_tier must be internal-only")
    tiers = require_mapping(payload.get("tiers"), f"{path}.tiers")
    required_tiers = {"internal-only", "operator-only", "public-edge"}
    if set(tiers) != required_tiers:
        raise ValueError(f"{path}.tiers must define exactly {sorted(required_tiers)}")
    surfaces = require_list(payload.get("surfaces"), f"{path}.surfaces")
    if len(surfaces) < 3:
        raise ValueError(f"{path}.surfaces must include at least three sample surfaces")
    for surface_index, raw_surface in enumerate(surfaces):
        surface_path = f"{path}.surfaces[{surface_index}]"
        surface = require_mapping(raw_surface, surface_path)
        require_identifier(surface.get("id"), f"{surface_path}.id")
        require_str(surface.get("title"), f"{surface_path}.title")
        tier = require_str(surface.get("publication_tier"), f"{surface_path}.publication_tier")
        if tier not in required_tiers:
            raise ValueError(f"{surface_path}.publication_tier must be one of {sorted(required_tiers)}")
        require_str(surface.get("reachability"), f"{surface_path}.reachability")
        require_str(surface.get("approval_notes"), f"{surface_path}.approval_notes")
        hostnames = require_list(surface.get("public_hostnames", []), f"{surface_path}.public_hostnames")
        if tier == "public-edge" and not hostnames:
            raise ValueError(f"{surface_path}.public_hostnames must not be empty for public-edge surfaces")
        if tier != "public-edge" and hostnames:
            raise ValueError(f"{surface_path}.public_hostnames must stay empty unless publication_tier is public-edge")
        for hostname_index, hostname in enumerate(hostnames):
            hostname = require_str(hostname, f"{surface_path}.public_hostnames[{hostname_index}]")
            _validate_example_scalar(
                "sample_public_hostname", hostname, f"{surface_path}.public_hostnames[{hostname_index}]"
            )


def _validate_rendered_secret_overlay(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}.schema_version must be {SUPPORTED_SCHEMA_VERSION}")
    secrets = require_mapping(payload.get("secrets"), f"{path}.secrets")
    if not secrets:
        raise ValueError(f"{path}.secrets must not be empty")
    for secret_id, secret_value in secrets.items():
        secret_path = f"{path}.secrets.{secret_id}"
        secret = require_mapping(secret_value, secret_path)
        kind = require_str(secret.get("kind"), f"{secret_path}.kind")
        if kind == "file":
            file_path = require_str(secret.get("path"), f"{secret_path}.path")
            if not file_path.startswith(".local/"):
                raise ValueError(f"{secret_path}.path must stay under .local/")
        elif kind == "env":
            env_name = require_str(secret.get("name"), f"{secret_path}.name")
            if env_name.upper() != env_name:
                raise ValueError(f"{secret_path}.name must use uppercase environment-variable style")
        else:
            raise ValueError(f"{secret_path}.kind must be either 'file' or 'env'")


def validate_reference_deployment_sources(
    *,
    sample_catalog_path: Path = SAMPLE_CATALOG_PATH,
    provider_profiles_path: Path = PROVIDER_PROFILES_PATH,
) -> None:
    provider_index = validate_provider_profile_catalog(
        load_provider_profiles(provider_profiles_path), path=provider_profiles_path
    )
    samples = validate_sample_catalog(
        load_sample_catalog(sample_catalog_path), provider_index, path=sample_catalog_path
    )

    for sample in samples:
        for profile_id in sample["supported_provider_profiles"]:
            profile = provider_index[profile_id]
            with tempfile.TemporaryDirectory(prefix=f"{sample['id']}-{profile_id}-") as temp_dir:
                output_dir = Path(temp_dir)
                render_reference_deployment_sample(
                    sample["id"],
                    profile_id,
                    output_dir=output_dir,
                    sample_catalog=load_sample_catalog(sample_catalog_path),
                    provider_profiles=load_provider_profiles(provider_profiles_path),
                )
                _validate_rendered_inventory(output_dir / "inventory" / "hosts.yml", profile)
                _validate_rendered_host_vars(output_dir / "inventory" / "host_vars" / "reference-proxmox.yml", profile)
                _validate_rendered_api_publication(output_dir / "config" / "api-publication.json")
                _validate_rendered_secret_overlay(
                    output_dir / ".local" / "reference-deployment" / "controller-local-secrets.json"
                )


def _list_payload() -> dict[str, Any]:
    provider_index = validate_provider_profile_catalog(load_provider_profiles())
    samples = validate_sample_catalog(load_sample_catalog(), provider_index)
    return {
        "samples": [
            {
                "id": sample["id"],
                "title": sample["title"],
                "supported_provider_profiles": sample["supported_provider_profiles"],
            }
            for sample in samples
        ],
        "profiles": [
            {
                "id": profile_id,
                "title": profile["title"],
            }
            for profile_id, profile in sorted(provider_index.items())
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render and validate ADR 0339 reference deployment samples.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("validate", help="Validate the committed sample and provider-profile sources.")
    subparsers.add_parser("list", help="List the available samples and provider profiles.")

    render = subparsers.add_parser("render", help="Render one sample for one provider profile.")
    render.add_argument("--sample", required=True, help="Sample id from reference-deployments/catalog.yaml.")
    render.add_argument(
        "--profile", required=True, help="Provider profile id from config/reference-provider-profiles.yaml."
    )
    render.add_argument(
        "--output-dir", type=Path, required=True, help="Output directory for the rendered starter files."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "validate":
            validate_reference_deployment_sources()
            print("Reference deployment samples OK")
            return 0

        if args.action == "list":
            print(json.dumps(_list_payload(), indent=2, sort_keys=True))
            return 0

        if args.action == "render":
            rendered_paths = render_reference_deployment_sample(
                args.sample,
                args.profile,
                output_dir=args.output_dir,
            )
            print(
                json.dumps(
                    {
                        "sample_id": args.sample,
                        "provider_profile_id": args.profile,
                        "output_dir": str(args.output_dir),
                        "rendered_files": [path.relative_to(args.output_dir).as_posix() for path in rendered_paths],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        parser.print_help()
        return 0
    except (FileNotFoundError, OSError, ValueError) as exc:
        return emit_cli_error("reference deployment samples", exc)


if __name__ == "__main__":
    raise SystemExit(main())
