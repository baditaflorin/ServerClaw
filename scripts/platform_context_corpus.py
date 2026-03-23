#!/usr/bin/env python3

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any


MARKDOWN_EXTENSIONS = {".md", ".markdown"}
JSON_EXTENSIONS = {".json"}
YAML_EXTENSIONS = {".yml", ".yaml"}
PLAIN_TEXT_EXTENSIONS = {".txt"}
H2_PATTERN = re.compile(r"^##\s+(?P<title>.+?)\s*$")
H1_PATTERN = re.compile(r"^#\s+(?P<title>.+?)\s*$")
PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")
DEFAULT_MAX_CHARS = 2400
DEFAULT_OVERLAP_CHARS = 240

CORPUS_PATHS: tuple[str, ...] = (
    "docs/adr",
    "docs/release-notes",
    "docs/runbooks",
    "receipts/live-applies",
)
CORPUS_FILES: tuple[str, ...] = (
    "versions/stack.yaml",
    "config/workflow-catalog.json",
    "config/command-catalog.json",
    "config/agent-tool-registry.json",
    "changelog.md",
    "VERSION",
)

MIRRORED_PATH_PREFIXES: tuple[str, ...] = (
    "docs/adr",
    "docs/runbooks",
    "receipts/live-applies",
)


def iter_corpus_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for relative_dir in CORPUS_PATHS:
        root = repo_root / relative_dir
        if not root.exists():
            continue
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            paths.append(path)
    for relative_file in CORPUS_FILES:
        path = repo_root / relative_file
        if path.exists():
            paths.append(path)
    return paths


def load_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in JSON_EXTENSIONS:
        return json.dumps(json.loads(path.read_text()), indent=2, sort_keys=True)
    if suffix in YAML_EXTENSIONS:
        return path.read_text()
    return path.read_text()


def normalize_relative_path(relative_path: str) -> str:
    for prefix in MIRRORED_PATH_PREFIXES:
        duplicated_prefix = f"{prefix}/{Path(prefix).name}/"
        if relative_path.startswith(duplicated_prefix):
            return f"{prefix}/{relative_path.removeprefix(duplicated_prefix)}"
    return relative_path


def document_kind_for_path(relative_path: str) -> str:
    if relative_path.startswith("docs/adr/"):
        return "adr"
    if relative_path.startswith("docs/runbooks/"):
        return "runbook"
    if relative_path.startswith("docs/release-notes/"):
        return "release_note"
    if relative_path.startswith("receipts/live-applies/"):
        return "receipt"
    if relative_path == "versions/stack.yaml":
        return "stack"
    if relative_path.startswith("config/"):
        return "catalog"
    if relative_path == "changelog.md":
        return "changelog"
    if relative_path == "VERSION":
        return "version"
    return "document"


def adr_number_for_path(relative_path: str) -> str | None:
    match = re.match(r"docs/adr/(?P<number>\d{4})-", relative_path)
    if match:
        return match.group("number")
    return None


def first_heading(text: str) -> str | None:
    for line in text.splitlines():
        match = H1_PATTERN.match(line.strip())
        if match:
            return match.group("title").strip()
    return None


def split_markdown_sections(text: str) -> list[tuple[str | None, str]]:
    lines = text.splitlines()
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    saw_section = False

    for line in lines:
        stripped = line.strip()
        match = H2_PATTERN.match(stripped)
        if match:
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
                current_lines = []
            current_heading = match.group("title").strip()
            current_lines.append(line)
            saw_section = True
            continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    if saw_section:
        return [(heading, body) for heading, body in sections if body]
    return [(None, text.strip())]


def split_plain_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    paragraphs = [item.strip() for item in PARAGRAPH_SPLIT_PATTERN.split(normalized) if item.strip()]
    if not paragraphs:
        paragraphs = [normalized]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            overlap = current[-overlap_chars:].strip()
            current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
            if len(current) <= max_chars:
                continue

        start = 0
        while start < len(paragraph):
            end = min(start + max_chars, len(paragraph))
            segment = paragraph[start:end].strip()
            if segment:
                chunks.append(segment)
            if end >= len(paragraph):
                current = ""
                break
            start = max(end - overlap_chars, start + 1)

    if current:
        chunks.append(current)

    deduped: list[str] = []
    for chunk in chunks:
        if not deduped or deduped[-1] != chunk:
            deduped.append(chunk)
    return deduped


def build_chunks(
    repo_root: Path,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    repo_root = repo_root.resolve()
    chunks: list[dict[str, Any]] = []
    for source_path in iter_corpus_paths(repo_root):
        relative_path = normalize_relative_path(source_path.relative_to(repo_root).as_posix())
        source_text = load_document_text(source_path)
        document_kind = document_kind_for_path(relative_path)
        document_title = first_heading(source_text) or source_path.stem.replace("-", " ")
        adr_number = adr_number_for_path(relative_path)
        section_groups = (
            split_markdown_sections(source_text)
            if source_path.suffix.lower() in MARKDOWN_EXTENSIONS
            else [(None, source_text.strip())]
        )

        chunk_index = 0
        for section_heading, section_body in section_groups:
            for segment in split_plain_text(
                section_body,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            ):
                payload = {
                    "chunk_id": chunk_identifier(relative_path, chunk_index, segment),
                    "source_path": relative_path,
                    "document_kind": document_kind,
                    "document_title": document_title,
                    "section_heading": section_heading,
                    "adr_number": adr_number,
                    "updated_at": source_path.stat().st_mtime,
                    "content": segment,
                    "char_count": len(segment),
                }
                chunks.append(payload)
                chunk_index += 1
    return chunks


def build_manifest(
    repo_root: Path,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> dict[str, Any]:
    chunks = build_chunks(repo_root, max_chars=max_chars, overlap_chars=overlap_chars)
    by_kind: dict[str, int] = {}
    sources: set[str] = set()
    for chunk in chunks:
        by_kind[chunk["document_kind"]] = by_kind.get(chunk["document_kind"], 0) + 1
        sources.add(chunk["source_path"])
    return {
        "repo_root": str(repo_root.resolve()),
        "source_count": len(sources),
        "chunk_count": len(chunks),
        "by_kind": dict(sorted(by_kind.items())),
        "max_chars": max_chars,
        "overlap_chars": overlap_chars,
    }


def chunk_identifier(relative_path: str, chunk_index: int, content: str) -> str:
    digest = hashlib.sha1(f"{relative_path}:{chunk_index}:{content}".encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))
