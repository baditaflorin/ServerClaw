from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import service_id_resolver  # noqa: E402


def test_exists_in_catalog_for_declared_service() -> None:
    assert service_id_resolver.exists_in_catalog("grafana") is True


def test_exists_in_catalog_for_infrastructure_playbook() -> None:
    assert service_id_resolver.exists_in_catalog("guest-log-shipping") is False


def test_cli_resolve_returns_input_for_non_catalog_playbook() -> None:
    assert service_id_resolver.main(["--resolve", "guest-log-shipping"]) == 0


def test_cli_exists_in_catalog_exit_codes() -> None:
    assert service_id_resolver.main(["--exists-in-catalog", "grafana"]) == 0
    assert service_id_resolver.main(["--exists-in-catalog", "guest-log-shipping"]) == 1
