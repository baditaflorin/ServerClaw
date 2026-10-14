from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from scripts import neko_tool


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generic_neko_assignment_uses_operator_identity_variable() -> None:
    config = yaml.safe_load((REPO_ROOT / "inventory/group_vars/all/neko.yml").read_text())

    assert config["neko_instances"] == {
        "operator": {
            "email": "{{ platform_operator_email }}",
            "port": 8080,
            "udp_range": "50000-50999",
        }
    }
    assert config["neko_allow_empty_instances"] is False


def test_neko_authentik_sync_defaults_follow_the_selected_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    identity = tmp_path / "identity.yml"
    identity.write_text("platform_domain: example.org\n", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_IDENTITY_OVERLAY", str(identity))
    monkeypatch.delenv("PLATFORM_CONFIG_PREFIX", raising=False)
    monkeypatch.delenv("LV3_AUTHENTIK_URL", raising=False)

    args = neko_tool.build_parser().parse_args(["sync-from-authentik", "--dry-run"])

    assert args.authentik_url == "https://id.example.org"
    assert args.group == "0mcp-platform-admins"


def test_neko_make_target_uses_overlay_derived_authentik_defaults() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("converge-neko:\n", 1)[1].split("\nconverge-paperless:", 1)[0]
    sync_line = next(line for line in target.splitlines() if "neko_tool.py" in line)

    assert "--json sync-from-authentik" in sync_line
    assert "--authentik-url" not in sync_line
    assert "--group" not in sync_line


def test_registry_does_not_replace_neko_instances_with_empty_default() -> None:
    registry = yaml.safe_load((REPO_ROOT / "inventory/group_vars/all/platform_services.yml").read_text())
    neko = registry["platform_service_registry"]["neko"]

    assert neko["extra_defaults"] == {"neko_multi_instance": True}
    assert "neko_instances" not in neko["extra_defaults"]


def test_neko_public_signalling_is_edge_only_and_monitoring_is_private() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory/host_vars/proxmox-host.yml").read_text())
    subdomains = json.loads((REPO_ROOT / "config/subdomain-catalog.json").read_text())
    neko_subdomain = next(entry for entry in subdomains["subdomains"] if entry["service_id"] == "neko")
    edge_role_defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml"
        ).read_text()
    )
    runtime_comms = host_vars["network_policy"]["guests"]["runtime-comms"]["allowed_inbound"]
    monitoring_probe = next(
        rule
        for rule in runtime_comms
        if rule.get("source") == "monitoring" and rule.get("description", "").startswith("Private Neko readiness")
    )
    udp_forward = next(rule for rule in host_vars["proxmox_public_ingress_udp_forwards"] if "listen_port_range" in rule)

    assert neko_subdomain["auth_requirement"] == "edge_oidc"
    assert "browser.{{ platform_domain }}" in edge_role_defaults["public_edge_authenticated_sites"]
    assert 8080 not in host_vars["proxmox_public_ingress_tcp_ports"]
    assert all(rule.get("listen_port") != 8080 for rule in host_vars["proxmox_public_ingress_tcp_forwards"])
    assert "runtime-comms" in udp_forward["target_host"]
    assert monitoring_probe["protocol"] == "tcp"
    assert monitoring_probe["ports"] == [8080]


def test_empty_teardown_opt_in_is_read_from_overlay_and_must_be_boolean(tmp_path: Path) -> None:
    overlay = tmp_path / "neko.yml"
    overlay.write_text("neko_allow_empty_instances: true\n", encoding="utf-8")

    assert neko_tool._overlay_allows_empty(overlay) is True

    overlay.write_text("neko_allow_empty_instances: 'true'\n", encoding="utf-8")
    try:
        neko_tool._overlay_allows_empty(overlay)
    except ValueError as exc:
        assert "must be a YAML boolean" in str(exc)
    else:
        raise AssertionError("string values must not authorize destructive teardown")


def test_all_neko_plays_guard_against_accidental_empty_reconciliation() -> None:
    playbook = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/playbooks/neko.yml").read_text()
    )
    assert len(playbook) == 4
    for index, play in enumerate(playbook):
        assert play["any_errors_fatal"] is True
        assert any(
            task.get("ansible.builtin.import_tasks") == "_includes/neko_input_guard.yml"
            for task in play.get("pre_tasks", [])
        )
        assert ("neko-edge-publication" in play.get("tags", [])) is (index == 2)

    guard = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/playbooks/_includes/neko_input_guard.yml"
    ).read_text()
    assert "(neko_instances | length > 0) or (neko_allow_empty_instances | default(false) | bool)" in guard

    nginx_template = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/playbooks/templates/nginx-site-neko.conf.j2"
    ).read_text()
    assert "# managed-by: role=neko_runtime adr=0380" in nginx_template
    assert "selected deployment's private <code>neko.yml</code> overlay" in nginx_template


def test_makefile_neko_wrapper_guards_inputs_and_has_an_isolated_route_tag() -> None:
    playbook = yaml.safe_load((REPO_ROOT / "playbooks/neko.yml").read_text())
    runtime_play, edge_play = playbook[1:]

    assert runtime_play["any_errors_fatal"] is True
    assert edge_play["any_errors_fatal"] is True
    for play in (runtime_play, edge_play):
        assert any(
            task.get("ansible.builtin.import_tasks")
            == "../collections/ansible_collections/lv3/platform/playbooks/_includes/neko_input_guard.yml"
            for task in play.get("pre_tasks", [])
        )

    assert "neko-edge-publication" not in runtime_play["tags"]
    edge_preflight = next(
        task for task in edge_play["pre_tasks"] if task.get("ansible.builtin.import_tasks") == "tasks/preflight.yml"
    )
    assert "neko-edge-publication" in edge_preflight["tags"]

    route_tasks = [task for task in edge_play["post_tasks"] if "neko-edge-publication" in task.get("tags", [])]
    assert [task["name"] for task in route_tasks] == [
        "Deploy browser.{{ platform_domain }} nginx site (Neko multi-instance email router)",
        "Enable browser.{{ platform_domain }} site",
        "Validate NGINX configuration before reloading",
        "Reload nginx to apply browser.{{ platform_domain }} site",
    ]
    assert route_tasks[-1]["when"] == "neko_nginx_site.changed"


def test_neko_tool_refuses_to_write_user_assignments_into_tracked_inventory() -> None:
    tracked_config = REPO_ROOT / "inventory/group_vars/all/neko.yml"
    before = tracked_config.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/neko_tool.py"),
            "--instances-file",
            str(tracked_config),
            "add",
            "test-user",
            "--email",
            "test-user@example.com",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Refusing to write Neko user assignments outside the private .local overlay" in result.stderr
    assert tracked_config.read_bytes() == before

    relative_result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/neko_tool.py"),
            "--instances-file",
            "inventory/group_vars/all/neko.yml",
            "add",
            "test-user",
            "--email",
            "test-user@example.com",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert relative_result.returncode != 0
    assert "Refusing to write Neko user assignments outside the private .local overlay" in relative_result.stderr
    assert tracked_config.read_bytes() == before
