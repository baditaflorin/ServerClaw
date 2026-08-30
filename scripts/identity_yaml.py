from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _find_identity_path() -> Path:
    """Locate inventory/group_vars/all/identity.yml relative to this script."""
    return Path(__file__).resolve().parents[1] / "inventory" / "group_vars" / "all" / "identity.yml"


def _load_scalar_identity_mapping(path: Path) -> dict[str, str]:
    import yaml

    if not path.exists():
        return {}
    with path.open() as handle:
        data = yaml.safe_load(handle) or {}
    return {key: value for key, value in data.items() if isinstance(value, str) and "{{" not in value}


def load_identity_vars() -> dict[str, str]:
    """Load simple scalar identity variables from identity.yml and the shared .local overlay."""
    path = _find_identity_path()
    identity_vars = _load_scalar_identity_mapping(path)

    from platform.repo import local_overlay_root, resolve_explicit_overlay_selector

    explicit_overlay = resolve_explicit_overlay_selector(
        "PLATFORM_IDENTITY_OVERLAY",
        repo_root=path.parents[3],
    )
    if explicit_overlay is not None:
        identity_vars.update(_load_scalar_identity_mapping(explicit_overlay))
        return identity_vars

    if os.environ.get("LV3_DISABLE_SHARED_LOCAL_IDENTITY", "").lower() in {"1", "true", "yes"}:
        return identity_vars

    overlay_path = local_overlay_root(path.parents[3]) / "identity.yml"
    identity_vars.update(_load_scalar_identity_mapping(overlay_path))
    return identity_vars


def load_tracked_generation_identity_vars(platform_path: Path | None = None) -> dict[str, str]:
    """Load the reproducible identity snapshot embedded in generated platform facts.

    Generated-artifact validation must not consult whichever shared ``.local``
    profile happens to be active on the current workstation. The tracked
    ``platform_generation.identity_overlay`` is the identity that produced the
    artifacts and is therefore the deterministic validation input.
    """

    import yaml

    if platform_path is None:
        platform_path = _find_identity_path().parents[1] / "platform.yml"
    if not platform_path.is_file():
        return {}
    payload = yaml.safe_load(platform_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    generation = payload.get("platform_generation", {})
    if not isinstance(generation, dict):
        return {}
    overlay = generation.get("identity_overlay", {})
    if not isinstance(overlay, dict):
        return {}
    return {
        key: value
        for key, value in overlay.items()
        if isinstance(key, str) and isinstance(value, str) and "{{" not in value
    }


def resolve_jinja2_vars(text: str, variables: dict[str, str] | None = None) -> str:
    """Resolve simple ``{{ var }}`` expressions in *text*."""
    if variables is None:
        variables = load_identity_vars()
    for key, value in variables.items():
        text = text.replace("{{ " + key + " }}", value)
        text = text.replace("{{" + key + "}}", value)
    return text


def load_yaml_with_identity(path: Path, variables: dict[str, str] | None = None) -> Any:
    """Load a YAML file, resolving ``{{ platform_domain }}`` and friends first."""
    import yaml

    raw = path.read_text()
    resolved = resolve_jinja2_vars(raw, variables)
    return yaml.safe_load(resolved)
