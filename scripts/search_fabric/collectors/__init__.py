from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import adr_collector, alert_collector, case_collector, catalog_collector, config_collector, receipt_collector, runbook_collector, topology_collector
from ..models import SearchDocument


Collector = Callable[[Path], list[SearchDocument]]

COLLECTORS: dict[str, Collector] = {
    "adrs": adr_collector.collect,
    "runbooks": runbook_collector.collect,
    "command_catalog": catalog_collector.collect,
    "configs": config_collector.collect,
    "receipts": receipt_collector.collect,
    "failure_cases": case_collector.collect,
    "alerts": alert_collector.collect,
    "topology": topology_collector.collect,
}


def available_collections() -> list[str]:
    return sorted(COLLECTORS)
