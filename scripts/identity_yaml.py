from __future__ import annotations

from pathlib import Path
from typing import Any


def _find_identity_path() -> Path:
    """Locate inventory/group_vars/all/identity.yml relative to this script."""
    return Path(__file__).resolve().parents[1] / "inventory" / "group_vars" / "all" / "identity.yml"


def load_identity_vars() -> dict[str, str]:
    """Load simple scalar identity variables from identity.yml."""
    import yaml

    path = _find_identity_path()
    if not path.exists():
        return {}
    with path.open() as handle:
        data = yaml.safe_load(handle) or {}
    return {key: value for key, value in data.items() if isinstance(value, str) and "{{" not in value}


def resolve_jinja2_vars(text: str, variables: dict[str, str] | None = None) -> str:
    """Resolve simple ``{{ var }}`` expressions in *text*."""
    if variables is None:
        variables = load_identity_vars()
    for key, value in variables.items():
        text = text.replace("{{ " + key + " }}", value)
        text = text.replace("{{" + key + "}}", value)
    return text


def load_yaml_with_identity(path: Path) -> Any:
    """Load a YAML file, resolving ``{{ platform_domain }}`` and friends first."""
    import yaml

    raw = path.read_text()
    resolved = resolve_jinja2_vars(raw)
    return yaml.safe_load(resolved)
