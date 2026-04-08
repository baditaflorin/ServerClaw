"""
scripts/goal_compiler — Deterministic Goal Compiler (ADR 0112).

Public surface
--------------
GoalCompiler
    Main compiler class.  Transforms natural-language instructions into typed
    CompiledIntent instances with integrated risk scoring.

GoalCompilationError
    Raised when an instruction cannot be compiled.

CompiledIntent / IntentTarget / IntentScope / ScoringContext
    Typed dataclasses that flow through the pipeline and are serialisable to
    YAML for pre-execution review.

RiskClass
    LOW / MEDIUM / HIGH / CRITICAL enum used by both the compiler and the
    risk_scorer module.

Usage example
-------------
    from scripts.goal_compiler import GoalCompiler, GoalCompilationError
    from pathlib import Path

    compiler = GoalCompiler(Path("/path/to/repo"))
    try:
        intent = compiler.compile("deploy netbox")
    except GoalCompilationError as exc:
        print(f"Compilation failed: {exc.code} — {exc.message}")
    else:
        print(compiler.as_yaml(intent))
"""

from .compiler import GoalCompiler, GoalCompilationError
from .models import (
    CompiledIntent,
    IntentScope,
    IntentTarget,
    RiskClass,
    ScoringContext,
)
from .resolver import resolve_scope, resolve_target, resolve_workflow_id

__all__ = [
    "CompiledIntent",
    "GoalCompilationError",
    "GoalCompiler",
    "IntentScope",
    "IntentTarget",
    "RiskClass",
    "ScoringContext",
    "resolve_scope",
    "resolve_target",
    "resolve_workflow_id",
]
