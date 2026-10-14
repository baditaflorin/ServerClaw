"""Unit tests for scripts/tailscale_policy_reconcile.py (the unattended, additive-only policy reconciler).

Everything runs offline against the synthetic fixture policy (documentation addresses only). Git, the CI status, the
Tailscale API and the alert channel are replaced by in-memory fakes, so no credential or network is involved.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import time
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
        self.apply = apply
        self.clock = 1_700_000_000.0
        local = tmp_path / "installed"
        local.mkdir()
        self.local = {}
        for repo_path, content in self.source.files.items():
            f = local / Path(repo_path).name
            f.write_text(content)
            self.local[repo_path] = f

    def run(self) -> int:
        return rec.run_once(
            api_login=lambda: self.api, source=self.source, guard=GUARD, local_files=self.local,
            state_dir=self.state_dir, textfile_dir=self.textfile_dir, apply_enabled=self.apply,
            notify=lambda title, body: self.notices.append((title, body)), now=lambda: self.clock,
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


def test_validate_failure_is_counted_and_the_circuit_opens_for_that_commit(tmp_path):
    h = Harness(tmp_path, ADDITIVE, validate=(False, "HTTP 400: test failed"))
    assert h.run() == 1 and h.run() == 1
    assert h.state()["failures"] == {"sha": SHA, "count": 2}
    assert h.api.posts == []
    assert h.run() == 2  # circuit open: not even a validate any more
    assert [t for t, _ in h.notices][-1] == "tailnet policy: reconcile stopped"
    h.source.head = lambda: "b" * 40  # main moved: a new commit gets its own attempts
    assert h.run() == 1


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
