---
name: Platform Observe
description: Summarize current LV3 platform state and query repo-grounded context before suggesting changes.
metadata:
  openclaw:
    compatibility: skill-md
  lv3:
    tool_refs:
      - get-platform-status
      - query-platform-context
    memory_refs:
      - memory:platform-context
    search_refs:
      - search:local-search
---
Use this skill when the user needs a quick operational picture of the LV3 platform.

Start by checking the current platform status. If the answer depends on repository context, query the platform-context API before making recommendations. Stay within governed tools and repo-grounded evidence rather than assuming hidden shell access.
