import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
