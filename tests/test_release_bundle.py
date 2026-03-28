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
