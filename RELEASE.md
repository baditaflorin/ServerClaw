# Release 0.177.26

- Date: 2026-03-28

## Summary
- integrated ADR 0198 by switching platform-context retrieval to local Ollama semantic embeddings, grounding operator and LLM query paths with cited vector matches, and hardening the governed `rag-context` live-apply wrapper across alias-aware service checks
- added bounded degraded-index recovery during governed live apply so the semantic platform-context collection self-heals legacy `384` to Ollama `768` vector-dimension drift without forcing a synchronous full mirrored-corpus rebuild

## Platform Impact
- this release is intended to promote the platform to `0.130.34` once the latest-`main` governed `rag-context` replay verifies healthy semantic vector retrieval on `docker-runtime-lv3`

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
