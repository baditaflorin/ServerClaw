# Dify Workflows

This directory stores exported Dify workflow artifacts that have been verified in the repo-managed environment and are ready for promotion toward Windmill-backed execution.

- branch-local smoke exports may be committed here during live-apply verification
- production promotion should prefer exported DSL artifacts over undocumented dashboard state
- this workstream keeps the initial smoke workflow here so another agent can replay import and export behavior without hidden context
