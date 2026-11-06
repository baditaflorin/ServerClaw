"""Unit tests for scripts/tailscale_policy_reconcile.py (the unattended, additive-only policy reconciler).

Everything runs offline against the synthetic fixture policy (documentation addresses only). Git, the CI status, the
Tailscale API and the alert channel are replaced by in-memory fakes, so no credential or network is involved.
"""

from __future__ import annotations

import copy
import http.client
import json
import shutil
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tailscale_policy_reconcile as rec  # noqa: E402
import tailscale_policy_sync as tps  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "tailscale"
GOOD = (FIXTURES / "good-policy.hujson").read_text()
GUARD_TEXT = (FIXTURES / "lockout-guard.json").read_text()
GUARD = json.loads(GUARD_TEXT)
SHA = "a" * 40
CLOCK0 = 1_700_000_000.0  # 2023-11-14T22:13:20Z

NEW_GRANT = {"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"]}
NEW_TEST = {"src": "203.0.113.10", "accept": ["203.0.113.30:9100"], "proto": "tcp"}


def parsed() -> dict:
    return copy.deepcopy(tps.parse_hujson(GOOD))


def text(policy: dict) -> str:
    return json.dumps(policy, indent=1)


def with_change(*, grants=(), tests=(), **sections) -> str:
    policy = parsed()
    policy["grants"] = [*policy["grants"], *grants]
    policy["tests"] = [*policy["tests"], *tests]
    policy.update(sections)
    return text(policy)


def decide(desired: str, live: str = GOOD) -> rec.Decision:
    return rec.classify(live, desired, GUARD)


# --- classification ----------------------------------------------------------------------------------------------


def test_identical_is_in_sync_and_comment_only_is_text_only():
    assert decide(GOOD).kind == "in_sync"
    assert decide(GOOD.replace("// scrape", "// scrape (reworded)")).kind == "text_only"


def test_reordered_grants_are_not_a_semantic_change():
    policy = parsed()
    policy["grants"].reverse()
    assert decide(text(policy)).kind == "text_only"


def test_a_guarded_grant_with_its_test_is_additive():
    result = decide(with_change(grants=[NEW_GRANT], tests=[NEW_TEST]))
    assert (result.kind, result.added_grants, result.added_tests, result.reasons) == ("additive", 1, 1, [])


def test_a_new_test_alone_is_additive():
    assert decide(with_change(tests=[NEW_TEST])).kind == "additive"


def test_a_tag_to_tag_grant_is_additive_when_proven():
    grant = {"src": ["tag:monitoring"], "dst": ["tag:db"], "ip": ["tcp:9187"]}
    test = {"src": "tag:monitoring", "accept": ["tag:db:9187"], "proto": "tcp"}
    assert decide(with_change(grants=[grant], tests=[test])).kind == "additive"


def test_a_port_range_needs_both_ends_proven():
    grant = {"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100-9102"]}
    both = {"src": "203.0.113.10", "accept": ["203.0.113.30:9100", "203.0.113.30:9102"], "proto": "tcp"}
    one = {"src": "203.0.113.10", "accept": ["203.0.113.30:9100"], "proto": "tcp"}
    assert decide(with_change(grants=[grant], tests=[both])).kind == "additive"
    assert decide(with_change(grants=[grant], tests=[one])).kind == "blocked"


def blocked_reasons(desired: str) -> str:
    result = decide(desired)
    assert result.kind == "blocked", result
    return " | ".join(result.reasons)


@pytest.mark.parametrize(
    "grant, needle",
    [
        ({"src": ["*"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"]}, "src *"),
        ({"src": ["group:admins"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"]}, "src group:admins"),
        ({"src": ["operator@example.com"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"]}, "operator@example.com"),
        ({"src": ["autogroup:member"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"]}, "autogroup:member"),
        ({"src": ["203.0.113.10/32"], "dst": ["198.51.100.0/24"], "ip": ["tcp:9100"]}, "single IPv4 host"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/31"], "ip": ["tcp:9100"]}, "single IPv4 host"),
        ({"src": ["203.0.113.10/32"], "dst": ["2001:db8::1/128"], "ip": ["tcp:9100"]}, "single IPv4 host"),
        ({"src": ["203.0.113.10/32"], "dst": ["tag:nobody"], "ip": ["tcp:9100"]}, "not defined in tagOwners"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["*"]}, "only explicit"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["9100"]}, "only explicit"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["icmp:*"]}, "only explicit"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:0"]}, "only explicit"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": []}, "ip must list"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:22"]}, "management ports"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:3389"]}, "management ports"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:8006"]}, "management ports"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:20-30"]}, "management ports"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:1000-2500"]}, "spans"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"], "srcPosture": ["x"]}, "unsupported keys"),
        ({"src": ["203.0.113.10/32"], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"], "via": ["tag:db"]}, "unsupported keys"),
        ({"src": [f"203.0.113.{i}/32" for i in range(1, 10)], "dst": ["203.0.113.30/32"], "ip": ["tcp:9100"]}, "max 8"),
        ({"dst": ["203.0.113.30/32"], "ip": ["tcp:9100"]}, "src must be"),
    ],
)
def test_grants_outside_the_guard_are_blocked(grant, needle):
    # a test that "proves" the grant is present, so the reason is the guard, not missing coverage
    test = {"src": "203.0.113.10", "accept": ["203.0.113.30:9100"], "proto": "tcp"}
    assert needle in blocked_reasons(with_change(grants=[grant], tests=[test]))


@pytest.mark.parametrize(
    "test",
    [
        {"src": "203.0.113.11", "accept": ["203.0.113.30:9100"], "proto": "tcp"},  # other source
        {"src": "203.0.113.10", "accept": ["203.0.113.31:9100"], "proto": "tcp"},  # other destination
        {"src": "203.0.113.10", "accept": ["203.0.113.30:9101"], "proto": "tcp"},  # other port
        {"src": "203.0.113.10", "accept": ["203.0.113.30:9100"], "proto": "udp"},  # other protocol
        {"src": "203.0.113.10", "deny": ["203.0.113.30:9100"], "proto": "tcp"},  # asserts the opposite
    ],
)
def test_a_grant_not_proven_by_an_added_test_is_blocked(test):
    assert "no added policy test accepts" in blocked_reasons(with_change(grants=[NEW_GRANT], tests=[test]))


def test_a_pre_existing_test_does_not_prove_a_new_grant():
    existing = {"src": "203.0.113.10", "accept": ["203.0.113.30:9100"], "proto": "tcp"}
    live = text({**parsed(), "tests": [*parsed()["tests"], existing]})
    desired = text({**parsed(), "tests": [*parsed()["tests"], existing], "grants": [*parsed()["grants"], NEW_GRANT]})
    assert "no added policy test accepts" in " ".join(rec.classify(live, desired, GUARD).reasons)


def test_a_removed_grant_or_test_is_blocked():
    policy = parsed()
    policy["grants"] = policy["grants"][:1]
    assert "removes 1 entries from grants" in blocked_reasons(text(policy))
    policy = parsed()
    policy["tests"] = policy["tests"][:1]
    assert "removes 1 entries from tests" in blocked_reasons(text(policy))


# --- a test may move a destination from deny to accept for a grant added in the same change (#539) -------------------

SPIRE_8081 = {"src": ["tag:monitoring"], "dst": ["192.0.2.66/32"], "ip": ["tcp:8081"]}
SPIRE_8082 = {"src": ["tag:monitoring"], "dst": ["192.0.2.66/32"], "ip": ["tcp:8082"]}
CLOSED_8082 = [  # the agent tag and its node by address: :8081 open, :8082 asserted closed
    {"src": "tag:monitoring", "accept": ["192.0.2.66:8081"], "deny": ["192.0.2.66:8082"], "proto": "tcp"},
    {"src": "203.0.113.10", "accept": ["192.0.2.66:8081"], "deny": ["192.0.2.66:8082"], "proto": "tcp"},
]
OPEN_8082 = [{**t, "accept": ["192.0.2.66:8081", "192.0.2.66:8082"]} for t in CLOSED_8082]
for t in OPEN_8082:
    del t["deny"]


def spire_policy(grants, tests) -> str:
    policy = parsed()
    policy["grants"] = [*policy["grants"], *grants]
    policy["tests"] = [*policy["tests"], *tests]
    return text(policy)


SPIRE_LIVE = spire_policy([SPIRE_8081], CLOSED_8082)


def test_539_a_new_grant_that_turns_a_deny_test_into_an_accept_is_additive():
    # #539 (2026-10-21): the canary agent tag gets :8082, and its two tests (by tag and by the node's address) move :8082
    # from deny to accept. On main's reconciler this was "removes 2 entries from tests", blocked for a human apply.
    result = rec.classify(SPIRE_LIVE, spire_policy([SPIRE_8081, SPIRE_8082], OPEN_8082), GUARD)
    assert (result.kind, result.added_grants, result.added_tests, result.reasons) == ("additive", 1, 2, [])


def changed_test(**fields) -> str:
    """#539 with the canary-tag test changed some other way as well (or instead)."""
    first = {**OPEN_8082[0], **fields}
    return spire_policy([SPIRE_8081, SPIRE_8082], [{k: v for k, v in first.items() if v is not None}, OPEN_8082[1]])


@pytest.mark.parametrize(
    "desired, why",
    [
        (changed_test(accept=["192.0.2.66:8082"]), "loses the :8081 accept"),
        (changed_test(accept=["192.0.2.66:8081", "192.0.2.66:8082"], deny=["192.0.2.66:8083"]), "gains a deny"),
        (changed_test(proto="udp"), "changes the protocol"),
        (changed_test(src="tag:db"), "changes the source"),
        (spire_policy([SPIRE_8081], OPEN_8082), "no new grant opens :8082"),
        (spire_policy([SPIRE_8081, {**SPIRE_8082, "ip": ["tcp:8083"]}], OPEN_8082), "the new grant opens another port"),
        (spire_policy([SPIRE_8081, {**SPIRE_8082, "dst": ["192.0.2.67/32"]}], OPEN_8082), "the new grant opens another host"),
        (spire_policy([SPIRE_8081, {**SPIRE_8082, "ip": ["udp:8082"]}], OPEN_8082), "the new grant opens udp, the test is tcp"),
        (spire_policy([SPIRE_8081], [{**t, "deny": []} for t in CLOSED_8082]), "drops a deny without accepting it"),
        (spire_policy([SPIRE_8081], [{**t, "accept": [], "deny": ["192.0.2.66:8081", "192.0.2.66:8082"]} for t in CLOSED_8082]), "accept to deny"),
    ],
)
def test_any_other_change_to_an_existing_test_is_still_a_removal(desired, why):
    reasons = rec.classify(SPIRE_LIVE, desired, GUARD).reasons
    assert any(r.startswith("removes ") and r.endswith(" entries from tests") for r in reasons), (why, reasons)


def test_a_moved_test_proves_only_its_moved_destination_not_its_old_accepts():
    # a second new grant 203.0.113.10 -> :8081 is "accepted" by the moved test only through an accept it already had
    extra = {"src": ["203.0.113.10/32"], "dst": ["192.0.2.66/32"], "ip": ["tcp:8081"]}
    reasons = " | ".join(rec.classify(SPIRE_LIVE, spire_policy([SPIRE_8081, SPIRE_8082, extra], OPEN_8082), GUARD).reasons)
    assert "no added policy test accepts 203.0.113.10 -> 192.0.2.66:8081" in reasons
    assert "entries from tests" not in reasons  # the moves themselves are fine


def test_539_is_applied_unattended(tmp_path):
    h = Harness(tmp_path, spire_policy([SPIRE_8081, SPIRE_8082], OPEN_8082), live=SPIRE_LIVE)
    assert h.run() == 0 and len(h.api.posts) == 1
    assert h.events()[-1]["event"] == "applied" and (h.events()[-1]["grants"], h.events()[-1]["tests"]) == (1, 2)


def test_the_real_539_classifies_as_additive():
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed in this image")
    blobs = [subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"{rev}:config/tailscale/policy.hujson"], capture_output=True, text=True)
             for rev in ("7d2b7433~1", "7d2b7433")]
    if any(b.returncode for b in blobs):
        pytest.skip("needs the private repository's history (not in a shallow clone or the public snapshot)")
    guard = json.loads((REPO_ROOT / "config" / "tailscale" / "lockout-guard.json").read_text())
    result = rec.classify(blobs[0].stdout, blobs[1].stdout, guard)
    assert (result.kind, result.added_grants, result.added_tests) == ("additive", 1, 2)


@pytest.mark.parametrize(
    "section, value",
    [
        ("tagOwners", {"tag:admin": ["group:admins"], "tag:monitoring": ["group:admins"], "tag:db": ["group:admins"], "tag:new": ["group:admins"]}),
        ("groups", {"group:admins": ["operator@example.com", "other@example.com"]}),
        ("autoApprovers", {"routes": {"198.51.100.7/32": ["tag:admin"], "198.51.100.0/24": ["tag:admin"]}}),
        ("ssh", [{"action": "accept", "src": ["tag:admin"], "dst": ["tag:db"], "users": ["root"]}]),
        ("nodeAttrs", [{"target": ["*"], "attr": ["funnel"]}]),
    ],
)
def test_a_changed_non_rule_section_is_blocked(section, value):
    assert f"section {section} differs" in blocked_reasons(with_change(**{section: value}))


def test_a_new_section_is_blocked():
    assert "section ssh differs" in blocked_reasons(with_change(ssh=[{"action": "accept"}]))


def test_dropping_the_lockout_tests_is_blocked_by_the_offline_check():
    policy = parsed()
    policy["tests"] = [t for t in policy["tests"] if t.get("src") != "203.0.113.10"]
    assert "lockout guard" in blocked_reasons(text(policy))


def test_too_many_added_grants_in_one_change_is_blocked():
    grants = [{"src": ["203.0.113.10/32"], "dst": [f"203.0.113.{40 + i}/32"], "ip": ["tcp:9100"]} for i in range(rec.MAX_ADDED_GRANTS + 1)]
    tests = [{"src": "203.0.113.10", "accept": [f"203.0.113.{40 + i}:9100" for i in range(rec.MAX_ADDED_GRANTS + 1)], "proto": "tcp"}]
    assert "adds 6 grants" in blocked_reasons(with_change(grants=grants, tests=tests))


def test_malformed_policy_is_blocked_not_raised():
    assert "not valid HuJSON" in " ".join(rec.classify(GOOD, '{"grants": [', GUARD).reasons)
    assert rec.classify(GOOD, "[]", GUARD).kind == "blocked"


# --- one run -----------------------------------------------------------------------------------------------------


class FakeAPI:
    def __init__(self, live: str, *, validate=(True, "valid"), set_status=200, applies=True):
        self.live, self.etag = live, '"etag-1"'
        self._validate, self.set_status, self.applies = validate, set_status, applies
        self.posts: list[tuple[str, str]] = []

    def get_policy(self):
        return self.live, self.etag

    def validate(self, body):
        return self._validate

    def set_policy(self, body, etag):
        self.posts.append((body, etag))
        if self.set_status == 200 and self.applies:
            self.live, self.etag = body, '"etag-2"'
        return self.set_status, "body"


class FakeSource:
    def __init__(self, desired: str, ci="success", files: dict[str, str] | None = None):
        self.desired, self.ci, self.error = desired, ci, None
        self.files = {rec.SYNC_PATH: "sync tool v1\n", rec.SELF_PATH: "reconciler v1\n", rec.GUARD_PATH: GUARD_TEXT, **(files or {})}

    def head(self):
        if self.error:
            raise tps.SyncError(self.error)
        return SHA

    def file(self, path, sha):
        return self.desired if path == rec.POLICY_PATH else self.files[path]

    def ci_status(self, sha):
        return self.ci


class Harness:
    def __init__(self, tmp_path: Path, desired: str, live: str = GOOD, *, ci="success", apply=True, **api_kwargs):
        self.state_dir, self.textfile_dir = tmp_path / "state", tmp_path / "textfile"
        self.api = FakeAPI(live, **api_kwargs)
        self.source = FakeSource(desired, ci)
        self.notices: list[tuple[str, str]] = []
        self.notify_fn = None  # a test may plug in the real notifier
        self.apply = apply
        self.clock = CLOCK0
        local = tmp_path / "installed"
        local.mkdir()
        self.local = {}
        for repo_path, content in self.source.files.items():
            f = local / Path(repo_path).name
            f.write_text(content)
            self.local[repo_path] = f

    def run(self, now=None) -> int:
        return rec.run_once(
            api_login=lambda: self.api, source=self.source, guard=GUARD, local_files=self.local,
            state_dir=self.state_dir, textfile_dir=self.textfile_dir, apply_enabled=self.apply,
            notify=self.notify_fn or (lambda title, body: self.notices.append((title, body))), now=now or (lambda: self.clock),
        )

    def metrics(self) -> dict[str, float]:
        out = {}
        for line in (self.textfile_dir / "tailscale_policy_reconcile.prom").read_text().splitlines():
            if line and not line.startswith("#"):
                name, value = line.split()
                out[name.removeprefix("tailscale_policy_reconcile_")] = float(value)
        return out

    def state(self) -> dict:
        return rec.load_state(self.state_dir)

    def events(self) -> list[dict]:
        path = self.state_dir / "reconcile" / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


ADDITIVE = with_change(grants=[NEW_GRANT], tests=[NEW_TEST])


def test_in_sync_run_does_nothing_and_reports_it(tmp_path):
    h = Harness(tmp_path, GOOD)
    assert h.run() == 0
    assert h.api.posts == [] and h.notices == []
    m = h.metrics()
    assert (m["in_sync"], m["blocked"], m["pending_apply"], m["look_ok"]) == (1, 0, 0, 1)
    assert m["last_run_timestamp_seconds"] == int(h.clock) and m["last_success_timestamp_seconds"] == int(h.clock)
    assert (h.textfile_dir / "tailscale_policy_reconcile.prom").stat().st_mode & 0o777 == 0o644  # node_exporter must read it


def test_an_additive_change_is_applied_once_with_the_etag_and_a_rollback_copy(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    assert h.run() == 0
    assert h.api.posts == [(ADDITIVE, '"etag-1"')]
    assert [t for t, _ in h.notices] == ["tailnet policy: applied"]
    rollbacks = list((h.state_dir / "rollback").glob("policy.*.hujson"))
    assert len(rollbacks) == 1 and rollbacks[0].read_text() == GOOD
    assert h.state()["applied_count"] == 1 and h.state()["last_applied_sha"] == SHA
    assert [e["event"] for e in h.events()] == ["applied"]
    assert h.metrics()["in_sync"] == 1 and h.metrics()["applied_total"] == 1
    # the next run finds live == git: no second apply, no noise
    assert h.run() == 0 and len(h.api.posts) == 1 and len(h.notices) == 1


def test_report_only_mode_never_applies_and_says_so_once(tmp_path):
    h = Harness(tmp_path, ADDITIVE, apply=False)
    assert h.run() == 0 and h.run() == 0
    assert h.api.posts == []
    assert [t for t, _ in h.notices] == ["tailnet policy: change waiting"]
    assert h.metrics()["pending_apply"] == 1 and h.metrics()["apply_enabled"] == 0


def test_a_pause_file_turns_applying_off(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    (h.state_dir / "reconcile").mkdir(parents=True)
    (h.state_dir / "reconcile" / "PAUSE").write_text("")
    assert h.run() == 0 and h.api.posts == []
    assert h.metrics()["apply_enabled"] == 0


@pytest.mark.parametrize("ci", ["pending", "unknown"])
def test_applying_waits_for_a_green_ci_on_that_commit(tmp_path, ci):
    h = Harness(tmp_path, ADDITIVE, ci=ci)
    assert h.run() == 0 and h.api.posts == []
    assert h.metrics()["pending_apply"] == 1 and h.notices == []
    h.source.ci = "success"
    assert h.run() == 0 and len(h.api.posts) == 1


def test_a_failed_ci_is_never_applied_and_needs_a_human(tmp_path):
    h = Harness(tmp_path, ADDITIVE, ci="failure")
    assert h.run() == 2 and h.api.posts == []
    assert h.metrics()["blocked"] == 1 and [t for t, _ in h.notices] == ["tailnet policy: CI failed"]


def test_a_blocked_change_is_reported_once_and_never_applied(tmp_path):
    removal = parsed()
    removal["grants"] = removal["grants"][:1]
    h = Harness(tmp_path, text(removal))
    assert h.run() == 2 and h.run() == 2
    assert h.api.posts == []
    assert [t for t, _ in h.notices] == ["tailnet policy: needs a human"]
    assert h.metrics()["blocked"] == 1 and h.metrics()["in_sync"] == 0
    assert h.events()[0]["event"] == "blocked"
    # fixed in git -> back in sync: one recovery notice
    h.source.desired = GOOD
    assert h.run() == 0
    assert [t for t, _ in h.notices] == ["tailnet policy: needs a human", "tailnet policy: back in sync"]


def test_the_notice_never_carries_policy_content(tmp_path):
    h = Harness(tmp_path, with_change(grants=[{**NEW_GRANT, "src": ["*"]}], tests=[NEW_TEST]))
    h.run()
    body = " ".join(b for _, b in h.notices)
    assert "203.0.113" not in body and "*" not in body


def test_a_modified_installed_tool_blocks_even_an_additive_change(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.source.files[rec.SYNC_PATH] = "sync tool v2 (merged, not yet reviewed and installed)\n"
    assert h.run() == 2 and h.api.posts == []
    assert "differs from git" in json.dumps(h.events()[0]["reasons"])


def test_a_weakened_guard_in_git_blocks_the_change_that_weakens_it(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.source.files[rec.GUARD_PATH] = json.dumps({"required_accept": []})
    assert h.run() == 2 and h.api.posts == []


def test_a_missing_installed_file_blocks(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.local[rec.SELF_PATH].unlink()
    assert h.run() == 2 and h.api.posts == []


def test_the_daily_cap_defers_the_fourth_apply(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    rec.save_state(h.state_dir, {"applied": [h.clock - 60, h.clock - 600, h.clock - 3600], "applied_count": 3})
    assert h.run() == 0 and h.api.posts == []
    assert h.metrics()["pending_apply"] == 1
    h.clock += 86400
    assert h.run() == 0 and len(h.api.posts) == 1


def test_the_cap_deferral_says_so_and_when_the_next_slot_opens(tmp_path, capsys):
    # 2026-10-21: an additive change with a green CI waited 2.5 h and the journal showed nothing but "decision additive":
    # the cap branch printed no line and wrote no event, so a capped run looked exactly like a stuck one.
    h = Harness(tmp_path, ADDITIVE)
    oldest = h.clock - 20 * 3600
    rec.save_state(h.state_dir, {"applied": [oldest, h.clock - 600, h.clock - 60], "applied_count": 3})
    assert h.run() == 0 and h.api.posts == []
    out = capsys.readouterr().out
    assert "daily cap: 3 rule-changing applies in 24h; waits until about 2023-11-15 02:13 UTC" in out
    deferred = [e for e in h.events() if e["event"] == "deferred_cap"]
    assert len(deferred) == 1 and deferred[0]["sha"] == SHA
    assert deferred[0]["waits_until"] == "2023-11-15 02:13 UTC" and deferred[0]["applied_in_window"] == 3
    assert deferred[0]["ts"] == int(h.clock)
    (title, body), = [n for n in h.notices if "daily cap" in n[0]]
    assert "2023-11-15 02:13 UTC" in body


def test_under_the_cap_nothing_is_reported_as_deferred(tmp_path, capsys):
    h = Harness(tmp_path, ADDITIVE)
    rec.save_state(h.state_dir, {"applied": [h.clock - 600, h.clock - 60], "applied_count": 2})
    assert h.run() == 0 and len(h.api.posts) == 1
    assert "daily cap:" not in capsys.readouterr().out
    assert [e for e in h.events() if e["event"] == "deferred_cap"] == []


class _Reply:
    def read(self):
        return b""


def test_a_failed_notice_is_logged_without_the_url_or_the_error_text(monkeypatch, capsys):
    # the notifier is best-effort and must never stop a run, but a wrong or dead channel must not be invisible either
    secret = "https://notify.example.invalid/very-secret-topic-9f3"

    def boom(req, timeout=0):
        raise OSError(f"connection refused to {secret}")

    monkeypatch.setattr(rec.urllib.request, "urlopen", boom)
    rec.ntfy_notifier(secret)("tailnet policy: daily cap", "body")  # must not raise
    err = capsys.readouterr().err
    assert "notice failed" in err and "OSError" in err and "daily cap" in err
    assert "HTTP" not in err  # an error without a status says no status
    for leaked in ("very-secret-topic", "notify.example.invalid", "connection refused", "https://"):
        assert leaked not in err


def test_a_notice_refused_with_a_status_logs_the_status_not_the_url(monkeypatch, capsys):
    import urllib.error

    secret = "https://notify.example.invalid/very-secret-topic-9f3"

    def refuse(req, timeout=0):
        raise urllib.error.HTTPError(secret, 404, "Not Found", {}, None)

    monkeypatch.setattr(rec.urllib.request, "urlopen", refuse)
    rec.ntfy_notifier(secret)("tailnet policy: needs a human", "body")
    err = capsys.readouterr().err
    assert "notice failed" in err and "HTTP 404" in err and "needs a human" in err
    assert "very-secret-topic" not in err and "notify.example.invalid" not in err


def test_a_delivered_notice_and_a_missing_channel_print_nothing(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(rec.urllib.request, "urlopen", lambda req, timeout=0: calls.append(req) or _Reply())
    rec.ntfy_notifier("https://notify.example.invalid/t")("title", "body")
    rec.ntfy_notifier(None)("title", "body")
    rec.ntfy_notifier("")("title", "body")
    assert len(calls) == 1
    out, err = capsys.readouterr()
    assert out == "" and err == ""


def _capped(h: Harness, applied: list[float]) -> None:
    rec.save_state(h.state_dir, {"applied": applied, "applied_count": len(applied)})


def test_a_capped_run_says_so_on_every_run_but_the_notice_goes_out_once(tmp_path, capsys):
    # the incident was a run that said nothing, run after run: the line and the event must not be tied to the notice
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
    for _ in range(3):
        assert h.run() == 0
        h.clock += 900
    assert capsys.readouterr().out.count("daily cap:") == 3
    assert len([e for e in h.events() if e["event"] == "deferred_cap"]) == 3
    assert len([n for n in h.notices if "daily cap" in n[0]]) == 1 and h.api.posts == []


def test_an_apply_older_than_24h_is_not_counted_for_the_slot(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 30 * 3600, h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
    assert h.run() == 0 and h.api.posts == []
    (event,) = [e for e in h.events() if e["event"] == "deferred_cap"]
    assert event["waits_until"] == "2023-11-15 02:13 UTC" and event["applied_in_window"] == 3  # the 30 h old one is not counted


def test_with_more_applies_than_the_cap_the_slot_is_when_the_count_drops_below_it(tmp_path):
    # reachable after a clock step back or a hand-edited state: 4 inside the window, cap 3, so TWO must age out
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 23 * 3600, h.clock - 3600, h.clock - 600, h.clock - 60])
    assert h.run() == 0
    (event,) = [e for e in h.events() if e["event"] == "deferred_cap"]
    free_at = h.clock - 3600 + 86400
    assert event["waits_until"] == time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(free_at)) and event["applied_in_window"] == 4
    h.clock = free_at + 1
    assert h.run() == 0 and len(h.api.posts) == 1  # and it really is free then


def test_the_slot_is_printed_in_utc_whatever_the_host_timezone(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TZ", "XXX-14")  # POSIX form, UTC+14, no tz database needed: a localtime() bug cannot hide on a UTC host
    time.tzset()
    try:
        assert time.localtime(CLOCK0).tm_hour != time.gmtime(CLOCK0).tm_hour  # the zone took effect, or this test proves nothing
        h = Harness(tmp_path, ADDITIVE)
        _capped(h, [h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
        assert h.run() == 0
    finally:
        monkeypatch.undo()
        time.tzset()
    assert "waits until about 2023-11-15 02:13 UTC" in capsys.readouterr().out


class _DeadStream:
    def write(self, data):
        raise OSError(28, "No space left on device")

    def flush(self):
        raise OSError(28, "No space left on device")


def test_reporting_can_never_stop_a_run_even_with_a_dead_stderr(tmp_path, monkeypatch):
    # observability must not turn a successful apply into an exception that skips the state save and the metrics
    def boom(req, timeout=0):
        raise OSError("down")

    monkeypatch.setattr(rec.urllib.request, "urlopen", boom)
    monkeypatch.setattr(sys, "stderr", _DeadStream())
    assert rec.ntfy_notifier("https://notify.example.invalid/t")("tailnet policy: applied", "body") is None
    h = Harness(tmp_path, ADDITIVE)
    h.notify_fn = rec.ntfy_notifier("https://notify.example.invalid/t")
    assert h.run() == 0 and len(h.api.posts) == 1
    assert h.state()["applied"] == [int(h.clock)] and h.metrics()["applied_total"] == 1


def test_an_unwritable_events_log_does_not_turn_a_deferral_into_a_crash(tmp_path, capsys):
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
    (h.state_dir / "reconcile" / "events.jsonl").mkdir()  # a directory where the log file should be: every append fails
    assert h.run() == 0 and h.api.posts == []
    assert any("daily cap" in title for title, _ in h.notices) and h.metrics()["pending_apply"] == 1
    assert h.state()["notified"].startswith("cap:")
    out, err = capsys.readouterr()
    assert "daily cap:" in out  # the line does not depend on the event
    assert "audit event not written (IsADirectoryError): deferred_cap" in err


@pytest.mark.parametrize("bad", [float("inf"), 1e300, 1e19])
def test_absurd_timestamps_in_the_state_do_not_crash_the_deferral(tmp_path, bad, capsys):
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [bad, bad, bad])
    assert h.run() == 0 and h.api.posts == []
    assert "daily cap:" in capsys.readouterr().out and "an unknown time" in [n for n in h.notices if "daily cap" in n[0]][0][1]
    assert h.metrics()["pending_apply"] == 1


def test_the_deferral_report_survives_a_dead_stdout(tmp_path, monkeypatch):
    t = 1_700_000_000.0
    state = {"applied": [t - 20 * 3600, t - 600, t - 60]}
    monkeypatch.setattr(sys, "stdout", _DeadStream())
    rec._report_deferral(state, tmp_path, SHA, "2023-11-15 02:13 UTC", t)  # must not raise
    monkeypatch.undo()
    events = (tmp_path / "reconcile" / "events.jsonl").read_text()
    assert "deferred_cap" in events and "2023-11-15 02:13 UTC" in events


T0 = CLOCK0


@pytest.mark.parametrize("applied, want", [
    ([], "now"),
    ([T0 - 600, T0 - 60], "now"),                                                    # under the cap: nothing to wait for
    ([T0 - 20 * 3600, T0 - 600, T0 - 60], "2023-11-15 02:13 UTC"),                   # at the cap: when the oldest ages out
    ([T0 - 30 * 3600, T0 - 20 * 3600, T0 - 600, T0 - 60], "2023-11-15 02:13 UTC"),   # a 30 h old apply is not counted
    ([T0 - 23 * 3600, T0 - 3600, T0 - 600, T0 - 60], "2023-11-15 21:13 UTC"),        # over the cap: the (n-c+1)-th oldest
    ([float("inf")] * 3, "an unknown time"),                                         # hostile state.json: never raise
    ([1e300] * 3, "an unknown time"),
    (["x", "y", "z"], "an unknown time"),
    ([T0 - 60, T0 - 20 * 3600, T0 - 600], "2023-11-15 02:13 UTC"),                   # unsorted input (a clock step back appends out of order)
    ([T0 - 30 * 3600, T0 - 29 * 3600, T0 - 600, T0 - 60], "now"),                    # the window filter matters: only 2 are inside it
    (["x", T0 - 600, T0 - 60], "an unknown time"),                                   # one unreadable entry still counts, so 3 at the cap
    (["x", T0 - 600], "now"),                                                        # ... and under the cap there is nothing to wait for
])
def test_next_slot(applied, want):
    assert rec._next_slot({"applied": applied}, T0) == want


# --- review round 2 (2026-10-21): what an independent review of the first version found ---------------------------
#
# A hand-edited or damaged state.json must hold the cap (fail closed), never crash the run before the notice, the metrics and the
# state save; an audit line or a print that fails AFTER the tailnet was changed must not lose the apply; an integrity block must say
# what to do; and the leak and "once per state change" claims need tests that fail when they are broken.

HOSTILE_APPLIED = [
    ["x", "y", "z"], "abc", "", {}, {"a": 1}, None, 5, [None] * 3, [[1], [2], [3]], [10**400] * 3, [float("nan")] * 3, [True] * 3,
    [float("inf")] * 3, [1e300] * 3, False, [1e18] * 3,
]
HOSTILE_IDS = ["strings", "str", "empty-str", "empty-dict", "dict", "null", "int", "nulls", "nested", "huge-int", "nan", "bools", "inf", "1e300",
               "false", "beyond-gmtime"]


@pytest.mark.parametrize("bad", HOSTILE_APPLIED, ids=HOSTILE_IDS)
def test_unreadable_applied_counts_as_the_cap_being_spent(bad):
    assert rec._applies_today({"applied": bad}, T0) >= rec.MAX_APPLIES_PER_DAY
    assert rec._next_slot({"applied": bad}, T0) == "an unknown time"


def test_an_apply_exactly_24h_old_is_out_of_the_window_and_one_second_younger_is_in():
    assert rec._applies_today({"applied": [T0 - 86400] * 3}, T0) == 0
    assert rec._applies_today({"applied": [T0 - 86399] * 3}, T0) == 3
    assert rec._next_slot({"applied": [T0 - 86400, T0 - 600, T0 - 60]}, T0) == "now"
    assert rec._next_slot({"applied": [T0 - 86399, T0 - 600, T0 - 60]}, T0) == "2023-11-14 22:13 UTC"  # frees in 1 s, floored to the minute


def test_one_unreadable_entry_counts_and_a_missing_field_is_empty():
    assert rec._applies_today({"applied": ["x", T0 - 600, T0 - 60]}, T0) == 3
    assert rec._applies_today({"applied": [T0 - 30 * 3600, "x"]}, T0) == 1  # an aged-out entry is not counted, garbage is
    assert rec._applies_today({}, T0) == 0 and rec._next_slot({}, T0) == "now"


@pytest.mark.parametrize("bad", HOSTILE_APPLIED, ids=HOSTILE_IDS)
def test_a_hand_edited_applied_field_holds_the_cap_instead_of_crashing_the_run(tmp_path, bad, capsys):
    h = Harness(tmp_path, ADDITIVE)
    rec.save_state(h.state_dir, {"applied": bad, "applied_count": 3})
    assert h.run() == 0 and h.api.posts == []  # held back, never applied, and no traceback
    assert "daily cap:" in capsys.readouterr().out
    (title, body), = [n for n in h.notices if "daily cap" in n[0]]
    assert "an unknown time" in body
    assert h.metrics()["pending_apply"] == 1 and h.state()["notified"].startswith("cap:")
    assert [e["waits_until"] for e in h.events() if e["event"] == "deferred_cap"] == ["an unknown time"]


def test_a_text_only_apply_never_reads_the_applied_field(tmp_path):
    reworded = GOOD.replace("// scrape", "// scrape (reworded)")
    h = Harness(tmp_path, reworded)
    h.api = FakeTailscale(GOOD)
    rec.save_state(h.state_dir, {"applied": "garbage", "applied_count": 3})
    assert h.run() == 0 and h.api.posts == [reworded]


def test_an_audit_event_that_cannot_be_written_after_an_apply_does_not_lose_the_apply(tmp_path, capsys):
    # live was changed by the POST; an exception from the audit line used to skip the state save, so the apply was never counted
    # against the cap and the next run read the new ETag as a change from outside
    h = Harness(tmp_path, ADDITIVE)
    rec.save_state(h.state_dir, {"live_etag": '"etag-1"', "applied": [], "applied_count": 0})
    (h.state_dir / "reconcile").mkdir(parents=True, exist_ok=True)
    (h.state_dir / "reconcile" / "events.jsonl").mkdir()  # a directory where the log file should be: every append fails
    assert h.run() == 0 and len(h.api.posts) == 1
    state = h.state()
    assert state["applied"] == [int(h.clock)] and state["applied_count"] == 1 and state["live_etag"] == '"etag-2"'
    assert h.metrics()["applied_total"] == 1 and [t for t, _ in h.notices] == ["tailnet policy: applied"]
    err = capsys.readouterr().err
    assert err == "reconcile: audit event not written (IsADirectoryError): applied\n"  # class and event name only, no path, no error text
    assert h.run() == 0 and h.metrics()["in_sync"] == 1 and len(h.api.posts) == 1  # no false alarm, nothing applied twice


class _DiesOn:
    """A stdout that works until a given text is written to it (a closed pipe in the middle of a run)."""

    def __init__(self, needle):
        self.needle = needle

    def write(self, data):
        if self.needle in data:
            raise OSError(32, "Broken pipe")
        return len(data)

    def flush(self):
        pass


def test_stdout_dying_right_after_the_post_does_not_lose_the_apply(tmp_path, monkeypatch):
    h = Harness(tmp_path, ADDITIVE)
    monkeypatch.setattr(sys, "stdout", _DiesOn("  applied; new etag"))
    assert h.run() == 0 and len(h.api.posts) == 1
    assert h.state()["applied"] == [int(h.clock)] and h.metrics()["applied_total"] == 1


def test_the_best_effort_helpers_never_raise_on_dead_streams(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", _DeadStream())
    monkeypatch.setattr(sys, "stderr", _DeadStream())
    rec._say("x")
    rec._say("x", err=True)
    (tmp_path / "reconcile").mkdir()
    (tmp_path / "reconcile" / "events.jsonl").mkdir()
    assert rec._log_best_effort(tmp_path, {"event": "applied"}, CLOCK0) is False  # the failure is reported on a dead stderr, quietly
    monkeypatch.undo()
    assert rec._log_best_effort(tmp_path / "ok", {"event": "applied"}, CLOCK0) is True


def _integrity_problem(h: Harness, kind: str) -> None:
    if kind == "differs":
        h.source.files[rec.SYNC_PATH] = "sync tool v2 (merged, not yet reviewed and installed)\n"
    elif kind == "missing":  # in production only a race or an unreadable file gets here: a missing guard or sync tool stops the run earlier
        h.local[rec.SELF_PATH].unlink()
    else:  # git cannot be read for that file (a transient failure of the lazy blob fetch)
        real = h.source.file

        def file(path, sha):
            if path == rec.GUARD_PATH:
                raise tps.SyncError("git: could not read the blob")
            return real(path, sha)

        h.source.file = file


@pytest.mark.parametrize("kind", ["differs", "missing", "unreadable-in-git"])
@pytest.mark.parametrize("desired", ["in_sync", "additive", "text_only"])
def test_an_integrity_block_names_the_installer_whatever_the_policy_and_the_problem(tmp_path, desired, kind):
    wanted = {"in_sync": GOOD, "additive": ADDITIVE, "text_only": GOOD.replace("// scrape", "// scrape (reworded)")}[desired]
    h = Harness(tmp_path, wanted)  # in_sync: live equals git, there is nothing to plan
    _integrity_problem(h, kind)
    assert h.run() == 2 and h.api.posts == []
    (title, body), = h.notices
    assert title == "tailnet policy: needs a human"
    assert "scripts/tailscale-policy-reconcile-install.sh" in body and SHA[:12] in body
    assert "checkout" in body and "named in the journal" in body  # where to run it from, and where the exact problem is
    assert "on CT108" not in body  # the installer runs from a checkout and installs onto CT108; it cannot be run there
    assert "tailscale-policy-ct108.sh" not in body and "differs from live" not in body
    assert "differ from git" not in body  # one problem class is a git read failure, not a difference


# --- review round 3: wrong-typed state fields, a re-read that fails after the POST --------------------------------


WRONG_TYPED = [
    ("applied_count", "x"), ("applied_count", None), ("applied_count", [3]), ("applied_count", True), ("applied_count", 1.5),
    ("applied_count", float("nan")), ("applied_count", -1), ("applied_count", 10**309),  # a literal too big for a float64 is a 1e309 sample
    ("failures", "x"), ("failures", [1]), ("failures", {"policy": "p", "count": "many"}), ("failures", {"count": 1.5}),
    ("failures", {"count": 10**309}),
    ("out_of_band", "x"), ("out_of_band", [1]), ("out_of_band", 5), ("out_of_band", {"unknown": "x"}), ("out_of_band", {"unknown": True}),
    ("out_of_band", {"sync_tool": 1, "unknown": "x"}), ("out_of_band", {"unknown": 10**309}),  # one good entry does not excuse a bad one
    ("out_of_band_last", "x"), ("out_of_band_last", [1]), ("out_of_band_last", float("nan")), ("out_of_band_last", float("inf")),
    ("out_of_band_last", float("-inf")), ("out_of_band_last", 10**309),
    ("last_success", "x"), ("last_success", [1]), ("last_success", True), ("last_success", float("inf")),  # inf would blind the dead-man alert
    ("last_success", float("-inf")), ("last_success", 10**309),
    ("live_etag", 5), ("live_etag", ["a"]), ("notified", 5), ("notified", ["a"]), ("unconverged", 5),
    ("last_sha", 5), ("last_applied_sha", ["a"]),
]


@pytest.mark.parametrize("key, bad", WRONG_TYPED, ids=[f"{k}={type(v).__name__}{i}" for i, (k, v) in enumerate(WRONG_TYPED)])
def test_a_wrong_typed_state_field_is_reset_and_the_apply_is_still_saved(tmp_path, capsys, key, bad):
    # these used to crash AFTER the tailnet POST (applied_count, out_of_band) or before it: the apply was then never counted
    h = Harness(tmp_path, ADDITIVE)
    rec.save_state(h.state_dir, {"applied": [], key: bad})
    assert h.run() == 0 and len(h.api.posts) == 1
    state = h.state()
    assert state["applied"] == [int(h.clock)] and state["applied_count"] == 1 and h.metrics()["applied_total"] == 1
    err = capsys.readouterr().err
    assert f"reconcile: state.json field {key} had the wrong type ({type(bad).__name__}) and was reset\n" in err  # the type, never the value


def test_a_wrong_typed_applied_count_cannot_lift_the_cap(tmp_path):
    # measured on the first version: 5 additive policies in 50 minutes were all applied although the cap is 3
    h = Harness(tmp_path, ADDITIVE)
    h.api = FakeTailscale(GOOD)
    rec.save_state(h.state_dir, {"applied_count": "x"})
    for i in range(5):
        h.source.desired = policy_with(GOOD, "".join(grant_block("203.0.113.10", f"203.0.113.{30 + j}", 9100) for j in range(i + 1)),
                                       "".join(policy_test("203.0.113.10", f"203.0.113.{30 + j}:9100") for j in range(i + 1)))
        assert h.run() == 0
        h.clock += 600
    assert len(h.api.posts) == rec.MAX_APPLIES_PER_DAY and h.metrics()["pending_apply"] == 1


def test_a_state_the_reconciler_wrote_itself_is_never_touched(tmp_path, capsys):
    # the validation must have no false positives: failure count, apply, out-of-band change, blocked run
    h = Harness(tmp_path, ADDITIVE, validate=(False, "HTTP 400: test failed"))
    assert h.run() == 1  # failures.count 1
    h.api._validate = (True, "valid")
    assert h.run() == 0  # applied
    h.api.etag = '"etag-9"'  # a change from outside
    h.source.desired = text({**parsed(), "grants": parsed()["grants"][:1]})  # a removal: blocked
    assert h.run() == 2
    raw = json.loads((h.state_dir / "reconcile" / "state.json").read_text())
    assert {"applied", "applied_count", "failures", "live_etag", "notified", "last_sha", "last_applied_sha", "last_success", "out_of_band",
            "out_of_band_last"} <= set(raw)
    assert rec.load_state(h.state_dir) == raw
    assert "had the wrong type" not in capsys.readouterr().err


class _RereadFails(FakeAPI):
    """get_policy answers once, then raises what a real transport raises when the answer to the verifying GET never comes."""

    def __init__(self, live, exc):
        super().__init__(live)
        self.exc, self.reads = exc, 0

    def get_policy(self):
        self.reads += 1
        if self.reads > 1:
            raise self.exc
        return super().get_policy()


@pytest.mark.parametrize("exc", [
    TimeoutError("read timed out"), ConnectionResetError(104, "reset"), http.client.IncompleteRead(b"x"), http.client.RemoteDisconnected("closed"),
    http.client.BadStatusLine("x"), urllib.error.URLError("down"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
], ids=lambda e: type(e).__name__)
def test_a_re_read_that_fails_after_the_post_does_not_lose_the_apply(tmp_path, exc):
    # urllib wraps only request errors: a timeout or a dropped connection while reading the answer is not a SyncError, and it
    # used to skip the state save (apply never counted, the new ETag read as a change from outside on the next run)
    h = Harness(tmp_path, ADDITIVE)
    h.api = _RereadFails(GOOD, exc)
    assert h.run() == 1  # the apply landed but could not be verified: the same exit as a failed verification
    state = h.state()
    assert state["applied"] == [int(h.clock)] and state["applied_count"] == 1 and state["live_etag"] is None
    assert h.metrics()["applied_total"] == 1 and "tailnet policy: applied" in [t for t, _ in h.notices]
    (event,) = [e for e in h.events() if e["event"] == "applied"]
    assert event["post_apply_diff"] == [f"could not re-read the live policy: {type(exc).__name__}"]  # the class, never the message
    assert event["etag_after"] == "?"


class _RereadUnparsable(FakeAPI):
    """The verifying GET succeeds (200, a real ETag) but the body is not a policy (a proxy error page, a truncated body)."""

    def __init__(self, live):
        super().__init__(live)
        self.reads = 0

    def get_policy(self):
        self.reads += 1
        if self.reads > 1:
            return "this is not hujson {", '"etag-2"'
        return super().get_policy()


def test_a_re_read_that_returns_an_unparsable_body_keeps_the_etag_it_returned(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.api = _RereadUnparsable(GOOD)
    assert h.run() == 1
    assert h.state()["live_etag"] == '"etag-2"' and h.state()["applied"] == [int(h.clock)]  # known, so no "?" and no false alarm next run
    (event,) = [e for e in h.events() if e["event"] == "applied"]
    assert event["etag_after"] == '"etag-2"' and event["post_apply_diff"][0].startswith("could not re-read the live policy: ")
    h.clock += 900
    h.api.live = "unchanged after the apply"  # the next run reads the same ETag again: nothing happened outside
    h.api.reads = 0
    h.api.etag = '"etag-2"'
    h.api.get_policy = lambda: ("this is not hujson {", '"etag-2"')
    h.run()
    assert [t for t, _ in h.notices if "outside" in t] == [] and "out_of_band" not in h.state()


def test_a_re_read_that_fails_with_our_own_error_shows_its_message(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.api = _RereadFails(GOOD, tps.SyncError("GET /acl: HTTP 502"))
    assert h.run() == 1
    (event,) = [e for e in h.events() if e["event"] == "applied"]
    assert event["post_apply_diff"] == ["could not re-read the live policy: GET /acl: HTTP 502"]  # a SyncError's text is ours to show


@pytest.mark.parametrize("junk", ["{", "", "[]", "null", "3", '"x"', "[1, 2]", "true"])
def test_a_state_file_that_is_not_a_json_object_is_read_as_empty_so_the_cap_starts_over(tmp_path, junk):
    # a documented limit (runbook), pinned so that changing it is a decision: the next run is a fresh start
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
    (h.state_dir / "reconcile" / "state.json").write_text(junk)
    assert h.run() == 0 and len(h.api.posts) == 1


def test_a_log_event_that_cannot_be_serialised_is_reported_not_raised(tmp_path, capsys):
    assert rec._log_best_effort(tmp_path, {"event": "x", "bad": object()}, CLOCK0) is False
    assert capsys.readouterr().err == "reconcile: audit event not written (TypeError): x\n"


def test_a_policy_block_still_points_at_the_plan(tmp_path):
    removal = parsed()
    removal["grants"] = removal["grants"][:1]
    h = Harness(tmp_path, text(removal))
    assert h.run() == 2
    (title, body), = h.notices
    assert "tailscale-policy-ct108.sh plan" in body and "differs from live" in body and "install.sh" not in body


def test_an_integrity_problem_together_with_a_policy_block_still_points_at_the_plan(tmp_path):
    removal = parsed()
    removal["grants"] = removal["grants"][:1]
    h = Harness(tmp_path, text(removal))
    h.source.files[rec.SYNC_PATH] = "sync tool v2 (merged, not yet reviewed and installed)\n"
    assert h.run() == 2
    (title, body), = h.notices
    assert "tailscale-policy-ct108.sh plan" in body and "the live policy is not the problem" not in body
    assert "2 reason(s)" in body  # the installed-copy reason and the removal


def test_the_cap_test_the_slot_and_the_event_read_one_clock_value(tmp_path, monkeypatch):
    # the cap gate, the printed slot and the logged count must describe the same instant: an apply ageing out between three
    # separate clock reads would print "waits until about now" for a run that was held back
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
    seen: list[tuple[str, float]] = []

    def spy(name, time_arg_index):
        real = getattr(rec, name)

        def wrapper(*a, **k):
            seen.append((name, a[time_arg_index]))
            return real(*a, **k)

        monkeypatch.setattr(rec, name, wrapper)

    spy("_applies_today", 1)
    spy("_next_slot", 1)
    spy("_report_deferral", 4)
    ticks = iter(range(10**6))
    assert h.run(now=lambda: h.clock + next(ticks)) == 0  # every read of the clock gives a different value
    assert {n for n, _ in seen} == {"_applies_today", "_next_slot", "_report_deferral"}
    assert len({t for _, t in seen}) == 1


NEW_POLICY_2 = with_change(grants=[NEW_GRANT, {**NEW_GRANT, "dst": ["203.0.113.31/32"]}], tests=[NEW_TEST, {**NEW_TEST, "accept": ["203.0.113.31:9100"]}])


def test_applied_keeps_the_last_20_entries_and_an_unreadable_one_falls_off_after_20_applies(tmp_path):
    day = 86400
    h = Harness(tmp_path, ADDITIVE)
    rec.save_state(h.state_dir, {"applied": [h.clock - (30 + i) * day for i in range(25)], "applied_count": 25})
    assert h.run() == 0 and len(h.api.posts) == 1
    kept = h.state()["applied"]
    assert len(kept) == 20 and kept[-1] == int(h.clock)  # the runbook's "20 entries kept"
    (tmp_path / "second").mkdir()
    h2 = Harness(tmp_path / "second", ADDITIVE)
    rec.save_state(h2.state_dir, {"applied": ["x"] + [h2.clock - (30 + i) * day for i in range(19)], "applied_count": 19})
    assert h2.run() == 0 and len(h2.api.posts) == 1  # one unreadable entry lowers the cap to 2, it does not stop an apply
    assert "x" not in h2.state()["applied"] and len(h2.state()["applied"]) == 20  # the 20th apply pushes it out


def test_the_integrity_notice_counts_the_problems_not_the_notes_of_the_decision(tmp_path):
    # an in_sync decision can carry a note of its own (git's text is not in Tailscale's stored form): it is not a problem
    h = Harness(tmp_path, WRITTEN_526)
    h.api = FakeTailscale(WRITTEN_526)
    _integrity_problem(h, "differs")
    assert h.run() == 2
    (_, body), = h.notices
    assert "(1 problem(s)" in body


def test_the_integrity_notice_counts_the_problems_and_says_a_git_read_failure_is_usually_transient(tmp_path):
    h = Harness(tmp_path, GOOD)
    _integrity_problem(h, "differs")
    _integrity_problem(h, "missing")
    assert h.run() == 2
    (_, body), = h.notices
    assert "(2 problem(s)" in body and "usually transient" in body


def test_the_cap_notice_goes_out_once_across_unrelated_commits_and_again_for_a_new_policy(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
    assert h.run() == 0
    for i in range(3):
        h.source.head = lambda i=i: f"{i:040x}"  # main moves, the policy does not
        assert h.run() == 0
    assert [t for t, _ in h.notices] == ["tailnet policy: daily cap"]
    h.source.desired = NEW_POLICY_2  # a genuinely different waiting policy is announced again
    assert h.run() == 0
    assert [t for t, _ in h.notices] == ["tailnet policy: daily cap"] * 2


def test_the_cap_notice_body_says_how_many_which_commit_and_when(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    _capped(h, [h.clock - 20 * 3600, h.clock - 600, h.clock - 60])
    assert h.run() == 0
    (_, body), = h.notices
    assert body == (f"3 applies in 24h; {SHA[:12]} waits until about 2023-11-15 02:13 UTC. "
                    "A hand apply in the meantime is detected and alerted.")


# What urllib really raises reaches the notifier in several shapes; none may put the URL (the topic is the secret) or an error text
# into the journal, and every one must print the same one-line shape. Real transport errors wrap the OS error and are raised inside
# an `except` block (so they carry __context__ and __cause__).
SECRET_URL = "https://notify.example.invalid/very-secret-topic-9f3"


class _CodeIs(Exception):
    def __init__(self, code):
        super().__init__(f"failed for {SECRET_URL}")
        self.code = code


class _CodeRaises(Exception):
    @property
    def code(self):
        raise RuntimeError(SECRET_URL)


def _raise_url_error():
    raise urllib.error.URLError(OSError(f"tunnel to {SECRET_URL} failed"))


def _raise_inside_except():
    try:
        raise OSError(f"connection refused to {SECRET_URL}")
    except OSError:
        raise urllib.error.URLError("proxy failed")  # noqa: B904


NOTICE_SHAPES = [
    (_raise_url_error, "URLError"),
    (_raise_inside_except, "URLError"),
    (lambda: (_ for _ in ()).throw(ValueError(SECRET_URL)), "ValueError"),
    (lambda: (_ for _ in ()).throw(RuntimeError(SECRET_URL)), "RuntimeError"),
    (lambda: (_ for _ in ()).throw(KeyError(SECRET_URL)), "KeyError"),
    (lambda: (_ for _ in ()).throw(_CodeIs("404")), "_CodeIs"),  # a code that is not an int is not printed
    (lambda: (_ for _ in ()).throw(_CodeIs(True)), "_CodeIs"),
    (lambda: (_ for _ in ()).throw(_CodeIs(503)), "_CodeIs HTTP 503"),
    (lambda: (_ for _ in ()).throw(_CodeRaises()), "_CodeRaises"),  # a code that cannot even be read still gets its line
]


@pytest.mark.parametrize("raiser, label", NOTICE_SHAPES, ids=[label + str(i) for i, (_, label) in enumerate(NOTICE_SHAPES)])
def test_a_failed_notice_prints_one_fixed_line_for_every_exception_shape(monkeypatch, capsys, raiser, label):
    def boom(req, timeout=0):
        raiser()

    monkeypatch.setattr(rec.urllib.request, "urlopen", boom)
    assert rec.ntfy_notifier(SECRET_URL)("tailnet policy: daily cap", "body") is None
    out, err = capsys.readouterr()
    assert out == "" and err == f"reconcile: notice failed ({label}): tailnet policy: daily cap\n"
    for leaked in ("very-secret-topic", "notify.example.invalid", "https://", "tunnel", "refused"):
        assert leaked not in err


def test_a_placeholder_instead_of_a_url_is_reported_without_echoing_it(capsys):
    # the real urllib, no network: Request() itself rejects a value that is not a URL (this happened with a pasted placeholder)
    rec.ntfy_notifier("<your https ntfy topic URL>")("tailnet policy: daily cap", "body")
    out, err = capsys.readouterr()
    assert out == "" and err == "reconcile: notice failed (ValueError): tailnet policy: daily cap\n"


def test_validate_failure_is_counted_and_the_circuit_opens_for_that_policy(tmp_path):
    h = Harness(tmp_path, ADDITIVE, validate=(False, "HTTP 400: test failed"))
    assert h.run() == 1 and h.run() == 1
    failures = h.state()["failures"]
    assert failures["count"] == 2 and failures["sha"] == SHA and failures["policy"]
    assert h.api.posts == []
    assert h.run() == 2  # circuit open: not even a validate any more
    assert [t for t, _ in h.notices][-1] == "tailnet policy: reconcile stopped"
    # main takes unrelated commits all day: the SAME policy on a new commit must not reopen the circuit
    h.source.head = lambda: "b" * 40
    assert h.run() == 2 and h.state()["failures"]["count"] == 2
    # a different policy is a new thing to try
    h.source.desired = with_change(grants=[NEW_GRANT, {**NEW_GRANT, "dst": ["203.0.113.31/32"]}], tests=[NEW_TEST, {**NEW_TEST, "accept": ["203.0.113.31:9100"]}])
    assert h.run() == 1 and h.state()["failures"]["count"] == 1


def test_an_etag_race_is_retried_without_counting_a_failure(tmp_path):
    h = Harness(tmp_path, ADDITIVE, set_status=412)
    assert h.run() == 0
    assert h.state().get("failures", {}) == {} and h.metrics()["pending_apply"] == 1
    h.api.set_status = 200
    assert h.run() == 0 and h.api.live == ADDITIVE


def test_a_refused_apply_is_a_failure_with_live_unchanged(tmp_path):
    h = Harness(tmp_path, ADDITIVE, set_status=500)
    assert h.run() == 1
    assert h.state()["failures"]["count"] == 1 and h.api.live == GOOD
    assert [t for t, _ in h.notices] == ["tailnet policy: apply failed"]


def test_a_post_apply_difference_is_reported_as_a_failure(tmp_path):
    h = Harness(tmp_path, ADDITIVE, applies=False)  # 200 but the live policy did not change
    assert h.run() == 1
    assert h.metrics()["in_sync"] == 0
    assert h.events()[-1]["post_apply_diff"]


def test_not_being_able_to_look_is_exit_3_and_changes_nothing(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.source.error = "git fetch failed: network"
    assert h.run() == 3 and h.api.posts == []
    assert h.metrics()["look_ok"] == 0 and h.events()[0]["event"] == "could_not_look"


def test_text_only_difference_is_applied_after_ci(tmp_path):
    h = Harness(tmp_path, GOOD.replace("// scrape", "// scrape (reworded)"))
    assert h.run() == 0 and len(h.api.posts) == 1


# --- git and CI sources ------------------------------------------------------------------------------------------


def test_repo_slug_accepts_https_and_ssh_forms_and_rejects_others():
    assert rec.repo_slug("https://github.com/example-org/example-repo.git") == "example-org/example-repo"
    assert rec.repo_slug("git@github.com:example-org/example-repo") == "example-org/example-repo"
    with pytest.raises(tps.SyncError):
        rec.repo_slug("https://example.com/x/y.git")


def completed(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


@pytest.mark.parametrize(
    "statuses, rc, want",
    [
        ([{"context": rec.CI_CONTEXT, "state": "success"}], 0, "success"),
        ([{"context": rec.CI_CONTEXT, "state": "pending"}], 0, "pending"),
        ([{"context": rec.CI_CONTEXT, "state": "failure"}], 0, "failure"),
        ([{"context": rec.CI_CONTEXT, "state": "error"}], 0, "failure"),
        ([{"context": "ci/other", "state": "success"}], 0, "unknown"),
        ([], 0, "unknown"),
        ([], 1, "unknown"),
    ],
)
def test_ci_status_reads_only_the_required_context(monkeypatch, statuses, rc, want):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return completed(rc, json.dumps({"statuses": statuses}))

    monkeypatch.setattr(rec.subprocess, "run", fake_run)
    src = rec.GitSource(Path("/nonexistent"), "https://github.com/example-org/example-repo.git")
    assert src.ci_status(SHA) == want
    assert seen["cmd"][:2] == ["gh", "api"] and SHA in seen["cmd"][2]


def test_ci_status_is_unknown_when_gh_is_missing_or_output_is_garbage(monkeypatch):
    src = rec.GitSource(Path("/nonexistent"), "https://github.com/example-org/example-repo.git")
    monkeypatch.setattr(rec.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("gh")))
    assert src.ci_status(SHA) == "unknown"
    monkeypatch.setattr(rec.subprocess, "run", lambda *a, **k: completed(0, "not json"))
    assert src.ci_status(SHA) == "unknown"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed in this image")
def test_git_source_reads_a_file_at_a_commit_and_reports_git_errors(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@example.com", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    (repo / "f.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", "f.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@example.com", "-c", "user.name=a", "commit", "-q", "-m", "y"], check=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    src = rec.GitSource(repo, "https://github.com/example-org/example-repo.git")
    assert src.file("f.txt", sha) == "hello\n"
    with pytest.raises(tps.SyncError):
        src.file("missing.txt", sha)


# --- CLI ---------------------------------------------------------------------------------------------------------


def test_reconcile_requires_a_repo_url_and_status_prints_state(tmp_path, capsys, monkeypatch):
    guard = tmp_path / "guard.json"
    guard.write_text(GUARD_TEXT)
    monkeypatch.delenv("FLEET_TS_RECONCILE_REPO_URL", raising=False)
    assert rec.main(["reconcile", "--state-dir", str(tmp_path), "--guard", str(guard)]) == 3
    assert "--repo-url" in capsys.readouterr().err
    rec.save_state(tmp_path, {"last_sha": SHA})
    assert rec.main(["status", "--state-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert SHA in out and "PAUSE: no" in out


def test_the_default_mode_is_report_only():
    assert rec.build_parser().parse_args(["reconcile"]).apply is False


def test_the_real_policy_in_this_checkout_classifies_against_itself_as_in_sync():
    path = REPO_ROOT / "config" / "tailscale" / "policy.hujson"
    guard_path = REPO_ROOT / "config" / "tailscale" / "lockout-guard.json"
    if not path.exists():
        pytest.skip("sanitized snapshot: the real policy is private-repo only")
    real = path.read_text()
    assert rec.classify(real, real, json.loads(guard_path.read_text())).kind == "in_sync"


def test_time_is_injected_not_read_from_the_clock(tmp_path):
    h = Harness(tmp_path, GOOD)
    h.clock = 1234.0
    h.run()
    assert h.metrics()["last_run_timestamp_seconds"] == 1234
    assert abs(time.time() - 1234.0) > 1000


# --- notices follow the policy, not the commit ------------------------------------------------------------------


def test_a_waiting_change_pings_once_across_unrelated_commits(tmp_path):
    h = Harness(tmp_path, ADDITIVE, apply=False)
    assert h.run() == 0
    for i in range(3):
        h.source.head = lambda i=i: f"{i:040x}"  # main moves, the policy does not
        assert h.run() == 0
    assert [t for t, _ in h.notices] == ["tailnet policy: change waiting"]
    # a genuinely different waiting policy is announced again
    h.source.desired = with_change(grants=[NEW_GRANT, {**NEW_GRANT, "dst": ["203.0.113.31/32"]}], tests=[NEW_TEST, {**NEW_TEST, "accept": ["203.0.113.31:9100"]}])
    assert h.run() == 0
    assert [t for t, _ in h.notices] == ["tailnet policy: change waiting"] * 2


def test_a_comment_only_difference_never_pages_in_report_only_mode(tmp_path):
    h = Harness(tmp_path, GOOD.replace("// scrape", "// scrape (reworded)"), apply=False)
    assert h.run() == 0 and h.api.posts == [] and h.notices == []
    assert h.metrics()["pending_apply"] == 1  # still visible in the metrics
    assert h.events()[-1]["event"] == "would_apply"


def test_a_changed_policy_restarts_the_failure_count_even_on_the_same_commit(tmp_path):
    h = Harness(tmp_path, ADDITIVE, validate=(False, "HTTP 400: test failed"))
    assert h.run() == 1 and h.state()["failures"]["count"] == 1
    h.source.desired = with_change(grants=[NEW_GRANT, {**NEW_GRANT, "dst": ["203.0.113.31/32"]}], tests=[NEW_TEST, {**NEW_TEST, "accept": ["203.0.113.31:9100"]}])
    assert h.run() == 1 and h.state()["failures"]["count"] == 1  # a new policy is a new first failure


# --- Tailscale's stored form, the daily cap and changes made outside the reconciler ------------------------------


class FakeTailscale:
    """Behaves as Tailscale did on 2026-10-20 (OBSERVED in the 39 live copies on CT108): it keeps hujson.Format of what
    is posted, and its ETag is the sha256 of that stored text, so re-posting an identical policy keeps the ETag."""

    def __init__(self, text: str, reformat=None):
        self.reformat = reformat or tps.stored_form
        self.posts: list[str] = []
        self.store(text)

    def store(self, text: str) -> None:
        self.live = self.reformat(text)
        self.etag = '"%s"' % tps.sha256(self.live)

    def get_policy(self):
        return self.live, self.etag

    def validate(self, body):
        return True, "valid"

    def set_policy(self, body, etag):
        if etag != self.etag:
            return 412, "precondition failed"
        self.posts.append(body)
        self.store(body)
        return 200, "{}"

    def hand_apply(self, text: str, state_dir: Path | None = None) -> None:
        """A change outside the reconciler; with state_dir it went through tailscale_policy_sync.py apply on CT108."""
        before = self.etag
        self.store(text)
        if state_dir is not None:
            tps.record_apply(state_dir, etag_before=before, etag_after=self.etag, file_sha256=tps.sha256(text), rollback=Path("rollback"))


GRANTS_CLOSE = '\t],\n\n\t"autoApprovers"'  # the fixture's `grants` ends here, `tests` at the end of the file
TESTS_CLOSE = "\t],\n}"


def policy_with(base: str, grants: str = "", tests: str = "") -> str:
    """Raw HuJSON appended to the end of `grants` and `tests`, as a person or the edge-grants job writes it."""
    assert base.count(GRANTS_CLOSE) == 1 and base.count(TESTS_CLOSE) == 1
    return base.replace(GRANTS_CLOSE, grants + GRANTS_CLOSE).replace(TESTS_CLOSE, tests + TESTS_CLOSE)


def grant_block(src: str, dst: str, port: int) -> str:
    return '\t\t{"src": ["%s/32"], "dst": ["%s/32"], "ip": ["tcp:%d"]},\n' % (src, dst, port)


def policy_test(src: str, *accept: str) -> str:
    return '\t\t{"src": "%s", "accept": [%s], "proto": "tcp"},\n' % (src, ", ".join('"%s"' % a for a in accept))


STORED_DIR = REPO_ROOT / "tests" / "fixtures" / "tailscale" / "stored-form"
WRITTEN_526 = (STORED_DIR / "written-like-526.hujson").read_text()


def _526_blocks() -> tuple[str, str]:
    """#526's six grants and three tests exactly as written (one-line nine-port lists), cut out of the fixture."""
    lines = WRITTEN_526.splitlines(keepends=True)
    start = lines.index("\t\t// enrichment pool grants, as #526 wrote them\n") + 1
    end = start + 6 * 5
    tests = [line for line in lines if line.startswith('\t\t{"src": "203.0.113.')]
    return "".join(lines[start:end]), "".join(tests)


def test_live_in_the_stored_form_of_git_is_in_sync_and_never_posted(tmp_path, capsys):
    stored = tps.stored_form(WRITTEN_526)
    assert rec.classify(stored, WRITTEN_526, GUARD).kind == "in_sync"
    h = Harness(tmp_path, WRITTEN_526)
    h.api = FakeTailscale(WRITTEN_526)  # live is what Tailscale kept of git's text
    assert h.run() == 0 and h.api.posts == []
    m = h.metrics()
    assert (m["in_sync"], m["git_stored_form"], m["pending_apply"]) == (1, 0, 0)
    assert "not in Tailscale's stored form" in capsys.readouterr().out


def test_git_in_the_stored_form_reports_it(tmp_path):
    h = Harness(tmp_path, GOOD)
    assert h.run() == 0 and h.metrics()["git_stored_form"] == 1


def test_a_text_only_apply_neither_counts_against_the_cap_nor_waits_for_it(tmp_path):
    reworded = GOOD.replace("// scrape", "// scrape (reworded)")
    h = Harness(tmp_path, reworded)
    h.api = FakeTailscale(GOOD)
    full = [h.clock - 60, h.clock - 600, h.clock - 3600]
    rec.save_state(h.state_dir, {"applied": list(full), "applied_count": 3})
    assert h.run() == 0 and h.api.posts == [reworded]
    assert h.state()["applied"] == full  # not counted
    (event,) = [e for e in h.events() if e["event"] == "applied"]
    assert (event["kind"], event["counts_against_cap"], event["post_apply_diff"]) == ("text_only", False, [])
    assert h.metrics()["in_sync"] == 1 and "tailnet policy: daily cap" not in [t for t, _ in h.notices]
    # the cap still holds for a rule change
    h.source.desired = policy_with(reworded, grant_block("203.0.113.10", "203.0.113.30", 9100), policy_test("203.0.113.10", "203.0.113.30:9100"))
    assert h.run() == 0 and len(h.api.posts) == 1 and h.metrics()["pending_apply"] == 1


def test_the_cap_notice_says_when_the_next_slot_frees_and_that_a_hand_apply_is_alerted(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    rec.save_state(h.state_dir, {"applied": [h.clock - 3600, h.clock - 600, h.clock - 60], "applied_count": 3})
    assert h.run() == 0 and h.api.posts == []
    (title, body), = h.notices
    slot = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(h.clock - 3600 + 86400))
    assert title == "tailnet policy: daily cap" and slot in body and "hand apply" in body


def test_a_text_only_apply_that_leaves_live_in_another_form_is_not_repeated(tmp_path):
    # Tailscale changes its formatter: what it keeps is neither git's text nor stored_form()'s prediction
    def other_formatter(text):
        return tps.stored_form(text).replace("\t", "  ")

    reworded = GOOD.replace("// scrape", "// scrape (reworded)")
    h = Harness(tmp_path, reworded)
    h.api = FakeTailscale(GOOD, reformat=other_formatter)
    assert h.run() == 0 and len(h.api.posts) == 1  # once: it might have converged
    assert h.run() == 2 and len(h.api.posts) == 1  # it did not: a human adopts live's text, no apply every run
    assert h.metrics()["blocked"] == 1 and [t for t, _ in h.notices][-1] == "tailnet policy: needs a human"
    assert "adopt live's text" in json.dumps(h.events()[-1]["reasons"])


def oob(h: Harness) -> list[dict]:
    return [e for e in h.events() if e["event"] == "out_of_band_change"]


def test_the_first_run_takes_a_baseline_and_exports_both_counters_at_zero(tmp_path):
    h = Harness(tmp_path, GOOD)
    h.api = FakeTailscale(GOOD)
    assert h.run() == 0 and h.run() == 0
    assert oob(h) == [] and h.notices == []
    m = h.metrics()
    assert m['out_of_band_changes_total{via="sync_tool"}'] == 0 and m['out_of_band_changes_total{via="unknown"}'] == 0
    assert m["last_out_of_band_timestamp_seconds"] == 0
    prom = (h.textfile_dir / "tailscale_policy_reconcile.prom").read_text()
    assert prom.count("# TYPE tailscale_policy_reconcile_out_of_band_changes_total counter") == 1


def test_a_live_change_the_reconciler_did_not_make_is_counted_logged_and_announced(tmp_path):
    h = Harness(tmp_path, GOOD)
    h.api = FakeTailscale(GOOD)
    assert h.run() == 0
    before = h.api.etag
    h.api.hand_apply(GOOD.replace("// scrape", "// scrape (edited in the admin console)"))
    h.clock += 900
    assert h.run() == 0  # comment-only: the reconciler puts git's text back, uncapped
    (event,) = oob(h)
    assert (event["via"], event["etag_before"], event["etag_after"]) == ("unknown", before, json.loads(json.dumps(h.events()[0]["etag_after"])))
    m = h.metrics()
    assert m['out_of_band_changes_total{via="unknown"}'] == 1 and m['out_of_band_changes_total{via="sync_tool"}'] == 0
    assert m["last_out_of_band_timestamp_seconds"] == int(h.clock)
    assert [t for t, _ in h.notices][0] == "tailnet policy: changed outside the reconciler"
    assert "203.0.113" not in " ".join(b for _, b in h.notices)
    # its own apply that followed is not a change from outside, and an unchanged live policy is not either
    h.clock += 900
    assert h.run() == 0 and h.run() == 0 and len(oob(h)) == 1


def test_a_hand_apply_with_the_sync_tool_is_told_apart(tmp_path):
    h = Harness(tmp_path, GOOD)
    h.api = FakeTailscale(GOOD)
    assert h.run() == 0
    h.api.hand_apply(GOOD.replace("// scrape", "// scrape (sync tool)"), state_dir=h.state_dir)
    h.run()
    assert [e["via"] for e in oob(h)] == ["sync_tool"]
    assert h.metrics()['out_of_band_changes_total{via="sync_tool"}'] == 1


def test_a_hand_applied_merged_change_is_alerted_even_though_live_now_equals_git(tmp_path):
    # 2026-10-21: #533 was merged, waited behind the cap and was applied by hand at 06:37Z; the next run was in_sync, silently
    h = Harness(tmp_path, GOOD)
    h.api = FakeTailscale(GOOD)
    assert h.run() == 0
    h.source.desired = policy_with(GOOD, grant_block("203.0.113.10", "203.0.113.30", 9100), policy_test("203.0.113.10", "203.0.113.30:9100"))
    h.api.hand_apply(h.source.desired, state_dir=h.state_dir)
    assert h.run() == 0 and h.api.posts == []
    assert h.metrics()["in_sync"] == 1 and [e["via"] for e in oob(h)] == ["sync_tool"]


def test_an_etag_race_is_reported_as_a_change_from_outside(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.api = FakeTailscale(GOOD)
    real_set = h.api.set_policy

    def racing_set(body, etag):  # someone else writes between our GET and our POST
        h.api.hand_apply(GOOD.replace("// scrape", "// scrape (racing)"))
        return real_set(body, etag)

    h.api.set_policy = racing_set
    assert h.run() == 0 and h.api.posts == [] and h.metrics()["pending_apply"] == 1
    h.api.set_policy = real_set
    assert h.run() == 0 and len(h.api.posts) == 1
    assert [e["via"] for e in oob(h)] == ["unknown"]


def test_a_failed_re_read_after_an_apply_takes_a_new_baseline_not_an_alarm(tmp_path):
    h = Harness(tmp_path, ADDITIVE)
    h.api = FakeTailscale(GOOD)
    real_get, calls = h.api.get_policy, []

    def flaky_get():
        calls.append(1)
        if len(calls) == 2:  # the re-read right after the POST
            raise tps.SyncError("Tailscale API unreachable")
        return real_get()

    h.api.get_policy = flaky_get
    assert h.run() == 1  # the apply happened, its check did not
    assert h.state()["live_etag"] is None
    assert h.run() == 0 and oob(h) == []


def test_replay_2026_10_20_no_text_only_reapply_no_cap_exhaustion_and_the_hand_apply_is_caught(tmp_path):
    """The two days that made agents apply by hand, replayed with the same shapes of change (synthetic addresses).

    What happened (OBSERVED, CT108 events.jsonl and journal): 02:39 #522 applied; 15:32 six grants applied by hand with
    the sync tool, so 15:35 was blocked; 15:50 #524+#526 applied; 16:06 the same policy re-applied as text-only (its
    one-line lists are stored expanded), which spent the third slot of the 3-per-24h cap; #528 (17:39) waited until
    02:43 the next day; #533 (03:27) waited behind the cap and was applied by hand at 06:37.
    Wanted: no text-only re-apply, #528 and #533 applied on their first run, no cap notice, the hand apply counted."""
    import calendar

    g526, t526 = _526_blocks()
    p522 = tps.stored_form(policy_with(GOOD, grant_block("203.0.113.10", "203.0.113.30", 9100), policy_test("203.0.113.10", "203.0.113.30:9100")))
    spire = ('\t\t{"src": ["tag:monitoring"], "dst": ["192.0.2.66/32"], "ip": ["tcp:8081", "tcp:8082"]},\n'
             '\t\t{"src": ["tag:db"], "dst": ["192.0.2.66/32"], "ip": ["tcp:8081"]},\n')
    spire_tests = policy_test("tag:monitoring", "192.0.2.66:8081", "192.0.2.66:8082") + policy_test("tag:db", "192.0.2.66:8081")
    p524 = tps.stored_form(policy_with(p522, spire, spire_tests))
    p526 = policy_with(p524, g526, t526)  # merged as written: not in the stored form
    p528 = policy_with(p526, grant_block("203.0.113.40", "198.51.100.40", 8300), policy_test("203.0.113.40", "198.51.100.40:8300"))
    p527 = tps.stored_form(p528)  # #527, merged after #528
    four = '\t\t{"src": "203.0.113.41", "accept": ["198.51.100.141:8301", "198.51.100.141:8302", "198.51.100.141:8303", "198.51.100.141:8304"], "proto": "tcp"},\n'
    p533 = policy_with(p527, '\t\t{"src": ["203.0.113.41/32"], "dst": ["198.51.100.141/32"], "ip": ["tcp:8301", "tcp:8302", "tcp:8303", "tcp:8304"]},\n', four)
    assert tps.stored_form(p526) != p526 and tps.stored_form(p533) != p533  # the two texts that were not in the stored form

    day = calendar.timegm((2026, 10, 20, 0, 0, 0))
    at = lambda hh, mm, d=0: day + d * 86400 + hh * 3600 + mm * 60  # noqa: E731
    h = Harness(tmp_path, GOOD)
    h.api = FakeTailscale(GOOD)
    hand = lambda: h.api.hand_apply(policy_with(p522, g526, t526), state_dir=h.state_dir)  # noqa: E731
    changes = {at(2, 30): lambda: setattr(h.source, "desired", p522), at(15, 32): hand,
               at(15, 39): lambda: setattr(h.source, "desired", p524), at(15, 46): lambda: setattr(h.source, "desired", p526),
               at(17, 30): lambda: setattr(h.source, "desired", p528), at(19, 10): lambda: setattr(h.source, "desired", p527),
               at(3, 27, 1): lambda: setattr(h.source, "desired", p533)}
    runs = [at(hh, mm) for hh in range(2, 24) for mm in (5, 20, 35, 50)] + [at(hh, mm, 1) for hh in range(0, 8) for mm in (5, 20, 35, 50)]
    decisions = {}
    for ts in sorted([*runs, *changes]):
        h.clock = float(ts)
        if ts in changes:
            changes[ts]()
            continue
        h.run()
        decisions[ts] = h.metrics()

    applied = [e for e in h.events() if e["event"] == "applied"]
    # On the day: 02:39, 15:50, 16:06 (text-only, the cap's third slot), then #528 only at 02:43 and #533 by hand
    assert [e["ts"] for e in applied] == [at(2, 35), at(15, 50), at(17, 35), at(3, 35, 1)]
    assert len(h.api.posts) == 4  # no text-only re-apply: 16:05 and every run after it saw live == stored_form(git)
    assert "tailnet policy: daily cap" not in [t for t, _ in h.notices]
    assert {e.get("kind") for e in applied} == {"additive"}
    assert all(m["pending_apply"] == 0 for ts, m in decisions.items())  # nothing ever waited
    assert [(e["ts"], e["via"]) for e in oob(h)] == [(at(15, 35), "sync_tool")]  # the 15:32 hand apply, and only that
    assert decisions[at(15, 35)]["blocked"] == 1  # live had rules git lacked, as on the day
    assert decisions[at(16, 5)]["in_sync"] == 1 and decisions[at(16, 5)]["git_stored_form"] == 0
    assert decisions[at(19, 20)]["git_stored_form"] == 1  # after #527
    assert decisions[at(7, 50, 1)]["in_sync"] == 1
    assert tps.semantic_diff(tps.parse_hujson(h.api.live), tps.parse_hujson(p533)) == []
    window = sorted(e["ts"] for e in applied if e["counts_against_cap"])
    assert max(sum(1 for t in window if s <= t < s + 86400) for s in window) <= rec.MAX_APPLIES_PER_DAY


def test_a_console_edit_after_a_sync_tool_apply_is_not_credited_to_the_sync_tool(tmp_path):
    h = Harness(tmp_path, GOOD)
    h.api = FakeTailscale(GOOD)
    assert h.run() == 0
    h.api.hand_apply(GOOD.replace("// scrape", "// scrape (sync tool)"), state_dir=h.state_dir)
    h.api.hand_apply(GOOD.replace("// scrape", "// scrape (then the console)"))  # before the reconciler looked again
    h.run()
    assert [e["via"] for e in oob(h)] == ["unknown"]
