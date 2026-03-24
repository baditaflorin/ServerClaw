from __future__ import annotations

from pathlib import Path

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import flatten_text, load_json, load_yaml


def _receipt_alerts(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    alerts_root = repo_root / "receipts" / "alerts"
    if not alerts_root.exists():
        return documents
    for path in sorted(alerts_root.rglob("*.json")):
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            continue
        relative_path = relative_url(repo_root, path)
        title = str(payload.get("alert") or payload.get("summary") or path.stem)
        documents.append(
            build_document(
                collection="alerts",
                doc_id=f"alert:{relative_path}",
                title=title,
                body=flatten_text(payload),
                url=relative_path,
                metadata={
                    "source_path": relative_path,
                    "service": payload.get("service"),
                    "severity": payload.get("severity"),
                },
            )
        )
    return documents


def _rule_alerts(repo_root: Path) -> list[SearchDocument]:
    path = repo_root / "config" / "alertmanager" / "rules" / "platform.yml"
    payload = load_yaml(path, {})
    groups = payload.get("groups", []) if isinstance(payload, dict) else []
    relative_path = relative_url(repo_root, path)
    documents: list[SearchDocument] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for rule in group.get("rules", []):
            if not isinstance(rule, dict):
                continue
            alert_name = str(rule.get("alert") or "alert")
            documents.append(
                build_document(
                    collection="alerts",
                    doc_id=f"alert-rule:{alert_name}",
                    title=alert_name,
                    body=flatten_text(rule),
                    url=relative_path,
                    metadata={
                        "source_path": relative_path,
                        "service": rule.get("labels", {}).get("service_id"),
                        "severity": rule.get("labels", {}).get("severity"),
                    },
                )
            )
    return documents


def collect(repo_root: Path) -> list[SearchDocument]:
    documents = _receipt_alerts(repo_root)
    if documents:
        return documents
    return _rule_alerts(repo_root)
