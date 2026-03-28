import json
import subprocess
import tarfile
from pathlib import Path

import release_bundle


def test_determine_release_identity_marks_non_main_branches_as_prerelease() -> None:
    identity = release_bundle.determine_release_identity(
        ref_name="codex/ws-0233-live-apply",
        ref_type="branch",
        commit="1234567890abcdef1234567890abcdef12345678",
    )
    assert identity.prerelease is True
    assert identity.release_tag == "bundle-branch-codex-ws-0233-live-apply-1234567890ab"
    assert identity.asset_basename == "lv3-control-bundle-branch-codex-ws-0233-live-apply-1234567890ab"


def test_determine_release_identity_keeps_main_branch_stable() -> None:
    identity = release_bundle.determine_release_identity(
        ref_name="main",
        ref_type="branch",
        commit="fedcba0987654321fedcba0987654321fedcba09",
    )
    assert identity.prerelease is False
    assert identity.release_tag == "bundle-branch-main-fedcba098765"


def test_write_bundle_archive_embeds_manifest_and_selected_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(release_bundle, "REPO_ROOT", tmp_path)
    (tmp_path / "VERSION").write_text("0.177.37\n")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "gitea-release-bundle-cosign.pub").write_text("public-key\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "tool.py").write_text("print('ok')\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "example.json").write_text("{\"ok\": true}\n")
    files = [tmp_path / "scripts" / "tool.py", tmp_path / "config" / "example.json"]
    identity = release_bundle.determine_release_identity(
        ref_name="main",
        ref_type="branch",
        commit="0123456789abcdef0123456789abcdef01234567",
    )
    manifest = release_bundle.build_manifest(
        repository="ops/proxmox_florin_server",
        ref_name="main",
        ref_type="branch",
        commit="0123456789abcdef0123456789abcdef01234567",
        identity=identity,
        files=files,
        public_key_path=tmp_path / "keys" / "gitea-release-bundle-cosign.pub",
    )
    bundle_path = tmp_path / "build" / "bundle.tar.gz"
    release_bundle.write_bundle_archive(bundle_path, files=files, manifest=manifest)

    with tarfile.open(bundle_path, "r:gz") as archive:
        names = sorted(member.name for member in archive.getmembers())
        assert names == [
            "config/example.json",
            "release-bundle-manifest.json",
            "scripts/tool.py",
        ]
        manifest_payload = json.loads(archive.extractfile("release-bundle-manifest.json").read().decode("utf-8"))
    assert manifest_payload["contents"]["file_count"] == 2
    assert manifest_payload["bundle"]["verification_public_key"] == "keys/gitea-release-bundle-cosign.pub"
    assert manifest_payload["bundle"]["sigstore_bundle_asset"] == "lv3-control-bundle-branch-main-0123456789ab.tar.gz.sigstore.json"
    assert (
        manifest_payload["bundle"]["optional_detached_signature_asset"]
        == "lv3-control-bundle-branch-main-0123456789ab.tar.gz.sig"
    )


def test_resolve_tracked_bundle_files_respects_excludes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(release_bundle, "REPO_ROOT", tmp_path)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=tmp_path, check=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "keep.md").write_text("# keep\n")
    (tmp_path / ".local").mkdir()
    (tmp_path / ".local" / "ignore.txt").write_text("ignore\n")
    subprocess.run(["git", "add", "docs/keep.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    files = release_bundle.resolve_tracked_bundle_files(
        include_paths=["docs"],
        exclude_globs=[".local/**"],
    )
    assert [str(path.relative_to(tmp_path)).replace("\\", "/") for path in files] == ["docs/keep.md"]


def test_sign_bundle_writes_sigstore_bundle_argument(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "bundle.tar.gz"
    bundle_path.write_text("bundle")
    signature_path = tmp_path / "bundle.tar.gz.sig"
    sigstore_bundle_path = tmp_path / "bundle.tar.gz.sigstore.json"
    sigstore_bundle_path.write_text("{}")
    private_key_path = tmp_path / "cosign.key"
    private_key_path.write_text("key")
    password_file = tmp_path / "cosign.password"
    password_file.write_text("secret\n")

    monkeypatch.setattr(release_bundle, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release_bundle.shutil, "which", lambda path: path)

    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="signed-payload", stderr="")

    monkeypatch.setattr(release_bundle.subprocess, "run", fake_run)

    release_bundle.sign_bundle(
        bundle_path=bundle_path,
        signature_path=signature_path,
        sigstore_bundle_path=sigstore_bundle_path,
        private_key_path=private_key_path,
        password_file=password_file,
        cosign_path="cosign",
    )

    assert captured["command"] == [
        "cosign",
        "sign-blob",
        "--key",
        str(private_key_path),
        "--output-signature",
        str(signature_path),
        "--bundle",
        str(sigstore_bundle_path),
        "--tlog-upload=false",
        str(bundle_path),
    ]
    assert signature_path.read_text() == "signed-payload\n"


def test_verify_bundle_prefers_sigstore_bundle_when_present(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "bundle.tar.gz"
    bundle_path.write_text("bundle")
    public_key_path = tmp_path / "cosign.pub"
    public_key_path.write_text("pub")
    signature_path = tmp_path / "bundle.tar.gz.sig"
    signature_path.write_text("sig")
    sigstore_bundle_path = tmp_path / "bundle.tar.gz.sigstore.json"
    sigstore_bundle_path.write_text("{}")

    monkeypatch.setattr(release_bundle, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release_bundle.shutil, "which", lambda path: path)

    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(release_bundle.subprocess, "run", fake_run)

    release_bundle.verify_bundle(
        bundle_path=bundle_path,
        public_key_path=public_key_path,
        cosign_path="cosign",
        signature_path=signature_path,
        sigstore_bundle_path=sigstore_bundle_path,
    )

    assert captured["command"] == [
        "cosign",
        "verify-blob",
        "--key",
        str(public_key_path),
        "--bundle",
        str(sigstore_bundle_path),
        str(bundle_path),
    ]


def test_normalize_asset_url_reuses_explicit_gitea_host() -> None:
    asset_url = "http://git.lv3.org:3009/api/v1/repos/ops/proxmox_florin_server/releases/1/assets/2"
    normalized = release_bundle.normalize_asset_url(asset_url, gitea_url="http://100.64.0.1:3009")
    assert normalized == "http://100.64.0.1:3009/api/v1/repos/ops/proxmox_florin_server/releases/1/assets/2"


def test_download_asset_retries_transient_http_404(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "bundle.tar.gz"
    observed_calls: list[int] = []
    observed_sleeps: list[float] = []

    def fake_api_request(method: str, url: str, *, token: str, **_: object) -> tuple[int, bytes]:
        observed_calls.append(1)
        if len(observed_calls) < 3:
            raise RuntimeError(f"{method} {url} failed with HTTP 404: Not found")
        return 200, b"bundle-bytes"

    monkeypatch.setattr(release_bundle, "api_request", fake_api_request)
    monkeypatch.setattr(release_bundle.time, "sleep", lambda seconds: observed_sleeps.append(seconds))

    release_bundle.download_asset("http://example.test/bundle.tar.gz", token="token", destination=destination)

    assert destination.read_bytes() == b"bundle-bytes"
    assert len(observed_calls) == 3
    assert observed_sleeps == [1.0, 2.0]


def test_download_asset_candidates_falls_back_to_secondary_url(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "bundle.tar.gz"
    observed_urls: list[str] = []

    def fake_api_request(method: str, url: str, *, token: str, **_: object) -> tuple[int, bytes]:
        observed_urls.append(url)
        if url.endswith("/attachments/19"):
            raise RuntimeError(f"{method} {url} failed with HTTP 404: Not found")
        return 200, b"bundle-bytes"

    monkeypatch.setattr(release_bundle, "api_request", fake_api_request)
    monkeypatch.setattr(release_bundle.time, "sleep", lambda seconds: None)

    release_bundle.download_asset_candidates(
        [
            "http://10.10.10.20:3003/attachments/19",
            "http://10.10.10.20:3003/ops/proxmox_florin_server/releases/download/tag/bundle.tar.gz",
        ],
        token="token",
        destination=destination,
    )

    assert destination.read_bytes() == b"bundle-bytes"
    assert observed_urls == [
        "http://10.10.10.20:3003/attachments/19",
        "http://10.10.10.20:3003/ops/proxmox_florin_server/releases/download/tag/bundle.tar.gz",
    ]


def test_fetch_release_assets_prefers_attachment_detail_download_urls_with_release_download_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    release = {
        "id": 7,
        "assets": [
            {"id": 19, "name": "bundle.tar.gz", "browser_download_url": "http://git.lv3.org:3009/releases/download/bad"},
            {"id": 20, "name": "bundle.tar.gz.sigstore.json", "browser_download_url": "http://git.lv3.org:3009/releases/download/bad-sigstore"},
            {"id": 21, "name": "bundle.tar.gz.sha256", "browser_download_url": "http://git.lv3.org:3009/releases/download/bad-sha"},
        ],
    }
    downloaded_urls: list[str] = []

    monkeypatch.setattr(release_bundle, "fetch_release_by_tag", lambda *args, **kwargs: release)
    monkeypatch.setattr(
        release_bundle,
        "fetch_release_asset_detail",
        lambda **kwargs: {
            "browser_download_url": f"http://git.lv3.org:3009/attachments/{kwargs['attachment_id']}",
        },
    )

    def fake_download_asset_candidates(urls: list[str], *, token: str, destination: Path, **_: object) -> None:
        downloaded_urls.extend(urls)
        destination.write_text("payload")

    monkeypatch.setattr(release_bundle, "download_asset_candidates", fake_download_asset_candidates)

    release_bundle.fetch_release_assets_by_tag(
        gitea_url="http://10.10.10.20:3003",
        repository="ops/proxmox_florin_server",
        token="token",
        release_tag="bundle-branch-main-0123456789ab",
        destination_dir=tmp_path,
    )

    assert downloaded_urls == [
        "http://10.10.10.20:3003/attachments/19",
        "http://10.10.10.20:3003/releases/download/bad",
        "http://10.10.10.20:3003/attachments/21",
        "http://10.10.10.20:3003/releases/download/bad-sha",
        "http://10.10.10.20:3003/attachments/20",
        "http://10.10.10.20:3003/releases/download/bad-sigstore",
    ]
