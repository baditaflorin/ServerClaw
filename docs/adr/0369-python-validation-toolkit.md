# ADR 0369: Python Validation Toolkit

- **Date**: 2026-04-06
- **Status**: Accepted
- **Deciders**: platform team
- **Concern**: platform, dry
- **Tags**: python, validation, scripts, dry, tooling

## Implementation Summary (2026-04-10)

**Status: COMPLETE ✅**

- ✓ Created `scripts/validation_toolkit.py` with 15 canonical validation functions
- ✓ Migrated 57 scripts (100% of validation-heavy scripts)
- ✓ All base validators (require_mapping, require_str, require_list, etc.) centralized
- ✓ 55+ scripts extend toolkit with domain-specific validators (no duplication)
- ✓ Test coverage: `scripts/test_validation_toolkit.py`
- ✓ Pre-commit enforcement: rejects new scripts defining duplicate validators
- ✓ Eliminated ~1,500+ lines of copy-pasted validation code

## Context

The `scripts/` directory contains 43+ catalog and registry validation scripts. Each independently defines the same set of validation helper functions:

| Function | Occurrences | Example files |
|---|---|---|
| `require_mapping()` | 43 | agent_tool_registry.py, api_gateway_catalog.py, command_catalog.py |
| `require_str()` | 37 | Same files, plus workflow_catalog.py, service_catalog.py, etc. |
| `require_list()` | 37 | Same |
| `require_bool()` | 12 | Same |
| `require_int()` | 12 | api_gateway_catalog.py, slo_catalog.py, etc. |
| `require_identifier()` | 8 | api_gateway_catalog.py, health_probe_catalog.py |
| `require_http_url()` | 6 | api_gateway_catalog.py, synthetic_transaction_catalog.py |

### The exact duplication

All three of these scripts define **identical** logic with only cosmetic differences in type annotations:

**`scripts/agent_tool_registry.py` (lines 57-78):**
```python
def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value
```

**`scripts/command_catalog.py` (lines 51-55):**
```python
def require_mapping(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value
```

**`scripts/api_gateway_catalog.py` (lines 32-35):**
```python
def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value
```

The same pattern repeats for `require_str`, `require_list`, `require_bool`, etc. — identical logic, inconsistent type annotations, subtly different error messages.

### Additional problems

1. **`require_int()` has inconsistent signatures** — some scripts accept a `minimum` parameter, others don't.
2. **Specialised validators** like `require_identifier()`, `require_http_url()`, `require_semver()` exist only in a subset of scripts. When a new catalog needs them, they're copy-pasted from whichever script the author found first.
3. **Error messages are inconsistent** — some say "must be an object", others "must be a mapping", others "expected dict".
4. **All 43 scripts already import from `controller_automation_toolkit`**, making it a natural dependency graph ancestor for a shared validation module.

## Decision

Create a shared **validation toolkit module** at `scripts/validation_toolkit.py` containing all canonical validation functions. All 43+ catalog/registry scripts must import from this module instead of defining their own helpers.

### File location

```
scripts/validation_toolkit.py
```

### Module contents — exact function signatures and implementations

The module must contain **exactly** the following functions. Implementers must reproduce these signatures and docstrings. Do not add extra functions, do not rename parameters, do not change error message formats.

```python
"""Shared validation helpers for all catalog and registry validation scripts.

Every function follows the same contract:
- Takes a value (of unknown type) and a path string (for error messages).
- Returns the value cast to the expected type if valid.
- Raises ValueError with a message of the form "{path} must be <description>".

Usage:
    from validation_toolkit import require_str, require_mapping, require_list
"""

from __future__ import annotations

from typing import Any


def require_str(value: Any, path: str, *, allow_empty: bool = False) -> str:
    """Validate that value is a string. By default rejects empty/whitespace-only strings."""
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a non-empty string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    """Validate that value is a dict/mapping."""
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str, *, min_length: int = 0) -> list[Any]:
    """Validate that value is a list, optionally with a minimum length."""
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    if len(value) < min_length:
        raise ValueError(f"{path} must have at least {min_length} item(s)")
    return value


def require_string_list(value: Any, path: str, *, min_length: int = 0) -> list[str]:
    """Validate that value is a list of non-empty strings."""
    items = require_list(value, path, min_length=min_length)
    for i, item in enumerate(items):
        require_str(item, f"{path}[{i}]")
    return items


def require_bool(value: Any, path: str) -> bool:
    """Validate that value is a boolean. Rejects truthy/falsy non-booleans."""
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_int(value: Any, path: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    """Validate that value is an integer (not a bool). Optionally enforce bounds."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{path} must be <= {maximum}")
    return value


def require_identifier(value: Any, path: str) -> str:
    """Validate that value is a lowercase alphanumeric identifier (hyphens and underscores allowed)."""
    s = require_str(value, path)
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", s):
        raise ValueError(
            f"{path} must be a lowercase identifier (letters, digits, hyphens, underscores; must start with a letter)"
        )
    return s


def require_http_url(value: Any, path: str) -> str:
    """Validate that value is a string starting with http:// or https://."""
    s = require_str(value, path)
    if not s.startswith(("http://", "https://")):
        raise ValueError(f"{path} must be an HTTP(S) URL")
    return s


def require_semver(value: Any, path: str) -> str:
    """Validate that value looks like a semantic version (e.g., 1.2.3, v1.2.3)."""
    s = require_str(value, path)
    import re
    if not re.fullmatch(r"v?\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?", s):
        raise ValueError(f"{path} must be a semantic version (e.g., 1.2.3 or v1.2.3)")
    return s


def require_enum(value: Any, path: str, allowed: set[str] | list[str]) -> str:
    """Validate that value is a string and is one of the allowed values."""
    s = require_str(value, path)
    allowed_set = set(allowed)
    if s not in allowed_set:
        raise ValueError(f"{path} must be one of: {', '.join(sorted(allowed_set))}")
    return s


def require_path(value: Any, path: str) -> str:
    """Validate that value is a non-empty string that looks like a filesystem or URL path (starts with /)."""
    s = require_str(value, path)
    if not s.startswith("/"):
        raise ValueError(f"{path} must be an absolute path starting with /")
    return s


def optional(value: Any, path: str, validator, **kwargs):
    """Apply a validator only if value is not None. Returns None if value is None."""
    if value is None:
        return None
    return validator(value, path, **kwargs)
```

### Migration procedure for each script

The implementer must follow this exact procedure for **each** of the 43+ scripts. Do not batch — migrate one script at a time and verify.

#### Step 1: Identify the script's local validation functions

Open the script and search for `def require_`. List all locally defined validation functions.

#### Step 2: Verify each local function matches the canonical version

Compare each local function body with the canonical version in `validation_toolkit.py`. If the logic is identical (ignoring type annotations and error message wording), it can be replaced. If the local function has genuinely different behaviour (e.g., a `require_str` that allows empty strings), use the canonical version with the appropriate keyword argument (e.g., `require_str(value, path, allow_empty=True)`).

#### Step 3: Replace local definitions with imports

At the top of the script, add the import:
```python
from validation_toolkit import require_str, require_mapping, require_list, require_bool
# Add only the functions actually used by this script
```

Delete the local `def require_*` function definitions.

#### Step 4: Verify the script still works

```bash
# Run the script's own validation mode (most scripts support --check or validate subcommand)
python scripts/<script_name>.py --check

# Run the full gate validation
make validate-schemas
```

#### Step 5: Commit the single script migration

```bash
git add scripts/validation_toolkit.py scripts/<script_name>.py
git commit -m "refactor(<script_name>): use shared validation_toolkit — ADR 0369"
```

### Import path considerations

All 43 scripts live in `scripts/` at the repo root. `validation_toolkit.py` also lives in `scripts/`. Since Python resolves imports relative to the working directory and these scripts are invoked from the repo root (via `make` or direct `python scripts/foo.py`), the import `from validation_toolkit import ...` will work if the working directory is `scripts/`, but **will fail** if the working directory is the repo root.

**Solution:** Use a relative import or `sys.path` adjustment. The canonical pattern already used by these scripts is:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

Many scripts already have this for importing `controller_automation_toolkit`. If a script already has this `sys.path` line, no change is needed — `from validation_toolkit import ...` will work. If it does not, add the `sys.path` line.

### Scripts to migrate (complete list)

The implementer must migrate **all** of these scripts. Check each one off as completed:

1. `scripts/agent_tool_registry.py`
2. `scripts/api_gateway_catalog.py`
3. `scripts/api_publication.py`
4. `scripts/atlas_schema.py`
5. `scripts/command_catalog.py`
6. `scripts/workflow_catalog.py`
7. `scripts/service_catalog.py`
8. `scripts/slo_catalog.py`
9. `scripts/health_probe_catalog.py`
10. `scripts/synthetic_transaction_catalog.py`
11. `scripts/subdomain_catalog.py`
12. `scripts/certificate_catalog.py`
13. `scripts/data_catalog.py`
14. `scripts/persona_catalog.py`
15. `scripts/seed_data_catalog.py`
16. `scripts/restic_file_backup_catalog.py`
17. `scripts/service_redundancy_catalog.py`
18. `scripts/gate_bypass_waiver_catalog.py`
19. `scripts/replaceability_review_catalog.py`
20. `scripts/immutable_guest_replacement_catalog.py`

Plus any other scripts found by running:
```bash
grep -rl "def require_mapping\|def require_str\|def require_list" scripts/ --include="*.py"
```

### What NOT to do

- Do **not** move `validation_toolkit.py` into a Python package with `__init__.py`. Keep it as a flat module in `scripts/`.
- Do **not** add dependencies beyond the Python standard library. The module must work in the Docker validation container which has minimal packages.
- Do **not** change the error message format `"{path} must be ..."`. The pre-push gate and CI log parsers grep for this pattern.
- Do **not** add logging, colour output, or other side effects. These are pure validation functions.
- Do **not** create a base class or metaclass abstraction. Keep it as simple top-level functions.

## Consequences

**Positive:**
- Eliminates ~1,500+ lines of copy-pasted validation code across 43+ scripts.
- Standardises error messages — operators see consistent output regardless of which catalog fails validation.
- New catalogs get all validators for free via a single import line.
- Bug fixes (e.g., the `require_int` accepting booleans issue) propagate to all consumers automatically.

**Negative / Trade-offs:**
- Adds a shared dependency: a breaking change to `validation_toolkit.py` can break all 43 scripts simultaneously. Mitigated by requiring the full `make validate-schemas` pass before merging any change to the toolkit.
- Migration is mechanical but tedious — 43 scripts to update. Can be done incrementally.

## Implementation plan

1. Create `scripts/validation_toolkit.py` with the exact functions listed above
2. Write a simple test: `scripts/test_validation_toolkit.py` that exercises each function with valid and invalid inputs
3. Migrate scripts one at a time, starting with `agent_tool_registry.py` (highest profile, will catch issues early)
4. After each migration, run `make validate-schemas` to verify
5. Once all scripts are migrated, add a pre-push gate check that greps for `def require_mapping` or `def require_str` in `scripts/` (excluding `validation_toolkit.py`) to prevent regressions

## Depends on

None — this is a self-contained refactor with no external dependencies.

## Related

- ADR 0048 (Command Catalog Pattern) — established the per-catalog validator pattern that created this duplication
- ADR 0039 (Controller Automation Toolkit) — `controller_automation_toolkit.py` is the existing shared module; `validation_toolkit.py` follows the same pattern
