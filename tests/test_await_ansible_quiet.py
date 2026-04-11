from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "await_ansible_quiet.py"
SPEC = importlib.util.spec_from_file_location("await_ansible_quiet", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_process_table_reads_pid_ppid_and_command() -> None:
    entries = MODULE.parse_process_table(
        "100 1 /opt/homebrew/bin/ansible-playbook -i inventory/hosts.yml playbooks/glitchtip.yml --limit docker-runtime-lv3\n"
        "200 100 /usr/bin/python /tmp/ansible-module.py\n"
    )

    assert [(entry.pid, entry.ppid, entry.command) for entry in entries] == [
        (
            100,
            1,
            "/opt/homebrew/bin/ansible-playbook -i inventory/hosts.yml playbooks/glitchtip.yml --limit docker-runtime-lv3",
        ),
        (200, 100, "/usr/bin/python /tmp/ansible-module.py"),
    ]


def test_ancestor_pids_walks_the_parent_chain() -> None:
    entries = [
        MODULE.ProcessEntry(pid=10, ppid=1, command="/opt/homebrew/bin/ansible-playbook playbooks/glitchtip.yml"),
        MODULE.ProcessEntry(pid=20, ppid=10, command="/usr/bin/python /tmp/runner.py"),
        MODULE.ProcessEntry(pid=30, ppid=20, command="/usr/bin/python scripts/await_ansible_quiet.py"),
    ]

    assert MODULE.ancestor_pids(entries, 30) == {1, 10, 20, 30}


def test_find_blocking_processes_ignores_current_ancestors_and_shell_watchers() -> None:
    entries = [
        MODULE.ProcessEntry(
            pid=10,
            ppid=1,
            command="/opt/homebrew/bin/ansible-playbook -i inventory/hosts.yml playbooks/glitchtip.yml --limit docker-runtime-lv3,nginx-lv3",
        ),
        MODULE.ProcessEntry(
            pid=20,
            ppid=10,
            command="/usr/bin/python /tmp/ansible-runner.py",
        ),
        MODULE.ProcessEntry(
            pid=30,
            ppid=1,
            command="/opt/homebrew/bin/ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --limit docker-runtime-lv3",
        ),
        MODULE.ProcessEntry(
            pid=40,
            ppid=1,
            command="/bin/zsh -lc while true; do ps -ef | rg 'ansible-playbook .*--limit .*docker-runtime-lv3'; done",
        ),
        MODULE.ProcessEntry(
            pid=50,
            ppid=1,
            command="rg ansible-playbook .*--limit .*docker-runtime-lv3",
        ),
    ]

    blockers = MODULE.find_blocking_processes(
        entries,
        required_hosts=("docker-runtime-lv3", "nginx-lv3"),
        ignored_pids={10, 20},
    )

    assert blockers == [entries[2]]
