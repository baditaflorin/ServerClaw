from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import flatten_text, load_json


def _command_documents(repo_root: Path, path: Path) -> list[SearchDocument]:
    payload = load_json(path, {"commands": {}})
    relative_path = relative_url(repo_root, path)
    documents: list[SearchDocument] = []
    for command_id, command in sorted(payload.get("commands", {}).items()):
        if not isinstance(command, dict):
            continue
        tags = command.get("scope")
        if isinstance(tags, list):
            tag_text = " ".join(str(item) for item in tags)
        else:
            tag_text = str(tags or "")
        body = "\n".join(
            item
            for item in [
                str(command.get("description", "")),
                flatten_text(command.get("expected_preconditions")),
                flatten_text(command.get("failure_guidance")),
                flatten_text(command.get("inputs")),
                tag_text,
            ]
            if item
        )
        documents.append(
            build_document(
                collection="command_catalog",
                doc_id=f"command:{command_id}",
                title=command_id,
                body=body,
                url=relative_path,
                metadata={
                    "catalog_type": "command",
                    "source_path": relative_path,
                    "workflow_id": command.get("workflow_id"),
                    "tags": command.get("scope", []),
                },
            )
        )
    return documents


def _workflow_documents(repo_root: Path, path: Path) -> list[SearchDocument]:
    payload = load_json(path, {"workflows": {}})
    relative_path = relative_url(repo_root, path)
    documents: list[SearchDocument] = []
    for workflow_id, workflow in sorted(payload.get("workflows", {}).items()):
        if not isinstance(workflow, dict):
            continue
        body = "\n".join(
            item
            for item in [
                str(workflow.get("description", "")),
                flatten_text(workflow.get("outputs")),
                flatten_text(workflow.get("verification_commands")),
                flatten_text(workflow.get("implementation_refs")),
                flatten_text(workflow.get("preflight")),
            ]
            if item
        )
        documents.append(
            build_document(
                collection="command_catalog",
                doc_id=f"workflow:{workflow_id}",
                title=workflow_id,
                body=body,
                url=relative_path,
                metadata={
                    "catalog_type": "workflow",
                    "source_path": relative_path,
                    "owner_runbook": workflow.get("owner_runbook"),
                    "live_impact": workflow.get("live_impact"),
                    "tags": workflow.get("implementation_refs", []),
                },
            )
        )
    return documents


def collect(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    documents.extend(_command_documents(repo_root, repo_root / "config" / "command-catalog.json"))
    documents.extend(_workflow_documents(repo_root, repo_root / "config" / "workflow-catalog.json"))
    return documents
