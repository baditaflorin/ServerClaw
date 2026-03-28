from pathlib import Path

import yaml

from scripts.dify_smoke import maybe_langfuse_trace_config


def test_langfuse_trace_config_prefers_internal_service_url(tmp_path: Path) -> None:
    local_dir = tmp_path / ".local" / "langfuse"
    local_dir.mkdir(parents=True)
    (local_dir / "project-public-key.txt").write_text("public", encoding="utf-8")
    (local_dir / "project-secret-key.txt").write_text("secret", encoding="utf-8")

    platform_vars_path = tmp_path / "inventory" / "group_vars"
    platform_vars_path.mkdir(parents=True)
    (platform_vars_path / "platform.yml").write_text(
        yaml.safe_dump(
            {
                "platform_service_topology": {
                    "langfuse": {
                        "urls": {
                            "internal": "http://10.10.10.20:3002",
                            "public": "https://langfuse.lv3.org",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert maybe_langfuse_trace_config(tmp_path) == {
        "public_key": "public",
        "secret_key": "secret",
        "host": "http://10.10.10.20:3002",
    }
