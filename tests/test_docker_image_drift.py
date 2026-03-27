from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import docker_image_drift as drift  # noqa: E402


def test_collect_drift_detects_mismatched_digest(monkeypatch) -> None:
    monkeypatch.setattr(
        drift,
        "iter_runtime_images",
        lambda: [
            {
                "image_id": "windmill_runtime",
                "service_id": "windmill",
                "runtime_host": "docker-runtime-lv3",
                "container_name": "windmill-server",
                "expected_digest": "sha256:expected",
                "expected_reference": "ghcr.io/windmill/windmill:1@sha256:expected",
            }
        ],
    )
    monkeypatch.setattr(
        drift,
        "inspect_runtime_image",
        lambda context, runtime_host, container_name: {
            "repo_digests": ["ghcr.io/windmill/windmill@sha256:actual"],
            "running_reference": "ghcr.io/windmill/windmill:1@sha256:actual",
            "running_digest": "sha256:actual",
        },
    )

    records = drift.collect_drift(context={})

    assert len(records) == 1
    assert records[0]["severity"] == "warn"
    assert records[0]["service"] == "windmill"
    assert records[0]["running_digest"] == "sha256:actual"


def test_collect_drift_skips_matching_digest(monkeypatch) -> None:
    monkeypatch.setattr(
        drift,
        "iter_runtime_images",
        lambda: [
            {
                "image_id": "netbox_runtime",
                "service_id": "netbox",
                "runtime_host": "docker-runtime-lv3",
                "container_name": "netbox",
                "expected_digest": "sha256:expected",
                "expected_reference": "docker.io/netboxcommunity/netbox:main@sha256:expected",
            }
        ],
    )
    monkeypatch.setattr(
        drift,
        "inspect_runtime_image",
        lambda context, runtime_host, container_name: {
            "repo_digests": ["docker.io/netboxcommunity/netbox@sha256:expected"],
            "running_reference": "docker.io/netboxcommunity/netbox:main@sha256:expected",
            "running_digest": "sha256:expected",
        },
    )

    assert drift.collect_drift(context={}) == []
