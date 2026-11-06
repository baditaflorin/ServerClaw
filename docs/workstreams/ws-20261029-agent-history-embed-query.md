# WS-20261029: agent-history semantic search

## Status

Applied on 2026-10-29: #626 merged (eecdace2); the policy was applied by hand from main (rollback copy `/var/lib/tailscale-policy-sync/rollback/policy.20261029T204354Z.92ff5ba607e8.hujson` on CT108) and the role by the working provisioning command (failed=0). The embedding backlog drains unattended on mac14.

## Goal

The live store (VM 155) returned nothing for `semantic` and for the semantic leg of `hybrid`: no vector existed and the store had no
query-embedding endpoint. This change gives the store both halves: it embeds each search question through bge-m3 on an Apple-GPU Mac, and an
embedding worker on that Mac fills the vectors with a separate embed token.

## Change

- Role `agent_history_runtime`: the OpenBao key `embed_tokens` is rendered to `embed-token` and passed as `-embedTokenFile`; the embed flags
  (`-embedUrl -embedModel -embedApi -embedDimensions -embedTimeout -embedCacheSize`) are passed when `agent_history_embed_url` is set; the
  OpenBao Agent's health check waits for the new file; input assertions refuse an endpoint without a model, an `http` address outside a
  loopback, private or tailnet range, and a key set other than the five known names. The endpoint is set in `inventory/host_vars/agent-history.yml` (the Mac's tailnet IP is already in the policy), so a later converge cannot silently drop it.
- Tailnet policy: one grant, `tag:agent-history` to mac14's `/32`, `tcp:8443`, with a test that accepts that port and denies the Mac's ssh,
  screen sharing, https, the Ollama port itself, and the other Macs.
- Runbook section "Semantic search: the embeddings Mac" with the design, the reason for plain http by tailnet IP (Ollama's Host-header check),
  the check, the rollback and the token rotation.
- Test `tests/test_agent_history_runtime_embed.py` renders the real compose template and evaluates the real input assertions.
