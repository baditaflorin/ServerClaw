"""VM701 (infer-pg-primary) memory guardrails after the 2026-10-31 01:25Z global OOM (ADR 0495).

Pinned here: the installer's fstab line and the README agree (the cap is 10 GiB, in both); the fstab rewrite is idempotent and touches only the /dev/shm tmpfs line
(tested through the script's functions, which are sourced and never run as an installer); the two hostconf files say what the ADR says (values, mode, group, both
listed on the host, the incident named, the `postgresql.auto.conf` shadowing stated); the designed parallel-query ceiling stays under the cap; huge pages are NOT part
of this change; and the runbook keeps the apply order that `hostconf.py apply` needs (it rolls a file back when `postgresql.auto.conf` still shadows it).
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
D = REPO / "config/0infer/pg-primary-memory"
SCRIPT = D / "install-vm.sh"
README = D / "README.md"
ADR = REPO / "docs/adr/0495-pg-primary-memory-guardrails.md"
RUNBOOK = REPO / "docs/runbooks/host-local-config.md"

spec = importlib.util.spec_from_file_location("hostconf_pg_primary_memory", REPO / "scripts/hostconf.py")
hostconf = importlib.util.module_from_spec(spec)
sys.modules["hostconf_pg_primary_memory"] = hostconf
spec.loader.exec_module(hostconf)

HOST = "infer-pg-primary"
PARALLEL = "postgresql-parallel-guardrails.infer-pg-primary"
WORK_MEM = "postgresql-work-mem-guardrails.infer-pg-primary"
MiB, GiB = 2**20, 2**30
LINE = "tmpfs /dev/shm tmpfs rw,nosuid,nodev,size=10G 0 0"


def shell(code: str, text: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """bash -c `code` with the installer sourced ($1). Sourcing only defines functions: the installer runs only when it is executed."""
    return subprocess.run(
        ["bash", "-c", f'source "$1" && {code}', "_", str(SCRIPT)], input=text, capture_output=True, text=True, env=env
    )


def installer_var(name: str) -> str:
    p = shell(f'printf %s "${{{name}}}"')
    assert p.returncode == 0, p.stderr
    return p.stdout


def rewrite(fn: str, text: str) -> str:
    p = shell(fn, text)
    assert p.returncode == 0, p.stderr
    return p.stdout


# ───────────────────────────── the installer and the README ─────────────────────────────


def test_the_installer_is_valid_shell_undoable_and_executable():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    text = SCRIPT.read_text()
    assert "--undo" in text and "mount -o remount,size=" in text and "findmnt" in text
    assert os.access(SCRIPT, os.X_OK), "the other installers of config/0infer are executable"


def test_sourcing_the_installer_runs_nothing(tmp_path):
    """The test relies on this: an empty PATH would make `id`, `hostname` and `mount` fail at once if main ran."""
    p = subprocess.run(
        ["/bin/bash", "-c", 'source "$1" && echo defined', "_", str(SCRIPT)],
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path)},
    )
    assert p.returncode == 0 and p.stdout == "defined\n", p.stderr


def test_the_installers_line_and_the_readme_agree():
    assert installer_var("LINE") == LINE
    assert installer_var("SIZE") == "10G"
    assert int(installer_var("SIZE_BYTES")) == 10 * GiB
    text = README.read_text()
    assert f"`{LINE}`" in text, "the README must quote the installer's fstab line"
    assert "size=10G" in text and "10,737,418,240" in text and "10 GiB" in text
    assert "66,560" in text and "66560" in text and "no ballooning" in text and "cannot be hot-removed" in text
    assert "2026-10-31" in text and "08:02Z" in text and "08:17Z" in text


def test_the_readme_says_where_the_other_pieces_are_and_what_is_not_here():
    text = README.read_text()
    for needle in (
        "postgresql-parallel-guardrails.infer-pg-primary",
        "postgresql-work-mem-guardrails.infer-pg-primary",
        "adr/0495",
        "huge pages",
        "--undo",
        "fstab.bak-shm",
    ):
        assert needle in text, needle


# ───────────────────────────── the fstab rewrite (a pure function of its input) ─────────────────────────────

HEAD = "# /etc/fstab\nUUID=abcd / ext4 defaults 0 1\ntmpfs /tmp tmpfs size=30G 0 0\n"

CASES = {
    "no line yet": (HEAD, HEAD + LINE + "\n"),
    "the line is already there": (HEAD + LINE + "\n", HEAD + LINE + "\n"),
    "another size": (
        HEAD + "tmpfs /dev/shm tmpfs defaults,noexec,size=2G 0 0\n",
        HEAD + "tmpfs /dev/shm tmpfs defaults,noexec,size=10G 0 0\n",
    ),
    "a percent size": (
        HEAD + "tmpfs /dev/shm tmpfs rw,size=50% 0 0\n",
        HEAD + "tmpfs /dev/shm tmpfs rw,size=10G 0 0\n",
    ),
    "no size option": (
        HEAD + "tmpfs /dev/shm tmpfs defaults 0 0\n",
        HEAD + "tmpfs /dev/shm tmpfs defaults,size=10G 0 0\n",
    ),
    "a commented line is not the line": (
        "#tmpfs /dev/shm tmpfs size=1G 0 0\n# tmpfs /dev/shm tmpfs size=2G 0 0\n",
        "#tmpfs /dev/shm tmpfs size=1G 0 0\n# tmpfs /dev/shm tmpfs size=2G 0 0\n" + LINE + "\n",
    ),
    "another tmpfs mount is not touched": (
        "tmpfs /dev/shmx tmpfs size=1G 0 0\ntmpfs /run tmpfs size=1G 0 0\n",
        "tmpfs /dev/shmx tmpfs size=1G 0 0\ntmpfs /run tmpfs size=1G 0 0\n" + LINE + "\n",
    ),
}


@pytest.mark.parametrize("name", CASES)
def test_the_fstab_rewrite(name):
    before, after = CASES[name]
    once = rewrite("fstab_with_shm_size 10G", before)
    assert once == after
    assert rewrite("fstab_with_shm_size 10G", once) == once, "a second run must change nothing"


def test_a_line_that_already_has_the_size_is_kept_byte_for_byte():
    odd = HEAD + "tmpfs\t/dev/shm\ttmpfs\trw,nodev,size=10G\t0\t0\n"
    assert rewrite("fstab_with_shm_size 10G", odd) == odd


@pytest.mark.parametrize("name", CASES)
def test_the_undo_removes_only_the_shm_line(name):
    _, after = CASES[name]
    expected = "".join(line for line in after.splitlines(keepends=True) if not re.match(r"tmpfs\s+/dev/shm\s", line))
    assert rewrite("fstab_without_shm", after) == expected


def test_add_then_undo_gives_the_original_file_back():
    assert rewrite("fstab_without_shm", rewrite("fstab_with_shm_size 10G", HEAD)) == HEAD


# ───────────────────────────── the two hostconf files ─────────────────────────────


@pytest.fixture(scope="module")
def manifest():
    return hostconf.load_manifest()


def settings(manifest, fid):
    return hostconf.parse_settings("pg_conf_d", (hostconf.FILES_DIR / manifest["files"][fid]["src"]).read_text())


def test_the_manifest_is_valid(manifest):
    assert hostconf.manifest_problems(manifest) == []


def test_the_parallel_guardrail_file(manifest):
    f = manifest["files"][PARALLEL]
    assert f["dest"] == "/etc/postgresql/18/main/conf.d/98-parallel-guardrails.conf"
    assert (f["mode"], f["group"]) == ("0640", "postgres")
    assert settings(manifest, PARALLEL) == {
        "max_parallel_workers_per_gather": "4",
        "max_parallel_workers": "12",
        "temp_file_limit": "150GB",
    }
    assert f["expect"] == [
        {"pg_setting": "max_parallel_workers_per_gather", "cluster": "18/main", "value": "4"},
        {"pg_setting": "max_parallel_workers", "cluster": "18/main", "value": "12"},
        {"pg_setting": "temp_file_limit", "cluster": "18/main", "value": "150GB"},
    ]


def test_the_work_mem_guardrail_file_is_a_file_of_its_own(manifest):
    """Applied 30 minutes after the parallel file so a regression is attributable to one knob: work_mem must not be in the first file."""
    f = manifest["files"][WORK_MEM]
    assert f["dest"] == "/etc/postgresql/18/main/conf.d/98-work-mem-guardrails.conf"
    assert (f["mode"], f["group"]) == ("0640", "postgres")
    assert settings(manifest, WORK_MEM) == {"work_mem": "64MB"}
    assert f["expect"] == [{"pg_setting": "work_mem", "cluster": "18/main", "value": "64MB"}]
    assert "work_mem" not in settings(manifest, PARALLEL)


@pytest.mark.parametrize("fid", [PARALLEL, WORK_MEM])
def test_each_purpose_names_the_incident_and_the_shadowing(manifest, fid):
    purpose = " ".join(manifest["files"][fid]["purpose"].split())
    for needle in (
        "2026-10-31",
        "01:25Z",
        "global OOM",
        "parallel-query",
        "ADR 0495",
        "postgresql.auto.conf",
        "overrides conf.d",
        "ALTER SYSTEM RESET",
        "97-log-connections",
    ):
        assert needle in purpose, needle
    assert manifest["files"][fid]["src"].endswith(".infer-pg-primary.conf")


def test_only_the_primary_carries_the_two_files_and_conf_d_stays_in_name_order(manifest):
    listed = manifest["hosts"][HOST]["files"]
    assert PARALLEL in listed and WORK_MEM in listed
    assert not [
        fid
        for fid, h in manifest["hosts"].items()
        if fid != HOST and (PARALLEL in h.get("files", []) or WORK_MEM in h.get("files", []))
    ]
    dests = [manifest["files"][i]["dest"] for i in listed if "/conf.d/" in manifest["files"][i]["dest"]]
    assert len(dests) == len(set(dests)) and dests == sorted(dests), "Postgres reads conf.d in name order"


SYSCTL_HP = "sysctl-postgres-hugepages.infer-pg-primary"
CONF_HP = "postgresql-huge-pages.infer-pg-primary"
NEEDED_PAGES = 12628  # shared_memory_size_in_huge_pages of the 24.66 GiB segment, read on VM701 on 2026-10-31
HUGE_PAGE = 2 * MiB


def test_the_huge_pages_files_and_the_names_the_window_kit_uses(manifest):
    """S2 (ADR 0495): the kit and the runbook name these ids, destinations and files; renaming one silently breaks the window."""
    sysctl, conf = manifest["files"][SYSCTL_HP], manifest["files"][CONF_HP]
    assert sysctl["dest"] == "/etc/sysctl.d/91-postgres-hugepages.conf"
    assert sysctl["src"] == "sysctl-postgres-hugepages.infer-pg-primary.conf"
    assert conf["dest"] == "/etc/postgresql/18/main/conf.d/99-huge-pages.conf"
    assert conf["src"] == "postgresql-huge-pages.infer-pg-primary.conf"
    assert (conf["mode"], conf["group"]) == ("0640", "postgres")
    assert "mode" not in sysctl and "group" not in sysctl, "the sysctl file is the default 0644 root:root"
    assert settings_of("sysctl", sysctl, manifest) == {"vm.nr_hugepages": "12800"}
    assert settings(manifest, CONF_HP) == {"huge_pages": "on"}
    assert sysctl["expect"] == [{"sysctl": "vm.nr_hugepages", "value": "12800"}]
    assert conf["expect"] == [{"pg_setting": "huge_pages", "cluster": "18/main", "value": "on"}]


def settings_of(kind: str, entry: dict, manifest) -> dict[str, str]:
    return hostconf.parse_settings(kind, (hostconf.FILES_DIR / entry["src"]).read_text())


def test_the_reservation_covers_the_segment_with_the_margin_the_files_state(manifest):
    reserved = int(settings_of("sysctl", manifest["files"][SYSCTL_HP], manifest)["vm.nr_hugepages"])
    assert reserved >= NEEDED_PAGES, "fewer pages than the segment needs: huge_pages = on would not start"
    assert reserved - NEEDED_PAGES == 172 and (reserved - NEEDED_PAGES) * HUGE_PAGE == 344 * MiB
    assert reserved * HUGE_PAGE == 25 * GiB and round(NEEDED_PAGES * HUGE_PAGE / GiB, 2) == 24.66


def test_only_the_primary_carries_the_huge_pages_files_and_they_do_not_reorder_the_conf_d(manifest):
    assert {
        fid for fid, h in manifest["hosts"].items() if SYSCTL_HP in h.get("files", []) or CONF_HP in h.get("files", [])
    } == {HOST}
    listed = manifest["hosts"][HOST]["files"]
    assert SYSCTL_HP in listed and CONF_HP in listed
    sysctls = [
        manifest["files"][i]["dest"] for i in listed if manifest["files"][i]["dest"].startswith("/etc/sysctl.d/")
    ]
    assert len(sysctls) == len(set(sysctls)) and "/etc/sysctl.d/91-postgres-hugepages.conf" in sysctls
    for fid in listed:  # nothing else on the host sets either value, so no file shadows the new ones
        if fid not in (SYSCTL_HP, CONF_HP):
            text = (hostconf.FILES_DIR / manifest["files"][fid]["src"]).read_text()
            assert not re.search(r"^\s*(vm\.nr_hugepages|huge_pages)\b", text, re.M), fid


def test_the_huge_pages_purposes_state_what_the_tool_does(manifest):
    """Read from scripts/hostconf.py and checked on a throwaway Postgres 17 (2026-10-31): a restart setting still shows its running value after the reload, so `apply` rolls it back."""
    sysctl = " ".join(manifest["files"][SYSCTL_HP]["purpose"].split())
    for needle in (
        "sysctl -p",
        "ONLY",
        "Postgres stopped",
        "12628",
        "172 pages",
        "344 MiB",
        "25.0 GiB",
        "balloon",
        "exits 5",
        "ADR 0495",
        "planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h)",
    ):
        assert needle in sysctl, needle
    conf = " ".join(manifest["files"][CONF_HP]["purpose"].split())
    for needle in (
        "RESTART",
        "pending_restart",
        "never restarts",
        "exits 5",
        "ALTER SYSTEM",
        "ADR 0495",
        "planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h)",
        "huge_pages",
    ):
        assert needle in conf, needle
    for fid, header in (
        (SYSCTL_HP, ("sysctl -p", "ONLY with Postgres stopped", "balloon", "12628", "172 pages")),
        (CONF_HP, ("NEEDS A RESTART", "pending_restart", "never restarts", "exits 5")),
    ):
        text = (hostconf.FILES_DIR / manifest["files"][fid]["src"]).read_text()
        for needle in header:
            assert needle in text, (fid, needle)


# ───────────────────────────── the arithmetic of ADR 0495 ─────────────────────────────


def node(work_mem_mib: int, workers: int, multiplier: int = 2) -> int:
    """One parallel hash node: work_mem x hash_mem_multiplier x (workers + 1 leader)."""
    return work_mem_mib * multiplier * (workers + 1) * MiB


def test_the_designed_ceiling_stays_under_the_cap_and_the_old_one_did_not(manifest):
    cap = int(installer_var("SIZE_BYTES"))
    incident_excess = 24.5 * GiB  # shmem beyond the 24.6 GiB segment at the 2026-10-31 kill
    parallel = settings(manifest, PARALLEL)
    workers, total = int(parallel["max_parallel_workers_per_gather"]), int(parallel["max_parallel_workers"])
    gathers = total // workers
    work_mem = int(settings(manifest, WORK_MEM)["work_mem"].removesuffix("MB"))
    assert gathers == 3, "12 workers at 4 per gather: at most 3 fully staffed gathers"
    # before S1: 24 workers, 4 per gather, 256 MB global and 512 MB on the role domainscope_app (a role setting in the application repository)
    assert (24 // 4) * node(512, 4) == 30 * GiB > incident_excess
    assert (24 // 4) * node(256, 4) == 15 * GiB
    # S1 as first decided (2 per gather, 12 in all): 6 gathers of 3 participants
    assert (12 // 2) * node(128, 2) == 4.5 * GiB
    # now (amendment of 2026-11-02): the role setting is 128 MiB (the application repository, not here), the global value is the file's
    assert node(128, workers) == 1280 * MiB == 1.25 * GiB
    assert gathers * node(128, workers) == 3.75 * GiB
    assert 2 * gathers * node(128, workers) == 7.5 * GiB
    assert node(work_mem, workers) == 640 * MiB
    assert gathers * node(work_mem, workers) == 1.875 * GiB
    assert 2 * gathers * node(128, workers) < cap < incident_excess, (
        "even two hash nodes per gather fit under the cap, and the cap is below what killed the cluster"
    )
    assert cap == 8 * node(128, workers), (
        "the cap holds 8 nodes of 1.25 GiB: it is the backstop for gathers that are not fully staffed"
    )
    text = ADR.read_text()
    for needle in ("30 GiB", "4.5 GiB", "5.0 GiB", "3.75 GiB", "7.5 GiB", "1.875 GiB", "640 MiB", "1.25 GiB"):
        assert needle in text, needle


def test_the_per_gather_knob_is_back_at_4_and_only_that_knob(manifest):
    """S1 acceptance, 2026-11-02: SELECT COUNT(*) FROM mv_domains_denormalized 0.42 s -> 0.62 s with workers per call 3.94 -> 1.97; the rule reverts only that knob."""
    parallel = settings(manifest, PARALLEL)
    assert parallel["max_parallel_workers_per_gather"] == "4", "the value S1 replaced"
    assert (parallel["max_parallel_workers"], parallel["temp_file_limit"]) == ("12", "150GB"), "the other S1 knobs stay"
    assert settings(manifest, WORK_MEM) == {"work_mem": "64MB"}, "the work_mem file is unchanged"
    f = manifest["files"][PARALLEL]
    text = (hostconf.FILES_DIR / f["src"]).read_text()
    for needle in (
        "max_parallel_workers_per_gather = 4 again",
        "0.42 s",
        "0.62 s",
        "3.94 -> 1.97",
        "3 gathers of 4 workers",
        "1.25 GiB",
        "3.75 GiB",
        "7.5 GiB",
        "640 MiB",
        "10 GiB cap",
    ):
        assert needle in text, needle
    assert "with 2 per gather" not in text
    purpose = " ".join(f["purpose"].split())
    for needle in (
        "4 per gather",
        "0.42 s",
        "0.62 s",
        "3.94 -> 1.97",
        "1.25 GiB",
        "3.75 GiB",
        "amendment of 2026-11-02",
    ):
        assert needle in purpose, needle
    assert "2 workers per gather" not in purpose


# ───────────────────────────── the ADR, the runbook, and public-repo hygiene ─────────────────────────────


def test_the_adr_records_decision_and_implementation_state():
    text = ADR.read_text()
    assert text.startswith("# ADR 0495:")
    for field in (
        "- Status: Accepted",
        "- Implementation Status: Partial",
        "- Implemented In Repo Version:",
        "- Implemented In Platform Version:",
        "- Implemented On:",
        "- Date: 2026-10-31",
    ):
        assert field in text, field
    for needle in (
        PARALLEL,
        WORK_MEM,
        "98-parallel-guardrails.conf",
        "98-work-mem-guardrails.conf",
        "08:02Z",
        "10 GiB",
        "66,560",
        "**applied** 2026-11-01 11:04Z (S1a)",
        "huge pages",
    ):
        assert needle in text, needle
    assert "sessions/2026-10-31-pg-primary-oom/README.md" in text


def test_the_adr_amendment_records_the_s2_plan_as_planned_not_applied():
    text = ADR.read_text()
    for needle in (
        SYSCTL_HP,
        CONF_HP,
        "91-postgres-hugepages.conf",
        "99-huge-pages.conf",
        "12,628",
        "12,800",
        "172 pages",
        "344 MiB",
        "S1c",
        "planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h)",
        "exits 5",
        "pending_restart",
    ):
        assert needle in text, needle
    assert "huge pages, alerts, role split | not started" not in text, (
        "huge pages are planned now; alerts and the role split are not"
    )


def test_the_adr_amendment_records_the_acceptance_result_and_the_restored_knob():
    text = ADR.read_text()
    section = text.split("## Amendment 2026-11-02", 1)[1]
    for needle in (
        "planned, applied Tue 2026-11-03 11:03Z",
        "2026-11-01",
        "11:04Z",
        "11:41Z",
        "0.42 s",
        "0.62 s",
        "+48 %",
        "15,455",
        "3.94",
        "1.97",
        "27.6 GiB",
        "max_parallel_workers_per_gather = 4",
        "1.25 GiB",
        "3.75 GiB",
        "7.5 GiB",
        "640 MiB",
        "1.875 GiB",
        "10 GiB cap",
        "not verified",
    ):
        assert needle in section, needle
    header = text.split("\n## ", 1)[0]
    assert "applied on 2026-11-01" in header and "2026-11-03 11:03Z" in header
    assert "**in git, not applied**" not in text.split("## Implementation state", 1)[1].split("## Consequences", 1)[0]


def test_the_runbook_keeps_the_apply_order_that_hostconf_needs(manifest):
    text = RUNBOOK.read_text()
    section = text.split("## Postgres settings that `postgresql.auto.conf` shadows", 1)[1].split("\n## ", 1)[0]
    positions = [
        section.index(s)
        for s in (
            "**Look, then back up.**",
            "**Make the shadow copy carry the new values",
            "**Apply the file**",
            "**Remove the shadow copy and reload**",
            "**Verify**",
        )
    ]
    assert positions == sorted(positions), "backup, seed, apply, reset, verify: in this order"
    for needle in (
        "postgresql.auto.conf.bak-",
        "ALTER SYSTEM SET",
        "ALTER SYSTEM RESET",
        "pg_reload_conf()",
        "sourcefile",
        "pending_restart",
        "exits 5",
        "multi-command string",
        "Rollback",
        PARALLEL,
        WORK_MEM,
    ):
        assert needle in section, needle
    # every name of both files is seeded with the file's value (so `apply` finds it in effect) and reset afterwards (so the file is not shadowed)
    for fid in (PARALLEL, WORK_MEM):
        for name, value in settings(manifest, fid).items():
            quoted = value if value.isdigit() else f"'{value}'"
            assert f"ALTER SYSTEM SET {name} = {quoted};" in section, name
            assert f"ALTER SYSTEM RESET {name};" in section, name
    assert "ADR 0495" in section and "never deletes" in section


def test_the_runbook_keeps_the_huge_pages_window_order():
    text = RUNBOOK.read_text()
    section = text.split("## Huge pages for infer-pg-primary", 1)[1].split("\n## ", 1)[0]
    steps = (
        "1. **Preflight, read-only.**",
        "2. **Back up and seed.**",
        "3. **`CHECKPOINT;` twice.**",
        "4. **Stop**",
        "5. **Reserve**",
        "6. **Start**",
        "7. **Verify, outage over**",
        "8. **Make it durable**",
        "9. **After**",
    )
    positions = [section.index(s) for s in steps]
    assert positions == sorted(positions), "preflight, seed, checkpoint, stop, reserve, start, verify, durable, after"
    for needle in (
        SYSCTL_HP,
        CONF_HP,
        "ALTER SYSTEM SET huge_pages = 'on'",
        "ALTER SYSTEM RESET huge_pages",
        "HugePages_Total",
        "HugePages_Free",
        "PageTables",
        "SHOW huge_pages",
        "huge_pages_status",
        "planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h)",
        "compact_memory",
        "**Fallback**",
        "**Rollback**",
        "vm.nr_hugepages=0",
        "hugepages=12800",
        "never restarts",
        "exit 5",
    ):
        assert needle in section, needle
    assert section.index("**Fallback**") > section.index("9. **After**") and section.index(
        "**Rollback**"
    ) > section.index("**Fallback**")
    # applying the restart setting before the stop is the order that cannot work: the seed comes first, the apply of the conf.d file only after the start
    assert (
        section.index("ALTER SYSTEM SET huge_pages")
        < section.index("Stop")
        < section.index("postgresql-huge-pages.infer-pg-primary --yes")
    )
    assert "docs/adr/0495-pg-primary-memory-guardrails.md" in text


def test_no_workstation_path_in_the_committed_files():
    """AGENTS.md, public repo mode: no absolute workstation paths."""
    files = [
        SCRIPT,
        README,
        ADR,
        hostconf.FILES_DIR / "postgresql-parallel-guardrails.infer-pg-primary.conf",
        hostconf.FILES_DIR / "postgresql-work-mem-guardrails.infer-pg-primary.conf",
        hostconf.FILES_DIR / "sysctl-postgres-hugepages.infer-pg-primary.conf",
        hostconf.FILES_DIR / "postgresql-huge-pages.infer-pg-primary.conf",
        RUNBOOK,
    ]
    for f in files:
        assert not re.search(r"/Users/|/home/[a-z]", f.read_text()), f


def test_the_s2_window_text_is_the_current_plan_everywhere(manifest):
    """The S2 window moved from 2026-11-02 to planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h).
    The old date must not survive in S2's own text; other 2026-11-02 mentions (the per-gather amendment of ADR 0495) are a different fact and stay."""
    plan = "planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h)"
    stale = ("2026-11-02 window", "2026-11-02 maintenance window", "2026-11-02 11:00", "Monday")
    for fid in (SYSCTL_HP, CONF_HP):
        purpose = " ".join(manifest["files"][fid]["purpose"].split())
        assert plan in purpose and not any(s in purpose for s in stale), fid
        assert not any(s in (hostconf.FILES_DIR / manifest["files"][fid]["src"]).read_text() for s in stale), fid
    adr = ADR.read_text()
    s2 = adr.split("### Huge pages (S2), planned", 1)[1].split("## Implementation state", 1)[0]
    assert plan in s2 and "2026-11-02" not in s2
    assert (
        "S1 was applied on 2026-11-01 with one regression" in s2
        and "#658" in s2
        and "2026-11-03" in s2
        and "follows 24 h later" in s2
    )
    for line in adr.splitlines():
        if line.startswith("6. **Huge pages") or ("91-postgres-hugepages.conf" in line and line.startswith("|")):
            assert plan in line and not any(s in line for s in stale), line
    runbook = RUNBOOK.read_text().split("## Huge pages for infer-pg-primary", 1)[1].split("\n## ", 1)[0]
    assert plan in runbook and not any(s in runbook for s in stale)
    assert (
        "S1c" in runbook
        and "planned 2026-11-04"
        in RUNBOOK.read_text().split("## Huge pages for infer-pg-primary", 1)[1].split("\n", 1)[0]
    )
    for path in (
        REPO / "workstreams/active/ws-20261031-pg-primary-hugepages.yaml",
        REPO / "docs/workstreams/ws-20261031-pg-primary-hugepages.md",
    ):
        text = path.read_text()
        assert "2026-11-02" not in text and "2026-11-04" in text, path
