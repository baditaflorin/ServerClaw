#!/usr/bin/env python3
"""
repowise_corpus.py — build a searchable chunk corpus from the git repository.

Indexes Python scripts, Ansible roles/playbooks, Jinja2 templates, config files,
and markdown docs into structured chunks for semantic embedding.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Language / chunk constants
# ---------------------------------------------------------------------------

CHUNK_MAX_CHARS = 2000
CHUNK_OVERLAP_CHARS = 200

# Which paths to walk (relative to repo root)
INDEX_DIRS: tuple[str, ...] = (
    "scripts",
    "platform",
    "collections/ansible_collections/lv3/platform/roles",
    "playbooks",
    "config",
    "docs/adr",
    "docs/runbooks",
)

# Which paths to exclude entirely
EXCLUDE_PATTERNS: tuple[str, ...] = (
    "__pycache__",
    ".git",
    "*.pyc",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    "build/",
    "dist/",
)

PYTHON_EXT = {".py"}
YAML_EXT = {".yml", ".yaml"}
JINJA_EXT = {".j2"}
MARKDOWN_EXT = {".md", ".markdown"}
JSON_EXT = {".json"}
HTML_EXT = {".html"}

ALL_INDEXED_EXT = PYTHON_EXT | YAML_EXT | JINJA_EXT | MARKDOWN_EXT | JSON_EXT | HTML_EXT

# Regex to detect Python function/class boundaries
PY_DEF_PATTERN = re.compile(r"^(class |def |async def )", re.MULTILINE)
# H2 markdown section
H2_PATTERN = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
# Ansible task name
ANSIBLE_TASK_NAME_PATTERN = re.compile(r"^\s*-\s+name:\s*(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk_id(file_path: str, start: int, text: str) -> str:
    digest = hashlib.sha256(f"{file_path}:{start}:{text[:64]}".encode()).hexdigest()[:16]
    return str(uuid.UUID(int=int(digest, 16) % (2**128)))


def _is_excluded(path: Path) -> bool:
    for part in path.parts:
        for pattern in EXCLUDE_PATTERNS:
            if pattern.endswith("/") and part == pattern.rstrip("/"):
                return True
            if part == pattern:
                return True
    return False


def _language(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in PYTHON_EXT:
        return "python"
    if ext in YAML_EXT:
        return "yaml"
    if ext in JINJA_EXT:
        return "jinja2"
    if ext in MARKDOWN_EXT:
        return "markdown"
    if ext in JSON_EXT:
        return "json"
    if ext in HTML_EXT:
        return "html"
    return "text"


def _document_kind(path: Path, repo_root: Path) -> str:
    rel = path.relative_to(repo_root)
    parts = rel.parts
    if parts[0] == "scripts":
        return "script"
    if parts[0] == "platform":
        return "platform_library"
    if "roles" in parts:
        return "ansible_role"
    if parts[0] == "playbooks":
        return "ansible_playbook"
    if parts[0] == "config":
        return "config"
    if parts[0] == "docs" and len(parts) > 1 and parts[1] == "adr":
        return "adr"
    if parts[0] == "docs" and len(parts) > 1 and parts[1] == "runbooks":
        return "runbook"
    return "doc"


def _split_plain_text(text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Split text into overlapping chunks on paragraph boundaries."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_len + len(para) > max_chars and current:
            chunk = "\n\n".join(current)
            chunks.append(chunk)
            # keep tail for overlap
            tail = chunk[-overlap:] if overlap else ""
            current = [tail, para] if tail else [para]
            current_len = len(tail) + len(para)
        else:
            current.append(para)
            current_len += len(para)
    if current:
        chunks.append("\n\n".join(current))
    return [c for c in chunks if len(c.strip()) > 40]


# ---------------------------------------------------------------------------
# Language-specific chunkers
# ---------------------------------------------------------------------------


def _chunks_python(text: str, file_path: str) -> list[dict[str, Any]]:
    """
    Chunk Python by top-level function/class blocks.
    Falls back to plain text splitting for files without clear boundaries.
    """
    lines = text.splitlines(keepends=True)
    chunks: list[dict[str, Any]] = []

    # Find top-level def/class positions
    boundaries: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if PY_DEF_PATTERN.match(line):
            name_match = re.match(r"(?:async )?(?:def|class)\s+(\w+)", line)
            name = name_match.group(1) if name_match else f"block_{i}"
            boundaries.append((i, name))

    if not boundaries:
        # No clear structure — plain chunks
        for seg in _split_plain_text(text):
            chunks.append(
                {
                    "chunk_type": "module",
                    "chunk_name": file_path.rsplit("/", 1)[-1],
                    "start_line": 0,
                    "text": seg,
                }
            )
        return chunks

    # Extract blocks between boundaries
    ranges: list[tuple[int, int, str]] = []
    for idx, (line_no, name) in enumerate(boundaries):
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)
        ranges.append((line_no, end, name))

    # Always include module-level header (imports, constants) if present
    first_boundary = boundaries[0][0]
    if first_boundary > 0:
        header = "".join(lines[:first_boundary]).strip()
        if header:
            chunks.append(
                {
                    "chunk_type": "module_header",
                    "chunk_name": "module:" + file_path.rsplit("/", 1)[-1],
                    "start_line": 0,
                    "text": header[:CHUNK_MAX_CHARS],
                }
            )

    for start_line, end_line, name in ranges:
        block = "".join(lines[start_line:end_line]).strip()
        if len(block) > CHUNK_MAX_CHARS:
            for seg in _split_plain_text(block):
                chunks.append(
                    {
                        "chunk_type": "function" if "def " in lines[start_line] else "class",
                        "chunk_name": name,
                        "start_line": start_line + 1,
                        "text": seg,
                    }
                )
        elif len(block) > 40:
            chunks.append(
                {
                    "chunk_type": "function" if "def " in lines[start_line] else "class",
                    "chunk_name": name,
                    "start_line": start_line + 1,
                    "text": block,
                }
            )

    return chunks


def _chunks_markdown(text: str, file_path: str) -> list[dict[str, Any]]:
    """Chunk markdown by H2 sections."""
    chunks: list[dict[str, Any]] = []
    sections = H2_PATTERN.split(text)

    # sections alternates: [pre_h2_text, h2_title, h2_body, ...]
    if len(sections) <= 1:
        for seg in _split_plain_text(text):
            chunks.append({"chunk_type": "section", "chunk_name": "intro", "start_line": 0, "text": seg})
        return chunks

    # Pre-H2 content (intro/frontmatter)
    intro = sections[0].strip()
    if intro and len(intro) > 40:
        chunks.append({"chunk_type": "intro", "chunk_name": "intro", "start_line": 0, "text": intro[:CHUNK_MAX_CHARS]})

    # Each H2 section
    i = 1
    while i < len(sections) - 1:
        title = sections[i].strip()
        body = sections[i + 1].strip()
        section_text = f"## {title}\n\n{body}"
        if len(section_text) > CHUNK_MAX_CHARS:
            for seg in _split_plain_text(section_text):
                chunks.append({"chunk_type": "section", "chunk_name": title, "start_line": 0, "text": seg})
        elif len(section_text) > 40:
            chunks.append({"chunk_type": "section", "chunk_name": title, "start_line": 0, "text": section_text})
        i += 2

    return chunks


def _chunks_yaml(text: str, file_path: str) -> list[dict[str, Any]]:
    """
    Chunk YAML by named task blocks (Ansible) or plain text splitting for other YAML.
    """
    chunks: list[dict[str, Any]] = []
    task_names = ANSIBLE_TASK_NAME_PATTERN.findall(text)

    if task_names:
        # Ansible-style: split on '- name:' boundaries
        parts = ANSIBLE_TASK_NAME_PATTERN.split(text)
        # parts: [pre, name1, body1, name2, body2, ...]
        pre = parts[0].strip()
        if pre and len(pre) > 40:
            chunks.append(
                {"chunk_type": "yaml_header", "chunk_name": "header", "start_line": 0, "text": pre[:CHUNK_MAX_CHARS]}
            )
        i = 1
        while i < len(parts) - 1:
            name = parts[i].strip()
            body = parts[i + 1].strip()
            task_text = f"- name: {name}\n{body}"
            if len(task_text) <= CHUNK_MAX_CHARS and len(task_text) > 40:
                chunks.append({"chunk_type": "ansible_task", "chunk_name": name, "start_line": 0, "text": task_text})
            elif len(task_text) > 40:
                for seg in _split_plain_text(task_text):
                    chunks.append({"chunk_type": "ansible_task", "chunk_name": name, "start_line": 0, "text": seg})
            i += 2
    else:
        for seg in _split_plain_text(text):
            chunks.append(
                {"chunk_type": "yaml", "chunk_name": file_path.rsplit("/", 1)[-1], "start_line": 0, "text": seg}
            )

    return chunks


def _chunks_generic(text: str, file_path: str, chunk_type: str) -> list[dict[str, Any]]:
    """Generic plain-text chunking for JSON, HTML, Jinja2, etc."""
    chunks = []
    for seg in _split_plain_text(text):
        chunks.append(
            {
                "chunk_type": chunk_type,
                "chunk_name": file_path.rsplit("/", 1)[-1],
                "start_line": 0,
                "text": seg,
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Main corpus builder
# ---------------------------------------------------------------------------


def iter_repo_paths(repo_root: Path) -> list[Path]:
    """Walk the indexed directories and return all eligible file paths."""
    paths: list[Path] = []
    for dir_str in INDEX_DIRS:
        dir_path = repo_root / dir_str
        if not dir_path.exists():
            continue
        for path in dir_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ALL_INDEXED_EXT:
                continue
            if _is_excluded(path):
                continue
            paths.append(path)
    return sorted(paths)


def build_chunks(repo_root: Path) -> list[dict[str, Any]]:
    """
    Walk the repo and return a list of chunk dicts ready for embedding.

    Each chunk dict has:
        id           - stable UUID string
        text         - the text to embed
        file_path    - path relative to repo_root
        language     - python | yaml | jinja2 | markdown | json | html
        document_kind - script | ansible_role | ansible_playbook | config | adr | runbook | doc
        chunk_type   - function | class | section | ansible_task | yaml | file | ...
        chunk_name   - human-readable name (function name, task name, section title)
        start_line   - approximate 1-based line number (0 if unknown)
    """
    all_chunks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for path in iter_repo_paths(repo_root):
        rel = str(path.relative_to(repo_root))
        lang = _language(path)
        kind = _document_kind(path, repo_root)

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if not text.strip():
            continue

        # Choose chunker by language
        if lang == "python":
            raw_chunks = _chunks_python(text, rel)
        elif lang == "markdown":
            raw_chunks = _chunks_markdown(text, rel)
        elif lang == "yaml":
            raw_chunks = _chunks_yaml(text, rel)
        else:
            raw_chunks = _chunks_generic(text, rel, lang)

        for rc in raw_chunks:
            chunk_text = rc["text"].strip()
            if not chunk_text or len(chunk_text) < 30:
                continue
            chunk_id = _chunk_id(rel, rc.get("start_line", 0), chunk_text)
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            all_chunks.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "file_path": rel,
                    "language": lang,
                    "document_kind": kind,
                    "chunk_type": rc.get("chunk_type", "block"),
                    "chunk_name": rc.get("chunk_name", ""),
                    "start_line": rc.get("start_line", 0),
                }
            )

    return all_chunks


def build_manifest(repo_root: Path, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    files_indexed = sorted({c["file_path"] for c in chunks})
    by_language: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for c in chunks:
        by_language[c["language"]] = by_language.get(c["language"], 0) + 1
        by_kind[c["document_kind"]] = by_kind.get(c["document_kind"], 0) + 1
    return {
        "total_chunks": len(chunks),
        "total_files": len(files_indexed),
        "by_language": by_language,
        "by_document_kind": by_kind,
        "files_indexed": files_indexed,
    }


if __name__ == "__main__":
    import json
    import sys

    repo_root = Path(__file__).resolve().parent.parent
    chunks = build_chunks(repo_root)
    manifest = build_manifest(repo_root, chunks)
    print(json.dumps(manifest, indent=2), file=sys.stderr)
    print(f"Built {manifest['total_chunks']} chunks from {manifest['total_files']} files", file=sys.stderr)
