"""pbs-prune-whatif.py (config/0infer/tier0-pbs2): the read-only "what would this retention change free?" scan of a PBS datastore.

Decisions about deleting backup copies were made on its numbers (2026-10-17), so its arithmetic is pinned against a synthetic datastore built the way PBS lays it out: index files
(.fidx fixed / .didx dynamic, 4096-byte header then digests) per snapshot, chunk files under .chunks/<first four hex digits>/<digest>. A chunk is freed only when EVERY snapshot that
references it (in any group or namespace) is deleted.
"""
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-pbs2" / "pbs-prune-whatif.py"
SIZES = {"a": 1_000, "b": 2_000, "c": 4_000, "d": 8_000, "e": 16_000}
DIG = {k: bytes([i + 1]) * 32 for i, k in enumerate(SIZES)}


def build(root: Path, layout: dict):
    """layout: {relative group dir: {snapshot name: ("fidx"|"didx", [chunk letters])}}"""
    (root / ".chunks").mkdir(parents=True)
    for k, n in SIZES.items():
        d = DIG[k].hex()
        (root / ".chunks" / d[:4]).mkdir(exist_ok=True)
        (root / ".chunks" / d[:4] / d).write_bytes(b"x" * n)
    for g, snaps in layout.items():
        for sn, (kind, chunks) in snaps.items():
            sd = root / g / sn
            sd.mkdir(parents=True)
            body = b"".join((bytes(8) + DIG[c]) if kind == "didx" else DIG[c] for c in chunks)
            (sd / f"drive.img.{kind}").write_bytes(bytes(4096) + body)
            (sd / "index.json.blob").write_bytes(b"{}")


LAYOUT = {
    "vm/1": {"2026-10-14T00:00:00Z": ("fidx", ["a", "b"]), "2026-10-15T00:00:00Z": ("fidx", ["b", "c"]), "2026-10-16T00:00:00Z": ("fidx", ["c", "d"])},
    "ns/other/vm/2": {"2026-10-15T00:00:00Z": ("didx", ["c", "e"]), "2026-10-16T00:00:00Z": ("didx", ["e"])},
}


def run(root, *args):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=dict(os.environ, PBS_STORE=str(root)))
    assert r.returncode == 0, r.stderr
    return r.stdout


def gb(n):
    return f"{n / 1e9:.1f}"


def test_the_scenario_frees_only_chunks_no_surviving_snapshot_references(tmp_path):
    build(tmp_path, LAYOUT)
    out = run(tmp_path, "keep-last=1:vm/1")                          # deletes 10-14 (a,b) and 10-15 (b,c); survivors reference c,d (vm/1) and c,e (other)
    # a: only the 10-14 snapshot -> freed. b: 10-14 and 10-15, both deleted -> freed. c: 10-15 deleted, but 10-16 of vm/1 and the other group keep it -> stays.
    assert "deletes 2 snapshots in 1 groups" in out
    assert f"frees {(SIZES['a'] + SIZES['b']) / 1e9:.1f} GB" in out


def test_a_chunk_shared_with_another_group_survives_the_deletion_of_one_group(tmp_path):
    build(tmp_path, LAYOUT)
    out = run(tmp_path, "drop=ns/other/vm/2")                        # e is only in this group (freed); c is also in vm/1 (stays)
    assert f"{SIZES['e'] / 1e9:.1f} GB" in out and "deletes 2 snapshots in 1 groups" in out
    out = run(tmp_path, "drop=vm/1")                                 # a, b, d are only in vm/1 (freed); c is shared with the other group (stays)
    assert f"{(SIZES['a'] + SIZES['b'] + SIZES['d']) / 1e9:.1f} GB" in out and "deletes 3 snapshots" in out


def test_keep_last_star_and_combined_scenarios_add_up_without_double_counting(tmp_path):
    build(tmp_path, LAYOUT)
    both = run(tmp_path, "keep-last=1:vm/1", "drop=ns/other/vm/2")   # deletes vm/1 10-14, 10-15 and the whole other group: freed = a, b, and e (c stays via vm/1's newest)
    assert "deletes 4 snapshots in 2 groups" in both and f"{(SIZES['a'] + SIZES['b'] + SIZES['e']) / 1e9:.1f} GB" in both
    star = run(tmp_path, "keep-last=1:*")
    assert "deletes 3 snapshots in 2 groups" in star


def test_the_table_reports_what_only_the_oldest_and_only_the_newest_snapshot_hold(tmp_path):
    build(tmp_path, LAYOUT)
    out = run(tmp_path)
    row = [l for l in out.splitlines() if l.startswith("vm/1 ")][0].split()
    assert row[1] == "3" and row[2] == f"{SIZES['a'] / 1e9:.1f}" and row[3] == f"{SIZES['d'] / 1e9:.1f}"      # oldest holds only a; newest holds only d
    assert "5 snapshots in 2 groups" in out and "5 chunk files" in out


def test_unknown_groups_and_scenarios_are_refused_and_nothing_is_modified(tmp_path):
    build(tmp_path, LAYOUT)
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    for bad in (["keep-last=2:vm/999"], ["drop=nope"], ["bogus=1"]):
        r = subprocess.run([sys.executable, str(SCRIPT), *bad], capture_output=True, text=True, env=dict(os.environ, PBS_STORE=str(tmp_path)))
        assert r.returncode != 0
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before
