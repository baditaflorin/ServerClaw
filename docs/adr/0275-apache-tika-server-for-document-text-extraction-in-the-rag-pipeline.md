# ADR 0275: Apache Tika Server For Document Text Extraction In The RAG Pipeline

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.102
- Implemented In Platform Version: 0.130.63
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

The platform's RAG context service (ADR 0198) and the ServerClaw memory
substrate (ADR 0263) accept user-supplied documents for semantic indexing, but
they have no extraction layer that converts binary file formats into clean
plaintext before embedding.

When a user uploads a PDF, a Word document, an Excel sheet, or an HTML page
today, the ingestion pipeline must either:

- reject non-plaintext inputs, or
- embed raw binary bytes that produce meaningless vectors

Neither outcome is acceptable as the document corpus grows. The embedding and
search quality depends entirely on the quality of the text fed to the Ollama
embedding model.

Tika Server is a CPU-only REST service that parses over a thousand file
formats and returns structured plaintext and metadata. It is the extraction
layer used by most enterprise search stacks for exactly this purpose.

## Decision

We will deploy **Apache Tika Server** as the canonical document extraction
service for the RAG and memory pipelines.

### Deployment rules

- Tika runs as a Docker Compose service on the docker-runtime VM
- It is internal-only; no NGINX route or public subdomain is issued for it
- The service exposes the standard `/tika` and `/meta` REST endpoints on the
  guest network
- Tika is stateless; it requires no database, no volume, and no secrets

### Extraction contract

- all non-plaintext document uploads entering the RAG or memory pipelines
  must pass through Tika before embedding
- Tika returns `text/plain` content plus metadata JSON; the pipeline stores
  both in the staging bucket (ADR 0274) before passing text to the embedder
- the pipeline preserves the Tika-reported MIME type and character set in the
  document provenance record

### Supported source types at launch

- PDF (including multi-column and scanned, where embedded text is present)
- Microsoft Office formats: DOCX, XLSX, PPTX, DOC, XLS, PPT
- OpenDocument formats: ODT, ODS, ODP
- HTML and XML (content extraction, not raw markup)
- plain text and CSV with charset detection

## Consequences

**Positive**

- RAG ingestion quality improves immediately because embeddings are generated
  from clean text instead of binary noise.
- The extraction layer is stateless and horizontally scalable without any
  coordination.
- Tika's MIME detection provides a verified content type that can gate what
  the pipeline accepts, preventing arbitrary file abuse.
- The wide format support future-proofs the corpus against format diversity
  without per-format parser maintenance.

**Negative / Trade-offs**

- Scanned-image PDFs without embedded text produce empty extraction results;
  OCR is not included in the standard Tika container and would require a
  separate decision.
- Tika's JVM startup overhead means it is not suited to one-shot invocation;
  it must run as a long-lived service to avoid cold-start latency on each
  extraction request.

## Boundaries

- Tika is the extraction layer only; it does not perform chunking, embedding,
  or storage.
- Tika does not replace the Ollama embedding model or the Qdrant vector store.
- OCR for purely image-based documents is out of scope for this ADR.
- Tika is not used for log parsing, metric ingestion, or structured config
  file handling.

## Related ADRs

- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3
- ADR 0263: Qdrant, PostgreSQL, and local search as the ServerClaw memory
  substrate
- ADR 0274: MinIO as the S3-compatible object storage layer

## References

- <https://tika.apache.org/2.9.2/gettingstarted.html>
