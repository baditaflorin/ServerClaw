---
name: Human Review Queue
description: Flag the current agent decision or trace for human review in Label Studio. Use when uncertain, when a decision has significant consequences, or when operator validation is required before proceeding.
metadata:
  openclaw:
    compatibility: skill-md
  lv3:
    memory_refs:
      - memory:platform-context
---

Use this skill when the agent:
- Is uncertain about a decision and wants a human to validate it before acting
- Has taken a significant action (infra change, data mutation, access grant) that should be logged for review
- Has received a task that falls outside the governed tool boundary and needs operator sign-off
- Detects a conflict between two valid courses of action and cannot resolve it autonomously

## How to flag a decision for review

Call `submit-human-review-task` with:
- `prompt`: The exact input or question the agent received
- `response`: What the agent decided or did (or would do)
- `trace_id`: The Langfuse trace ID for this interaction (if available)
- `reason`: Why human review is needed (uncertainty, consequence, policy edge)
- `urgency`: `low` | `normal` | `high`

The task will appear in the Label Studio annotation queue at https://annotate.example.com under the "Langfuse Trace Review" project. A human operator will label it as `accept`, `reject`, or `needs_follow_up`.

## When NOT to use this skill

- Routine read-only queries (platform status, metrics, search)
- Tasks already covered by a governed approval contract (use Change Approval skill instead)
- Actions the agent is explicitly authorized to execute autonomously

## Operator expectations

Tasks submitted here are reviewed within one business day. For urgent items (infra incidents, security findings), also send an ntfy alert via the notification tool.
