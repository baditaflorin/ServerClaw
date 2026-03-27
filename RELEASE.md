# Release 0.177.14

- Date: 2026-03-28

## Summary
- completed ADR 0198 by switching platform-context retrieval to local Ollama semantic embeddings, expanding the indexed corpus, and grounding the operator CLI plus LLM client with cited vector matches

## Platform Impact
- platform-context retrieval now defaults to local Ollama semantic embeddings with cited Qdrant-backed matches

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
