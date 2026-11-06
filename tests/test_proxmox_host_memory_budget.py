"""The pve-0mcp memory budget: the alert on the guaranteed footprint (config/prometheus/rules/proxmox-host-memory-budget.yml) and the arithmetic of the runbook.

2026-11-01: pve-0mcp (128716 MiB, 19 running VMs) fell to 3.9 percent available memory with its swap full. docs/runbooks/pve-0mcp-memory-budget.md is the proposal that came out of the
measurements: every running VM is guaranteed its balloon floor (or its whole memory when it has balloon 0), that sum was 103168 MiB (80.15 percent of RAM), and pvestatd keeps every ballooned
guest at its floor while the host is over its ballooning target. Pinned here: the alert's labels, delay and scoping, that promtool accepts the rule and passes its unit tests (which feed the
live snapshot of that day), that the unit-test file covers every alert in the rule file, and that the runbook's tables add up: the budget table (maximum, floor, fixed, guaranteed), the
proposal table against it, the apply plan's commands against the proposals, and the percentages and expected-available figures of the stage table.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "proxmox-host-memory-budget.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "proxmox_host_memory_budget_rules_test.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "pve-0mcp-memory-budget.md"
ALERT = "ProxmoxHostGuaranteedMemoryOverBudget"
HOST_RAM_MIB = 128716  # MemTotal of pve-0mcp, 131805900 kB
HELD_ABOVE_FLOORS_PERCENT = 6.7  # RSS of the VMs above their guaranteed sizes, 2026-11-01 13:31Z
HOST_OWN_PERCENT = 2.4  # kernel, slab, page tables, daemons
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _number(cell: str) -> int | None:
    cell = cell.strip().replace(",", "")
    return None if cell in ("-", "") else int(cell)


def _table(header_start: str) -> list[dict[str, str]]:
    """The rows of the markdown table whose header line starts with `header_start` (cells split on unescaped pipes)."""
    lines = _text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header_start))
    split = lambda line: [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]  # noqa: E731
    head = split(lines[start])
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(dict(zip(head, split(line), strict=True)))
    return rows


def _budget() -> dict[int, dict[str, int | None]]:
    rows = [r for r in _table("| VM | Name | In git | Maximum |") if r["VM"].isdigit()]
    return {
        int(r["VM"]): {k: _number(r[k]) for k in ("In git", "Maximum", "Floor", "Fixed", "Guaranteed", "Host RSS now")}
        | {"name": r["Name"]}
        for r in rows
    }


def _alerts() -> dict[str, dict]:
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


def _expr() -> str:
    return " ".join(_alerts()[ALERT]["expr"].split())


# ---- the alert ----------------------------------------------------------------------------------------------------------------------------------------------------------------


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_unit_tests_cover_every_alert_of_the_rule_file() -> None:
    tests = yaml.safe_load(PROMTOOL_TEST.read_text(encoding="utf-8"))
    assert [(PROMTOOL_TEST.parent / item).resolve() for item in tests["rule_files"]] == [RULES]
    covered = {check["alertname"] for case in tests["tests"] for check in case["alert_rule_test"]}
    assert covered == set(_alerts()), f"alerts without a promtool case: {sorted(set(_alerts()) - covered)}"


def test_the_alert_has_the_severity_delay_and_runbook_the_unit_tests_assume() -> None:
    rule = _alerts()[ALERT]
    assert rule["labels"] == {"severity": "warning", "service": "proxmox_host_memory_budget"}
    assert rule["for"] == "1h"
    assert (REPO / rule["annotations"]["runbook_url"]).is_file()
    assert rule["annotations"]["summary"] and "budget 80%" in rule["annotations"]["summary"]


def test_the_alert_counts_what_the_runbook_says_it_counts() -> None:
    """Floors of running VMs with a balloon, the whole memory of running VMs with balloon 0, one value per guest, 0mcp only, strictly above 80 percent of the host's RAM."""
    expr = _expr()
    assert expr.endswith("> 0.80")
    # every series is limited to the 0mcp hypervisor and to VMs; a duplicate scrape of one guest is counted once
    assert expr.count('pve_host="0mcp"') == 6
    assert expr.count('guest_type="vm"') == 5
    assert "max by (pve_host, guest_id)" in expr
    # the floor branch reads the minimum, the fixed branch the memory limit, and they are told apart by the balloon_enabled flag
    assert re.search(
        r"balloon_minimum_bytes\{[^}]*\} and on \(pve_host, guest_id\) \(fleet_proxmox_guest_balloon_enabled\{[^}]*\} == 1\)",
        expr,
    )
    assert re.search(
        r"memory_limit_bytes\{[^}]*\} and on \(pve_host, guest_id\) \(fleet_proxmox_guest_balloon_enabled\{[^}]*\} == 0\)",
        expr,
    )
    # stopped VMs (the template 9000) do not count
    assert 'fleet_proxmox_guest_info{pve_host="0mcp",guest_type="vm",status="running"} == 1' in expr
    # the denominator is the host's RAM
    assert "fleet_proxmox_host_memory_total_bytes" in expr


def test_the_alert_threshold_is_the_budget_ceiling_of_the_runbook() -> None:
    text = _text()
    assert "alarm above 80" in text.replace("**", "") or "an alarm above **80 percent**" in text
    assert f"{round(HOST_RAM_MIB * 0.80):,} MiB" in text  # 102,973
    assert f"{round(HOST_RAM_MIB * 0.75):,} MiB" in text  # 96,537


# ---- the runbook's arithmetic -------------------------------------------------------------------------------------------------------------------------------------------------------


def test_the_budget_table_adds_up() -> None:
    budget = _budget()
    assert len(budget) == 19  # the running VMs; the stopped template 9000 is not in the table
    for vmid, row in budget.items():
        assert (row["Floor"] is None) != (row["Fixed"] is None), f"VM {vmid} is either ballooned (floor) or fixed"
        assert row["Guaranteed"] == (row["Floor"] if row["Fixed"] is None else row["Fixed"]), vmid
        assert row["Guaranteed"] <= row["Maximum"], vmid
        if row["Fixed"] is not None:
            assert row["Fixed"] == row["Maximum"], vmid
    total = lambda key: sum(r[key] or 0 for r in budget.values())  # noqa: E731
    assert total("Maximum") == 142336
    assert total("Floor") == 80640 and sum(1 for r in budget.values() if r["Floor"] is not None) == 16
    assert total("Fixed") == 22528 and sorted(v for v, r in budget.items() if r["Fixed"] is not None) == [130, 180, 200]
    assert total("Guaranteed") == total("Floor") + total("Fixed") == 103168
    assert total("Host RSS now") == 111841
    text = _text()
    for figure in ("142,336", "103,168", "80,640", "22,528", "111,841", "80.15 percent", "110.6 percent"):
        assert figure in text, figure
    assert f"{103168 / HOST_RAM_MIB * 100:.2f}" == "80.15"
    assert f"{142336 / HOST_RAM_MIB * 100:.1f}" == "110.6"
    # the held-above-floor memory the summary and the budget formula quote: 8673 MiB net, 10633 gross
    over = [r["Host RSS now"] - r["Guaranteed"] for r in budget.values()]
    assert sum(over) == 8673 and sum(x for x in over if x > 0) == 10633
    assert round(8673 / HOST_RAM_MIB * 100, 1) == HELD_ABOVE_FLOORS_PERCENT


def test_the_proposals_start_from_the_numbers_of_the_budget_table() -> None:
    budget = _budget()
    rows = [r for r in _table("| Step | VM | Name | Now | Proposed |") if r["VM"].isdigit()]
    assert {r["Step"] for r in rows} >= {"P1", "P2", "P3", "P4 (optional)"}
    for r in rows:
        vmid = int(r["VM"])
        now = int(re.match(r"[\d,]+", r["Now"]).group(0).replace(",", ""))
        assert now == budget[vmid]["Guaranteed"], (vmid, r["Now"])
        assert budget[vmid]["name"] == r["Name"]
        proposed = _number(r["Proposed"])
        assert _number(r["Change"].replace("+", "")) == proposed - now, (vmid, r["Change"])
        assert proposed <= budget[vmid]["Maximum"], vmid  # a floor cannot exceed the maximum
        if proposed < now:
            assert r["Restart"] in ("no", "**yes**") and (
                vmid != 200 or r["Restart"] == "**yes**"
            )  # a fixed VM needs a restart to get a balloon


def test_the_apply_plan_commands_match_the_proposals_and_their_undo() -> None:
    proposals = {
        int(r["VM"]): r
        for r in _table("| Step | VM | Name | Now | Proposed |")
        if r["VM"].isdigit() and r["Step"].startswith("P")
    }
    plan = {r["Order"]: r for r in _table("| Order | Step | Commands |")}
    expected = {"A2": 154, "A3": 120, "A4": 200, "A5 (optional)": 100}
    for order, vmid in expected.items():
        proposed = _number(proposals[vmid]["Proposed"])
        now = int(re.match(r"[\d,]+", proposals[vmid]["Now"]).group(0).replace(",", ""))
        sets = re.findall(r"qm set (\d+) --balloon (\d+)", plan[order]["Commands"])
        assert sets == [(str(vmid), str(proposed))], (order, sets)
        assert re.findall(r"balloon (\d+)\"", plan[order]["Commands"]) in ([], [str(proposed)]), order
        undo = re.findall(r"qm set (\d+) --balloon (\d+)", plan[order]["Undo"])
        assert undo and undo[0][0] == str(vmid) and undo[0][1] in (str(now), "0"), (order, undo)
        assert re.findall(r"balloon (\d+)\"", plan[order]["Undo"]) in ([], [str(now)]), order
    assert "swapon --priority -2" in plan["A1"]["Commands"] and "12G" in plan["A1"]["Commands"]


def test_the_stage_table_matches_the_budget_and_the_proposals() -> None:
    budget = _budget()
    guaranteed = sum(r["Guaranteed"] for r in budget.values())
    change = {
        r["Step"]: _number(r["Change"].replace("+", ""))
        for r in _table("| Step | VM | Name | Now | Proposed |")
        if r["VM"].isdigit()
    }
    candidates = {
        "150": -2048,
        "155": -1536,
        "192": -768,
        "170": -512,
        "180": -1536,
    }  # "Candidates not proposed here" in section 6
    states = {
        "| Now |": guaranteed,
        "| After stage 1 (VM 120 +2,048, VM 154 -2,048) |": guaranteed + change["P1"] + change["P2"],
        "| After stage 2 (VM 200 floor 2,560) |": guaranteed + change["P1"] + change["P2"] + change["P3"],
        "| Also the optional VM 100 +1,024 |": guaranteed
        + change["P1"]
        + change["P2"]
        + change["P3"]
        + change["P4 (optional)"],
        "| Also every candidate cut of section 6 |": guaranteed
        + change["P1"]
        + change["P2"]
        + change["P3"]
        + sum(candidates.values()),
        "| CI builder moved off the host (VM 130 retired, owner's plan of 2026-10-29) |": guaranteed
        - budget[130]["Guaranteed"],
    }
    rows = {r["State"]: r for r in _table("| State | Guaranteed (MiB) |")}
    assert len(rows) == len(states)
    for label, value in states.items():
        row = rows[label.strip("| ")]
        assert _number(row["Guaranteed (MiB)"]) == value, label
        percent = value / HOST_RAM_MIB * 100
        assert row["Percent of RAM"] == f"{percent:.2f}", (label, percent)
        assert (
            row["Expected available"].split()[0]
            == f"{100 - percent - HELD_ABOVE_FLOORS_PERCENT - HOST_OWN_PERCENT:.1f}"
        ), (label, percent)
    # the budget rule: 75 percent by design, 80 as the alarm, and what is left of the owner's 15 percent available
    assert f"{100 - 15 - HELD_ABOVE_FLOORS_PERCENT - HOST_OWN_PERCENT:.1f}" == "75.9"


def test_the_runbook_says_which_steps_were_applied() -> None:
    """Sections 1 to 10 are the read-only snapshot of 2026-11-01 and say so; section 11 says what was applied afterwards."""
    text = _text()
    assert "stage 1 partly applied" in text.splitlines()[0]
    assert "no `qm set`, no restart, no swap, KSM or sysfs change" in text  # about the measurements of 2026-11-01
    assert "## 11. Status after stage 1 (2026-11-02 and 2026-11-03)" in text
    for applied in (
        "**applied 2026-11-02 10:43Z**",
        "**applied 2026-11-02 10:41Z**",
        "**applied 2026-11-02 23:09Z**",
        "**applied 2026-11-02 23:11Z**",
    ):
        assert applied in text, applied
    assert "**not applied; a stopgap exists, the choice is open**" in text


def test_the_status_section_adds_up_against_the_budget_table() -> None:
    """Section 11 starts from the budget table of 2026-11-01 and changes four VMs: 120 floor to its maximum, 122, 171 and 192 to fixed sizes."""
    budget = _budget()
    now = {
        120: (18432, 18432),
        122: (2048, 2048),
        171: (3072, 3072),
        192: (6144, 6144),
    }  # VM: (maximum now, guaranteed now)
    rows = {int(r["VM"]): r for r in _table("| VM | Name | Maximum before |") if r["VM"].isdigit()}
    assert sorted(rows) == sorted(now)
    for vmid, (maximum, guaranteed) in now.items():
        assert _number(rows[vmid]["Maximum before"]) == budget[vmid]["Maximum"], vmid
        assert _number(rows[vmid]["Guaranteed before"]) == budget[vmid]["Guaranteed"], vmid
        assert _number(rows[vmid]["Maximum now"]) == maximum and _number(rows[vmid]["Guaranteed now"]) == guaranteed, (
            vmid
        )
        assert guaranteed <= maximum, vmid
    guaranteed_before = sum(r["Guaranteed"] for r in budget.values())
    maxima_before = sum(r["Maximum"] for r in budget.values())
    guaranteed_now = guaranteed_before + sum(g - budget[v]["Guaranteed"] for v, (_, g) in now.items())
    maxima_now = maxima_before + sum(m - budget[v]["Maximum"] for v, (m, _) in now.items())
    assert (guaranteed_before, guaranteed_now) == (103168, 105728)
    assert (maxima_before, maxima_now) == (142336, 124928)
    text = _text()
    assert f"{guaranteed_now:,}" in text and f"{maxima_now:,}" in text
    guaranteed_percent = f"{guaranteed_now / HOST_RAM_MIB * 100:.2f}"
    maxima_percent = f"{maxima_now / HOST_RAM_MIB * 100:.1f}"
    assert (guaranteed_percent, maxima_percent) == ("82.14", "97.1")
    # the sentences that carry the figures, not just the figures somewhere in the page
    assert (
        f"to **{guaranteed_now:,} MiB**, which is **{guaranteed_percent} percent** of RAM (was 80.15 percent)" in text
    )
    assert f"to **{maxima_now:,} MiB**, which is **{maxima_percent} percent** of RAM (was 110.6 percent)" in text
    assert f"it computes {guaranteed_percent} percent, so it is pending" in text
    assert (
        f"(was 80.15 on 2026-11-01 ({guaranteed_percent} after" not in text
        and f"({guaranteed_percent} after the changes of section 11)" in text
    )
    ceiling = round(HOST_RAM_MIB * 0.80)  # 102,973
    assert f"{guaranteed_now - ceiling:,} MiB" == "2,755 MiB" and "**2,755 MiB** above it" in text
    after_a2 = guaranteed_now + (4096 - 6144)  # the A2 trial: VM 154 floor 6,144 to 4,096
    assert (
        f"{after_a2:,}" == "103,680"
        and f"{after_a2 / HOST_RAM_MIB * 100:.2f}" == "80.55"
        and "103,680 MiB, 80.55 percent" in text
    )
