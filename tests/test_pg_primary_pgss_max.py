"""VM701 (infer-pg-primary): pg_stat_statements.max 5000 -> 20000 rides on the restart of the huge-pages window (ADR 0495, rider).

The setting is restart-only (a postmaster setting of a preloaded library): after a reload SHOW still says 5000 and hostconf.py apply would read 5000 back, put the file back and exit 5
(checked on a throwaway Postgres 17). So the window order seeds it with ALTER SYSTEM before the stop, applies the file after the start and resets the seed, like huge_pages.
Pinned here: the entry, the file, the host list, the arithmetic of its cost, and that the runbook keeps that order for BOTH settings and one fallback for both.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADR = REPO / "docs/adr/0495-pg-primary-memory-guardrails.md"
RUNBOOK = REPO / "docs/runbooks/host-local-config.md"
SHARD = REPO / "workstreams/active/ws-20261031-pg-primary-hugepages.yaml"

spec = importlib.util.spec_from_file_location("hostconf_pg_pgss_max", REPO / "scripts/hostconf.py")
hostconf = importlib.util.module_from_spec(spec)
sys.modules["hostconf_pg_pgss_max"] = hostconf
spec.loader.exec_module(hostconf)

HOST = "infer-pg-primary"
FID = "postgresql-pgss-max.infer-pg-primary"
HUGE_CONF = "postgresql-huge-pages.infer-pg-primary"


@pytest.fixture(scope="module")
def manifest():
    return hostconf.load_manifest()


def runbook_section() -> str:
    return RUNBOOK.read_text().split("## Huge pages for infer-pg-primary", 1)[1].split("\n## ", 1)[0]


def test_the_manifest_is_valid(manifest):
    assert hostconf.manifest_problems(manifest) == []


def test_the_pgss_max_entry(manifest):
    f = manifest["files"][FID]
    assert f["dest"] == "/etc/postgresql/18/main/conf.d/99-pgss-max.conf"
    assert f["src"] == "postgresql-pgss-max.infer-pg-primary.conf"
    assert (f["mode"], f["group"]) == ("0640", "postgres")
    text = (hostconf.FILES_DIR / f["src"]).read_text()
    assert hostconf.parse_settings("pg_conf_d", text) == {"pg_stat_statements.max": "20000"}
    assert f["expect"] == [{"pg_setting": "pg_stat_statements.max", "cluster": "18/main", "value": "20000"}]


def test_only_the_primary_carries_it_after_the_huge_pages_file_in_read_order(manifest):
    assert {fid for fid, h in manifest["hosts"].items() if FID in h.get("files", [])} == {HOST}
    listed = manifest["hosts"][HOST]["files"]
    assert listed.index(FID) > listed.index(HUGE_CONF)
    dests = [manifest["files"][i]["dest"] for i in listed if "/conf.d/" in manifest["files"][i]["dest"]]
    assert dests == sorted(dests) and len(dests) == len(set(dests)), "Postgres reads conf.d in name order"
    for fid in listed:
        if fid != FID:
            text = (hostconf.FILES_DIR / manifest["files"][fid]["src"]).read_text()
            assert not re.search(r"^\s*pg_stat_statements\.max\b", text, re.M), (
                f"{fid} would shadow or duplicate the setting"
            )


def test_the_cost_fits_the_huge_pages_margin():
    """Measured on Postgres 17 with `postgres -C shared_memory_size`: 146 MB at 5000 entries, 152 MB at 20000 (whole MB, so the real figure is 5 to 7 MB)."""
    grown_mb = 152 - 146
    pages = grown_mb / 2  # 2 MiB per huge page
    assert pages == 3
    margin_pages = 12800 - 12628
    assert margin_pages == 172
    assert 5 * pages < margin_pages and (10 / 2) < margin_pages, (
        "even the 8-10 MB estimate (5 pages) is far inside the 172-page margin"
    )
    assert 172 - 3 == 169


@pytest.mark.parametrize("which", ["purpose", "header"])
def test_purpose_and_header_say_why_and_what_the_tool_does(manifest, which):
    f = manifest["files"][FID]
    text = " ".join(f["purpose"].split()) if which == "purpose" else (hostconf.FILES_DIR / f["src"]).read_text()
    for needle in (
        "5000",
        "20000",
        "RESTART",
        "pending_restart",
        "never restarts",
        "exits 5",
        "6 MB",
        "3.8 GB",
        "612 GB",
        "2,000",
        "ALTER SYSTEM",
        "ADR 0495",
    ):
        assert needle in text, needle


def test_the_runbook_seeds_both_before_the_stop_applies_both_after_the_start_and_resets_both():
    s = runbook_section()
    for needle in (
        "ALTER SYSTEM SET huge_pages = 'on';",
        "ALTER SYSTEM SET pg_stat_statements.max = 20000;",
        "ALTER SYSTEM RESET huge_pages;",
        "ALTER SYSTEM RESET pg_stat_statements.max;",
        "--file postgresql-huge-pages.infer-pg-primary --yes",
        "--file postgresql-pgss-max.infer-pg-primary --yes",
        "SHOW pg_stat_statements.max",
        "SELECT count(*) FROM pg_stat_statements",
    ):
        assert needle in s, needle
    seed_hp, seed_pgss = (
        s.index("ALTER SYSTEM SET huge_pages = 'on';"),
        s.index("ALTER SYSTEM SET pg_stat_statements.max = 20000;"),
    )
    stop, start = s.index("4. **Stop**"), s.index("6. **Start**")
    apply_hp, apply_pgss = (
        s.index("--file postgresql-huge-pages.infer-pg-primary --yes"),
        s.index("--file postgresql-pgss-max.infer-pg-primary --yes"),
    )
    reset_hp, reset_pgss = (
        s.index("ALTER SYSTEM RESET huge_pages;"),
        s.index("ALTER SYSTEM RESET pg_stat_statements.max;"),
    )
    assert seed_hp < stop and seed_pgss < stop, "both seeds before the stop"
    assert start < apply_hp < apply_pgss and apply_pgss < reset_hp and apply_pgss < reset_pgss, (
        "both applies after the start, both resets after the applies"
    )
    assert s.index("7. **Verify, outage over**") < s.index("8. **Make it durable**")


def test_the_runbook_fallback_and_rollback_cover_both_settings():
    s = runbook_section()
    fallback = s.split("**Fallback**", 1)[1].split("**Rollback**", 1)[0]
    for needle in (
        "`pg_stat_statements.max` 5000",
        "one restore covers both",
        "99-pgss-max.conf",
        "the rider waits for the next restart",
    ):
        assert needle in fallback, needle
    rollback = s.split("**Rollback**", 1)[1]
    assert "99-pgss-max.conf" in rollback and "reads 5000" in rollback
    preflight = s.split("1. **Preflight, read-only.**", 1)[1].split("2. **Back up and seed.**", 1)[0]
    assert "`SHOW pg_stat_statements.max` is `5000`" in preflight and "exactly the three new files" in preflight
    assert "Rider: `pg_stat_statements.max` 5000 -> 20000" in s


def test_the_adr_rider_records_what_was_checked_and_the_state():
    text = ADR.read_text()
    rider = text.split("**Rider: `pg_stat_statements.max` 5,000 -> 20,000**", 1)[1].split("## Implementation state", 1)[
        0
    ]
    for needle in (
        FID,
        "99-pgss-max.conf",
        "146 MB -> 152 MB",
        "about 3 of the 172 spare huge pages",
        "169 instead of 172",
        "14 entries",
        "`pending_restart` is true",
        "`applied` false",
        "exits 5",
        "one restore of the `postgresql.auto.conf` backup",
        "2,000+",
        "3.8 GB",
        "612 GB",
    ):
        assert needle in rider, needle
    state = text.split("## Implementation state", 1)[1].split("## Consequences", 1)[0]
    row = [line for line in state.splitlines() if "99-pgss-max.conf" in line]
    assert len(row) == 1 and "planned with S2" in row[0] and "nothing is applied by merging" in row[0]


def test_the_shard_owns_the_new_files():
    text = SHARD.read_text()
    for path in (
        "config/hostconf/files/postgresql-pgss-max.infer-pg-primary.conf",
        "tests/test_pg_primary_pgss_max.py",
    ):
        assert text.count(path) >= 2, f"{path} is a shared surface and an owned one"
    assert "pg_stat_statements.max" in text
