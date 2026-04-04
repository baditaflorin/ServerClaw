from __future__ import annotations

import importlib.util
import io
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


def test_normalize_snapshot_strips_trailing_whitespace_per_line() -> None:
    atlas_schema = load_module()

    normalized = atlas_schema.normalize_snapshot("line one  \nline two\t \n\n")

    assert normalized == "line one\nline two\n"


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


def test_validate_catalog_rejects_unknown_nats_subject(tmp_path: Path, monkeypatch) -> None:
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
            "nats_subject": "platform.db.missing",
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

    monkeypatch.setattr(atlas_schema, "load_topic_index", lambda: {})

    try:
        atlas_schema.validate_catalog(catalog, repo_root=tmp_path, require_snapshot_files=False)
    except ValueError as exc:
        assert "references unknown NATS topic" in str(exc)
    else:
        raise AssertionError("validate_catalog should reject unknown Atlas NATS subjects")


def test_validate_catalog_rejects_incompatible_nats_payload_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
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

    monkeypatch.setattr(
        atlas_schema,
        "load_topic_index",
        lambda: {
            "platform.db.schema_drift": {
                "status": "active",
                "payload_required": [
                    "database_id",
                    "database",
                    "severity",
                    "snapshot_path",
                    "snapshot_sha256",
                    "live_sha256",
                    "extra_required_key",
                ],
            }
        },
    )

    try:
        atlas_schema.validate_catalog(catalog, repo_root=tmp_path, require_snapshot_files=False)
    except ValueError as exc:
        assert "requires unsupported payload keys" in str(exc)
        assert "extra_required_key" in str(exc)
    else:
        raise AssertionError("validate_catalog should reject incompatible NATS payload contracts")


def test_run_drift_does_not_create_receipt_dir_when_schema_is_clean(monkeypatch, tmp_path: Path) -> None:
    atlas_schema = load_module()
    repo_root = tmp_path / "repo"
    snapshot_path = repo_root / "config" / "atlas" / "windmill.hcl"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text('table "users" {}\n', encoding="utf-8")
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
    receipt_dir = repo_root / "receipts" / "atlas-drift"
    original_mkdir = Path.mkdir

    @contextmanager
    def fake_openbao_url(_catalog, _context):
        yield "http://10.10.10.20:8201"

    @contextmanager
    def fake_postgres_endpoint(_catalog, _context):
        yield "10.10.10.50", 5432

    def guarded_mkdir(self, *args, **kwargs):
        if self == receipt_dir:
            raise AssertionError("clean drift runs should not create the receipt directory")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(atlas_schema, "load_catalog", lambda _path: catalog)
    monkeypatch.setattr(atlas_schema, "validate_catalog", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(atlas_schema, "load_docker_sdk", lambda: type("Docker", (), {"from_env": staticmethod(lambda: object())}))
    monkeypatch.setattr(atlas_schema, "load_controller_context", lambda: {"guests": {}})
    monkeypatch.setattr(atlas_schema, "resolve_openbao_url", fake_openbao_url)
    monkeypatch.setattr(atlas_schema, "resolve_postgres_endpoint", fake_postgres_endpoint)
    monkeypatch.setattr(atlas_schema, "openbao_login", lambda *_args, **_kwargs: "token")
    monkeypatch.setattr(
        atlas_schema,
        "request_dynamic_credentials",
        lambda *_args, **_kwargs: {"username": "atlas", "password": "secret"},
    )
    monkeypatch.setattr(
        atlas_schema,
        "inspect_live_schema",
        lambda *_args, **_kwargs: 'table "users" {}\n',
    )
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)

    exit_code, payload = atlas_schema.run_drift(
        repo_root=repo_root,
        catalog_path=repo_root / "config" / "atlas" / "catalog.json",
        write_receipts=True,
        publish_nats=True,
        publish_ntfy=True,
    )

    assert exit_code == 0
    assert payload["status"] == "clean"
    assert payload["receipt_paths"] == []
    assert payload["receipt_errors"] == []


def test_openbao_login_prefers_runtime_env_approle_json(monkeypatch) -> None:
    atlas_schema = load_module()
    captured: dict[str, object] = {}
    recovered: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"auth": {"client_token": "env-token"}}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv(
        "LV3_ATLAS_OPENBAO_APPROLE_JSON",
        json.dumps({"role_id": "role-from-env", "secret_id": "secret-from-env"}),
    )
    monkeypatch.setattr(
        atlas_schema,
        "ensure_openbao_unsealed",
        lambda _context, base_url: recovered.append(base_url),
    )
    monkeypatch.setattr(
        atlas_schema,
        "controller_secret_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file lookup should not run")),
    )
    monkeypatch.setattr(atlas_schema.urllib.request, "urlopen", fake_urlopen)

    token = atlas_schema.openbao_login(
        {"secret_manifest": {}},
        "http://127.0.0.1:8201",
        {"openbao": {"approle_secret_id": "openbao_atlas_approle"}},
    )

    assert token == "env-token"
    assert recovered == ["http://127.0.0.1:8201"]
    assert captured["url"] == "http://127.0.0.1:8201/v1/auth/approle/login"
    assert captured["payload"] == {"role_id": "role-from-env", "secret_id": "secret-from-env"}
    assert captured["timeout"] == 10


def test_load_openbao_init_payload_prefers_runtime_env_json(monkeypatch) -> None:
    atlas_schema = load_module()
    monkeypatch.setenv(
        "LV3_ATLAS_OPENBAO_INIT_JSON",
        json.dumps({"keys_base64": ["key-one"], "root_token": "root-token"}),
    )
    monkeypatch.setattr(
        atlas_schema,
        "controller_secret_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file lookup should not run")),
    )

    payload = atlas_schema.load_openbao_init_payload({"secret_manifest": {}})

    assert payload == {"keys_base64": ["key-one"], "root_token": "root-token"}


def test_load_openbao_init_payload_accepts_runtime_openbao_init_json(monkeypatch) -> None:
    atlas_schema = load_module()
    monkeypatch.delenv("LV3_ATLAS_OPENBAO_INIT_JSON", raising=False)
    monkeypatch.setenv(
        "OPENBAO_INIT_JSON",
        json.dumps({"keys_base64": ["key-one"], "root_token": "root-token"}),
    )
    monkeypatch.setattr(
        atlas_schema,
        "controller_secret_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file lookup should not run")),
    )

    payload = atlas_schema.load_openbao_init_payload({"secret_manifest": {}})

    assert payload == {"keys_base64": ["key-one"], "root_token": "root-token"}


def test_ensure_openbao_unsealed_uses_managed_init_payload_when_health_reports_sealed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    atlas_schema = load_module()
    unseal_keys: list[str] = []
    health_calls = 0

    init_payload_path = tmp_path / "openbao-init.json"
    init_payload_path.write_text(
        json.dumps({"keys_base64": ["key-one", "key-two", "key-three"]}),
        encoding="utf-8",
    )

    class FakeResponse:
        def __init__(self, payload: dict[str, object], *, status: int = 200) -> None:
            self._payload = payload
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        nonlocal health_calls
        if request.full_url.endswith("/v1/sys/health"):
            health_calls += 1
            payload = {"initialized": True, "sealed": health_calls == 1, "standby": False}
            if health_calls == 1:
                raise atlas_schema.urllib.error.HTTPError(
                    request.full_url,
                    503,
                    "sealed",
                    hdrs=None,
                    fp=io.BytesIO(json.dumps(payload).encode("utf-8")),
                )
            return FakeResponse(payload)
        if request.full_url.endswith("/v1/sys/unseal"):
            key = json.loads(request.data.decode("utf-8"))["key"]
            unseal_keys.append(key)
            return FakeResponse({"sealed": key != "key-two"})
        raise AssertionError(f"unexpected url {request.full_url}")

    monkeypatch.setattr(
        atlas_schema,
        "controller_secret_path",
        lambda _context, secret_id: init_payload_path
        if secret_id == "openbao_init_payload"
        else (_ for _ in ()).throw(AssertionError(f"unexpected secret id {secret_id}")),
    )
    monkeypatch.setattr(atlas_schema.urllib.request, "urlopen", fake_urlopen)

    atlas_schema.ensure_openbao_unsealed({"secret_manifest": {}}, "http://10.10.10.20:8201")

    assert unseal_keys == ["key-one", "key-two"]
    assert health_calls == 2


def test_maybe_publish_ntfy_prefers_runtime_env_password(monkeypatch) -> None:
    atlas_schema = load_module()
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["title"] = request.get_header("Title")
        captured["payload"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("LV3_NTFY_ALERTMANAGER_PASSWORD", "runtime-secret")
    monkeypatch.setattr(
        atlas_schema,
        "controller_secret_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file lookup should not run")),
    )
    monkeypatch.setattr(atlas_schema.urllib.request, "urlopen", fake_urlopen)

    payload = atlas_schema.maybe_publish_ntfy(
        catalog={
            "notifications": {
                "ntfy": {
                    "url": "http://10.10.10.20:2586/platform.db.warn",
                    "username": "alertmanager",
                    "password_secret_id": "ntfy_alertmanager_password",
                }
            }
        },
        context={"secret_manifest": {}},
        drifted_ids=["windmill"],
    )

    assert payload == {"published": True, "count": 1}
    assert captured["authorization"] == "Basic YWxlcnRtYW5hZ2VyOnJ1bnRpbWUtc2VjcmV0"
    assert captured["title"] == "Atlas drift detected"
    assert captured["payload"] == "Atlas drift detected for database snapshots: windmill"
    assert captured["timeout"] == 10


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


def test_run_atlas_falls_back_to_exception_class_names_when_docker_errors_is_missing(
    monkeypatch,
) -> None:
    atlas_schema = load_module()

    class ContainerError(Exception):
        def __init__(self, message: str, *, stderr: bytes | None = None) -> None:
            super().__init__(message)
            self.stderr = stderr

    class FakeContainers:
        @staticmethod
        def run(*args, **kwargs):
            raise ContainerError("atlas failed", stderr=b"dial tcp 10.200.1.1:57004: connect: connection refused")

    class FakeClient:
        containers = FakeContainers()

    monkeypatch.setattr(atlas_schema, "load_docker_sdk", lambda: object())
    monkeypatch.setattr(atlas_schema, "ensure_image", lambda client, image_ref: None)

    try:
        atlas_schema.run_atlas(
            FakeClient(),
            image_ref="docker.io/arigaio/atlas:test",
            command=["migrate", "lint"],
        )
    except RuntimeError as exc:
        assert "Atlas command failed" in str(exc)
        assert "connection refused" in str(exc)
    else:
        raise AssertionError("run_atlas should surface ContainerError failures even without docker.errors")


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


def test_resolve_openbao_url_can_force_direct_guest_ip_without_reachability_probe(monkeypatch) -> None:
    atlas_schema = load_module()
    checked_urls: list[str] = []

    def fake_http_reachable(url: str, *, timeout_seconds: float = 2.0) -> bool:
        checked_urls.append(url)
        return False

    @contextmanager
    def fake_guest_tunnel(context, guest_name, *, remote_bind):
        raise AssertionError("guest_tunnel should not be used when direct endpoints are forced")
        yield 0

    monkeypatch.setenv("LV3_ATLAS_FORCE_DIRECT_ENDPOINTS", "1")
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

    assert checked_urls == ["http://127.0.0.1:8201"]


def test_resolve_postgres_endpoint_can_force_direct_guest_ip_without_reachability_probe(monkeypatch) -> None:
    atlas_schema = load_module()

    def fake_host_reachable(host: str, port: int, *, timeout_seconds: float = 1.0) -> bool:
        raise AssertionError("host_reachable should not be used when direct endpoints are forced")

    @contextmanager
    def fake_guest_tunnel(context, guest_name, *, remote_bind):
        raise AssertionError("guest_tunnel should not be used when direct endpoints are forced")
        yield 0

    monkeypatch.setenv("LV3_ATLAS_FORCE_DIRECT_ENDPOINTS", "1")
    monkeypatch.setattr(atlas_schema, "host_reachable", fake_host_reachable)
    monkeypatch.setattr(atlas_schema, "guest_tunnel", fake_guest_tunnel)

    catalog = {
        "runtime": {
            "postgres_guest": "postgres-lv3",
            "postgres_port": 5432,
        }
    }
    context = {"guests": {"postgres-lv3": "10.10.10.50"}}

    with atlas_schema.resolve_postgres_endpoint(catalog, context) as (host, port):
        assert (host, port) == ("10.10.10.50", 5432)


def test_dev_postgres_force_removes_ephemeral_container_on_cleanup(monkeypatch) -> None:
    atlas_schema = load_module()
    removed: list[tuple[list[str], float]] = []
    captured_run_kwargs: dict[str, object] = {}

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
                captured_run_kwargs.update(kwargs)
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

    assert captured_run_kwargs["ports"] == {"5432/tcp": ("0.0.0.0", 55432)}
    assert len(removed) == 1
    assert removed[0][0][:3] == ["docker", "rm", "-f"]
    assert removed[0][0][3].startswith("atlas-lint-")
    assert removed[0][0][3].endswith("-55432")
    assert removed[0][1] == 10.0


def test_guest_tunnel_binds_on_all_interfaces_for_sibling_containers(monkeypatch) -> None:
    atlas_schema = load_module()
    captured: dict[str, object] = {}

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            captured["terminated"] = True

        def wait(self, timeout):
            captured["wait_timeout"] = timeout
            return 0

        def kill(self):
            raise AssertionError("guest_tunnel should not need to kill a healthy tunnel")

    def fake_build_guest_ssh_tunnel_command(context, guest_name, *, local_bind, remote_bind):
        captured["context"] = context
        captured["guest_name"] = guest_name
        captured["local_bind"] = local_bind
        captured["remote_bind"] = remote_bind
        return ["ssh", "-N"]

    def fake_popen(command, stdout, stderr, text):
        captured["popen_command"] = command
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["text"] = text
        return FakeProcess()

    def fake_wait_for_tunnel(process, port):
        captured["wait_port"] = port

    monkeypatch.setattr(atlas_schema, "reserve_local_port", lambda: 55432)
    monkeypatch.setattr(atlas_schema, "build_guest_ssh_tunnel_command", fake_build_guest_ssh_tunnel_command)
    monkeypatch.setattr(atlas_schema.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(atlas_schema, "wait_for_tunnel", fake_wait_for_tunnel)

    context = {"host_user": "ops", "host_addr": "100.64.0.1", "guests": {"postgres-lv3": "10.10.10.50"}}
    with atlas_schema.guest_tunnel(context, "postgres-lv3", remote_bind="127.0.0.1:5432") as local_port:
        assert local_port == 55432

    assert captured["guest_name"] == "postgres-lv3"
    assert captured["local_bind"] == "0.0.0.0:55432"
    assert captured["remote_bind"] == "127.0.0.1:5432"
    assert captured["wait_port"] == 55432
    assert captured["terminated"] is True
    assert captured["wait_timeout"] == 3
