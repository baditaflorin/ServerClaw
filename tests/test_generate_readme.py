from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_readme  # noqa: E402


def test_render_preserves_existing_generated_status_blocks(tmp_path: Path) -> None:
    template = tmp_path / "README.md.j2"
    template.write_text(
        "# Platform\n\n<!-- BEGIN GENERATED: platform-status -->\n<!-- END GENERATED: platform-status -->\n",
        encoding="utf-8",
    )
    current = tmp_path / "README.md"
    current.write_text(
        "# Previous\n\n<!-- BEGIN GENERATED: platform-status -->\n"
        "live status\n<!-- END GENERATED: platform-status -->\n",
        encoding="utf-8",
    )

    rendered = generate_readme.render(template, current_path=current)

    assert "live status" in rendered
    assert "<!-- BEGIN GENERATED: platform-status -->" in rendered
    assert "<!-- END GENERATED: platform-status -->" in rendered


def test_architecture_template_does_not_embed_a_deployment_subnet() -> None:
    template = (REPO_ROOT / "docs" / "templates" / "README.md.j2").read_text(encoding="utf-8")

    assert "10.10.10." not in template
