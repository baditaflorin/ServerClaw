from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


TASK_PATTERN = re.compile(r"^TASK \[(?P<label>.+?)\]\s+\*+$")
HOST_RESULT_PATTERN = re.compile(r"^(?P<kind>changed|fatal): \[(?P<host>[^\]]+)\]")
UNREACHABLE_PATTERN = re.compile(r"UNREACHABLE!", re.IGNORECASE)
DRIFT_EVENT_TOPICS = {
    "warn": "platform.drift.warn",
    "critical": "platform.drift.critical",
    "unreachable": "platform.drift.unreachable",
}


def drift_event_topic(severity: str) -> str:
    normalized = str(severity).strip().lower()
    if normalized == "warning":
        normalized = "warn"
    if normalized not in DRIFT_EVENT_TOPICS:
        raise ValueError(f"unsupported drift severity '{severity}'")
    return DRIFT_EVENT_TOPICS[normalized]


def split_role_task(label: str) -> tuple[str | None, str]:
    if " : " not in label:
        return None, label.strip()
    role, task = label.split(" : ", 1)
    return role.strip(), task.strip()


def build_record(
    *,
    host: str,
    role: str | None,
    task: str,
    source: str,
    detail: str,
    unreachable: bool = False,
    diff_before: str = "",
    diff_after: str = "",
) -> dict[str, Any]:
    event = drift_event_topic("unreachable" if unreachable else "warn")
    return {
        "source": source,
        "host": host,
        "role": role,
        "task": task,
        "detail": detail,
        "diff_before": diff_before,
        "diff_after": diff_after,
        "severity": "critical" if unreachable else "warn",
        "event": event,
        "type": "unreachable" if unreachable else "changed",
        "shared_surfaces": [host, role or "", task],
    }


def parse_json_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    plays = payload.get("plays", [])
    if not isinstance(plays, list):
        return records

    for play in plays:
        tasks = play.get("tasks", [])
        if not isinstance(tasks, list):
            continue
        for task_entry in tasks:
            task_meta = task_entry.get("task", {})
            label = str(task_meta.get("name", "")).strip()
            role, task_name = split_role_task(label) if label else (None, "unnamed task")
            hosts = task_entry.get("hosts", {})
            if not isinstance(hosts, dict):
                continue
            for host, result in hosts.items():
                if not isinstance(result, dict):
                    continue
                if result.get("unreachable"):
                    records.append(
                        build_record(
                            host=host,
                            role=role,
                            task=task_name,
                            source="ansible-check-mode",
                            detail=str(result.get("msg", "host unreachable")),
                            unreachable=True,
                        )
                    )
                    continue
                if not result.get("changed"):
                    continue
                diff = result.get("diff")
                before = ""
                after = ""
                if isinstance(diff, list) and diff:
                    first_diff = diff[0]
                    if isinstance(first_diff, dict):
                        before = str(first_diff.get("before", ""))
                        after = str(first_diff.get("after", ""))
                elif isinstance(diff, dict):
                    before = str(diff.get("before", ""))
                    after = str(diff.get("after", ""))
                records.append(
                    build_record(
                        host=host,
                        role=role,
                        task=task_name,
                        source="ansible-check-mode",
                        detail="changed in check mode",
                        diff_before=before,
                        diff_after=after,
                    )
                )
    return records


def parse_text_payload(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current_role: str | None = None
    current_task = "unknown task"
    diff_before: list[str] = []
    diff_after: list[str] = []
    capture_before = False
    capture_after = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        task_match = TASK_PATTERN.match(line)
        if task_match:
            current_role, current_task = split_role_task(task_match.group("label"))
            diff_before = []
            diff_after = []
            capture_before = False
            capture_after = False
            continue
        if line.startswith("--- "):
            capture_before = True
            capture_after = False
            continue
        if line.startswith("+++ "):
            capture_before = False
            capture_after = True
            continue
        if line.startswith("@@ "):
            capture_before = False
            capture_after = False
            continue
        host_match = HOST_RESULT_PATTERN.match(line)
        if host_match:
            host = host_match.group("host")
            if UNREACHABLE_PATTERN.search(line):
                records.append(
                    build_record(
                        host=host,
                        role=current_role,
                        task=current_task,
                        source="ansible-check-mode",
                        detail=line,
                        unreachable=True,
                    )
                )
                continue
            if host_match.group("kind") == "changed":
                records.append(
                    build_record(
                        host=host,
                        role=current_role,
                        task=current_task,
                        source="ansible-check-mode",
                        detail="changed in check mode",
                        diff_before="\n".join(diff_before),
                        diff_after="\n".join(diff_after),
                    )
                )
            continue
        if capture_before:
            diff_before.append(line)
            continue
        if capture_after:
            diff_after.append(line)
            continue

    return records


def parse_ansible_output(text: str) -> list[dict[str, Any]]:
    payload = text.strip()
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return parse_text_payload(text)
    if isinstance(parsed, dict):
        return parse_json_payload(parsed)
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse ansible --check --diff output into drift records.")
    parser.add_argument("input", nargs="?", help="Optional path to ansible output. Defaults to stdin.")
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.input:
        text = open(args.input, encoding="utf-8").read()
    else:
        text = sys.stdin.read()
    records = parse_ansible_output(text)
    print(json.dumps(records, indent=args.indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
