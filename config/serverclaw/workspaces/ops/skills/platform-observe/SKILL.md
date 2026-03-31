---
name: Platform Observe (Ops Workspace Override)
description: Workspace-local override that prioritizes production receipts, live-applied runbooks, and current operator-safe routes.
metadata:
  openclaw:
    compatibility: skill-md
  lv3:
    tool_refs:
      - get-platform-status
      - list-recent-receipts
      - query-platform-context
    memory_refs:
      - memory:platform-context
    search_refs:
      - search:local-search
---
Use this workspace-local override for the `ops` workspace whenever a question touches the live estate.

Prefer the latest live-apply receipts and current runbooks over older architecture-only notes. When there is tension between intent and live state, surface the discrepancy explicitly and anchor the answer in the most recent verified evidence.
