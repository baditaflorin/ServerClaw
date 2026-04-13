from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_makefile_live_apply_service_loads_descriptor_vars_when_present() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    live_apply_block = makefile.split("live-apply-service:\n", 1)[1].split("\n\n", 1)[0]

    assert 'descriptor_args=""' in live_apply_block
    assert "playbooks/vars/$(service).yml" in live_apply_block
    assert "INFO live-apply-service: loading playbook descriptor" in live_apply_block
    assert "$$descriptor_args" in live_apply_block


def test_makefile_only_references_existing_playbooks_and_descriptor_files() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    referenced_paths = {
        Path(match) for match in re.findall(r"\$\(REPO_ROOT\)/(playbooks/[A-Za-z0-9._/-]+\.yml)", makefile)
    }

    missing_paths = sorted(str(path) for path in referenced_paths if not (REPO_ROOT / path).exists())
    assert missing_paths == []
