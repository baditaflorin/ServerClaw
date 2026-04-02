from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scopes = load_module("lv3_ansible_execution_scopes", "platform/ansible/execution_scopes.py")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root = tmp_path
    inventory_path = tmp_path / "inventory" / "hosts.yml"
    write(
        inventory_path,
        """
all:
  children:
    production:
      hosts:
        alpha:
        beta:
    proxmox_hosts:
      hosts:
        alpha:
""".strip()
        + "\n",
    )
    catalog_path = tmp_path / "config" / "ansible-execution-scopes.yaml"
    write(
        catalog_path,
        """
playbooks:
  playbooks/leaf-alpha.yml:
    playbook_id: leaf-alpha
    mutation_scope: host
    shared_surfaces:
      - service:alpha
  playbooks/leaf-beta.yml:
    playbook_id: leaf-beta
    mutation_scope: host
    shared_surfaces:
      - service:beta
  collections/ansible_collections/lv3/platform/playbooks/leaf-collection.yml:
    playbook_id: collection-leaf
    mutation_scope: platform
    shared_surfaces:
      - service:collection
""".strip()
        + "\n",
    )
    write(repo_root / "playbooks" / "leaf-alpha.yml", "---\n- hosts: alpha\n")
    write(repo_root / "playbooks" / "leaf-beta.yml", "---\n- hosts: beta\n")
    write(
        repo_root / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "leaf-collection.yml",
        "---\n- hosts: alpha:beta\n",
    )
    write(
        tmp_path / "Makefile",
        """
live-apply-service:
\t$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/services/$(service).yml --env $(env)
converge-wrapper:
\t$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/wrapper.yml --env $(env)
""".strip()
        + "\n",
    )
    return tmp_path, catalog_path, inventory_path


def test_resolve_playbook_scope_inherits_single_import(tmp_path: Path) -> None:
    repo_root, catalog_path, _inventory_path = make_repo(tmp_path)
    write(
        repo_root / "playbooks" / "wrapper.yml",
        """
---
- import_playbook: leaf-alpha.yml
""".strip()
        + "\n",
    )

    resolved = scopes.resolve_playbook_scope("playbooks/wrapper.yml", repo_root=repo_root, catalog_path=catalog_path)

    assert resolved.mutation_scope == "host"
    assert resolved.source_leaf_playbooks == ("playbooks/leaf-alpha.yml",)
    assert resolved.shared_surfaces == (
        "playbooks/wrapper.yml",
        "playbooks/leaf-alpha.yml",
        "service:alpha",
    )


def test_resolve_playbook_scope_aggregates_multiple_children_to_platform(tmp_path: Path) -> None:
    repo_root, catalog_path, _inventory_path = make_repo(tmp_path)
    write(
        repo_root / "playbooks" / "group.yml",
        """
---
- import_playbook: leaf-alpha.yml
- import_playbook: leaf-beta.yml
""".strip()
        + "\n",
    )

    resolved = scopes.resolve_playbook_scope("playbooks/group.yml", repo_root=repo_root, catalog_path=catalog_path)

    assert resolved.mutation_scope == "platform"
    assert resolved.source_leaf_playbooks == ("playbooks/leaf-alpha.yml", "playbooks/leaf-beta.yml")
    assert "service:alpha" in resolved.shared_surfaces
    assert "service:beta" in resolved.shared_surfaces


def test_validate_scope_catalog_covers_live_apply_service_wrappers(tmp_path: Path) -> None:
    repo_root, catalog_path, inventory_path = make_repo(tmp_path)
    write(
        repo_root / "playbooks" / "services" / "alpha.yml",
        """
---
- import_playbook: ../leaf-alpha.yml
""".strip()
        + "\n",
    )
    write(
        repo_root / "playbooks" / "services" / "collection.yml",
        """
---
- import_playbook: ../../collections/ansible_collections/lv3/platform/playbooks/leaf-collection.yml
""".strip()
        + "\n",
    )
    write(repo_root / "playbooks" / "wrapper.yml", "---\n- import_playbook: leaf-alpha.yml\n")

    scopes.validate_scope_catalog(repo_root=repo_root, catalog_path=catalog_path, inventory_path=inventory_path)


def test_plan_playbook_execution_discovers_hosts_and_writes_inventory_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, catalog_path, inventory_path = make_repo(tmp_path)
    write(repo_root / "playbooks" / "leaf-alpha.yml", "---\n- hosts: alpha\n")

    calls: list[list[str]] = []

    def fake_run(command: list[str], cwd: Path, text: bool, capture_output: bool, check: bool = False):
        del cwd, text, capture_output, check
        calls.append(command)
        if command[0] == "ansible-inventory":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=yaml.safe_dump(
                    {
                        "all": {
                            "children": {
                                "production": {
                                    "hosts": {
                                        "alpha": {
                                            "ansible_host": "10.0.0.10",
                                        }
                                    }
                                }
                            }
                        }
                    }
                ),
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr(scopes.subprocess, "run", fake_run)

    plan = scopes.plan_playbook_execution(
        "playbooks/leaf-alpha.yml",
        env="production",
        run_id="run-123",
        repo_root=repo_root,
        catalog_path=catalog_path,
        inventory_path=inventory_path,
    )

    assert plan.limit_expression == "alpha"
    assert plan.mutation_scope == "host"
    assert Path(plan.inventory_shard_path).read_text(encoding="utf-8")
    assert (repo_root / ".ansible" / "shards" / "config").is_symlink()
    assert (repo_root / ".ansible" / "shards" / "config").resolve() == (repo_root / "config").resolve()
    assert calls[0][0] == "ansible-inventory"
    assert calls[1][0] == "ansible-inventory"


def test_discover_target_hosts_renders_env_based_host_expressions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, catalog_path, inventory_path = make_repo(tmp_path)
    del catalog_path
    write(
        repo_root / "playbooks" / "env-hosts.yml",
        """
---
- hosts: "{{ 'proxmox_hosts:&staging' if (env | default('production')) == 'staging' else 'proxmox_hosts:&production' }}"
""".strip()
        + "\n",
    )
    write(
        inventory_path,
        """
all:
  children:
    production:
      hosts:
        alpha:
    staging:
      hosts:
        beta:
    proxmox_hosts:
      hosts:
        alpha:
        beta:
""".strip()
        + "\n",
    )

    calls: list[list[str]] = []

    def fake_run(command: list[str], cwd: Path, text: bool, capture_output: bool, check: bool = False):
        del cwd, text, capture_output, check
        calls.append(command)
        if command[0] != "ansible-inventory":
            raise AssertionError(command)
        selected_hosts = {"alpha": {"ansible_host": "10.0.0.10"}}
        if "proxmox_hosts:&staging" in command:
            selected_hosts = {"beta": {"ansible_host": "10.0.0.20"}}
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=yaml.safe_dump({"all": {"children": {"selected": {"hosts": selected_hosts}}}}),
            stderr="",
        )

    monkeypatch.setattr(scopes.subprocess, "run", fake_run)

    production_hosts = scopes.discover_target_hosts(
        "playbooks/env-hosts.yml",
        env="production",
        repo_root=repo_root,
        inventory_path=inventory_path,
    )
    staging_hosts = scopes.discover_target_hosts(
        "playbooks/env-hosts.yml",
        env="staging",
        repo_root=repo_root,
        inventory_path=inventory_path,
    )

    assert production_hosts == ("alpha",)
    assert staging_hosts == ("beta",)
    assert calls[0][calls[0].index("-l") + 1] == "proxmox_hosts:&production"
    assert calls[1][calls[1].index("-l") + 1] == "proxmox_hosts:&staging"


def test_run_scoped_playbook_uses_primary_inventory_for_group_vars_and_shard_for_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, catalog_path, inventory_path = make_repo(tmp_path)
    write(repo_root / "playbooks" / "leaf-alpha.yml", "---\n- hosts: alpha\n")

    def fake_plan(*args, **kwargs):
        del args, kwargs
        return scopes.PlannedPlaybookExecution(
            playbook_path="playbooks/leaf-alpha.yml",
            env="production",
            run_id="run-456",
            mutation_scope="host",
            execution_class="mutation",
            target_lane=None,
            target_hosts=("alpha",),
            limit_expression="alpha",
            inventory_shard_path=str(repo_root / ".ansible" / "shards" / "run-456" / "leaf-alpha-production.json"),
            shared_surfaces=("playbooks/leaf-alpha.yml", "service:alpha", "host:alpha"),
            source_leaf_playbooks=("playbooks/leaf-alpha.yml",),
        )

    captured: list[list[str]] = []

    def fake_run(command: list[str], cwd: Path, text: bool, check: bool = False):
        del cwd, text, check
        captured.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(scopes, "plan_playbook_execution", fake_plan)
    monkeypatch.setattr(scopes.subprocess, "run", fake_run)

    result = scopes.run_scoped_playbook(
        "playbooks/leaf-alpha.yml",
        env="production",
        repo_root=repo_root,
        catalog_path=catalog_path,
        inventory_path=inventory_path,
        passthrough_args=["--private-key", "/tmp/test.id_ed25519"],
    )

    assert result.returncode == 0
    assert captured == [
        [
            "ansible-playbook",
            "-i",
            str(inventory_path),
            "-i",
            str(repo_root / ".ansible" / "shards" / "run-456" / "leaf-alpha-production.json"),
            "--limit",
            "alpha",
            str(repo_root / "playbooks" / "leaf-alpha.yml"),
            "-e",
            "env=production",
            "--private-key",
            "/tmp/test.id_ed25519",
        ]
    ]


def test_real_repo_scope_resolution_for_live_apply_paths() -> None:
    api_scope = scopes.resolve_playbook_scope(
        "playbooks/services/api-gateway.yml",
        repo_root=REPO_ROOT,
        catalog_path=REPO_ROOT / "config" / "ansible-execution-scopes.yaml",
    )
    plausible_scope = scopes.resolve_playbook_scope(
        "playbooks/services/plausible.yml",
        repo_root=REPO_ROOT,
        catalog_path=REPO_ROOT / "config" / "ansible-execution-scopes.yaml",
    )
    monitoring_scope = scopes.resolve_playbook_scope(
        "playbooks/monitoring-stack.yml",
        repo_root=REPO_ROOT,
        catalog_path=REPO_ROOT / "config" / "ansible-execution-scopes.yaml",
    )

    assert api_scope.mutation_scope == "lane"
    assert api_scope.target_lane == "lane:runtime-control"
    assert api_scope.source_leaf_playbooks == ("playbooks/api-gateway.yml",)
    assert plausible_scope.mutation_scope == "platform"
    assert plausible_scope.source_leaf_playbooks == ("playbooks/plausible.yml",)
    assert monitoring_scope.mutation_scope == "platform"
    assert "playbooks/services/grafana.yml" in monitoring_scope.source_leaf_playbooks
