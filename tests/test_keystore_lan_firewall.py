"""config/keystore-mesh/lan-publish/keystore-lan-firewall: the allow list becomes exactly the rules it names, and nothing wider is accepted."""
from __future__ import annotations

import subprocess
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "config" / "keystore-mesh" / "lan-publish"
SCRIPT = DIR / "keystore-lan-firewall"


def run(tmp: Path, conf_text: str | None, *args: str, **env):
    conf = tmp / "allow.conf"
    if conf_text is not None:
        conf.write_text(conf_text)
    full_env = {"PATH": "/usr/bin:/bin", "KEYSTORE_LAN_ALLOW": str(conf), **env}
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=full_env)


def test_default_allow_list_is_the_two_failover_hosts_and_a_final_drop(tmp_path):
    r = subprocess.run(["bash", str(SCRIPT), "--print"], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "KEYSTORE_LAN_ALLOW": str(DIR / "keystore-lan-allow.conf")})
    assert r.returncode == 0, r.stderr
    rules = [l for l in r.stdout.splitlines() if l.startswith("-A ")]
    assert rules == ["-A KEYSTORE-LAN -s 10.10.10.10 -j RETURN", "-A KEYSTORE-LAN -s 10.10.10.30 -j RETURN", "-A KEYSTORE-LAN -j DROP"]
    assert ":KEYSTORE-LAN - [0:0]" in r.stdout and r.stdout.count("COMMIT") == 1


def test_the_jump_matches_the_original_destination_on_the_lan_interface_only(tmp_path):
    r = run(tmp_path, "10.10.10.10\n", "--print")
    jump = [l for l in r.stdout.splitlines() if l.startswith("jump:")][0]
    for part in ("-I DOCKER-USER 1", "-i eth0", "-p tcp", "--ctorigdst 10.10.10.91", "--ctorigdstport 18021", "--ctdir ORIGINAL", "-j KEYSTORE-LAN"):
        assert part in jump, (part, jump)


def test_comments_and_blank_lines_are_ignored(tmp_path):
    r = run(tmp_path, "# nginx-lv3\n\n  10.10.10.10   # the edge\n", "--print")
    assert [l for l in r.stdout.splitlines() if l.startswith("-A ")] == ["-A KEYSTORE-LAN -s 10.10.10.10 -j RETURN", "-A KEYSTORE-LAN -j DROP"]


def test_ranges_wildcards_and_junk_are_refused(tmp_path):
    for bad in ("10.10.10.0/24", "10.10.10.*", "*", "0.0.0.0", "10.10.10.300", "10.20.10", "any", "10.10.10.10 10.10.10.30"):
        r = run(tmp_path, f"10.10.10.10\n{bad}\n", "--print")
        assert r.returncode == 2, (bad, r.stdout, r.stderr)
        assert "refusing" in r.stderr
        assert "-A KEYSTORE-LAN" not in r.stdout, "a bad list must not print any rule"


def test_an_empty_list_closes_the_port_for_everybody(tmp_path):
    r = run(tmp_path, "# nobody\n", "--print")
    assert r.returncode == 0
    assert [l for l in r.stdout.splitlines() if l.startswith("-A ")] == ["-A KEYSTORE-LAN -j DROP"]
    assert "no allowed hosts" in r.stderr


def test_apply_replaces_the_chain_in_one_restore_and_does_not_duplicate_the_jump(tmp_path):
    log = tmp_path / "calls.log"
    (tmp_path / "iptables").write_text(f'#!/bin/bash\necho "iptables $*" >> {log}\n[ "$1" = "-C" ] && exit 1\nexit 0\n')
    (tmp_path / "iptables-restore").write_text(f'#!/bin/bash\necho "restore $*" >> {log}\ncat >> {log}\n')
    for f in ("iptables", "iptables-restore"):
        (tmp_path / f).chmod(0o755)
    r = run(tmp_path, "10.10.10.10\n", IPTABLES=str(tmp_path / "iptables"), IPTABLES_RESTORE=str(tmp_path / "iptables-restore"))
    assert r.returncode == 0, r.stderr
    text = log.read_text()
    assert "restore --noflush" in text and "-A KEYSTORE-LAN -j DROP" in text
    assert text.count("iptables -I DOCKER-USER 1") == 1 and "iptables -F" not in text, "no flush of the chain outside the transaction"


def test_installer_and_unit_are_wired_to_docker():
    assert subprocess.run(["bash", "-n", str(DIR / "install-vm.sh")]).returncode == 0
    unit = (DIR / "keystore-lan-firewall.service").read_text()
    assert "Requires=docker.service" in unit and "After=docker.service" in unit and "PartOf=docker.service" in unit
    assert "ExecStart=/usr/local/sbin/keystore-lan-firewall" in unit
    assert "--undo" in (DIR / "install-vm.sh").read_text()
