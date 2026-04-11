"""ADR 0118 — BM25 + signal-overlap case retrieval.

No embeddings. No vector database. Symbolic matching on structured fields
combined with BM25 full-text scoring over the case document body.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def tokenize(value: str) -> list[str]:
    return TOKEN_PATTERN.findall(normalize_text(value))


def case_document(case: dict[str, Any]) -> str:
    """Concatenate all searchable text fields of a case into one document string."""
    fields = [
        case.get("title", ""),
        case.get("affected_service", ""),
        case.get("root_cause", ""),
        case.get("root_cause_category", ""),
        " ".join(case.get("symptoms", [])),
        " ".join(case.get("remediation_steps", [])),
    ]
    correlated_signals = case.get("correlated_signals", {})
    if isinstance(correlated_signals, dict):
        fields.append(" ".join(f"{key} {value}" for key, value in correlated_signals.items()))
    return " ".join(str(field) for field in fields if field)


def signal_weight(name: str) -> float:
    """Higher weight for semantically meaningful signal names."""
    lowered = name.lower()
    if any(token in lowered for token in ("certificate", "deploy", "error", "dependency", "drift", "health")):
        return 2.5
    if any(token in lowered for token in ("cpu", "memory", "disk", "latency", "duration")):
        return 1.5
    return 1.0


def comparable_signal_match(current: Any, candidate: Any) -> bool:
    """Return True if two signal values are considered equivalent."""
    if isinstance(current, bool) and isinstance(candidate, bool):
        return current is candidate
    if isinstance(current, (int, float)) and isinstance(candidate, (int, float)):
        if current == candidate:
            return True
        baseline = abs(float(current)) or 1.0
        return abs(float(current) - float(candidate)) / baseline <= 0.1
    if isinstance(current, str) and isinstance(candidate, str):
        return normalize_text(current) == normalize_text(candidate)
    return False


class CaseRetriever:
    """Retrieve the most similar historical failure cases for a new incident.

    Scoring model (composite):
        composite = (bm25 * 0.65) + (signal_overlap * 3.0) + service_boost + category_boost

    service_boost  — +1.0 when affected_service is an exact match
    category_boost — +0.5 when root_cause_category is in the triage hypothesis list
    signal_overlap — cosine-style weighted overlap over correlated_signals key-value pairs
    """

    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def _bm25_scores(self, cases: list[dict[str, Any]], query: str) -> dict[str, float]:
        query_tokens = tokenize(query)
        if not query_tokens or not cases:
            return {str(case["case_id"]): 0.0 for case in cases}

        documents = [tokenize(case_document(case)) for case in cases]
        avg_doc_length = sum(len(doc) for doc in documents) / max(len(documents), 1)
        document_frequency: Counter[str] = Counter()
        for doc in documents:
            document_frequency.update(set(doc))

        scores: dict[str, float] = {}
        for case, tokens in zip(cases, documents, strict=False):
            token_counts = Counter(tokens)
            score = 0.0
            doc_length = len(tokens) or 1
            for term in query_tokens:
                frequency = token_counts.get(term, 0)
                if frequency == 0:
                    continue
                docs_with_term = document_frequency.get(term, 0)
                idf = math.log(1 + ((len(cases) - docs_with_term + 0.5) / (docs_with_term + 0.5)))
                numerator = frequency * (self.k1 + 1)
                denominator = frequency + self.k1 * (1 - self.b + self.b * (doc_length / max(avg_doc_length, 1)))
                score += idf * (numerator / denominator)
            scores[str(case["case_id"])] = round(score, 6)
        return scores

    def _signal_overlap(
        self,
        current_signals: dict[str, Any],
        case_signals: dict[str, Any],
    ) -> tuple[float, int]:
        if not current_signals or not case_signals:
            return 0.0, 0

        overlap = 0.0
        max_score = 0.0
        matched = 0
        for key, current_value in current_signals.items():
            weight = signal_weight(key)
            max_score += weight
            if key in case_signals and comparable_signal_match(current_value, case_signals[key]):
                overlap += weight
                matched += 1
        return round(overlap / max(max_score, 1.0), 6), matched

    def find_similar(
        self,
        *,
        cases: list[dict[str, Any]],
        query: str,
        affected_service: str,
        current_signals: dict[str, Any] | None = None,
        category_hints: list[str] | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return up to *limit* cases ranked by composite similarity score."""
        category_hints = [hint for hint in (category_hints or []) if hint]
        scores = self._bm25_scores(cases, query)
        matches: list[dict[str, Any]] = []
        for case in cases:
            case_id = str(case["case_id"])
            service_boost = 1.0 if case.get("affected_service") == affected_service else 0.0
            category_boost = 0.5 if case.get("root_cause_category") in category_hints else 0.0
            signal_overlap, matched_signal_count = self._signal_overlap(
                current_signals or {},
                case.get("correlated_signals", {}) if isinstance(case.get("correlated_signals"), dict) else {},
            )
            lexical_score = scores.get(case_id, 0.0)
            composite = round(
                (lexical_score * 0.65) + (signal_overlap * 3.0) + service_boost + category_boost,
                6,
            )
            enriched = dict(case)
            enriched["scores"] = {
                "lexical": lexical_score,
                "signal_overlap": signal_overlap,
                "service_boost": service_boost,
                "category_boost": category_boost,
                "matched_signal_count": matched_signal_count,
                "composite": composite,
            }
            matches.append(enriched)

        matches.sort(
            key=lambda item: (
                float(item["scores"]["composite"]),
                float(item["scores"]["lexical"]),
                item.get("resolved_at") or "",
                item.get("updated_at") or "",
            ),
            reverse=True,
        )
        return matches[:limit]

    def search(
        self,
        *,
        cases: list[dict[str, Any]],
        query: str,
        affected_service: str | None = None,
        current_signals: dict[str, Any] | None = None,
        category_hints: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Broad search — affected_service filter is optional."""
        service = affected_service or ""
        return self.find_similar(
            cases=cases,
            query=query,
            affected_service=service,
            current_signals=current_signals,
            category_hints=category_hints,
            limit=limit,
        )
