"""Unit tests for scripts/tailscale_policy_sync.py (Tailscale policy as code).

Everything runs offline against synthetic fixture policies. The Tailscale API and the vault credential route are
replaced by an in-memory fake, so no credential or network is involved.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tailscale_policy_sync as tps  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "tailscale"
GOOD = (FIXTURES / "good-policy.hujson").read_text()
GUARD = json.loads((FIXTURES / "lockout-guard.json").read_text())
REAL_POLICY = REPO_ROOT / "config" / "tailscale" / "policy.hujson"
REAL_GUARD = REPO_ROOT / "config" / "tailscale" / "lockout-guard.json"


def policy(**overrides):
    base = tps.parse_hujson(GOOD)
    base.update(overrides)
    return base


# --- HuJSON ------------------------------------------------------------------------------------------------------


def test_hujson_comments_trailing_commas_and_slashes_in_strings():
    parsed = tps.parse_hujson(GOOD)
    assert parsed["tagOwners"]["tag:db"] == ["group:admins"]
    text = '{"a": "http://x//y", /* c */ "b": [1, 2,], // tail\n}'
    assert tps.parse_hujson(text) == {"a": "http://x//y", "b": [1, 2]}


def test_hujson_escaped_quote_and_comma_in_string():
    assert tps.parse_hujson(r'{"a": "q\"//,]", }') == {"a": 'q"//,]'}


@pytest.mark.parametrize("bad", ['{"a": ', '{"a": "x', '{"a": 1 /* open'])
def test_hujson_rejects_malformed(bad):
    with pytest.raises(tps.SyncError):
        tps.parse_hujson(bad)


# --- diffing -----------------------------------------------------------------------------------------------------


def test_identical_policies_have_empty_diffs():
    assert tps.semantic_diff(tps.parse_hujson(GOOD), tps.parse_hujson(GOOD)) == []
    assert tps.text_diff(GOOD, GOOD) == []


def test_text_diff_ignores_line_endings_and_trailing_newline_only():
    assert tps.text_diff(GOOD.replace("\n", "\r\n"), GOOD.rstrip("\n")) == []


def test_comment_only_change_is_text_diff_not_semantic():
    edited = GOOD.replace('"tests": [', '// added comment\n\t"tests": [', 1)
    assert tps.semantic_diff(tps.parse_hujson(GOOD), tps.parse_hujson(edited)) == []
    assert any("added comment" in line for line in tps.text_diff(GOOD, edited))


def test_added_and_removed_rule_are_reported():
    live = tps.parse_hujson(GOOD)
    desired = tps.parse_hujson(GOOD)
    desired["grants"].append({"src": ["tag:admin"], "dst": ["tag:db"], "ip": ["tcp:5432"]})
    removed = desired["grants"].pop(0)
    lines = tps.semantic_diff(live, desired)
    assert any(line.startswith("+ grants[]") and "5432" in line for line in lines)
    assert any(line.startswith("- grants[]") and json.dumps(removed["ip"]).replace(" ", "") in line for line in lines)


def test_reorder_is_reported_without_add_remove():
    live = tps.parse_hujson(GOOD)
    desired = tps.parse_hujson(GOOD)
    desired["grants"].reverse()
    lines = tps.semantic_diff(live, desired)
    assert lines == ["~ grants: same items, different order"]


def test_scalar_and_nested_key_changes():
    live, desired = tps.parse_hujson(GOOD), tps.parse_hujson(GOOD)
    desired["autoApprovers"]["routes"]["198.51.100.7/32"] = ["tag:db"]
    del desired["groups"]
    lines = tps.semantic_diff(live, desired)
    assert any(line.startswith("- groups:") for line in lines)
    assert any("autoApprovers.routes.198.51.100.7/32" in line for line in lines)


# --- offline checks ----------------------------------------------------------------------------------------------


def test_good_fixture_passes_all_checks():
    assert tps.check_policy(GOOD, GUARD) == []


def test_check_skips_missing_default_policy_only_in_sanitized_snapshot(tmp_path, monkeypatch, capsys):
    policy_path = tmp_path / "config" / "tailscale" / "policy.hujson"
    manifest = tmp_path / "config" / "publication-sanitization.yaml"
    monkeypatch.setattr(tps, "DEFAULT_POLICY", policy_path)
    monkeypatch.setattr(tps, "PUBLICATION_MANIFEST", manifest)

    assert run("check") == 0
    assert "skipped" in capsys.readouterr().out


def test_check_keeps_missing_policy_fatal_in_private_source(tmp_path, monkeypatch, capsys):
    policy_path = tmp_path / "config" / "tailscale" / "policy.hujson"
    manifest = tmp_path / "config" / "publication-sanitization.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("private source marker\n")
    monkeypatch.setattr(tps, "DEFAULT_POLICY", policy_path)
    monkeypatch.setattr(tps, "PUBLICATION_MANIFEST", manifest)

    assert run("check") == 1
    assert "policy file not found" in capsys.readouterr().err


def test_syntax_error_is_reported():
    assert tps.check_policy("{ nope", GUARD)


def test_acl_allow_all_is_forbidden():
    p = policy(acls=[{"action": "accept", "src": ["*"], "dst": ["*:*"]}])
    assert any("allow-all" in e for e in tps.forbidden_pattern_errors(p))


def test_grant_allow_all_is_forbidden():
    for grant in (
        {"src": ["*"], "dst": ["*"], "ip": ["*"]},
        {"src": ["*"], "dst": ["*"]},
    ):
        p = policy(grants=[grant])
        assert any("allow-all" in e for e in tps.forbidden_pattern_errors(p)), grant


def test_scoped_wildcard_ports_are_not_flagged():
    # tag -> tag on all ports is a normal pattern (the real policy has several); only "*" -> "*" is forbidden.
    p = policy(grants=[{"src": ["tag:admin"], "dst": ["tag:db"], "ip": ["*"]}])
    assert tps.forbidden_pattern_errors(p) == []


def test_unknown_tag_anywhere_is_rejected():
    for key, value in (
        ("grants", [{"src": ["tag:ghost"], "dst": ["tag:db"], "ip": ["tcp:1"]}]),
        ("tests", [{"src": "tag:admin", "accept": ["tag:ghost:22"]}]),
        ("autoApprovers", {"routes": {"198.51.100.9/32": ["tag:ghost"]}}),
        ("ssh", [{"action": "accept", "src": ["tag:admin"], "dst": ["tag:ghost"], "users": ["root"]}]),
    ):
        errors = tps.tag_errors(policy(**{key: value}))
        assert any("tag:ghost" in e for e in errors), key


def test_unknown_tag_as_tag_owner_is_rejected():
    p = policy(tagOwners={"tag:admin": ["tag:ghost"], "tag:db": ["group:admins"], "tag:monitoring": ["group:admins"]})
    assert any("tag:ghost" in e for e in tps.tag_errors(p))


def test_missing_tagowners_is_rejected():
    p = policy()
    del p["tagOwners"]
    assert tps.tag_errors(p)


# --- lockout guard -----------------------------------------------------------------------------------------------


def test_lockout_guard_requires_mac_and_bastion_ssh_tests():
    p = policy(tests=[t for t in policy()["tests"] if t["src"] != "203.0.113.10"])
    errors = tps.lockout_guard_errors(p, GUARD)
    assert len(errors) == 2 and all("203.0.113.10" in e for e in errors)


def test_lockout_guard_fails_when_one_bastion_dropped_from_accept():
    p = policy()
    p["tests"][1]["accept"] = ["203.0.113.20:22"]
    errors = tps.lockout_guard_errors(p, GUARD)
    assert errors == [e for e in errors if "203.0.113.21:22" in e] and len(errors) == 1


def test_lockout_guard_does_not_accept_a_deny_entry():
    p = policy()
    p["tests"][1] = {"src": "203.0.113.10", "deny": ["203.0.113.20:22", "203.0.113.21:22"]}
    assert len(tps.lockout_guard_errors(p, GUARD)) == 2


def test_guard_file_without_entries_is_an_error():
    assert tps.lockout_guard_errors(policy(), {"required_accept": []})


def test_check_policy_requires_tests():
    p = policy(tests=[])
    assert any("no `tests`" in e for e in tps.check_policy(json.dumps(p), {"required_accept": []}))


@pytest.mark.skipif(not REAL_POLICY.exists(), reason="config/tailscale is stripped from the public mirror")
def test_committed_policy_passes_offline_checks_and_pins_mac_and_bastions():
    guard = json.loads(REAL_GUARD.read_text())
    assert tps.check_policy(REAL_POLICY.read_text(), guard) == []
    pairs = {(g["src"], g["dst"]) for g in guard["required_accept"]}
    # operator Mac (florins-macbook-air) -> 0mcp and 0docker hypervisors/bastions on :22
    assert ("100.116.198.31", "203.0.113.6:22") in pairs
    assert ("100.116.198.31", "203.0.113.5:22") in pairs


# --- metrics -----------------------------------------------------------------------------------------------------


def test_metric_lines_ok_and_error_shapes():
    ok = "\n".join(tps.metric_lines(ok=True, semantic=True, text=False, now=1700000000))
    assert 'tailscale_policy_drift{kind="semantic"} 1' in ok
    assert 'tailscale_policy_drift{kind="text"} 0' in ok
    assert "tailscale_policy_last_check_timestamp_seconds 1700000000" in ok
    assert "tailscale_policy_check_success 1" in ok
    bad = "\n".join(tps.metric_lines(ok=False, semantic=False, text=False, now=1700000000))
    assert "tailscale_policy_check_success 0" in bad and "tailscale_policy_drift" not in bad


# --- plan / apply / drift with a fake API ------------------------------------------------------------------------


class FakeAPI:
    def __init__(self, live: str, etag: str = '"etag-1"', validate=(True, "ok"), set_status: int = 200):
        self.live, self.etag, self._validate, self.set_status = live, etag, validate, set_status
        self.posted: list[tuple[str, str]] = []

    def get_policy(self):
        return self.live, self.etag

    def validate(self, text):
        return self._validate

    def set_policy(self, text, etag):
        self.posted.append((text, etag))
        if self.set_status == 200:
            self.live, self.etag = text, '"etag-2"'
        return self.set_status, "body"


@pytest.fixture
def env(tmp_path, monkeypatch):
    desired = GOOD.replace('"tcp:9100"', '"tcp:9101"')  # one semantic change vs. live
    pol = tmp_path / "policy.hujson"
    pol.write_text(desired)
    guard = tmp_path / "guard.json"
    guard.write_text(json.dumps(GUARD))
    fake = FakeAPI(GOOD)
    monkeypatch.setattr(tps.TailscaleAPI, "login", classmethod(lambda cls: fake))
    base = ["--file", str(pol), "--guard", str(guard)]
    state = ["--state-dir", str(tmp_path / "state")]
    return {"pol": pol, "guard": guard, "fake": fake, "base": base, "state": state, "tmp": tmp_path}


def run(*argv):
    return tps.main(list(argv))


def test_plan_in_sync_reports_empty_diff(env, capsys):
    env["pol"].write_text(GOOD)
    assert run("plan", *env["base"], *env["state"], "--detailed-exitcode") == 0
    assert "no differences" in capsys.readouterr().out


def test_plan_with_changes_exits_2_only_when_asked(env):
    assert run("plan", *env["base"], *env["state"]) == 0
    assert run("plan", *env["base"], *env["state"], "--detailed-exitcode") == 2


def test_plan_fails_and_records_nothing_when_validation_fails(env):
    env["fake"]._validate = (False, "test(s) failed")
    assert run("plan", *env["base"], *env["state"]) == 1
    assert not (env["tmp"] / "state" / "plan.json").exists()


def test_plan_fails_on_lockout_guard(env):
    bad = tps.parse_hujson(GOOD)
    bad["tests"] = bad["tests"][:1]
    env["pol"].write_text(json.dumps(bad))
    assert run("plan", *env["base"], *env["state"]) == 1
    assert not (env["tmp"] / "state" / "plan.json").exists()


def test_apply_refuses_without_a_plan(env):
    assert run("apply", *env["base"], *env["state"], "--yes") == 1
    assert env["fake"].posted == []


def test_apply_refuses_stale_plan(env):
    run("plan", *env["base"], *env["state"])
    plan_file = env["tmp"] / "state" / "plan.json"
    plan = json.loads(plan_file.read_text())
    plan["created"] = time.time() - 10_000
    plan_file.write_text(json.dumps(plan))
    assert run("apply", *env["base"], *env["state"], "--yes") == 1
    assert env["fake"].posted == []


def test_apply_refuses_when_file_changed_after_plan(env):
    run("plan", *env["base"], *env["state"])
    env["pol"].write_text(env["pol"].read_text() + "\n// edited after plan\n")
    assert run("apply", *env["base"], *env["state"], "--yes") == 1
    assert env["fake"].posted == []


def test_apply_refuses_when_live_policy_changed_after_plan(env):
    run("plan", *env["base"], *env["state"])
    env["fake"].etag = '"etag-concurrent"'
    assert run("apply", *env["base"], *env["state"], "--yes") == 1
    assert env["fake"].posted == []


def test_apply_posts_with_if_match_saves_rollback_and_consumes_plan(env):
    run("plan", *env["base"], *env["state"])
    assert run("apply", *env["base"], *env["state"], "--yes") == 0
    ((text, etag),) = env["fake"].posted
    assert etag == '"etag-1"' and text == env["pol"].read_text()
    rollbacks = list((env["tmp"] / "state" / "rollback").glob("policy.*.hujson"))
    assert len(rollbacks) == 1 and rollbacks[0].read_text() == GOOD  # the pre-apply live policy
    assert oct(rollbacks[0].stat().st_mode & 0o777) == "0o600"
    assert not (env["tmp"] / "state" / "plan.json").exists()  # a plan is single-use
    assert run("apply", *env["base"], *env["state"], "--yes") == 1  # so a replay is refused


def test_apply_reports_api_refusal_and_keeps_going_no_further(env):
    env["fake"].set_status = 412
    run("plan", *env["base"], *env["state"])
    assert run("apply", *env["base"], *env["state"], "--yes") == 1


def test_apply_with_no_changes_does_not_post(env):
    env["pol"].write_text(GOOD)
    run("plan", *env["base"], *env["state"])
    assert run("apply", *env["base"], *env["state"], "--yes") == 0
    assert env["fake"].posted == []


def test_drift_writes_metrics_and_exit_codes(env):
    textfile = env["tmp"] / "tf"
    assert run("drift", *env["base"], "--textfile-dir", str(textfile)) == 2
    prom = (textfile / "tailscale_policy.prom").read_text()
    assert 'tailscale_policy_drift{kind="semantic"} 1' in prom

    env["pol"].write_text(GOOD)
    assert run("drift", *env["base"], "--textfile-dir", str(textfile)) == 0
    prom = (textfile / "tailscale_policy.prom").read_text()
    assert 'tailscale_policy_drift{kind="semantic"} 0' in prom and 'kind="text"} 0' in prom


def test_drift_text_only_difference_counts_as_drift(env):
    env["pol"].write_text(GOOD.replace('"tests": [', '// c\n\t"tests": [', 1))
    textfile = env["tmp"] / "tf"
    assert run("drift", *env["base"], "--textfile-dir", str(textfile)) == 2
    prom = (textfile / "tailscale_policy.prom").read_text()
    assert 'kind="semantic"} 0' in prom and 'kind="text"} 1' in prom


def test_drift_api_error_exits_3_and_flags_failed_check(env, monkeypatch):
    def boom(cls):
        raise tps.SyncError("API unreachable")

    monkeypatch.setattr(tps.TailscaleAPI, "login", classmethod(boom))
    textfile = env["tmp"] / "tf"
    assert run("drift", *env["base"], "--textfile-dir", str(textfile)) == 3
    prom = (textfile / "tailscale_policy.prom").read_text()
    assert "tailscale_policy_check_success 0" in prom and "tailscale_policy_drift" not in prom


# --- credentials -------------------------------------------------------------------------------------------------


def test_credential_command_override_and_no_secret_in_errors(tmp_path, monkeypatch):
    script = tmp_path / "cred.sh"
    script.write_text('#!/bin/sh\necho \'{"client_id": "id-x", "client_secret": "s3cret-value"}\'\n')
    script.chmod(0o755)
    monkeypatch.setenv("TS_POLICY_CRED_CMD", str(script))
    assert tps.fetch_oauth_client() == {"client_id": "id-x", "client_secret": "s3cret-value"}

    bad = tmp_path / "bad.sh"
    bad.write_text("#!/bin/sh\necho 'not json s3cret-value'\n")
    bad.chmod(0o755)
    monkeypatch.setenv("TS_POLICY_CRED_CMD", str(bad))
    with pytest.raises(tps.SyncError) as exc:
        tps.fetch_oauth_client()
    assert "s3cret-value" not in str(exc.value)


def test_default_credential_route_is_the_documented_vault_wrapper():
    cmd = tps.VAULT_CMD
    assert cmd[0] == "systemd-run" and "/root/bin/fleet-vault.py" in cmd
    assert cmd[-2:] == ["raw", "tailscale_policy_oauth_client"]
