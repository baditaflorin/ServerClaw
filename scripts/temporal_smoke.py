#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker


@activity.defn
async def build_smoke_result(name: str) -> dict[str, str]:
    return {
        "message": f"temporal-smoke:{name}",
        "activity": "build_smoke_result",
    }


@workflow.defn
class TemporalSmokeWorkflow:
    @workflow.run
    async def run(self, name: str) -> dict[str, str]:
        return await workflow.execute_activity(
            build_smoke_result,
            name,
            schedule_to_close_timeout=timedelta(seconds=30),
            start_to_close_timeout=timedelta(seconds=30),
        )


@dataclass
class SmokeReport:
    address: str
    namespace: str
    task_queue: str
    workflow_id: str
    run_id: str
    elapsed_ms: int
    result: dict[str, str]


async def run_smoke(*, address: str, namespace: str, workflow_id_prefix: str, name: str) -> SmokeReport:
    task_queue = f"{workflow_id_prefix}-queue-{uuid.uuid4().hex[:10]}"
    workflow_id = f"{workflow_id_prefix}-{uuid.uuid4().hex}"
    started = time.perf_counter()
    client = await Client.connect(address, namespace=namespace)
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[TemporalSmokeWorkflow],
        activities=[build_smoke_result],
    ):
        handle = await client.start_workflow(
            TemporalSmokeWorkflow.run,
            name,
            id=workflow_id,
            task_queue=task_queue,
            execution_timeout=timedelta(seconds=60),
            run_timeout=timedelta(seconds=60),
            task_timeout=timedelta(seconds=10),
        )
        result = await handle.result()
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return SmokeReport(
        address=address,
        namespace=namespace,
        task_queue=task_queue,
        workflow_id=workflow_id,
        run_id=handle.result_run_id,
        elapsed_ms=elapsed_ms,
        result=result,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a minimal end-to-end Temporal workflow smoke.")
    parser.add_argument("--address", default="127.0.0.1:7233", help="Temporal frontend gRPC address.")
    parser.add_argument("--namespace", default="lv3", help="Temporal namespace to target.")
    parser.add_argument("--workflow-id-prefix", default="temporal-smoke", help="Workflow id prefix.")
    parser.add_argument("--name", default="lv3", help="Workflow payload used by the smoke activity.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = asyncio.run(
        run_smoke(
            address=args.address,
            namespace=args.namespace,
            workflow_id_prefix=args.workflow_id_prefix,
            name=args.name,
        )
    )
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
