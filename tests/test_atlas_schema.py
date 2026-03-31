from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from contextlib import contextmanager


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "atlas_schema.py"


def load_module():
    spec = importlib.util.spec_from_file_location("atlas_schema", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_catalog_accepts_repo_catalog() -> None:
    atlas_schema = load_module()
    catalog_path = REPO_ROOT / "config" / "atlas" / "catalog.json"

    catalog = atlas_schema.load_catalog(catalog_path)
    atlas_schema.validate_catalog(catalog, repo_root=REPO_ROOT)

    assert catalog["schema_version"] == "1.0.0"
    assert len(catalog["databases"]) >= 20
    assert catalog["openbao"]["database_role"] == "postgres-atlas-readonly"


def test_select_lint_targets_skips_when_changed_files_are_unrelated() -> None:
    atlas_schema = load_module()
    catalog = atlas_schema.load_catalog(REPO_ROOT / "config" / "atlas" / "catalog.json")

    selected = atlas_schema.select_lint_targets(
        catalog,
        changed_files=("docs/runbooks/configure-openbao.md",),
        explicit_target_ids=(),
    )

    assert selected == []


def test_select_lint_targets_includes_migration_changes() -> None:
    atlas_schema = load_module()
    catalog = atlas_schema.load_catalog(REPO_ROOT / "config" / "atlas" / "catalog.json")

    selected = atlas_schema.select_lint_targets(
        catalog,
        changed_files=("migrations/0017_serverclaw_memory_schema.sql",),
        explicit_target_ids=(),
    )

    assert [target["id"] for target in selected] == ["platform-control-plane"]


def test_parse_changed_files_reads_validation_environment(monkeypatch) -> None:
    atlas_schema = load_module()
    monkeypatch.setenv(
        "LV3_VALIDATION_CHANGED_FILES_JSON",
        json.dumps(["migrations/0010_world_state_schema.sql", "config/atlas/catalog.json"]),
    )

    assert atlas_schema.parse_changed_files() == (
        "migrations/0010_world_state_schema.sql",
        "config/atlas/catalog.json",
    )


def test_diff_preview_is_bounded() -> None:
    atlas_schema = load_module()
    left = "\n".join(f"left-{index}" for index in range(260))
    right = "\n".join(f"right-{index}" for index in range(260))

    preview = atlas_schema.diff_preview(left, right, label="windmill")

    assert preview[0].startswith("--- windmill-snapshot")
    assert preview[-1] == "... diff truncated ..."
    assert len(preview) == 201


def test_validate_catalog_allows_bootstrap_snapshot_creation(tmp_path: Path) -> None:
    atlas_schema = load_module()
    (tmp_path / "migrations").mkdir()
    catalog = {
        "schema_version": "1.0.0",
        "atlas_image_ref": "docker.io/arigaio/atlas:test",
        "dev_postgres_image": "docker.io/library/postgres:16",
        "runtime": {
            "openbao_guest": "docker-runtime-lv3",
            "openbao_url": "http://127.0.0.1:8201",
            "postgres_guest": "postgres-lv3",
            "postgres_port": 5432,
        },
        "openbao": {
            "approle_secret_id": "openbao_atlas_approle",
            "database_role": "postgres-atlas-readonly",
        },
        "notifications": {
            "nats_subject": "platform.db.schema_drift",
            "ntfy": {
                "url": "http://10.10.10.20:2586/platform.db.warn",
                "username": "alertmanager",
                "password_secret_id": "ntfy_alertmanager_password",
            },
        },
        "receipts": {
            "drift_dir": "receipts/atlas-drift",
        },
        "lint_targets": [
            {
                "id": "platform-control-plane",
                "path": "migrations",
                "latest": 1,
                "triggers": ["migrations/"],
                "dev_database": "atlas_lint",
            }
        ],
        "databases": [
            {
                "id": "windmill",
                "database": "windmill",
                "snapshot_path": "config/atlas/windmill.hcl",
            }
        ],
    }

    atlas_schema.validate_catalog(catalog, repo_root=tmp_path, require_snapshot_files=False)


def test_normalize_global_option_order_moves_repo_flags_before_subcommand() -> None:
    atlas_schema = load_module()

    normalized = atlas_schema.normalize_global_option_order(
        [
            "drift",
            "--repo-root",
            "/srv/proxmox_florin_server",
            "--format",
            "json",
            "--write-receipts",
            "--publish-nats",
        ]
    )

    assert normalized == [
        "--repo-root",
        "/srv/proxmox_florin_server",
        "--format",
        "json",
        "drift",
        "--write-receipts",
        "--publish-nats",
    ]


def test_main_accepts_repo_flags_after_the_subcommand(capsys) -> None:
    atlas_schema = load_module()

    exit_code = atlas_schema.main(
        [
            "validate",
            "--repo-root",
            str(REPO_ROOT),
            "--catalog",
            str(REPO_ROOT / "config" / "atlas" / "catalog.json"),
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"status": "ok"' in captured.out


def test_inspect_live_schema_uses_default_community_compatible_output(monkeypatch) -> None:
    atlas_schema = load_module()
    captured: dict[str, object] = {}

    def fake_run_atlas(client, *, image_ref, command, host_repo_root=None):
        captured["image_ref"] = image_ref
        captured["command"] = command
        return "table \"users\" {}\n"

    monkeypatch.setattr(atlas_schema, "run_atlas", fake_run_atlas)

    result = atlas_schema.inspect_live_schema(
        object(),
        atlas_image_ref="docker.io/arigaio/atlas:test",
        database_url="postgres://example",
    )

    assert result == "table \"users\" {}\n"
    assert captured["image_ref"] == "docker.io/arigaio/atlas:test"
    assert captured["command"] == [
        "schema",
        "inspect",
        "--url",
        "postgres://example",
    ]


def test_lint_scope_args_defaults_to_latest_one() -> None:
    atlas_schema = load_module()

    assert atlas_schema.lint_scope_args({}) == ["--latest", "1"]


def test_lint_target_passes_latest_scope_to_atlas(monkeypatch) -> None:
    atlas_schema = load_module()
    commands: list[list[str]] = []

    class FakeDevPostgres:
        def __enter__(self):
            return {
                "host": "host.docker.internal",
                "port": 57004,
                "database": "atlas_lint",
                "username": "postgres",
                "password": "postgres",
            }

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_dev_postgres(client, image_ref, database_name):
        assert database_name == "atlas_lint"
        return FakeDevPostgres()

    def fake_run_atlas(client, *, image_ref, command, host_repo_root=None):
        commands.append(command)
        return ""

    monkeypatch.setattr(atlas_schema, "dev_postgres", fake_dev_postgres)
    monkeypatch.setattr(atlas_schema, "run_atlas", fake_run_atlas)

    result = atlas_schema.lint_target(
        object(),
        atlas_image_ref="docker.io/arigaio/atlas:test",
        dev_postgres_image="docker.io/library/postgres:16",
        host_repo_root=REPO_ROOT,
        target={
            "id": "platform-control-plane",
            "path": "migrations",
            "dev_database": "atlas_lint",
            "latest": 1,
        },
    )

    assert result == {
        "target_id": "platform-control-plane",
        "path": "migrations",
        "status": "passed",
    }
    assert commands == [
        [
            "migrate",
            "lint",
            "--dir",
            "file:///workspace/migrations",
            "--dev-url",
            "postgres://postgres:postgres@host.docker.internal:57004/atlas_lint?sslmode=disable",
            "--latest",
            "1",
        ]
    ]


def test_replace_loopback_host_rewrites_local_openbao_url_to_guest_ip() -> None:
    atlas_schema = load_module()

    assert (
        atlas_schema.replace_loopback_host("http://127.0.0.1:8201", "10.10.10.20")
        == "http://10.10.10.20:8201"
    )
    assert (
        atlas_schema.replace_loopback_host("http://localhost:8201/v1/sys/health", "10.10.10.20")
        == "http://10.10.10.20:8201/v1/sys/health"
    )
    assert (
        atlas_schema.replace_loopback_host("https://10.10.10.20:8200", "10.10.10.20")
        == "https://10.10.10.20:8200"
    )


def test_resolve_openbao_url_prefers_direct_guest_ip_before_ssh_tunnel(monkeypatch) -> None:
    atlas_schema = load_module()
    checked_urls: list[str] = []

    def fake_http_reachable(url: str, *, timeout_seconds: float = 2.0) -> bool:
        checked_urls.append(url)
        return url == "http://10.10.10.20:8201"

    @contextmanager
    def fake_guest_tunnel(context, guest_name, *, remote_bind):
        raise AssertionError("guest_tunnel should not be used when the guest IP is directly reachable")
        yield 0

    monkeypatch.setattr(atlas_schema, "http_reachable", fake_http_reachable)
    monkeypatch.setattr(atlas_schema, "guest_tunnel", fake_guest_tunnel)

    catalog = {
        "runtime": {
            "openbao_guest": "docker-runtime-lv3",
            "openbao_url": "http://127.0.0.1:8201",
        }
    }
    context = {"guests": {"docker-runtime-lv3": "10.10.10.20"}}

    with atlas_schema.resolve_openbao_url(catalog, context) as resolved_url:
        assert resolved_url == "http://10.10.10.20:8201"

    assert checked_urls == [
        "http://127.0.0.1:8201",
        "http://10.10.10.20:8201",
    ]


def test_dev_postgres_force_removes_ephemeral_container_on_cleanup(monkeypatch) -> None:
    atlas_schema = load_module()
    removed: list[tuple[list[str], float]] = []

    class FakeExecResult:
        exit_code = 0
        output = b"ready"

    class FakeContainer:
        def exec_run(self, argv):
            assert argv == ["pg_isready", "-U", "postgres", "-d", "atlas_lint"]
            return FakeExecResult()

    class FakeClient:
        class containers:
            @staticmethod
            def run(*args, **kwargs):
                return FakeContainer()

    monkeypatch.setattr(atlas_schema, "ensure_image", lambda client, image_ref: None)
    monkeypatch.setattr(atlas_schema, "reserve_local_port", lambda: 55432)

    def fake_subprocess_run(argv, *, check, stdout, stderr, timeout):
        removed.append((list(argv), timeout))
        return None

    monkeypatch.setattr(atlas_schema.subprocess, "run", fake_subprocess_run)

    with atlas_schema.dev_postgres(FakeClient(), "docker.io/library/postgres:16", "atlas_lint") as database:
        assert database["host"] == "host.docker.internal"
        assert database["port"] == 55432

    assert len(removed) == 1
    assert removed[0][0][:3] == ["docker", "rm", "-f"]
    assert removed[0][0][3].startswith("atlas-lint-")
    assert removed[0][0][3].endswith("-55432")
    assert removed[0][1] == 10.0
