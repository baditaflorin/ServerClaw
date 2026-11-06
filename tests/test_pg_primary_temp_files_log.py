"""VM701 (infer-pg-primary): temporary files of 64 MB or more are logged with their statement (ADR 0495, amendment of 2026-11-04).

Why: pg_stat_database counts 612 GB of temporary files (3,540 files, 177 MB on average) since 2026-10-31, pg_stat_statements attributes only 3.8 GB (a 5,000-entry table that evicts),
so the statements behind the spills are unknown. The file only logs; nothing shadows it (log_temp_files is -1 today and not in postgresql.auto.conf), so a plain apply works.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADR = REPO / "docs/adr/0495-pg-primary-memory-guardrails.md"
SHARD = REPO / "workstreams/active/ws-20261031-pg-primary-memory.yaml"

spec = importlib.util.spec_from_file_location("hostconf_pg_temp_files_log", REPO / "scripts/hostconf.py")
hostconf = importlib.util.module_from_spec(spec)
sys.modules["hostconf_pg_temp_files_log"] = hostconf
spec.loader.exec_module(hostconf)

HOST = "infer-pg-primary"
FID = "postgresql-temp-files-log.infer-pg-primary"


@pytest.fixture(scope="module")
def manifest():
    return hostconf.load_manifest()


def test_the_manifest_is_valid(manifest):
    assert hostconf.manifest_problems(manifest) == []


def test_the_temp_files_log_entry(manifest):
    f = manifest["files"][FID]
    assert f["dest"] == "/etc/postgresql/18/main/conf.d/98-temp-files-log.conf"
    assert f["src"] == "postgresql-temp-files-log.infer-pg-primary.conf"
    assert (f["mode"], f["group"]) == ("0640", "postgres")
    text = (hostconf.FILES_DIR / f["src"]).read_text()
    assert hostconf.parse_settings("pg_conf_d", text) == {"log_temp_files": "64MB"}
    assert f["expect"] == [{"pg_setting": "log_temp_files", "cluster": "18/main", "value": "64MB"}]
    assert 64 * 1024 == 65536, "SHOW prints 65536 kB as 64MB: the expectation string is what the server prints"


def test_only_the_primary_carries_it_and_nothing_else_sets_the_value(manifest):
    assert {fid for fid, h in manifest["hosts"].items() if FID in h.get("files", [])} == {HOST}
    for fid in manifest["hosts"][HOST]["files"]:
        if fid != FID:
            text = (hostconf.FILES_DIR / manifest["files"][fid]["src"]).read_text()
            assert not re.search(r"^\s*log_temp_files\b", text, re.M), f"{fid} would shadow or duplicate the setting"
    dests = [
        manifest["files"][i]["dest"]
        for i in manifest["hosts"][HOST]["files"]
        if "/conf.d/" in manifest["files"][i]["dest"]
    ]
    assert len(dests) == len(set(dests))


def test_the_numbers_of_the_reason_agree():
    assert round(612 * 1024 / 3540) == 177, "612 GB in 3,540 files is 177 MB on average"
    assert 3.8 < 612 * 0.01, "pg_stat_statements attributes under 1 % of the spilled bytes"
    assert round(612 / 104) == 6 and round(3540 / 104) == 34, (
        "612 GB and 3,540 files in the 104 h from 2026-10-31 01:25Z to 2026-11-04 09:42Z: about 6 GB and 34 files an hour on average"
    )
    assert round(1.9 * 1024 / 177) == 11, (
        "at the recent 1.9 GB an hour that is about 11 files an hour, 'about ten to a few tens' of lines"
    )


def test_purpose_header_and_adr_say_why_and_how_to_undo(manifest):
    f = manifest["files"][FID]
    purpose = " ".join(f["purpose"].split())
    header = (hostconf.FILES_DIR / f["src"]).read_text()
    adr = ADR.read_text().split("## Amendment 2026-11-04", 1)[1]
    for text in (purpose, header):
        for needle in ("612 GB", "3,540", "177 MB", "3.8 GB", "5,000", "2,000", "64 MB", "ADR 0495"):
            assert needle in text, needle
    for needle in ("612 GB", "3,540", "177 MB", "3.8 GB", "5,000", "2,000", "64 MB", "log_temp_files = 64MB"):
        assert needle in adr, needle
    assert "about 6 GB an hour since 2026-10-31" in header and "about 34 at the average" in header
    for text in (purpose, header):
        assert "not in postgresql.auto.conf" in text and "plain" in text and "Rollback" in text and "reload" in text
    for needle in (
        "planned, applied after the merge",
        "about 6 GB an hour since 2026-10-31",
        "about 34 at the average",
        "131088384",
        "12 MB spill",
        "per file",
        "`STATEMENT:`",
        "plain `python3 scripts/hostconf.py apply",
        "Rollback: remove the file",
        "pg_settings.source",
    ):
        assert needle in adr, needle


def test_the_adr_amendment_is_dated_and_the_change_is_recorded_only_there():
    text = ADR.read_text()
    assert len(re.findall(r"^## Amendment 2026-11-04: temporary files are logged", text, re.M)) == 1
    assert "log_temp_files" not in text.split("## Amendment 2026-11-04", 1)[0], (
        "the change is recorded only in its own amendment"
    )


def test_the_shard_owns_the_new_files():
    text = SHARD.read_text()
    for path in (
        "config/hostconf/files/postgresql-temp-files-log.infer-pg-primary.conf",
        "tests/test_pg_primary_temp_files_log.py",
    ):
        assert text.count(path) >= 2, f"{path} is a shared surface and an owned one"
    assert "log_temp_files" in text
