"""The zram swap unit of the 0own hypervisor (config/0own/zram-swap/zram-swap.service) must not close a boot ordering cycle.

2026-10-22: the horizon check boot_ordering_cycle counted 2 cycles in the boot transaction of the hypervisor and `systemd-analyze verify default.target` named them:

  1. default dependencies: sysinit.target -> swap.target -> zram-swap.service -> basic.target -> sockets.target -> iscsid.socket -> sysinit.target
  2. After=local-fs.target: local-fs.target -> zram-swap.service -> swap.target -> tmp.mount -> local-fs.target

A drop-in could not fix the second one (an empty After= does not remove a line of the unit file), so the unit is kept in git. At boot systemd deletes a start job to break a cycle
(it said tmp.mount), so this is pinned here: the unit is parsed and the ordering edges that matter are checked against the vendor edges that close the loops, with a tiny cycle search.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIR = REPO / "config" / "0own" / "zram-swap"
UNIT = DIR / "zram-swap.service"
INSTALL = DIR / "install.sh"


def _unit() -> dict[str, dict[str, list[str]]]:
    """Section -> key -> every value (systemd allows a key more than once; the values of a list key are split on spaces)."""
    sections: dict[str, dict[str, list[str]]] = {}
    current = ""
    for raw in UNIT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        key, _, value = line.partition("=")
        sections[current].setdefault(key, []).append(value)
    return sections


def _words(values: list[str]) -> set[str]:
    return {w for v in values for w in v.split()}


def _boot_edges(unit: dict[str, dict[str, list[str]]]) -> set[tuple[str, str]]:
    """(a, b) = a starts before b. The vendor edges are the ones of Debian 13 / systemd 257 that close the two loops; the unit's own edges come from its file."""
    z = "zram-swap.service"
    edges = {
        ("swap.target", "sysinit.target"),    # sysinit.target is After=swap.target
        ("sysinit.target", "iscsid.socket"),  # iscsid.socket keeps its default After=sysinit.target
        ("iscsid.socket", "sockets.target"),  # sockets.target is After= its sockets
        ("sockets.target", "basic.target"),   # basic.target is After=sockets.target
        ("swap.target", "tmp.mount"),         # tmp.mount: After=swap.target
        ("tmp.mount", "local-fs.target"),     # tmp.mount: Before=local-fs.target
    }
    u = unit["Unit"]
    for target in _words(u.get("Before", [])):
        edges.add((z, target))
    for target in _words(u.get("After", [])):
        edges.add((target, z))
    if u.get("DefaultDependencies", ["yes"])[-1].strip().lower() != "no":
        # the implicit dependencies of a service unit
        edges |= {("basic.target", z), ("sysinit.target", z)}
    return edges


def _has_cycle(edges: set[tuple[str, str]]) -> list[str] | None:
    graph: dict[str, list[str]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt, 0) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if state.get(nxt, 0) == 0:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for n in list(graph):
        if state.get(n, 0) == 0:
            found = visit(n)
            if found:
                return found
    return None


def test_the_unit_adds_no_boot_ordering_cycle() -> None:
    assert _has_cycle(_boot_edges(_unit())) is None, _has_cycle(_boot_edges(_unit()))


def test_the_model_finds_both_loops_of_2026_10_22_when_the_unit_is_changed_back() -> None:
    """The check above is only worth something if it fails for the two shapes that were live."""
    base = _unit()
    with_defaults = {s: {k: list(v) for k, v in d.items()} for s, d in base.items()}
    del with_defaults["Unit"]["DefaultDependencies"]
    loop1 = _has_cycle(_boot_edges(with_defaults))
    # the implicit After=basic.target / After=sysinit.target of a service unit: a loop through swap.target (the search may report the shortest, through sysinit.target, or the one through basic.target)
    assert loop1 and "zram-swap.service" in loop1 and "swap.target" in loop1, loop1
    with_after = {s: {k: list(v) for k, v in d.items()} for s, d in base.items()}
    with_after["Unit"]["After"] = ["local-fs.target"]
    # local-fs.target -> zram-swap.service needs the edge from local-fs.target into tmp.mount's chain: tmp.mount -> local-fs.target is the vendor edge, so the loop is closed
    loop2 = _has_cycle(_boot_edges(with_after))
    assert loop2 and "tmp.mount" in loop2 and "local-fs.target" in loop2, loop2


def test_the_unit_keeps_what_it_is_for() -> None:
    u = _unit()
    unit, service, install = u["Unit"], u["Service"], u["Install"]
    assert unit["DefaultDependencies"] == ["no"]
    assert "swap.target" in _words(unit["Before"]) and "shutdown.target" in _words(unit["Before"])
    assert _words(unit.get("Conflicts", [])) == {"shutdown.target"}
    assert "After" not in unit, "an After= line of this unit closes a loop through tmp.mount or basic.target (see the header of the unit file)"
    assert service["Type"] == ["oneshot"] and service["RemainAfterExit"] == ["yes"]
    start = service["ExecStart"][0]
    for needle in ("modprobe zram", "zstd", "8G", "mkswap", "swapon -p 100 /dev/zram0"):
        assert needle in start, needle
    assert "swapoff /dev/zram0" in service["ExecStop"][0]
    assert install["WantedBy"] == ["multi-user.target"]


def test_the_installer_is_valid_shell_and_has_an_undo_that_refuses_a_cycle() -> None:
    assert subprocess.run(["bash", "-n", str(INSTALL)], capture_output=True, check=False).returncode == 0
    text = INSTALL.read_text(encoding="utf-8")
    for needle in ("--undo", "systemd-analyze verify default.target", "ordering cycle", "daemon-reload", "10-no-default-deps.conf", "/root/zram-swap-backups"):
        assert needle in text, needle
    assert "systemctl restart" not in text and "systemctl start" not in text, "the running swap must not be touched"
