#!/usr/bin/env python3
"""PostgreSQL smoke tests for restored guests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any


DEFAULT_DATABASES: tuple[str, ...] = (
    "keycloak",
    "mattermost",
    "netbox",
    "openbao",
    "windmill",
)


def _result(name: str, status: str, **details: Any) -> dict[str, Any]:
    payload = {"name": name, "status": status}
    payload.update(details)
    return payload


def run_smoke_tests(
    execute_command: Callable[[str], Any],
    *,
    databases: Sequence[str] = DEFAULT_DATABASES,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    readiness = execute_command("pg_isready -h 127.0.0.1 -p 5432")
    if readiness.returncode != 0:
        results.append(
            _result(
                "postgres_ready",
                "fail",
                required=True,
                stdout=readiness.stdout,
                stderr=readiness.stderr,
            )
        )
        return results

    results.append(_result("postgres_ready", "pass", required=True, stdout=readiness.stdout))

    for database in databases:
        table_count = execute_command(
            "sudo -u postgres psql"
            f" -d {database} -Atqc \"SELECT count(*) FROM information_schema.tables\""
        )
        dump_check = execute_command(
            f"sudo -u postgres pg_dump --schema-only -d {database} >/dev/null"
        )

        if table_count.returncode == 0 and dump_check.returncode == 0:
            results.append(
                _result(
                    f"{database}_database_accessible",
                    "pass",
                    required=True,
                    table_count=table_count.stdout.strip(),
                )
            )
            continue

        results.append(
            _result(
                f"{database}_database_accessible",
                "fail",
                required=True,
                stdout=table_count.stdout,
                stderr="\n".join(part for part in (table_count.stderr, dump_check.stderr) if part).strip(),
            )
        )

    return results
