"""Deployment loader and resolver — ADR 0439/0440.

Single source of truth for "which deployment is this command operating on?".
Every multi-deployment-aware script imports `resolve_active_slug` and
`load` from this module.

Resolution precedence (first hit wins):

    1. explicit slug passed by caller (CLI flag)
    2. $DEPLOYMENT environment variable
    3. .deployment marker inside the current worktree
    4. .local/active-deployment in the main repo
    5. DeploymentNotResolvedError — never silently default to "prod"

Layout (per ADR 0440):

    .local/deployments/<slug>/
        identity.yml
        topology.yml
        profile.yml
        generated/
        secrets/
        receipts/
        state/

This module reads the operator-authored files (identity / topology /
profile) and exposes a typed `Deployment` object. Generation of
`generated/*` is the job of the per-artifact scripts; this module only
loads inputs and validates them.

CLI usage (Makefile shim):

    python3 scripts/deployment.py resolve [--quiet]
        Print the resolved slug to stdout; exit 0 on success, 2 on
        not-resolved. With --quiet, suppress the human-readable error.

    python3 scripts/deployment.py list
        Print every slug under .local/deployments/, one per line.

    python3 scripts/deployment.py validate [--slug <slug>] [--all]
        Schema-validate one or every deployment.

    python3 scripts/deployment.py whoami
        Print the active deployment + worktree binding (if any) +
        identity summary.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class DeploymentError(Exception):
    """Base class for deployment loader errors."""


class DeploymentNotResolvedError(DeploymentError):
    """No deployment slug could be resolved from any source."""


class DeploymentNotFoundError(DeploymentError):
    """Slug was provided but no directory exists for it."""


class DeploymentValidationError(DeploymentError):
    """Schema validation failed for one or more files."""


def _find_main_repo_root(start: Path | None = None) -> Path:
    """Resolve the main (non-worktree) repo root.

    Worktrees under .claude/worktrees/<name>/ have their own working
    tree but share .git/worktrees metadata with the main repo. The
    main repo's .git is a directory; a worktree's .git is a file.
    git rev-parse --git-common-dir returns the shared directory in
    either case; its parent is the main repo root.
    """
    cwd = (start or Path.cwd()).resolve()
    try:
        out = subprocess.check_output(
            ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            common = Path(out)
            return common.parent
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    # Fallback: walk up looking for pyproject.toml + scripts/ dir
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "scripts").is_dir():
            return candidate
    raise DeploymentError(f"Could not locate repo root from {cwd}")


REPO_ROOT: Path = _find_main_repo_root()
DEPLOYMENTS_DIR: Path = REPO_ROOT / ".local" / "deployments"
ACTIVE_FILE: Path = REPO_ROOT / ".local" / "active-deployment"
SCHEMA_DIR: Path = REPO_ROOT / "config" / "contracts" / "deployment-v1"


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise DeploymentValidationError(f"{path} did not parse to a mapping")
    return data


def _find_worktree_marker(start: Path | None = None) -> Path | None:
    """Return the path of a `.deployment` marker if cwd is inside a worktree."""
    cwd = (start or Path.cwd()).resolve()
    for candidate in [cwd, *cwd.parents]:
        marker = candidate / ".deployment"
        if marker.is_file():
            return marker
        # Stop at the worktree's own root (where .git is either dir or file)
        if (candidate / ".git").exists():
            return None
    return None


def resolve_active_slug(
    explicit: str | None = None,
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> str:
    """Return the active deployment slug.

    Precedence is enforced strictly. The caller must pass `explicit` if
    they have a CLI override; falling back to env / marker / active-file
    happens only when explicit is None or empty.
    """
    if explicit:
        return explicit

    env = os.environ if env is None else env
    if env.get("DEPLOYMENT"):
        return env["DEPLOYMENT"].strip()

    marker = _find_worktree_marker(cwd)
    if marker is not None:
        slug = marker.read_text().strip()
        if slug:
            return slug

    if ACTIVE_FILE.is_file():
        slug = ACTIVE_FILE.read_text().strip()
        if slug:
            return slug

    raise DeploymentNotResolvedError(
        "No deployment resolved. Set one of:\n"
        "  - pass --deployment <slug> on the CLI / deployment=<slug> to make\n"
        "  - export DEPLOYMENT=<slug>\n"
        "  - run `make bind-worktree slug=<slug>` inside a worktree\n"
        "  - run `make use-deployment slug=<slug>` to set the repo default\n"
        f"Known deployments: {', '.join(list_all()) or '(none yet — run `make new-deployment slug=<slug> apex=<domain>`)'}"
    )


def list_all() -> list[str]:
    """Return every deployment slug present under .local/deployments/."""
    if not DEPLOYMENTS_DIR.is_dir():
        return []
    return sorted(p.name for p in DEPLOYMENTS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


@dataclass
class Deployment:
    slug: str
    root: Path
    identity: dict[str, Any]
    topology: dict[str, Any]
    profile: dict[str, Any]

    @property
    def generated_dir(self) -> Path:
        return self.root / "generated"

    @property
    def secrets_dir(self) -> Path:
        return self.root / "secrets"

    @property
    def receipts_dir(self) -> Path:
        return self.root / "receipts"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def platform_domain(self) -> str:
        return self.identity.get("platform_domain", "")

    @property
    def operator_email(self) -> str:
        return self.identity.get("platform_operator_email", "")

    @property
    def operator_name(self) -> str:
        return self.identity.get("platform_operator_name", "")

    def ensure_runtime_dirs(self) -> None:
        for d in (self.generated_dir, self.secrets_dir, self.receipts_dir, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list[str]:
        """Schema-validate identity / topology / profile.

        Returns a list of human-readable errors; empty list means valid.
        Uses jsonschema if available; falls back to a minimal required-keys
        check if not (so the loader works on a fresh checkout before
        `pip install`).
        """
        errors: list[str] = []
        try:
            from jsonschema import Draft202012Validator  # type: ignore
        except ImportError:
            return self._validate_minimal()

        for name, payload in [
            ("identity", self.identity),
            ("topology", self.topology),
            ("profile", self.profile),
        ]:
            schema_path = SCHEMA_DIR / f"{name}.schema.json"
            if not schema_path.is_file():
                continue
            schema = json.loads(schema_path.read_text())
            validator = Draft202012Validator(schema)
            for err in validator.iter_errors(payload):
                loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
                errors.append(f"[{name}:{loc}] {err.message}")
        return errors

    def _validate_minimal(self) -> list[str]:
        errors: list[str] = []
        required_identity = (
            "platform_domain",
            "platform_operator_email",
            "platform_operator_name",
        )
        for key in required_identity:
            if not self.identity.get(key):
                errors.append(f"[identity:{key}] missing or empty")
        if "proxmox_guests" in self.topology and not isinstance(self.topology["proxmox_guests"], list):
            errors.append("[topology:proxmox_guests] must be a list")
        if "profiles" in self.profile and not isinstance(self.profile["profiles"], list):
            errors.append("[profile:profiles] must be a list")
        return errors


def load(slug: str | None = None, *, validate: bool = True) -> Deployment:
    """Load a deployment by slug. Resolves the active slug if None."""
    if slug is None:
        slug = resolve_active_slug()

    root = DEPLOYMENTS_DIR / slug
    if not root.is_dir():
        known = list_all()
        raise DeploymentNotFoundError(
            f"Deployment {slug!r} not found at {root}. Known: {', '.join(known) if known else '(none)'}"
        )

    identity_path = root / "identity.yml"
    topology_path = root / "topology.yml"
    profile_path = root / "profile.yml"

    identity = _read_yaml(identity_path) if identity_path.is_file() else {}
    topology = _read_yaml(topology_path) if topology_path.is_file() else {}
    profile = _read_yaml(profile_path) if profile_path.is_file() else {}

    deployment = Deployment(
        slug=slug,
        root=root,
        identity=identity,
        topology=topology,
        profile=profile,
    )

    if validate:
        errors = deployment.validate()
        if errors:
            raise DeploymentValidationError(f"Deployment {slug!r} failed schema validation:\n  " + "\n  ".join(errors))

    return deployment


# ---------------------------------------------------------------------------
# Service profile resolution (ADR 0441)
# ---------------------------------------------------------------------------


def _load_service_profiles() -> dict[str, dict[str, Any]]:
    """Load the committed profile catalog from inventory/group_vars/all/."""
    catalog_path = REPO_ROOT / "inventory" / "group_vars" / "all" / "service_profiles.yml"
    if not catalog_path.is_file():
        return {}
    raw = _read_yaml(catalog_path)
    return raw.get("service_profiles", {}) or {}


def _load_service_registry() -> dict[str, dict[str, Any]]:
    """Load the committed service catalog (used for requires_services)."""
    registry_path = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
    if not registry_path.is_file():
        return {}
    raw = _read_yaml(registry_path)
    return raw.get("platform_service_registry", {}) or {}


def _profile_closure(
    profile_name: str, catalog: dict[str, dict[str, Any]], visiting: set[str] | None = None
) -> set[str]:
    """Recursively expand a profile's `extends` graph, returning the union of
    declared services. Cycles raise DeploymentValidationError."""
    visiting = visiting or set()
    if profile_name in visiting:
        raise DeploymentValidationError(
            f"Profile cycle detected involving {profile_name!r}: {' -> '.join(sorted(visiting))} -> {profile_name}"
        )
    if profile_name not in catalog:
        raise DeploymentValidationError(
            f"Unknown profile {profile_name!r}. Known: {', '.join(sorted(catalog)) or '(none)'}"
        )
    visiting = visiting | {profile_name}
    entry = catalog[profile_name]
    services: set[str] = set(entry.get("services", []) or [])
    for parent in entry.get("extends", []) or []:
        services |= _profile_closure(parent, catalog, visiting)
    return services


def resolve_enabled_services(
    deployment: Deployment,
    *,
    profile_catalog: dict[str, dict[str, Any]] | None = None,
    service_registry: dict[str, dict[str, Any]] | None = None,
) -> set[str]:
    """Compute the set of enabled services for a deployment per ADR 0441.

    Order of operations:
        1. Union closure of every named profile in `profiles:`.
        2. Add `extra_services:`.
        3. Subtract `disabled_services:`.
        4. Walk `requires_services` to a fixed point (implicit deps).
        5. Verify no required dependency was hard-disabled.
    """
    profile_catalog = profile_catalog or _load_service_profiles()
    service_registry = service_registry or _load_service_registry()

    profile = deployment.profile
    enabled: set[str] = set()

    for name in profile.get("profiles", []) or []:
        enabled |= _profile_closure(name, profile_catalog)

    enabled |= set(profile.get("extra_services", []) or [])

    disabled = set(profile.get("disabled_services", []) or [])
    enabled -= disabled

    # Walk requires_services to a fixed point.
    while True:
        added: set[str] = set()
        for svc in list(enabled):
            requires = service_registry.get(svc, {}).get("requires_services", []) or []
            for dep in requires:
                if dep in disabled:
                    raise DeploymentValidationError(
                        f"Service {svc!r} requires {dep!r}, but {dep!r} is in "
                        f"disabled_services for deployment {deployment.slug!r}. "
                        f"Either enable {dep!r} or remove {svc!r} from the profile."
                    )
                if dep not in enabled:
                    added.add(dep)
        if not added:
            break
        enabled |= added

    return enabled


# ---------------------------------------------------------------------------
# CLI entrypoints (Makefile shim + operator convenience)
# ---------------------------------------------------------------------------


def _cmd_resolve(args: argparse.Namespace) -> int:
    try:
        slug = resolve_active_slug()
    except DeploymentNotResolvedError as exc:
        if not args.quiet:
            print(str(exc), file=sys.stderr)
        return 2
    print(slug)
    return 0


def _cmd_list(_: argparse.Namespace) -> int:
    for slug in list_all():
        print(slug)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    slugs = list_all() if args.all else [args.slug or resolve_active_slug()]
    failures = 0
    for slug in slugs:
        try:
            d = load(slug, validate=False)
            errors = d.validate()
            if errors:
                failures += 1
                print(f"[FAIL] {slug}", file=sys.stderr)
                for err in errors:
                    print(f"    {err}", file=sys.stderr)
            else:
                print(f"[ OK ] {slug}")
        except DeploymentError as exc:
            failures += 1
            print(f"[FAIL] {slug}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def _cmd_whoami(_: argparse.Namespace) -> int:
    try:
        slug = resolve_active_slug()
    except DeploymentNotResolvedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    sources = []
    if os.environ.get("DEPLOYMENT"):
        sources.append("$DEPLOYMENT env var")
    marker = _find_worktree_marker()
    if marker is not None:
        sources.append(
            f"worktree marker {marker.relative_to(REPO_ROOT) if marker.is_relative_to(REPO_ROOT) else marker}"
        )
    if ACTIVE_FILE.is_file():
        sources.append(f"active-deployment file ({ACTIVE_FILE.relative_to(REPO_ROOT)})")

    print(f"Active deployment: {slug}")
    print(f"Resolved via:      {sources[0] if sources else '(unknown)'}")

    try:
        d = load(slug)
    except DeploymentError as exc:
        print(f"Status:            {exc}")
        return 1

    print(f"Apex domain:       {d.platform_domain or '(unset)'}")
    print(f"Operator:          {d.operator_name or '(unset)'} <{d.operator_email or 'unset'}>")
    print(f"Root:              {d.root.relative_to(REPO_ROOT) if d.root.is_relative_to(REPO_ROOT) else d.root}")
    print(f"Profiles:          {', '.join(d.profile.get('profiles', []) or []) or '(none)'}")
    return 0


def _cmd_resolve_dir(args: argparse.Namespace) -> int:
    """Print the absolute path to a deployment's directory."""
    slug = args.slug or resolve_active_slug()
    print(DEPLOYMENTS_DIR / slug)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deployment", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser("resolve", help="Print active slug")
    p_resolve.add_argument("--quiet", action="store_true")
    p_resolve.set_defaults(func=_cmd_resolve)

    p_list = sub.add_parser("list", help="List known deployments")
    p_list.set_defaults(func=_cmd_list)

    p_validate = sub.add_parser("validate", help="Schema-validate a deployment")
    grp = p_validate.add_mutually_exclusive_group()
    grp.add_argument("--slug")
    grp.add_argument("--all", action="store_true")
    p_validate.set_defaults(func=_cmd_validate)

    p_whoami = sub.add_parser("whoami", help="Show active deployment + identity")
    p_whoami.set_defaults(func=_cmd_whoami)

    p_dir = sub.add_parser("resolve-dir", help="Print absolute path to a deployment's directory")
    p_dir.add_argument("--slug")
    p_dir.set_defaults(func=_cmd_resolve_dir)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
