"""The CT trim exclusion is narrowly scoped and refuses ambiguous fstab state."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "config/0own/ct-names/exclude-weekly-trim.py"
spec = importlib.util.spec_from_file_location("ct_trim", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_exclusion_changes_only_ct_entry_and_is_idempotent():
    original = (
        "# managed fstab\nUUID=root / ext4 defaults 0 1\nUUID=abc /srv/ct-names ext4 defaults,noatime,nofail 0 2\n"
    )
    result = mod.updated_fstab(original, "/srv/ct-names", "abc")
    assert result == original.replace("defaults,noatime,nofail", "defaults,noatime,nofail,X-fstrim.notrim")
    assert mod.updated_fstab(result, "/srv/ct-names", "abc") == result
    with pytest.raises(ValueError):
        mod.updated_fstab(original, "/srv/ct-names", "wrong")
    with pytest.raises(ValueError):
        mod.updated_fstab(original + original.splitlines(keepends=True)[-1], "/srv/ct-names", "abc")
    with pytest.raises(ValueError):
        mod.updated_fstab(original.replace("/srv/ct-names", "/other"), "/srv/ct-names", "abc")
