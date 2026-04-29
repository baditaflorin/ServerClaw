"""ADR 0457 + ws-0460 sweep regression test.

ws-0460 (PR #88) wired `lv3.platform.host_pinning_guard` into the
shared `playbooks/tasks/preflight.yml` surface so 52 service playbooks
inherit the guard automatically. This test locks that wiring in:

  1. `playbooks/tasks/preflight.yml` includes the host_pinning_guard
     role at the top.
  2. Every service playbook that imports `tasks/preflight.yml`
     transitively benefits from the guard.
  3. The role itself exists at the documented path.
  4. `playbooks/public-edge.yml` (which doesn't go through shared
     preflight) still has the guard wired explicitly.

Catches the "someone refactored the shared preflight" and "someone
moved the role" regression classes that ws-0460's sweep is
load-bearing on.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOKS_DIR = REPO_ROOT / "playbooks"
SHARED_PREFLIGHT = PLAYBOOKS_DIR / "tasks" / "preflight.yml"
PUBLIC_EDGE = PLAYBOOKS_DIR / "public-edge.yml"
ROLE_DIR = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "host_pinning_guard"
)


def test_role_exists_at_documented_path():
    """The role's path is referenced in:
      - playbooks/tasks/preflight.yml (include_role.name)
      - playbooks/public-edge.yml (roles list)
    Moving it would break both. This test catches the move directly.
    """
    assert ROLE_DIR.is_dir(), f"missing role directory: {ROLE_DIR}"
    assert (ROLE_DIR / "tasks" / "main.yml").is_file()
    assert (ROLE_DIR / "defaults" / "main.yml").is_file()
    assert (ROLE_DIR / "meta" / "main.yml").is_file()


def test_shared_preflight_includes_host_pinning_guard():
    """ws-0460 wired the role into tasks/preflight.yml. The sweep relies
    on that one file. If somebody removes it during a refactor, every
    service playbook silently loses the guard."""
    content = SHARED_PREFLIGHT.read_text()
    # Match either an `include_role: name: ...` block or a single-line form.
    assert "host_pinning_guard" in content, (
        f"{SHARED_PREFLIGHT.relative_to(REPO_ROOT)} no longer references host_pinning_guard. "
        "ws-0460 sweep is broken — every service playbook that imports this preflight "
        "has lost the lv3 ↔ 0fork oauth2-proxy@4180 collision guard."
    )


def test_shared_preflight_invokes_role_via_include_role():
    """Defensive: not just any text occurrence — must actually be an
    `include_role` (or `import_role`) directive that references the role."""
    content = SHARED_PREFLIGHT.read_text()
    pattern = re.compile(
        r"(include_role|import_role):\s*\n\s*name:\s*lv3\.platform\.host_pinning_guard",
        re.MULTILINE,
    )
    assert pattern.search(content), (
        "host_pinning_guard is mentioned in tasks/preflight.yml but not via "
        "include_role/import_role. Make sure the role is actually invoked."
    )


def test_public_edge_playbook_wires_role_explicitly():
    """playbooks/public-edge.yml does NOT import tasks/preflight.yml.
    It must have host_pinning_guard wired explicitly in its `roles:` list
    (PR #87). Catches accidental removal during nginx_edge_publication
    refactors."""
    content = PUBLIC_EDGE.read_text()
    assert "lv3.platform.host_pinning_guard" in content, (
        "playbooks/public-edge.yml no longer wires host_pinning_guard. "
        "The shared preflight surface does NOT cover this playbook — the "
        "guard must remain in its `roles:` list explicitly (PR #87)."
    )


def _service_playbooks_using_shared_preflight() -> list[Path]:
    """Every playbook under playbooks/*.yml that imports tasks/preflight.yml."""
    matches: list[Path] = []
    for pb in PLAYBOOKS_DIR.glob("*.yml"):
        try:
            text = pb.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if "tasks/preflight.yml" in text:
            matches.append(pb)
    return sorted(matches)


def test_service_playbooks_inherit_via_shared_preflight():
    """At least 50 service playbooks (per ws-0460 PR description) use
    the shared preflight surface. If that count drops dramatically,
    something went wrong with the wiring or with how this test detects
    it."""
    matches = _service_playbooks_using_shared_preflight()
    # ws-0460 reported 52. Assert >= 30 to allow for some files moving
    # around without flapping; the actual sweep coverage matters.
    assert len(matches) >= 30, (
        f"only {len(matches)} service playbooks import tasks/preflight.yml "
        f"(expected >= 30 per ws-0460). The host_pinning_guard sweep coverage "
        f"may be regressing."
    )


@pytest.mark.parametrize(
    "playbook_name",
    ["ops-portal.yml", "keycloak.yml", "gitea.yml", "mail-platform.yml", "openbao.yml"],
)
def test_canonical_service_playbooks_use_shared_preflight(playbook_name):
    """Spot-check the most operationally critical playbooks. Each one
    must transitively pull in host_pinning_guard via the shared preflight."""
    pb = PLAYBOOKS_DIR / playbook_name
    if not pb.is_file():
        pytest.skip(f"{playbook_name} not present (may be a service that was removed)")
    content = pb.read_text()
    assert "tasks/preflight.yml" in content, (
        f"{playbook_name} no longer imports tasks/preflight.yml — host_pinning_guard "
        f"sweep no longer covers this playbook. The 0fork ↔ lv3 collision class is "
        f"reachable for this service."
    )
