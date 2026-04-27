"""Migrate the existing single-deployment layout into the per-deployment
layout introduced by ADR 0440.

Modes:
  default  Dry-run; report planned operations.
  --apply  Execute the moves and write the active-deployment marker.
  --rollback  Reverse a previously-applied migration for the given slug.

Source paths (existing layout):

    .local/identity.yml
    inventory/host_vars/proxmox-host.yml         (committed)
    inventory/group_vars/platform.yml            (committed, generated)
    inventory/hosts.yml                          (committed, generated)
    build/platform-manifest.json                 (committed, generated)
    build/onboarding/                            (committed, generated)
    .local/<service>/                            (per-service secrets)

Destination paths (per-deployment layout for slug "prod"):

    .local/deployments/prod/identity.yml
    .local/deployments/prod/topology.yml
    .local/deployments/prod/profile.yml          (synthesised from live state)
    .local/deployments/prod/generated/platform.yml
    .local/deployments/prod/generated/hosts.yml
    .local/deployments/prod/generated/platform-manifest.json
    .local/deployments/prod/generated/onboarding/
    .local/deployments/prod/secrets/<service>/   (per-service)
    .local/active-deployment                     (containing "prod")

Usage:

    python3 scripts/migrate_to_multi_deployment.py
        Dry-run; prints planned moves. (Phase 1 default.)

    python3 scripts/migrate_to_multi_deployment.py --slug prod
        Use a different target slug.

    python3 scripts/migrate_to_multi_deployment.py --apply
        Execute the moves.

    python3 scripts/migrate_to_multi_deployment.py --rollback --slug prod
        Move artefacts back to their pre-migration paths. Refuses if the
        original paths are occupied (i.e. somebody re-generated the old
        layout while the new one was active).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.deployment import DEPLOYMENTS_DIR, REPO_ROOT


@dataclass
class MoveOp:
    src: Path
    dst: Path
    kind: str  # "move", "copy", "synthesise", "write"
    note: str = ""

    def render(self, root: Path) -> str:
        def rel(p: Path) -> str:
            try:
                return str(p.relative_to(root))
            except ValueError:
                return str(p)

        marker = {
            "move": "MV",
            "copy": "CP",
            "synthesise": "GEN",
            "write": "WRITE",
        }.get(self.kind, "??")
        if self.kind in ("synthesise", "write"):
            return f"  [{marker}] -> {rel(self.dst)}  {self.note}".rstrip()
        return f"  [{marker}] {rel(self.src)} -> {rel(self.dst)}  {self.note}".rstrip()


@dataclass
class MigrationPlan:
    slug: str
    deployment_root: Path
    operations: list[MoveOp] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def add(self, op: MoveOp) -> None:
        self.operations.append(op)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def skip(self, msg: str) -> None:
        self.skipped.append(msg)


# ---------------------------------------------------------------------------
# Sources we know how to migrate. Each entry is (src_relative_to_repo, dst_relative_to_deployment_root, kind).
# ---------------------------------------------------------------------------

OPERATOR_AUTHORED_MOVES = [
    (".local/identity.yml", "identity.yml"),
    ("inventory/host_vars/proxmox-host.yml", "topology.yml"),
]

GENERATED_MOVES = [
    ("inventory/group_vars/platform.yml", "generated/platform.yml"),
    ("inventory/hosts.yml", "generated/hosts.yml"),
    ("build/platform-manifest.json", "generated/platform-manifest.json"),
]

GENERATED_TREE_MOVES = [
    ("build/onboarding", "generated/onboarding"),
]


# ---------------------------------------------------------------------------
# Per-service secret directories under .local/<service>/. We DO NOT
# automatically migrate these in Phase 1 — they're the highest-risk move
# (touch a wrong path and live credentials are gone). The plan reports
# them but does not stage moves; Phase 4 (out of scope for the migration
# script itself) handles secret directory migration via dedicated tooling.
# ---------------------------------------------------------------------------

PRESERVED_LOCAL_DIRS = {"deployments", "ssh", "hetzner"}


def _scan_secret_dirs(repo_root: Path) -> list[Path]:
    local = repo_root / ".local"
    if not local.is_dir():
        return []
    return sorted(
        p for p in local.iterdir() if p.is_dir() and p.name not in PRESERVED_LOCAL_DIRS and not p.name.startswith(".")
    )


def build_plan(slug: str, repo_root: Path | None = None) -> MigrationPlan:
    if repo_root is None:
        repo_root = REPO_ROOT
    deployment_root = DEPLOYMENTS_DIR / slug
    plan = MigrationPlan(slug=slug, deployment_root=deployment_root)

    if deployment_root.exists() and any(deployment_root.iterdir()):
        plan.warn(
            f".local/deployments/{slug}/ already exists and is non-empty. "
            f"Migration would refuse in --apply mode without --force."
        )

    # Operator-authored sources
    for src_rel, dst_rel in OPERATOR_AUTHORED_MOVES:
        src = repo_root / src_rel
        dst = deployment_root / dst_rel
        if src.is_file():
            plan.add(MoveOp(src=src, dst=dst, kind="move", note="operator-authored — moved out of git/.local root"))
        else:
            plan.skip(f"{src_rel} not present, skipping")

    # Generated artifacts (committed today; should leave git after move)
    for src_rel, dst_rel in GENERATED_MOVES:
        src = repo_root / src_rel
        dst = deployment_root / dst_rel
        if src.is_file():
            plan.add(MoveOp(src=src, dst=dst, kind="move", note="generated artifact — leaves git after Phase 2"))
        else:
            plan.skip(f"{src_rel} not present, skipping")

    # Generated trees
    for src_rel, dst_rel in GENERATED_TREE_MOVES:
        src = repo_root / src_rel
        dst = deployment_root / dst_rel
        if src.is_dir():
            plan.add(MoveOp(src=src, dst=dst, kind="move", note="generated tree — leaves git after Phase 2"))
        else:
            plan.skip(f"{src_rel} not present, skipping")

    # profile.yml — synthesised, not moved
    plan.add(
        MoveOp(
            src=Path("(synthesised from live lv3_service_topology)"),
            dst=deployment_root / "profile.yml",
            kind="synthesise",
            note="ADR 0441 — placeholder profile listing every currently-deployed service",
        )
    )

    # active-deployment marker
    plan.add(
        MoveOp(
            src=Path(f"(slug={slug})"),
            dst=repo_root / ".local" / "active-deployment",
            kind="write",
            note="single-line marker pointing at the new deployment",
        )
    )

    # Per-service secret directories — reported but not staged
    secret_dirs = _scan_secret_dirs(repo_root)
    if secret_dirs:
        plan.warn(
            f"{len(secret_dirs)} per-service secret directory under .local/ "
            f"would migrate to .local/deployments/{slug}/secrets/ in a later "
            f"phase. Phase 1 dry-run reports them only:"
        )
        for d in secret_dirs:
            plan.warnings.append(f"    .local/{d.name}/")

    return plan


def _synthesise_profile_stub(slug: str, repo_root: Path) -> str:
    """Produce a minimal profile.yml YAML body.

    Phase 1 cannot inspect the live deployment to enumerate active
    services — we'd need either live SSH access or a parsed
    lv3_service_topology snapshot. Instead, we emit a stub that asks
    the operator to fill in the profile interactively (or that
    Phase 2's --apply mode can populate from a snapshot).
    """
    return (
        f"# Service profile for deployment {slug!r}.\n"
        "# Synthesised by scripts/migrate_to_multi_deployment.py — review and edit.\n"
        "#\n"
        "# Phase 2 will replace this stub with the live service set computed\n"
        "# from inventory/host_vars/proxmox-host.yml::lv3_service_topology.\n"
        "---\n"
        "profiles:\n"
        "  - core\n"
        "extra_services: []\n"
        "disabled_services: []\n"
        "service_overrides: {}\n"
    )


def execute_plan(plan: MigrationPlan, *, force: bool = False) -> None:
    """Apply a migration plan. Phase 2+ only."""
    if plan.deployment_root.exists() and any(plan.deployment_root.iterdir()) and not force:
        raise SystemExit(f"Refusing to migrate: {plan.deployment_root} is non-empty. Pass --force to proceed.")

    plan.deployment_root.mkdir(parents=True, exist_ok=True)
    (plan.deployment_root / "generated").mkdir(parents=True, exist_ok=True)
    (plan.deployment_root / "secrets").mkdir(parents=True, exist_ok=True)
    (plan.deployment_root / "receipts").mkdir(parents=True, exist_ok=True)
    (plan.deployment_root / "state").mkdir(parents=True, exist_ok=True)

    for op in plan.operations:
        if op.kind == "move":
            op.dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(op.src), str(op.dst))
        elif op.kind == "copy":
            op.dst.parent.mkdir(parents=True, exist_ok=True)
            if op.src.is_dir():
                shutil.copytree(str(op.src), str(op.dst), dirs_exist_ok=True)
            else:
                shutil.copy2(str(op.src), str(op.dst))
        elif op.kind == "synthesise":
            op.dst.parent.mkdir(parents=True, exist_ok=True)
            op.dst.write_text(_synthesise_profile_stub(plan.slug, REPO_ROOT))
        elif op.kind == "write":
            op.dst.parent.mkdir(parents=True, exist_ok=True)
            op.dst.write_text(plan.slug + "\n")
        else:
            raise SystemExit(f"Unknown op kind: {op.kind}")


def build_rollback_plan(slug: str, repo_root: Path | None = None) -> MigrationPlan:
    """Reverse the directional moves of build_plan() for an applied migration.

    Inverts every move in OPERATOR_AUTHORED_MOVES, GENERATED_MOVES,
    GENERATED_TREE_MOVES. Skips synthesised artefacts (profile.yml stub)
    and the active-deployment marker — the operator can delete those by
    hand.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    deployment_root = DEPLOYMENTS_DIR / slug
    plan = MigrationPlan(slug=slug, deployment_root=deployment_root)

    if not deployment_root.is_dir():
        plan.warn(f"Deployment {slug!r} does not exist at {deployment_root}.")
        return plan

    all_moves = (
        [(s, d, "file") for s, d in OPERATOR_AUTHORED_MOVES]
        + [(s, d, "file") for s, d in GENERATED_MOVES]
        + [(s, d, "tree") for s, d in GENERATED_TREE_MOVES]
    )
    for orig_rel, dep_rel, _kind in all_moves:
        orig = repo_root / orig_rel
        dep = deployment_root / dep_rel
        if not dep.exists():
            plan.skip(f"{dep_rel} not present in deployment, skipping")
            continue
        if orig.exists():
            plan.warn(f"{orig_rel} already exists — refusing to overwrite. Move it aside before rolling back.")
            continue
        plan.add(MoveOp(src=dep, dst=orig, kind="move", note="rollback — restoring pre-migration path"))

    return plan


def execute_rollback(plan: MigrationPlan) -> None:
    if plan.warnings:
        raise SystemExit("Refusing to rollback while warnings are present:\n  " + "\n  ".join(plan.warnings))
    for op in plan.operations:
        op.dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(op.src), str(op.dst))

    marker = REPO_ROOT / ".local" / "active-deployment"
    if marker.exists() and marker.read_text().strip() == plan.slug:
        marker.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--slug", default="prod", help="Target deployment slug (default: prod)")
    parser.add_argument("--apply", action="store_true", help="Actually perform the migration")
    parser.add_argument("--rollback", action="store_true", help="Reverse a previously-applied migration for --slug")
    parser.add_argument("--force", action="store_true", help="Overwrite a non-empty target directory (--apply only)")
    args = parser.parse_args(argv)

    if args.rollback:
        plan = build_rollback_plan(args.slug)
        print(f"Rollback plan for deployment slug = {args.slug!r}")
        print(f"Source root: {plan.deployment_root}")
        print()
        if not plan.operations:
            print("  (no operations — nothing to roll back)")
        else:
            print("Planned operations:")
            for op in plan.operations:
                print(op.render(REPO_ROOT))
        if plan.skipped:
            print()
            print("Skipped:")
            for s in plan.skipped:
                print(f"  - {s}")
        if plan.warnings:
            print()
            print("Warnings:")
            for w in plan.warnings:
                print(f"  - {w}")
        if not args.apply:
            print()
            print("Dry-run only. Re-run with --rollback --apply to execute.")
            return 0
        if plan.warnings:
            print()
            print("Refusing to roll back while warnings are present.", file=sys.stderr)
            return 2
        print()
        print("Executing rollback...")
        execute_rollback(plan)
        print("Done.")
        return 0

    plan = build_plan(args.slug)

    print(f"Migration plan for deployment slug = {args.slug!r}")
    print(f"Target root: {plan.deployment_root}")
    print()
    if not plan.operations:
        print("  (no operations — nothing to migrate)")
    else:
        print("Planned operations:")
        for op in plan.operations:
            print(op.render(REPO_ROOT))

    if plan.skipped:
        print()
        print("Skipped:")
        for s in plan.skipped:
            print(f"  - {s}")

    if plan.warnings:
        print()
        print("Warnings:")
        for w in plan.warnings:
            print(f"  - {w}")

    if not args.apply:
        print()
        print("Dry-run only. Re-run with --apply to execute.")
        return 0

    print()
    print("Executing migration...")
    execute_plan(plan, force=args.force)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
