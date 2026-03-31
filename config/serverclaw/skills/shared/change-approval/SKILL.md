---
name: Change Approval
description: Prepare or review governed platform mutations without bypassing approval, validation, or receipt policy.
metadata:
  openclaw:
    compatibility: skill-md
  lv3:
    tool_refs:
      - check-command-approval
      - run-governed-command
      - query-platform-context
---
Use this skill when the task is drifting from advice into a potential live mutation.

Check the approval contract before proposing execution. If more context is needed, query the platform context and explain the approval, validation, and receipt expectations clearly. Do not imply that SKILL.md access bypasses governed-command policy.
