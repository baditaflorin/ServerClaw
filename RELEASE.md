# Release 0.142.0

- Date: 2026-03-25

## Summary
- Implemented ADR 0145 with a repo-managed Ollama runtime on `docker-runtime-lv3`, a pinned `ollama/ollama:0.18.2` image, a declarative startup model catalog, and health/dependency/catalog wiring for the new private inference service.
- Added `platform/llm/client.py` plus bounded goal-compiler fallback routing so unmatched instructions can use local inference without breaking deterministic rule matches, and recorded those calls under the new `llm.inference` ledger event type.
- Wired Open WebUI to the private Ollama endpoint through `host.docker.internal`, added controller and guest runbooks for the local inference path, and verified live Ollama connectivity with startup-model presence plus a three-run latency probe on `llama3.2:3b`.
- Recorded the mainline live-apply receipts for the private Ollama runtime and the Open WebUI connector after re-converging both stacks on 2026-03-25.

## Platform Impact
- repository version advances to 0.142.0; platform version advances to 0.130.2 after the ADR 0145 private Ollama runtime and Open WebUI connector are live-applied from `main`

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
