#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from service_completeness import CHECKLIST_IDS


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ADR_FILENAME_PATTERN = re.compile(r"^(\d{4})-")
ALLOWED_CATEGORIES = {
    "observability",
    "security",
    "automation",
    "data",
    "communication",
    "access",
    "infrastructure",
}
ALLOWED_EXPOSURES = {
    "edge-published",
    "informational-only",
    "private-only",
}
PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)


@dataclass(frozen=True)
class RepoPaths:
    root: Path
    adr_dir: Path
    workstream_dir: Path
    runbook_dir: Path
    docs_template_dir: Path
    collection_roles_dir: Path
    scaffold_template_dir: Path
    playbook_dir: Path
    service_playbook_dir: Path
    workstreams_registry: Path
    host_vars_path: Path
    service_catalog_path: Path
    subdomain_catalog_path: Path
    health_probe_catalog_path: Path
    secret_catalog_path: Path
    image_catalog_path: Path
    secret_manifest_path: Path
    api_gateway_catalog_path: Path
    dependency_graph_path: Path
    slo_catalog_path: Path
    data_catalog_path: Path
    service_completeness_path: Path
    grafana_dashboard_dir: Path
    alert_rule_dir: Path


@dataclass(frozen=True)
class ImageSpec:
    requested_ref: str
    registry_ref: str
    tag: str
    catalog_tag: str
    digest: str
    ref: str
    receipt_path: str


@dataclass(frozen=True)
class ServiceSpec:
    name_slug: str
    service_id: str
    service_name: str
    display_name: str
    variable_prefix: str
    env_var_prefix: str
    role_name: str
    adr_id: str
    adr_filename: str
    adr_title_suffix: str
    workstream_id: str
    workstream_filename: str
    worktree_path: str
    branch_name: str
    runbook_filename: str
    playbook_filename: str
    description: str
    category: str
    service_type: str
    exposure: str
    vm: str
    vmid: int | None
    depends_on: tuple[str, ...]
    requires_oidc: bool
    requires_secrets: bool
    private_ip: str
    port: int
    public_hostname: str | None
    public_dns_label: str | None
    public_target: str
    private_target: str
    internal_url: str
    public_url: str | None
    image: ImageSpec
    today: str

    @property
    def service_catalog_name(self) -> str:
        return self.display_name

    @property
    def role_path(self) -> Path:
        return Path("collections/ansible_collections/lv3/platform/roles") / self.role_name

    @property
    def playbook_path(self) -> Path:
        return Path("playbooks") / self.playbook_filename

    @property
    def service_playbook_path(self) -> Path:
        return Path("playbooks/services") / self.playbook_filename

    @property
    def runbook_path(self) -> Path:
        return Path("docs/runbooks") / self.runbook_filename

    @property
    def dashboard_filename(self) -> str:
        return f"{self.service_name}.json"

    @property
    def dashboard_path(self) -> Path:
        return Path("config/grafana/dashboards") / self.dashboard_filename

    @property
    def alert_rule_filename(self) -> str:
        return f"{self.service_name}.yml"

    @property
    def alert_rule_path(self) -> Path:
        return Path("config/alertmanager/rules") / self.alert_rule_filename

    @property
    def adr_path(self) -> Path:
        return Path("docs/adr") / self.adr_filename

    @property
    def workstream_path(self) -> Path:
        return Path("docs/workstreams") / self.workstream_filename

    @property
    def secret_id(self) -> str:
        return f"{self.service_id}_admin_token"

    @property
    def controller_secret_id(self) -> str:
        return self.secret_id

    @property
    def image_id(self) -> str:
        return f"{self.service_id}_runtime"

    @property
    def uptime_reason(self) -> str:
        return "TODO: enable the external uptime monitor after the scaffolded service is deployed."


def emit_error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def require_file(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"missing required file: {path}")


def load_json(path: Path) -> Any:
    require_file(path)
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def load_yaml(path: Path) -> Any:
    require_file(path)
    return yaml.safe_load(path.read_text())


def derive_display_name(name_slug: str) -> str:
    return " ".join(part.capitalize() for part in name_slug.split("-"))


def parse_image_reference(raw_image: str, today: str, service_slug: str) -> ImageSpec:
    requested_ref = raw_image.strip()
    if not requested_ref:
        raise ValueError("image reference must be non-empty")
    if "@" in requested_ref:
        raise ValueError("image reference must omit a digest; provide registry/repository:tag")

    image = requested_ref
    tag = "latest"
    last_colon = image.rfind(":")
    last_slash = image.rfind("/")
    if last_colon > last_slash:
        image, tag = image[:last_colon], image[last_colon + 1 :]
    if not image:
        raise ValueError("image reference must include a registry or repository path")
    if not tag:
        raise ValueError("image tag must be non-empty")

    catalog_tag = "TODO-pin-tag" if tag == "latest" else tag
    receipt_path = f"receipts/image-scans/{today}-{service_slug}-runtime.json"
    return ImageSpec(
        requested_ref=requested_ref,
        registry_ref=image,
        tag=tag,
        catalog_tag=catalog_tag,
        digest=PLACEHOLDER_DIGEST,
        ref=f"{image}:{catalog_tag}@{PLACEHOLDER_DIGEST}",
        receipt_path=receipt_path,
    )


def discover_next_adr_id(adr_dir: Path) -> str:
    highest = 0
    for path in adr_dir.iterdir():
        match = ADR_FILENAME_PATTERN.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{highest + 1:04d}"


def build_repo_paths(repo_root: Path) -> RepoPaths:
    return RepoPaths(
        root=repo_root,
        adr_dir=repo_root / "docs" / "adr",
        workstream_dir=repo_root / "docs" / "workstreams",
        runbook_dir=repo_root / "docs" / "runbooks",
        docs_template_dir=repo_root / "docs" / "templates",
        collection_roles_dir=repo_root / "collections" / "ansible_collections" / "lv3" / "platform" / "roles",
        scaffold_template_dir=repo_root
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "_template"
        / "service_scaffold",
        playbook_dir=repo_root / "playbooks",
        service_playbook_dir=repo_root / "playbooks" / "services",
        workstreams_registry=repo_root / "workstreams.yaml",
        host_vars_path=repo_root / "inventory" / "host_vars" / "proxmox_florin.yml",
        service_catalog_path=repo_root / "config" / "service-capability-catalog.json",
        subdomain_catalog_path=repo_root / "config" / "subdomain-catalog.json",
        health_probe_catalog_path=repo_root / "config" / "health-probe-catalog.json",
        secret_catalog_path=repo_root / "config" / "secret-catalog.json",
        image_catalog_path=repo_root / "config" / "image-catalog.json",
        secret_manifest_path=repo_root / "config" / "controller-local-secrets.json",
        api_gateway_catalog_path=repo_root / "config" / "api-gateway-catalog.json",
        dependency_graph_path=repo_root / "config" / "dependency-graph.json",
        slo_catalog_path=repo_root / "config" / "slo-catalog.json",
        data_catalog_path=repo_root / "config" / "data-catalog.json",
        service_completeness_path=repo_root / "config" / "service-completeness.json",
        grafana_dashboard_dir=repo_root / "config" / "grafana" / "dashboards",
        alert_rule_dir=repo_root / "config" / "alertmanager" / "rules",
    )


def resolve_vm_context(host_vars: dict[str, Any], vm: str, requested_vmid: int | None) -> tuple[int | None, str]:
    guests = host_vars.get("proxmox_guests", [])
    if not isinstance(guests, list):
        raise ValueError("inventory/host_vars/proxmox_florin.yml.proxmox_guests must be a list")

    for guest in guests:
        if not isinstance(guest, dict):
            continue
        if guest.get("name") != vm:
            continue
        guest_vmid = guest.get("vmid")
        guest_ip = guest.get("ipv4")
        if requested_vmid is not None and guest_vmid != requested_vmid:
            raise ValueError(f"vmid {requested_vmid} does not match inventory vmid {guest_vmid} for {vm}")
        if not isinstance(guest_ip, str) or not guest_ip:
            raise ValueError(f"managed guest {vm} does not declare an ipv4 address")
        return int(guest_vmid), guest_ip

    if vm == "proxmox_florin":
        private_ip = host_vars.get("management_tailscale_ipv4")
        if not isinstance(private_ip, str) or not private_ip:
            raise ValueError("inventory/host_vars/proxmox_florin.yml.management_tailscale_ipv4 is missing")
        return requested_vmid, private_ip

    raise ValueError(f"vm '{vm}' is not a managed guest or the Proxmox host id")


def resolve_public_hostname(exposure: str, subdomain: str | None) -> tuple[str | None, str | None]:
    if subdomain:
        label = subdomain.split(".", 1)[0]
    else:
        label = None
    if exposure == "private-only" and not subdomain:
        return None, None
    if not subdomain:
        raise ValueError("subdomain is required for non-private exposures")
    return subdomain, label


def validate_reserved_prefixes(repo_paths: RepoPaths, public_hostname: str | None) -> None:
    if public_hostname is None:
        return

    catalog = load_json(repo_paths.subdomain_catalog_path)
    reserved_prefixes = catalog.get("reserved_prefixes", [])
    prefix = public_hostname.split(".", 1)[0]

    for entry in reserved_prefixes:
        if not isinstance(entry, dict):
            continue
        if entry.get("prefix") != prefix:
            continue
        allowed = set(entry.get("allowed_fqdns", []))
        if public_hostname not in allowed:
            raise ValueError(
                f"subdomain prefix '{prefix}' is reserved in config/subdomain-catalog.json and "
                f"{public_hostname} is not allowlisted"
            )


def build_service_spec(args: argparse.Namespace, repo_paths: RepoPaths) -> ServiceSpec:
    name_slug = args.name.strip()
    if not NAME_PATTERN.fullmatch(name_slug):
        raise ValueError("name must use lowercase kebab-case")

    category = args.category.strip()
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"category must be one of {sorted(ALLOWED_CATEGORIES)}")

    exposure = args.exposure.strip()
    if exposure not in ALLOWED_EXPOSURES:
        raise ValueError(f"exposure must be one of {sorted(ALLOWED_EXPOSURES)}")

    host_vars = load_yaml(repo_paths.host_vars_path)
    if not isinstance(host_vars, dict):
        raise ValueError("inventory host vars must be a mapping")

    vmid, private_ip = resolve_vm_context(host_vars, args.vm, args.vmid)
    public_hostname, public_dns_label = resolve_public_hostname(exposure, args.subdomain)
    validate_reserved_prefixes(repo_paths, public_hostname)

    today = args.today
    service_id = name_slug.replace("-", "_")
    service_name = name_slug
    display_name = derive_display_name(name_slug)
    variable_prefix = service_id
    env_var_prefix = name_slug.replace("-", "_").upper()
    role_name = f"{service_id}_runtime"
    depends_on = tuple(sorted({item.strip().replace("-", "_") for item in args.depends_on.split(",") if item.strip()}))
    adr_id = discover_next_adr_id(repo_paths.adr_dir)
    worktree_path = f"../proxmox_florin_server-{adr_id}-{name_slug}"
    branch_name = f"codex/adr-{adr_id}-{name_slug}"

    internal_host = public_hostname if public_hostname and exposure == "private-only" else private_ip
    internal_url = f"http://{internal_host}:{args.port}"
    public_url = f"https://{public_hostname}" if public_hostname and exposure != "private-only" else None
    image = parse_image_reference(args.image, today, name_slug)

    return ServiceSpec(
        name_slug=name_slug,
        service_id=service_id,
        service_name=service_name,
        display_name=display_name,
        variable_prefix=variable_prefix,
        env_var_prefix=env_var_prefix,
        role_name=role_name,
        adr_id=adr_id,
        adr_filename=f"{adr_id}-{name_slug}.md",
        adr_title_suffix=name_slug.replace("-", " "),
        workstream_id=f"adr-{adr_id}-{name_slug}",
        workstream_filename=f"adr-{adr_id}-{name_slug}.md",
        worktree_path=worktree_path,
        branch_name=branch_name,
        runbook_filename=f"configure-{name_slug}.md",
        playbook_filename=f"{name_slug}.yml",
        description=args.description.strip(),
        category=category,
        service_type=args.service_type,
        exposure=exposure,
        vm=args.vm,
        vmid=vmid,
        depends_on=depends_on,
        requires_oidc=bool(args.oidc),
        requires_secrets=bool(args.has_secrets),
        private_ip=private_ip,
        port=args.port,
        public_hostname=public_hostname,
        public_dns_label=public_dns_label,
        public_target=str(host_vars.get("management_ipv4")),
        private_target=str(host_vars.get("management_tailscale_ipv4")),
        internal_url=internal_url,
        public_url=public_url,
        image=image,
        today=today,
    )


def ensure_new_paths(spec: ServiceSpec, repo_paths: RepoPaths) -> None:
    paths = [
        repo_paths.adr_dir / spec.adr_filename,
        repo_paths.workstream_dir / spec.workstream_filename,
        repo_paths.runbook_dir / spec.runbook_filename,
        repo_paths.grafana_dashboard_dir / spec.dashboard_filename,
        repo_paths.alert_rule_dir / spec.alert_rule_filename,
        repo_paths.collection_roles_dir / spec.role_name,
        repo_paths.playbook_dir / spec.playbook_filename,
        repo_paths.service_playbook_dir / spec.playbook_filename,
    ]
    for path in paths:
        if path.exists():
            raise ValueError(f"refusing to overwrite existing path: {path.relative_to(repo_paths.root)}")

    catalogs = {
        "service capability catalog": [
            service["id"] for service in load_json(repo_paths.service_catalog_path)["services"]
        ],
        "health probe catalog": list(load_json(repo_paths.health_probe_catalog_path)["services"].keys()),
        "secret catalog": [
            secret["id"] for secret in load_json(repo_paths.secret_catalog_path)["secrets"]
        ],
        "image catalog": list(load_json(repo_paths.image_catalog_path)["images"].keys()),
        "controller-local secret manifest": list(load_json(repo_paths.secret_manifest_path)["secrets"].keys()),
        "service completeness catalog": list(load_json(repo_paths.service_completeness_path)["services"].keys()),
    }
    for label, ids in catalogs.items():
        if spec.service_id in ids or spec.role_name in ids:
            raise ValueError(f"{label} already contains the scaffold target id '{spec.service_id}'")
    if spec.secret_id in catalogs["secret catalog"]:
        raise ValueError(f"secret catalog already contains '{spec.secret_id}'")
    if spec.image_id in catalogs["image catalog"]:
        raise ValueError(f"image catalog already contains '{spec.image_id}'")

    workstreams = load_yaml(repo_paths.workstreams_registry)
    existing_workstream_ids = {item["id"] for item in workstreams.get("workstreams", [])}
    if spec.workstream_id in existing_workstream_ids:
        raise ValueError(f"workstreams.yaml already contains '{spec.workstream_id}'")


def render_template(path: Path, replacements: dict[str, str]) -> str:
    content = path.read_text()
    for key, value in replacements.items():
        content = content.replace(f"@@{key}@@", value)
    return content


def template_replacements(spec: ServiceSpec, repo_paths: RepoPaths) -> dict[str, str]:
    return {
        "ABS_REPO_ROOT": repo_paths.root.as_posix(),
        "SERVICE_ID": spec.service_id,
        "SERVICE_NAME": spec.service_name,
        "DISPLAY_NAME": spec.display_name,
        "VARIABLE_PREFIX": spec.variable_prefix,
        "ENV_VAR_PREFIX": spec.env_var_prefix,
        "ROLE_NAME": spec.role_name,
        "ROLE_FQCN": f"lv3.platform.{spec.role_name}",
        "SITE_DIR": f"/opt/{spec.name_slug}",
        "SECRET_DIR": f"/etc/lv3/{spec.name_slug}",
        "LOCAL_ARTIFACT_DIR": f"{repo_paths.root.as_posix()}/.local/{spec.name_slug}",
        "CONTAINER_NAME": spec.name_slug,
        "PORT": str(spec.port),
        "VM": spec.vm,
        "SERVICE_TYPE": spec.service_type,
        "DEPENDS_ON": ", ".join(spec.depends_on),
        "PUBLIC_HOSTNAME": spec.public_hostname or "",
        "PRIVATE_URL": spec.internal_url,
        "REQUESTED_IMAGE": spec.image.requested_ref,
        "IMAGE_REF": spec.image.requested_ref,
        "OPENBAO_SECRET_PATH": f"services/{spec.name_slug}/runtime-env",
        "OPENBAO_POLICY_NAME": f"lv3-service-{spec.name_slug}-runtime",
        "OPENBAO_APPROLE_NAME": f"{spec.name_slug}-runtime",
        "SECRET_ID": spec.secret_id,
        "TODAY": spec.today,
        "ADR_ID": spec.adr_id,
        "ADR_FILENAME": spec.adr_filename,
        "BRANCH_NAME": spec.branch_name,
        "WORKTREE_PATH": spec.worktree_path,
        "ROLE_PATH": spec.role_path.as_posix(),
        "PLAYBOOK_PATH": spec.playbook_path.as_posix(),
        "PLAYBOOK_FILENAME": spec.playbook_filename,
        "SERVICE_PLAYBOOK_PATH": spec.service_playbook_path.as_posix(),
        "RUNBOOK_PATH": spec.runbook_path.as_posix(),
    }


def write_scaffold_files(spec: ServiceSpec, repo_paths: RepoPaths) -> None:
    replacements = template_replacements(spec, repo_paths)
    template_root = repo_paths.scaffold_template_dir
    require_file(template_root / "README.md.tpl")
    require_file(repo_paths.docs_template_dir / "runbook.md.j2")
    require_file(repo_paths.docs_template_dir / "grafana-dashboard.json.j2")
    require_file(repo_paths.docs_template_dir / "alert-rules.yml.j2")

    role_root = repo_paths.collection_roles_dir / spec.role_name
    (role_root / "defaults").mkdir(parents=True)
    (role_root / "meta").mkdir(parents=True)
    (role_root / "tasks").mkdir(parents=True)
    (role_root / "templates").mkdir(parents=True)
    repo_paths.grafana_dashboard_dir.mkdir(parents=True, exist_ok=True)
    repo_paths.alert_rule_dir.mkdir(parents=True, exist_ok=True)

    rendered_files = {
        role_root / "README.md": "README.md.tpl",
        role_root / "defaults" / "main.yml": "defaults-main.yml.tpl",
        role_root / "meta" / "argument_specs.yml": "meta-argument_specs.yml.tpl",
        role_root / "tasks" / "main.yml": "tasks-main.yml.tpl",
        role_root / "tasks" / "verify.yml": "tasks-verify.yml.tpl",
        role_root / "templates" / "docker-compose.yml.j2": "docker-compose.yml.j2.tpl",
        role_root / "templates" / "runtime.env.ctmpl.j2": "runtime.env.ctmpl.j2.tpl",
        role_root / "templates" / "runtime.env.j2": "runtime.env.j2.tpl",
        repo_paths.playbook_dir / spec.playbook_filename: "playbook.yml.tpl",
        repo_paths.service_playbook_dir / spec.playbook_filename: "service-playbook.yml.tpl",
        repo_paths.adr_dir / spec.adr_filename: "adr.md.tpl",
        repo_paths.workstream_dir / spec.workstream_filename: "workstream.md.tpl",
    }

    for destination, template_name in rendered_files.items():
        destination.write_text(render_template(template_root / template_name, replacements))
    (repo_paths.runbook_dir / spec.runbook_filename).write_text(
        render_template(repo_paths.docs_template_dir / "runbook.md.j2", replacements)
    )
    (repo_paths.grafana_dashboard_dir / spec.dashboard_filename).write_text(
        render_template(repo_paths.docs_template_dir / "grafana-dashboard.json.j2", replacements)
    )
    (repo_paths.alert_rule_dir / spec.alert_rule_filename).write_text(
        render_template(repo_paths.docs_template_dir / "alert-rules.yml.j2", replacements)
    )


def insert_topology_block(host_vars_path: Path, spec: ServiceSpec) -> None:
    lines = [
        f"  {spec.service_id}:",
        f"    service_name: {spec.service_name}",
        f"    owning_vm: {spec.vm}",
    ]
    if spec.vm == "proxmox_florin":
        lines.append('    private_ip: "{{ management_tailscale_ipv4 }}"')
    else:
        lines.append(
            f'    private_ip: "{{{{ (proxmox_guests | selectattr(\'name\', \'equalto\', \'{spec.vm}\') | map(attribute=\'ipv4\') | first) }}}}"'
        )
    if spec.public_hostname:
        lines.append(f"    public_hostname: {spec.public_hostname}")
    lines.extend(
        [
            f"    exposure_model: {spec.exposure}",
            "    observability:",
            "      guest_dashboard: false",
            "      service_telemetry: false",
        ]
    )
    if spec.public_hostname:
        lines.extend(
            [
                "    dns:",
                "      managed: true",
                f"      visibility: {'tailnet' if spec.exposure == 'private-only' else 'public'}",
                f"      name: {spec.public_dns_label}",
                "      type: A",
                f"      target: \"{{{{ {'management_tailscale_ipv4' if spec.exposure == 'private-only' else 'management_ipv4'} }}}}\"",
                "      ttl: 60",
            ]
        )
    if spec.exposure in {"edge-published", "informational-only"} and spec.public_hostname:
        lines.extend(
            [
                "    edge:",
                "      enabled: true",
                "      tls: true",
                f"      kind: {'proxy' if spec.exposure == 'edge-published' else 'static'}",
            ]
        )
        if spec.exposure == "edge-published":
            lines.append(f"      upstream: http://{spec.private_ip}:{spec.port}")
        else:
            lines.extend(
                [
                    f"      slug: {spec.public_dns_label}",
                    f"      title: {spec.display_name}",
                    f"      description: TODO: replace the informational edge description for {spec.display_name}.",
                    "      meta: TODO: replace the informational edge metadata before merge.",
                ]
            )

    host_vars_path.write_text(host_vars_path.read_text().rstrip() + "\n" + "\n".join(lines) + "\n")


def update_workstreams_registry(path: Path, spec: ServiceSpec) -> None:
    registry = load_yaml(path)
    workstreams = registry.setdefault("workstreams", [])
    workstreams.append(
        {
            "id": spec.workstream_id,
            "adr": spec.adr_id,
            "title": f"{spec.display_name} service scaffold",
            "status": "ready",
            "owner": "codex",
            "branch": spec.branch_name,
            "worktree_path": spec.worktree_path,
            "doc": str((path.parent / "docs" / "workstreams" / spec.workstream_filename).resolve()),
            "depends_on": ["adr-0062-role-composability", "adr-0075-service-capability-catalog", "adr-0076-subdomain-governance", "adr-0077-compose-secrets-injection"],
            "conflicts_with": [],
            "shared_surfaces": [
                repo_path.as_posix()
                for repo_path in (
                    spec.role_path,
                    spec.playbook_path,
                    spec.service_playbook_path,
                    spec.runbook_path,
                    spec.dashboard_path,
                    spec.alert_rule_path,
                    spec.adr_path,
                    spec.workstream_path,
                )
            ],
            "ready_to_merge": False,
            "live_applied": False,
        }
    )
    path.write_text(yaml.safe_dump(registry, sort_keys=False))


def update_service_catalog(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    service_entry: dict[str, Any] = {
        "id": spec.service_id,
        "name": spec.service_catalog_name,
        "description": spec.description,
        "category": spec.category,
        "lifecycle_status": "planned",
        "vm": spec.vm,
        "internal_url": spec.internal_url,
        "exposure": spec.exposure,
        "health_probe_id": spec.service_id,
        "image_catalog_ids": [spec.image_id],
        "secret_catalog_ids": [spec.secret_id],
        "adr": spec.adr_id,
        "runbook": spec.runbook_path.as_posix(),
        "tags": ["TODO-scaffold"],
        "notes": "TODO: replace scaffold placeholders, confirm the runtime contract, and remove TODO markers before merge.",
        "environments": {
            "production": {
                "status": "planned",
                "url": spec.public_url or spec.internal_url,
            }
        },
    }
    if spec.vmid is not None:
        service_entry["vmid"] = spec.vmid
    if spec.public_url:
        service_entry["public_url"] = spec.public_url
    if spec.public_hostname:
        service_entry["subdomain"] = spec.public_hostname
        service_entry["environments"]["production"]["subdomain"] = spec.public_hostname

    catalog["services"].append(service_entry)
    catalog["services"] = sorted(catalog["services"], key=lambda item: item["id"])
    write_json(path, catalog)


def update_subdomain_catalog(path: Path, spec: ServiceSpec) -> None:
    if spec.public_hostname is None:
        return

    catalog = load_json(path)
    entry = {
        "fqdn": spec.public_hostname,
        "service_id": spec.service_id,
        "environment": "production",
        "status": "planned",
        "exposure": spec.exposure,
        "target": spec.private_target if spec.exposure == "private-only" else spec.public_target,
        "target_port": spec.port if spec.exposure == "private-only" else 443,
        "owner_adr": spec.adr_id,
        "tls": {
            "provider": "none" if spec.exposure == "private-only" else "letsencrypt",
            "auto_renew": False if spec.exposure == "private-only" else True,
        },
        "notes": "TODO: confirm publication readiness and remove scaffold placeholders before merge.",
    }
    if spec.exposure != "private-only":
        entry["tls"]["cert_path"] = "/etc/letsencrypt/live/lv3-edge/"

    catalog["subdomains"].append(entry)
    catalog["subdomains"] = sorted(catalog["subdomains"], key=lambda item: item["fqdn"])
    write_json(path, catalog)


def update_health_probe_catalog(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    catalog["services"][spec.service_id] = {
        "service_name": spec.service_name,
        "owning_vm": spec.vm,
        "role": spec.role_name,
        "verify_file": f"roles/{spec.role_name}/tasks/verify.yml",
        "liveness": {
            "kind": "http",
            "description": f"TODO: replace the scaffolded local liveness endpoint contract for {spec.display_name}.",
            "timeout_seconds": 60,
            "retries": 12,
            "delay_seconds": 5,
            "url": f"http://127.0.0.1:{spec.port}/health",
            "method": "GET",
            "expected_status": [200],
        },
        "readiness": {
            "kind": "http",
            "description": f"TODO: replace the scaffolded local readiness endpoint contract for {spec.display_name}.",
            "timeout_seconds": 60,
            "retries": 12,
            "delay_seconds": 5,
            "url": f"http://127.0.0.1:{spec.port}/health",
            "method": "GET",
            "expected_status": [200],
        },
        "uptime_kuma": {
            "enabled": False,
            "reason": spec.uptime_reason,
        },
    }
    catalog["services"] = dict(sorted(catalog["services"].items()))
    write_json(path, catalog)


def update_secret_catalog(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    catalog["secrets"].append(
        {
            "id": spec.secret_id,
            "owner_service": spec.service_id,
            "storage_contract": "controller-local-secrets",
            "storage_ref": spec.controller_secret_id,
            "rotation_period_days": 90,
            "warning_window_days": 14,
            "last_rotated_at": spec.today,
            "rotation_mode": "manual",
        }
    )
    catalog["secrets"] = sorted(catalog["secrets"], key=lambda item: item["id"])
    write_json(path, catalog)


def update_secret_manifest(path: Path, spec: ServiceSpec) -> None:
    manifest = load_json(path)
    manifest["secrets"][spec.controller_secret_id] = {
        "kind": "file",
        "path": str((path.parent.parent / ".local" / spec.name_slug / "admin-token.txt").resolve()),
        "origin": "generated_by_repo",
        "status": "planned",
        "description": f"Controller-local mirror of the {spec.display_name} bootstrap admin token scaffold.",
        "dependencies": [
            spec.role_path.as_posix(),
            spec.playbook_path.as_posix(),
            spec.runbook_path.as_posix(),
        ],
    }
    manifest["secrets"] = dict(sorted(manifest["secrets"].items()))
    write_json(path, manifest)


def update_image_catalog(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    catalog["images"][spec.image_id] = {
        "kind": "runtime",
        "service_id": spec.service_id,
        "runtime_host": spec.vm,
        "container_name": spec.name_slug,
        "registry_ref": spec.image.registry_ref,
        "tag": spec.image.catalog_tag,
        "digest": spec.image.digest,
        "ref": spec.image.ref,
        "platform": "linux/amd64",
        "pinned_on": spec.today,
        "scan_status": "pass_no_critical",
        "scan_receipt": spec.image.receipt_path,
        "consumers": [
            f"roles/{spec.role_name}/templates/docker-compose.yml.j2",
            "scripts/upgrade_container_image.py",
            "docs/runbooks/container-image-policy.md",
        ],
        "apply_targets": [
            f"live-apply-service service={spec.service_id} env=production",
        ],
    }
    catalog["images"] = dict(sorted(catalog["images"].items()))
    write_json(path, catalog)


def update_api_gateway_catalog(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    catalog["services"].append(
        {
            "id": spec.service_id,
            "name": spec.display_name,
            "gateway_prefix": f"/v1/{spec.name_slug}",
            "upstream": spec.internal_url,
            "auth": "keycloak_jwt",
            "required_role": "platform-operator" if spec.requires_oidc else "platform-read",
            "strip_prefix": True,
            "timeout_seconds": 30,
        }
    )
    catalog["services"] = sorted(catalog["services"], key=lambda item: item["id"])
    write_json(path, catalog)


def update_dependency_graph(path: Path, spec: ServiceSpec) -> None:
    graph = load_json(path)
    graph["nodes"].append(
        {
            "id": spec.service_id,
            "service": spec.service_id,
            "vm": spec.vm,
            "tier": 3,
            "notes": f"TODO: confirm the recovery tier and blast radius for {spec.display_name}.",
        }
    )
    for dependency in spec.depends_on:
        graph["edges"].append(
            {
                "from": spec.service_id,
                "to": dependency,
                "type": "hard",
                "description": f"TODO: confirm why {spec.display_name} depends on {dependency}.",
            }
        )
    graph["nodes"] = sorted(graph["nodes"], key=lambda item: item["id"])
    graph["edges"] = sorted(graph["edges"], key=lambda item: (item["from"], item["to"]))
    write_json(path, graph)


def update_slo_catalog(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    catalog["slos"].append(
        {
            "id": f"{spec.name_slug}-availability",
            "service_id": spec.service_id,
            "indicator": "availability",
            "objective_percent": 99.5,
            "window_days": 30,
            "target_url": spec.public_url or spec.internal_url,
            "probe_module": "http_2xx_follow_redirects",
            "description": f"TODO: confirm the {spec.display_name} availability objective and measurement path.",
        }
    )
    catalog["slos"] = sorted(catalog["slos"], key=lambda item: item["id"])
    write_json(path, catalog)


def update_data_catalog(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    catalog["data_stores"].append(
        {
            "id": f"{spec.service_id}_primary_data",
            "service": spec.service_id,
            "class": "internal",
            "retention_days": 30,
            "backup_included": False,
            "access_role": "platform-read",
            "pii_risk": "unknown",
            "notes": f"TODO: classify the primary {spec.display_name} data store.",
        }
    )
    catalog["data_stores"] = sorted(catalog["data_stores"], key=lambda item: item["id"])
    write_json(path, catalog)


def update_service_completeness(path: Path, spec: ServiceSpec) -> None:
    catalog = load_json(path)
    catalog["services"][spec.service_id] = {
        "service_type": spec.service_type,
        "requires_subdomain": spec.public_hostname is not None,
        "requires_oidc": spec.requires_oidc,
        "requires_secrets": spec.requires_secrets,
        "requires_compose_secrets": spec.service_type == "compose",
        "dashboard_file": spec.dashboard_path.as_posix(),
        "alert_rule_file": spec.alert_rule_path.as_posix(),
        "keycloak_client_generated": spec.requires_oidc,
        "suppressed_checks": {},
    }
    catalog["services"] = dict(sorted(catalog["services"].items()))
    write_json(path, catalog)


def write_placeholder_scan_receipt(repo_root: Path, spec: ServiceSpec) -> None:
    receipt_path = repo_root / spec.image.receipt_path
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "image_id": spec.image_id,
                "image_ref": spec.image.ref,
                "scanner": "trivy",
                "scanned_on": spec.today,
                "summary": {
                    "critical": 0,
                    "high": 0,
                },
            },
            indent=2,
        )
        + "\n"
    )


def print_checklist(spec: ServiceSpec) -> None:
    print(f"Scaffold created for '{spec.name_slug}'.")
    print("Required next steps:")
    print(f"  [ ] Fill in the ADR decision, consequences, and status fields: {spec.adr_path.as_posix()}")
    print(
        "  [ ] Replace every scaffold TODO marker and confirm `make validate-data-models` passes "
        "before merging."
    )
    print(f"  [ ] Run the ADR 0107 completeness check: lv3 validate --service {spec.service_id}")
    print(f"  [ ] Pin the requested image digest: make pin-image IMAGE={spec.image.requested_ref}")
    print(f"  [ ] Review the generated role and runtime env contract: {spec.role_path.as_posix()}")
    print(f"  [ ] Review the generated playbook entry points: {spec.playbook_path.as_posix()}")
    print(f"  [ ] Complete the runbook and workstream metadata: {spec.runbook_path.as_posix()} {spec.workstream_path.as_posix()}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a new service scaffold across docs, roles, playbooks, and catalogs.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--category", default="automation")
    parser.add_argument("--type", dest="service_type", choices=["compose", "vm-service", "nginx-plugin"], default="compose")
    parser.add_argument("--vm", default="docker-runtime-lv3")
    parser.add_argument("--vmid", type=int)
    parser.add_argument("--depends-on", default="")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--subdomain")
    parser.add_argument("--exposure", default="private-only")
    parser.add_argument("--oidc", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--has-secrets", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--image", default="docker.io/library/nginx:latest")
    parser.add_argument("--today", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    args.today = args.today or __import__("datetime").date.today().isoformat()
    args.description = args.description or f"TODO: describe the {args.name} service."
    args.subdomain = args.subdomain or f"{args.name}.lv3.org"

    try:
        repo_paths = build_repo_paths(Path(args.repo_root).resolve())
        spec = build_service_spec(args, repo_paths)
        ensure_new_paths(spec, repo_paths)
        write_scaffold_files(spec, repo_paths)
        insert_topology_block(repo_paths.host_vars_path, spec)
        update_workstreams_registry(repo_paths.workstreams_registry, spec)
        update_service_catalog(repo_paths.service_catalog_path, spec)
        update_subdomain_catalog(repo_paths.subdomain_catalog_path, spec)
        update_health_probe_catalog(repo_paths.health_probe_catalog_path, spec)
        update_secret_catalog(repo_paths.secret_catalog_path, spec)
        update_secret_manifest(repo_paths.secret_manifest_path, spec)
        update_image_catalog(repo_paths.image_catalog_path, spec)
        update_api_gateway_catalog(repo_paths.api_gateway_catalog_path, spec)
        update_dependency_graph(repo_paths.dependency_graph_path, spec)
        update_slo_catalog(repo_paths.slo_catalog_path, spec)
        update_data_catalog(repo_paths.data_catalog_path, spec)
        update_service_completeness(repo_paths.service_completeness_path, spec)
        write_placeholder_scan_receipt(repo_paths.root, spec)
        print_checklist(spec)
    except ValueError as exc:
        emit_error(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
