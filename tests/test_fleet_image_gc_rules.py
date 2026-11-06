"""Keep the GC failure signal scoped and included in normal convergence."""
from pathlib import Path
import shutil
import subprocess
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class ImageGcRuleTests(unittest.TestCase):
    def test_scope_and_convergence(self):
        doc = yaml.safe_load((ROOT / "config/prometheus/rules/fleet-image-gc.yml").read_text())
        rule = doc["groups"][0]["rules"][0]
        self.assertEqual(rule["alert"], "FleetImageGcFailed")
        self.assertEqual(rule["for"], "3m")
        self.assertEqual(rule["labels"], {"severity": "warning", "service": "fleet_image_gc"})
        self.assertEqual(rule["expr"], 'max by (host, instance, name) (node_systemd_unit_state{name=~"fleet-image-gc-.+[.]service", state="failed"}) == 1')
        defaults = yaml.safe_load((ROOT / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/defaults/main.yml").read_text())
        self.assertIn("fleet-image-gc.yml", defaults["monitoring_prometheus_adopted_rule_files"])
        self.assertTrue((ROOT / rule["annotations"]["runbook_url"]).is_file())

    def test_timer_grace_absence_and_exact_name_join(self):
        rules = yaml.safe_load((ROOT / "config/prometheus/rules/fleet-image-gc.yml").read_text())["groups"][0]["rules"]
        stale = next(rule for rule in rules if rule["alert"] == "FleetImageGcTimerStale")
        self.assertEqual(stale["alert"], "FleetImageGcTimerStale")
        self.assertEqual(stale["for"], "10m")
        self.assertIn("fleet_image_gc_timer_expected_since_seconds", stale["expr"])
        self.assertIn("node_boot_time_seconds", stale["expr"])
        self.assertIn("unless on (host, instance, name)", stale["expr"])
        self.assertEqual(stale["expr"].count("3 * 3600"), 3)

    def test_runner_artifact_failure_is_a_single_failed_state_warning(self):
        rules = yaml.safe_load((ROOT / "config/prometheus/rules/fleet-image-gc.yml").read_text())["groups"][0]["rules"]
        rule = next(rule for rule in rules if rule["alert"] == "FleetRunnerArtifactGcFailed")
        self.assertEqual(rule["for"], "3m")
        self.assertEqual(rule["labels"], {"severity": "warning", "service": "fleet_runner_artifact_gc"})
        self.assertTrue((ROOT / rule["annotations"]["runbook_url"]).is_file())

    @unittest.skipUnless(shutil.which("promtool"), "promtool is not installed")
    def test_promtool(self):
        for args in (["check", "rules", "config/prometheus/rules/fleet-image-gc.yml"],
                     ["test", "rules", "tests/promtool/fleet_image_gc_rules_test.yml"]):
            result = subprocess.run(["promtool", *args], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
