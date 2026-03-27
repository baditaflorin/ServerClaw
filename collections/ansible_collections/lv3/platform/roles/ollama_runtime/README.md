# ollama_runtime

Converges a private Ollama runtime on `docker-runtime-lv3`, persists pulled models
under `/data/ollama/models`, and syncs the repo-managed startup models declared in
`config/ollama-models.yaml`.
