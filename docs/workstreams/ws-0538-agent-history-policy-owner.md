# WS-0538: Remove the temporary co-owner of tag:agent-history

## Status

In progress. The pull request is open and not merged; nothing is applied. No `[live-apply]` marker.

## Goal

ADR 0494 made `tag:pool-runtime` a temporary co-owner of `tag:agent-history` because the enrolment OAuth client can mint only `tag:pool-runtime` keys: the guest joined with that tag and re-advertised the new one. VM 155 is provisioned, the node carries `tag:agent-history` and is signed under Tailnet Lock, so the co-owner is no longer needed and is a standing risk (any `tag:pool-runtime` node could mint or re-tag into the store's tag).

## Change

`config/tailscale/policy.hujson`: `"tag:agent-history": ["group:admins"]` (was `["group:admins", "tag:pool-runtime"]`) and the comment says why. Nothing else.

## Applying it

The CT108 reconciler classifies it `blocked` (section `tagOwners` differs), so it is not applied automatically: a human runs `scripts/tailscale-policy-ct108.sh plan`, reads it, then `apply`. Merging changes nothing on the tailnet by itself.
