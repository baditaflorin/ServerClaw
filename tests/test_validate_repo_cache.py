from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_REPO_SCRIPT = REPO_ROOT / "scripts" / "validate_repo.sh"


def test_validate_repo_supports_shared_ansible_collection_cache() -> None:
    script = VALIDATE_REPO_SCRIPT.read_text()

    assert "LV3_ANSIBLE_COLLECTIONS_DIR" in script
    assert "LV3_ANSIBLE_COLLECTIONS_SHA_FILE" in script
    assert "sha256sum \"$requirements_file\"" in script
    assert "cmp -s" in script
