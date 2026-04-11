#!/usr/bin/env python3
"""Bootstrap .local/ overlay from controller-local-secrets.json manifest.

Reads the secret manifest and creates:
  - Directory scaffold with .gitkeep files
  - ED25519 SSH keypair for bootstrap access
  - Random passwords for generated_by_repo secrets
  - Stub JSON/YAML files where structure templates exist
  - Checklist of externally-provided secrets that require manual action

Usage:
    python scripts/init_local_overlay.py                # interactive, aborts if .local/ exists
    python scripts/init_local_overlay.py --force         # overwrite missing files only (safe)
    python scripts/init_local_overlay.py --dry-run       # show what would be created
    python scripts/init_local_overlay.py --scaffold-only # directories + .gitkeep only, no secrets
"""

from __future__ import annotations

import argparse
import json
import secrets
import string
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
EXAMPLE_DIR = REPO_ROOT / "local-overlay-template"


def resolve_local_overlay_root() -> Path:
    """Mirror the logic from scripts/resolve_local_overlay_root.sh."""
    try:
        common_dir = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return Path(common_dir).parent / ".local"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return REPO_ROOT / ".local"


def load_manifest() -> dict:
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def generate_password(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_hex_key(length: int = 32) -> str:
    return secrets.token_hex(length)


def generate_ssh_keypair(target_dir: Path, dry_run: bool = False) -> None:
    private_key = target_dir / "bootstrap.id_ed25519"
    if private_key.exists():
        print(f"  [skip] {private_key} already exists")
        return
    if dry_run:
        print(f"  [dry-run] would generate SSH keypair at {private_key}")
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            str(private_key),
            "-N",
            "",
            "-C",
            "serverclaw-bootstrap",
        ],
        check=True,
        capture_output=True,
    )
    print(f"  [created] SSH keypair: {private_key}")


def infer_file_content(secret_name: str, info: dict) -> str | None:
    """Generate sensible default content based on secret type and name."""
    path = info.get("path", "")
    origin = info.get("origin", "")

    # SSH keys are handled separately
    if "ssh" in secret_name and path.endswith(".id_ed25519"):
        return None
    if path.endswith(".pub"):
        return None

    # JSON files get empty JSON object or array
    if path.endswith(".json"):
        if "token" in secret_name or "auth" in secret_name:
            return "{}\n"
        return "{}\n"

    # Password/secret/key text files get random passwords
    if origin == "generated_by_repo":
        if any(kw in secret_name for kw in ("password", "secret", "key", "token")):
            return generate_password() + "\n"
        if "api_key" in secret_name or "api_token" in secret_name:
            return generate_hex_key(24) + "\n"
        # Generic generated file — random password is a safe default
        return generate_password() + "\n"

    # Externally provided — create placeholder
    if origin in ("provided_externally", "provided_or_generated_externally"):
        return f"# REPLACE: {info.get('description', secret_name)}\n"

    return None


def create_scaffold(
    local_root: Path, manifest: dict, *, dry_run: bool = False, force: bool = False, scaffold_only: bool = False
) -> tuple[list[str], list[str]]:
    """Create the .local/ directory tree and populate files.

    Returns (created_files, external_secrets_needed).
    """
    created: list[str] = []
    external: list[str] = []
    seen_dirs: set[str] = set()

    for secret_name, info in sorted(manifest["secrets"].items()):
        if info.get("kind") != "file":
            continue
        path_str = info.get("path", "")
        if not path_str.startswith(".local/"):
            continue

        # Compute target path relative to .local/
        rel = path_str[len(".local/") :]
        target = local_root / rel
        target_dir = target.parent

        # Ensure directory exists
        dir_key = str(target_dir)
        if dir_key not in seen_dirs:
            seen_dirs.add(dir_key)
            if not target_dir.exists():
                if dry_run:
                    print(f"  [dry-run] mkdir {target_dir}")
                else:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    created.append(str(target_dir))

        # Track external secrets
        if info.get("origin") in ("provided_externally", "provided_or_generated_externally"):
            external.append(f"{path_str}: {info.get('description', secret_name)}")

        if scaffold_only:
            continue

        # Skip if file exists and not forcing
        if target.exists() and not force:
            continue

        # Skip if file exists (even with force, don't overwrite real secrets)
        if target.exists():
            continue

        # Generate content
        content = infer_file_content(secret_name, info)
        if content is None:
            continue

        if dry_run:
            print(f"  [dry-run] would create {target}")
        else:
            target.write_text(content)
            # Restrict permissions on secret files
            target.chmod(0o600)
            created.append(str(target))
            print(f"  [created] {target}")

    # Ensure .gitkeep in empty dirs
    for dir_path in sorted(seen_dirs):
        d = Path(dir_path)
        if d.exists() and not any(d.iterdir()):
            gitkeep = d / ".gitkeep"
            if not gitkeep.exists() and not dry_run:
                gitkeep.touch()

    return created, external


def generate_example_scaffold(manifest: dict) -> None:
    """Generate .local-example/ with placeholder files and README."""
    if EXAMPLE_DIR.exists():
        print(f"  [skip] {EXAMPLE_DIR} already exists")
        return

    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    # Create README
    readme = EXAMPLE_DIR / "README.md"
    readme.write_text(
        "# .local/ Overlay Directory\n"
        "\n"
        "This directory is the template for your deployment's local secrets and state.\n"
        "Copy it to `.local/` and populate with real values:\n"
        "\n"
        "    cp -r .local-example .local\n"
        "    python scripts/init_local_overlay.py --force\n"
        "\n"
        "Or run the automated scaffold directly:\n"
        "\n"
        "    make init-local\n"
        "\n"
        "## Structure\n"
        "\n"
        "Each subdirectory corresponds to a service. Files with `.example` suffix\n"
        "show the expected format — rename them (drop `.example`) and fill in real values.\n"
        "\n"
        "## Secret Origins\n"
        "\n"
        "- **generated_by_repo**: Automatically generated by `make init-local`\n"
        "- **provided_externally**: You must provide these (API keys, registrar tokens, etc.)\n"
        "- **provided_or_generated_externally**: Generate yourself or obtain from a provider\n"
        "\n"
        "## Never Commit This Directory\n"
        "\n"
        "`.local/` is in `.gitignore` and protected by a pre-commit hook.\n"
        "See ADR 0376 for the full incident analysis.\n"
    )

    # Create directory tree with .gitkeep
    seen_dirs: set[str] = set()
    for _name, info in sorted(manifest["secrets"].items()):
        if info.get("kind") != "file":
            continue
        path_str = info.get("path", "")
        if not path_str.startswith(".local/"):
            continue
        rel = path_str[len(".local/") :]
        d = EXAMPLE_DIR / Path(rel).parent
        dkey = str(d)
        if dkey not in seen_dirs:
            seen_dirs.add(dkey)
            d.mkdir(parents=True, exist_ok=True)
            gitkeep = d / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()

    print(f"  [created] {EXAMPLE_DIR}/ with {len(seen_dirs)} subdirectories")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap .local/ overlay from secret manifest")
    parser.add_argument("--force", action="store_true", help="Create missing files even if .local/ exists")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without doing it")
    parser.add_argument("--scaffold-only", action="store_true", help="Create directories only, no secret files")
    parser.add_argument("--generate-example", action="store_true", help="Generate .local-example/ scaffold")
    args = parser.parse_args()

    manifest = load_manifest()
    print(f"Loaded manifest: {len(manifest['secrets'])} secrets defined\n")

    if args.generate_example:
        generate_example_scaffold(manifest)
        return

    local_root = resolve_local_overlay_root()

    if local_root.exists() and not args.force and not args.dry_run:
        print(f"ERROR: {local_root} already exists.")
        print("Use --force to create missing files, or --dry-run to preview.")
        sys.exit(1)

    print(f"Target: {local_root}\n")

    # Stage 1: Generate SSH keypair
    print("=== Stage 1: SSH Bootstrap Key ===")
    generate_ssh_keypair(local_root / "ssh", dry_run=args.dry_run)

    # Stage 2: Create directory scaffold and populate secrets
    print("\n=== Stage 2: Secret Scaffold ===")
    created, external = create_scaffold(
        local_root,
        manifest,
        dry_run=args.dry_run,
        force=args.force,
        scaffold_only=args.scaffold_only,
    )

    # Stage 3: Report
    print("\n=== Summary ===")
    print(f"  Files created: {len(created)}")
    print(f"  External secrets needed: {len(external)}")

    if external:
        print("\n=== Action Required: External Secrets ===")
        print("The following secrets must be provided manually:\n")
        for item in sorted(external):
            print(f"  - {item}")

    print("\nDone. Run 'make verify-bootstrap' to check readiness.")


if __name__ == "__main__":
    main()
