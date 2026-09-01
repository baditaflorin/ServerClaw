import json
import subprocess
import textwrap
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "platform-service-watchdog.yml"
GRAFANA_SHADOW_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "grafana-shadow-watchdog.yml"
WATCHDOG_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "platform_service_watchdog"
    / "templates"
    / "lv3-service-watchdog.sh.j2"
)
WATCHDOG_TASKS_PATH = WATCHDOG_TEMPLATE_PATH.parent.parent / "tasks" / "main.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


class PlatformServiceWatchdogRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = WATCHDOG_TEMPLATE_PATH.read_text()

    def test_successful_restart_resets_consecutive_failures(self) -> None:
        restart_block = self.template.split('if restart_service "${svc}"', maxsplit=1)[1]
        restart_block = restart_block.split("fi", maxsplit=1)[0]

        self.assertIn('increment_restart_count "${svc}"', restart_block)
        self.assertIn('set_failure_count "${svc}" 0', restart_block)

    def test_missing_compose_directory_never_triggers_restart(self) -> None:
        missing_directory_guard = self.template.split('if [[ ! -d "${compose_dir}" ]]', maxsplit=1)[1]
        missing_directory_guard = missing_directory_guard.split('restarts_this_hour=', maxsplit=1)[0]

        self.assertIn("refusing restart", missing_directory_guard)
        self.assertIn("return 0", missing_directory_guard)

    def test_excluded_recovery_precedes_any_driver_action(self) -> None:
        excluded_start = self.template.index("exclude_restart")
        driver_start = self.template.index("case ", excluded_start)
        excluded_block = self.template[excluded_start:driver_start]

        self.assertLess(excluded_start, driver_start)
        self.assertIn("auto-restart excluded", excluded_block)
        self.assertIn("return 0", excluded_block)
        self.assertNotIn("restart_service", excluded_block)
        self.assertNotIn("increment_restart_count", excluded_block)

    def test_shadow_mode_precedes_compose_validation_and_never_executes_a_recovery(self) -> None:
        shadow_start = self.template.index('if [[ "${recovery_mode}" == "shadow" ]]')
        compose_guard_start = self.template.index('if [[ ! -d "${compose_dir}" ]]')
        shadow_block = self.template[shadow_start:compose_guard_start]

        self.assertLess(shadow_start, compose_guard_start)
        self.assertIn('recovery_actions["${svc}"]="would_restart"', shadow_block)
        self.assertIn("SHADOW recovery", shadow_block)
        self.assertNotIn("restart_service", shadow_block)
        self.assertNotIn("increment_restart_count", shadow_block)
        self.assertNotIn("set_failure_count", shadow_block)
        self.assertNotIn("systemctl restart --", shadow_block)

    def test_systemd_recovery_is_explicitly_shadow_only(self) -> None:
        tasks = WATCHDOG_TASKS_PATH.read_text()

        self.assertIn("Validate systemd watchdog recovery settings", tasks)
        self.assertIn("item.systemd_unit is defined", tasks)
        self.assertIn("recovery_mode: shadow", tasks)
        self.assertIn("Validate systemd watchdog recovery units are loaded", tasks)
        self.assertIn("--property=LoadState", tasks)
        self.assertIn("check_mode: false", tasks)
        self.assertIn("service_watchdog_systemd_unit_state.rc != 0", tasks)
        self.assertIn("systemd enforcement is not implemented", self.template)
        self.assertNotIn("systemctl restart --", self.template)

    def test_systemd_shadow_handler_records_without_executing(self) -> None:
        harness = textwrap.dedent(
            """\
            set -euo pipefail
            failure_count=1
            restart_count=0
            restart_calls=0
            systemctl_calls=0
            notification_count=0
            FAILURE_THRESHOLD=2
            MAX_RESTARTS_PER_HOUR=6
            HOSTNAME=watchdog-test
            NTFY_TITLE=watchdog-test
            declare -A recovery_actions

            get_failure_count() { printf '%s\\n' "${failure_count}"; }
            set_failure_count() { failure_count="$2"; }
            get_restart_count_this_hour() { printf '%s\\n' "${restart_count}"; }
            increment_restart_count() { restart_count=$((restart_count + 1)); }
            log_info() { :; }
            log_warn() { :; }
            log_error() { :; }
            send_ntfy() { notification_count=$((notification_count + 1)); }
            restart_service() { restart_calls=$((restart_calls + 1)); return 1; }
            systemctl() { systemctl_calls=$((systemctl_calls + 1)); return 1; }

            source <(awk '/^handle_unhealthy\\(\\) \\{/{capture=1} capture {print} capture && /^}\\s*$/{exit}' "$1")
            handle_unhealthy grafana systemd shadow grafana-server.service '' '' '' false

            [[ "${failure_count}" == "2" ]]
            [[ "${restart_count}" == "0" ]]
            [[ "${restart_calls}" == "0" ]]
            [[ "${systemctl_calls}" == "0" ]]
            [[ "${notification_count}" == "1" ]]
            [[ "${recovery_actions[grafana]}" == "would_restart" ]]
            """
        )
        result = subprocess.run(
            ["bash", "-c", harness, "watchdog-shadow-harness", str(WATCHDOG_TEMPLATE_PATH)],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_grafana_uses_a_dedicated_systemd_shadow_recovery_lane(self) -> None:
        pilot_plays = yaml.safe_load(GRAFANA_SHADOW_PLAYBOOK_PATH.read_text())
        self.assertEqual(len(pilot_plays), 2)
        legacy_handoff, pilot = pilot_plays

        self.assertIn("monitoring-staging", legacy_handoff["hosts"])
        self.assertIn("monitoring-staging", pilot["hosts"])
        self.assertEqual(legacy_handoff["gather_facts"], True)
        self.assertEqual(pilot["gather_facts"], False)

        legacy_role = next(
            item for item in legacy_handoff["roles"] if item["role"].endswith("platform_service_watchdog")
        )
        self.assertEqual(legacy_role["vars"]["service_watchdog_name"], "monitoring")
        self.assertEqual(
            [service["name"] for service in legacy_role["vars"]["service_watchdog_services"]],
            ["alertmanager"],
        )
        self.assertTrue(legacy_role["vars"]["service_watchdog_services"][0]["exclude_from_auto_restart"])

        role = next(item for item in pilot["roles"] if item["role"].endswith("platform_service_watchdog"))
        services = role["vars"]["service_watchdog_services"]

        self.assertEqual([service["name"] for service in services], ["grafana"])
        grafana = services[0]
        self.assertEqual(grafana["name"], "grafana")
        self.assertEqual(grafana["recovery_mode"], "shadow")
        self.assertEqual(grafana["systemd_unit"], "grafana-server.service")
        self.assertNotIn("compose_dir", grafana)
        self.assertNotIn("compose_service", grafana)

        platform_plays = yaml.safe_load(WATCHDOG_PLAYBOOK_PATH.read_text())
        monitoring_play = next(play for play in platform_plays if play["name"].endswith("monitoring"))
        platform_role = next(item for item in monitoring_play["roles"] if item["role"].endswith("platform_service_watchdog"))
        self.assertIn("monitoring-staging", monitoring_play["hosts"])
        self.assertEqual(
            [service["name"] for service in platform_role["vars"]["service_watchdog_services"]],
            ["alertmanager"],
        )
        self.assertTrue(platform_role["vars"]["service_watchdog_services"][0]["exclude_from_auto_restart"])

        legacy_post_tasks = legacy_handoff["post_tasks"]
        legacy_flush = next(
            task for task in legacy_post_tasks if task["name"] == "Apply the legacy watchdog handoff before enabling Grafana shadow mode"
        )
        self.assertEqual(legacy_flush["ansible.builtin.meta"], "flush_handlers")
        self.assertEqual(legacy_flush["when"], "not ansible_check_mode")
        legacy_ownership_assertion = next(
            task
            for task in legacy_post_tasks
            if task["name"] == "Verify the legacy watchdog no longer contains a Grafana service block"
        )
        self.assertEqual(
            legacy_ownership_assertion["ansible.builtin.command"]["argv"][2],
            'svc_name="grafana"',
        )
        self.assertTrue(
            any(
                task["name"] == "Verify the legacy watchdog no longer contains a Grafana service block"
                and task["when"] == "not ansible_check_mode"
                for task in legacy_post_tasks
            )
        )

    def test_pilot_dry_run_keeps_only_read_only_health_preconditions(self) -> None:
        legacy_handoff, pilot = yaml.safe_load(GRAFANA_SHADOW_PLAYBOOK_PATH.read_text())

        legacy_timer_precondition = next(
            task
            for task in legacy_handoff["pre_tasks"]
            if task["name"] == "Verify the legacy monitoring watchdog timer is active before handoff"
        )
        self.assertEqual(legacy_timer_precondition["check_mode"], False)

        unit_precondition = next(
            task
            for task in legacy_handoff["pre_tasks"]
            if task["name"] == "Verify the native Grafana recovery unit is loaded before handoff"
        )
        self.assertEqual(unit_precondition["check_mode"], False)
        self.assertIn("--property=LoadState", unit_precondition["ansible.builtin.command"]["argv"])

        quiesce = next(
            task
            for task in legacy_handoff["pre_tasks"]
            if task["name"] == "Quiesce the legacy monitoring watchdog during the Grafana handoff"
        )
        self.assertEqual(quiesce["when"], "not ansible_check_mode")

        for play in (legacy_handoff, pilot):
            health_tasks = [
                task
                for task in play.get("pre_tasks", []) + play.get("post_tasks", [])
                if "ansible.builtin.uri" in task
            ]
            self.assertEqual(len(health_tasks), 1)
            self.assertEqual(health_tasks[0]["check_mode"], False)

        pilot_verify = next(task for task in pilot["post_tasks"] if task["name"] == "Verify Grafana shadow watchdog")
        self.assertEqual(pilot_verify["when"], "not ansible_check_mode")
        final_ownership = next(
            task for task in pilot["post_tasks"] if task["name"] == "Verify Grafana is owned only by the shadow watchdog"
        )
        self.assertEqual(final_ownership["when"], "not ansible_check_mode")

    def test_status_file_contains_recovery_receipts(self) -> None:
        self.assertIn('\\"recovery_driver\\"', self.template)
        self.assertIn('\\"recovery_mode\\"', self.template)
        self.assertIn('\\"systemd_unit\\"', self.template)
        self.assertIn('\\"recovery_action\\"', self.template)

    def test_pilot_has_one_canonical_scoped_converge_entrypoint(self) -> None:
        makefile = MAKEFILE_PATH.read_text()
        check_target = makefile.split("\ncheck-grafana-shadow-watchdog:", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
        apply_target = makefile.split("converge-grafana-shadow-watchdog:", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
        workflow = json.loads(WORKFLOW_CATALOG_PATH.read_text())["workflows"]["converge-grafana-shadow-watchdog"]
        command = json.loads(COMMAND_CATALOG_PATH.read_text())["commands"]["converge-grafana-shadow-watchdog"]
        scopes = yaml.safe_load(EXECUTION_SCOPES_PATH.read_text())["playbooks"]
        scope = scopes["playbooks/grafana-shadow-watchdog.yml"]

        self.assertIn("$(MAKE) preflight WORKFLOW=converge-grafana-shadow-watchdog", check_target)
        self.assertIn("$(MAKE) preflight WORKFLOW=converge-grafana-shadow-watchdog", apply_target)
        self.assertIn("--check --diff", check_target)
        self.assertIn("playbooks/grafana-shadow-watchdog.yml", check_target)
        self.assertIn("playbooks/grafana-shadow-watchdog.yml", apply_target)
        self.assertNotIn("$(EXTRA_ARGS)", check_target)
        self.assertNotIn("$(EXTRA_ARGS)", apply_target)
        self.assertEqual(workflow["preferred_entrypoint"]["target"], "converge-grafana-shadow-watchdog")
        self.assertEqual(workflow["target_lane"], "lane:monitoring")
        self.assertEqual(workflow["budget"]["max_restarts"], 0)
        self.assertEqual(command["workflow_id"], "converge-grafana-shadow-watchdog")
        self.assertEqual(scope["mutation_scope"], "lane")
        self.assertEqual(scope["target_lane"], "lane:monitoring")
        self.assertIn("roles/platform_service_watchdog", scope["shared_surfaces"])

    def test_woodpecker_probe_accepts_no_content_health_response(self) -> None:
        plays = yaml.safe_load(WATCHDOG_PLAYBOOK_PATH.read_text())
        docker_runtime_play = next(play for play in plays if play["name"].endswith("docker-runtime"))
        role = next(item for item in docker_runtime_play["roles"] if item["role"].endswith("platform_service_watchdog"))
        woodpecker = next(service for service in role["vars"]["service_watchdog_services"] if service["name"] == "woodpecker")

        self.assertEqual(woodpecker["expected_status"], "204")


if __name__ == "__main__":
    unittest.main()
