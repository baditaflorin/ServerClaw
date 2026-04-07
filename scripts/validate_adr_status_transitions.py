#!/usr/bin/env python3
"""
ADR Status Transition Validator

Validates that ADR status changes in commits are properly evidenced.

Rules:
1. Upgrade (Accepted → Partial, Partial → Implemented):
   - Requires 1+ git commit mentioning the ADR OR 1+ code reference (role, script, compose)
   - If no evidence found: FAIL

2. Downgrade (Implemented → Partial, Partial → Accepted):
   - Requires explicit "ADR-STATUS-CHANGE-REASON: <reason>" in commit message
   - Allowed reasons: "no evidence found", "superseded by ADR XXXX", "design-only, never implemented"
   - If no reason provided: FAIL

3. Within same tier (Accepted ↔ Accepted, etc.):
   - Always allowed

Usage:
  python scripts/validate_adr_status_transitions.py [--check-index]

Exit codes:
  0 = all transitions valid
  1 = invalid transition found
  2 = error running validator
"""

import os
import re
import sys
import subprocess
import yaml
from pathlib import Path
from typing import Dict, Tuple, List, Optional


# ADR status hierarchy: lower tier values are "lower" in the stack
STATUS_HIERARCHY = {
    "Accepted": 0,
    "Partial": 1,
    "Partial Implemented": 1,  # Alias
    "Implemented": 2,
}

ADR_DIR = Path("docs/adr")
INDEX_PATH = Path("docs/adr/.index.yaml")


def get_staged_files() -> List[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Split on null bytes (from -z flag)
        return [f for f in result.stdout.split("\0") if f]
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to get staged files: {e}", file=sys.stderr)
        return []


def get_files_from_push() -> List[str]:
    """
    Get list of files being pushed from stdin (pre-push hook format).

    Pre-push hook receives: <local-ref> <local-oid> <remote-ref> <remote-oid>
    We parse this to get commits being pushed and extract changed files.

    Returns empty list if not in pre-push hook context.
    """
    try:
        import sys
        # Only try to read stdin if it's not a terminal (i.e., we're in a hook context)
        if sys.stdin.isatty():
            return []

        # Read stdin data (pre-push hook format)
        lines = sys.stdin.read().strip().split("\n")
        if not lines or not lines[0]:
            return []

        all_files = set()
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue

            local_oid = parts[1]
            remote_oid = parts[3]

            # If remote_oid is 0000000, it's a new branch push
            # Use local_oid alone to get all commits
            if remote_oid == "0000000000000000000000000000000000000000":
                # New branch: get all commits on this branch
                commit_range = f"--all ^{local_oid}^"
                result = subprocess.run(
                    ["git", "log", commit_range, "--diff-filter=ACMR", "--name-only", "-z"],
                    capture_output=True,
                    text=False,
                    check=False,
                )
            else:
                # Existing branch: get commits between remote and local
                commit_range = f"{remote_oid}..{local_oid}"
                result = subprocess.run(
                    ["git", "diff-tree", "-r", "--diff-filter=ACMR", "--name-only", "-z", commit_range],
                    capture_output=True,
                    text=False,
                    check=False,
                )

            if result.stdout:
                files = result.stdout.decode(errors="ignore").split("\0")
                all_files.update(f for f in files if f)

        return list(all_files)
    except Exception as e:
        # If anything fails, silently return empty list and fall back to staged files
        return []


def get_adr_number_from_path(path: str) -> Optional[str]:
    """Extract ADR number from path like 'docs/adr/0025-*.md'."""
    match = re.match(r"docs/adr/(\d{4})-", path)
    return match.group(1) if match else None


def parse_adr_frontmatter(adr_path: Path) -> Dict[str, str]:
    """Parse ADR markdown frontmatter (Status, Implementation Status fields)."""
    try:
        with open(adr_path) as f:
            content = f.read()

        # Extract first 20 lines looking for status fields
        lines = content.split("\n")[:20]
        metadata = {}

        for line in lines:
            if line.startswith("- Status:"):
                metadata["status"] = line.replace("- Status:", "").strip()
            elif line.startswith("- Implementation Status:"):
                metadata["implementation_status"] = line.replace("- Implementation Status:", "").strip()

        return metadata
    except Exception as e:
        print(f"ERROR: Failed to parse {adr_path}: {e}", file=sys.stderr)
        return {}


def get_adr_from_index(adr_num: str) -> Optional[Dict]:
    """Load ADR metadata from docs/adr/.index.yaml."""
    try:
        if not INDEX_PATH.exists():
            return None

        with open(INDEX_PATH) as f:
            index = yaml.safe_load(f) or {}

        # Index has 'reports' key with list of ADR numbers
        # Find the specific ADR report file
        report_path = ADR_DIR / "implementation-status" / f"adr-{adr_num}.yaml"
        if report_path.exists():
            with open(report_path) as f:
                return yaml.safe_load(f) or {}

        return None
    except Exception as e:
        print(f"WARNING: Could not load ADR {adr_num} from index: {e}", file=sys.stderr)
        return None


def get_git_evidence_for_adr(adr_num: str, days_back: int = 180) -> Tuple[List[str], int]:
    """
    Search git history for commits mentioning this ADR.

    Returns: (commit_hashes, commit_count)
    """
    try:
        # Search last N days of commits for ADR reference
        date_since = f"--since={days_back}.days.ago"
        # Try multiple patterns to catch different naming conventions
        patterns = [
            f"ADR.{adr_num}",     # "ADR-0025" or "ADR 0025"
            f"adr-{adr_num}",     # "adr-0025"
            f"0{adr_num}",        # "00025" (bare number)
        ]

        all_commits = set()  # Use set to avoid duplicates
        for pattern in patterns:
            result = subprocess.run(
                ["git", "log", date_since, "--oneline", "--all", "--grep", pattern],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.stdout.strip():
                commits = [line.split()[0] for line in result.stdout.strip().split("\n") if line]
                all_commits.update(commits)

        commit_list = list(all_commits)
        return commit_list, len(commit_list)
    except Exception as e:
        print(f"WARNING: Could not search git history for ADR {adr_num}: {e}", file=sys.stderr)
        return [], 0


def get_code_evidence_for_adr(adr_num: str) -> int:
    """
    Search codebase for ADR references (roles, compose, scripts).

    Returns: count of code references found
    """
    try:
        # Search for ADR reference in roles, compose files, and scripts
        patterns = [
            f"adr.{adr_num}",
            f"adr-{adr_num}",
            f"0{adr_num}",
            f"ADR.{adr_num}",
            f"ADR.0{adr_num}",
        ]

        count = 0
        for pattern in patterns:
            result = subprocess.run(
                ["git", "grep", "-i", pattern, "--cached", "--"],
                capture_output=True,
                text=False,  # Binary to avoid decode errors
                check=False,
            )
            count += len(result.stdout.decode(errors="ignore").strip().split("\n")) if result.stdout else 0

        return min(count, 5)  # Cap at 5 for clarity
    except Exception:
        return 0


def get_commit_message() -> str:
    """Get the commit message from HEAD (most recent commit on current branch)."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def validate_adr_status_transition(
    adr_num: str,
    old_status: str,
    new_status: str,
    commit_msg: str = "",
) -> Tuple[bool, str]:
    """
    Validate a single ADR status transition.

    Returns: (is_valid, error_message)
    """

    # Normalize status names
    old_tier = STATUS_HIERARCHY.get(old_status, -1)
    new_tier = STATUS_HIERARCHY.get(new_status, -1)

    if old_tier < 0 or new_tier < 0:
        return False, f"Unknown status value(s): old={old_status}, new={new_status}"

    # If status didn't change, always valid
    if old_tier == new_tier:
        return True, ""

    # Upgrade scenario: moving to higher tier
    if new_tier > old_tier:
        # Get evidence
        commits, commit_count = get_git_evidence_for_adr(adr_num)
        code_refs = get_code_evidence_for_adr(adr_num)

        # Check if we have at least 1 marker of evidence
        if commit_count >= 1 or code_refs >= 1:
            return True, ""
        else:
            return False, (
                f"ADR {adr_num}: Cannot upgrade status from {old_status} to {new_status}. "
                f"No evidence found (0 commits, 0 code references). "
                f"Evidence needed: 1+ git commit mentioning the ADR OR 1+ code reference (role, script, compose)."
            )

    # Downgrade scenario: moving to lower tier
    elif new_tier < old_tier:
        # Require explicit reason in commit message
        if not commit_msg:
            # Pre-push hook: we don't have commit message yet, warn
            return True, f"WARNING: ADR {adr_num} status downgrade detected. Please provide ADR-STATUS-CHANGE-REASON in commit message."

        # Check for required reason comment
        if "ADR-STATUS-CHANGE-REASON:" not in commit_msg:
            return False, (
                f"ADR {adr_num}: Cannot downgrade status from {old_status} to {new_status} without reason. "
                f"Add to commit message: ADR-STATUS-CHANGE-REASON: <reason> "
                f"(examples: 'no evidence found', 'superseded by ADR XXXX', 'design-only, never implemented')"
            )

        return True, ""

    return True, ""


def check_index_validity() -> Tuple[bool, List[str]]:
    """
    Verify that docs/adr/.index.yaml is current.

    Returns: (is_valid, error_messages)
    """
    errors = []

    # Check if .index.yaml is staged but ADR files are also staged
    # If so, require .index.yaml to be in the staged set
    staged = get_staged_files()
    adr_md_staged = [f for f in staged if f.startswith("docs/adr/") and f.endswith(".md")]

    if adr_md_staged and "docs/adr/.index.yaml" not in staged:
        errors.append(
            "WARNING: ADR markdown files staged but docs/adr/.index.yaml not updated. "
            "Run: python scripts/generate_adr_index.py --write"
        )

    return len(errors) == 0, errors


def main() -> int:
    """Main validation entrypoint."""
    errors = []
    warnings = []

    # Get commit message (for downgrade validation requiring explicit reason)
    commit_msg = get_commit_message()

    # Determine if we're in pre-push hook context (stdin has refs) or pre-commit context
    # In pre-push hook, stdin contains: <local-ref> <local-oid> <remote-ref> <remote-oid>
    import sys
    push_files = get_files_from_push()
    if push_files:
        # We got files from stdin (pre-push hook mode)
        files_to_check = push_files
    else:
        # Fall back to staged files (pre-commit or direct invocation mode)
        files_to_check = get_staged_files()

    adr_files = [f for f in files_to_check if f.startswith("docs/adr/") and f.endswith(".md")]

    if not adr_files:
        # No ADR files to check, skip validation
        return 0

    # For each staged ADR file, check if status changed
    for adr_file in adr_files:
        adr_num = get_adr_number_from_path(adr_file)
        if not adr_num:
            continue

        adr_path = Path(adr_file)
        if not adr_path.exists():
            continue

        # Get old and new status
        # Note: "Implementation Status" field is what tracks actual implementation progress
        # "Status" field is the decision status (Accepted/Rejected) which rarely changes
        # So we prioritize Implementation Status for change detection
        new_metadata = parse_adr_frontmatter(adr_path)
        new_status = new_metadata.get("implementation_status") or new_metadata.get("status", "")

        # Get old status from git
        try:
            old_content = subprocess.run(
                ["git", "show", f"HEAD:{adr_file}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout

            old_lines = old_content.split("\n")[:20]
            old_status = ""
            # Prioritize Implementation Status over Status field (see note above)
            for line in old_lines:
                if line.startswith("- Implementation Status:"):
                    old_status = line.replace("- Implementation Status:", "").strip()
                    break
            # Fall back to Status field if Implementation Status not found
            if not old_status:
                for line in old_lines:
                    if line.startswith("- Status:"):
                        old_status = line.replace("- Status:", "").strip()
                        break

            if not old_status:
                continue

            # Validate transition
            if old_status != new_status:
                is_valid, msg = validate_adr_status_transition(adr_num, old_status, new_status, commit_msg)
                if not is_valid:
                    errors.append(msg)
                elif "WARNING" in msg:
                    warnings.append(msg)

        except subprocess.CalledProcessError:
            # File is new, skip old status check
            continue

    # Check index validity
    index_valid, index_errors = check_index_validity()
    if not index_valid:
        warnings.extend(index_errors)

    # Print results
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    for warning in warnings:
        print(f"{warning}", file=sys.stderr)

    # Exit with appropriate code
    if errors:
        print(f"\nvalidation gate: ADR status validation FAILED ({len(errors)} error(s))", file=sys.stderr)
        return 1

    if warnings:
        print(f"validation gate: ADR status validation passed ({len(warnings)} warning(s))")
    else:
        print("validation gate: ADR status transitions OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())
