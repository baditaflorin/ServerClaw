# ADR 0285: Paperless-ngx As The Document Management And Archive API

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform processes documents in several places:

- **Apache Tika** (ADR 0275) extracts text from uploaded files for the RAG
  pipeline
- **MinIO** (ADR 0274) stores raw document objects
- **Qdrant** (ADR 0198) indexes semantic embeddings of document chunks

None of these provide a document *lifecycle* layer: a place where documents
are tagged, classified, associated with correspondents and document types,
given a date, archived, and made retrievable by metadata or full-text search
without querying three separate systems.

Today, scanned documents, invoices, contracts, and reference PDFs are stored
as files in MinIO with no metadata beyond the object key. Retrieving a
specific document requires knowing its key. There is no API to ask "give me
all invoices from vendor X in 2025" or "show me documents tagged
`compliance`". Operators resort to browser sessions in MinIO's console or
`mc` commands to find files.

Paperless-ngx is a CPU-only, open-source document management system that
performs OCR on uploaded documents, classifies them by correspondent, type,
and tag, stores the full text and metadata in PostgreSQL, and exposes a
documented REST API for all document operations—upload, search, metadata
update, download, bulk edit, and deletion. The REST API includes an OpenAPI
specification and is the same interface used by the Paperless-ngx web UI,
meaning every UI action is also available as an authenticated HTTP call.

## Decision

We will deploy **Paperless-ngx** as the document management and archive API
for the platform.

### Deployment rules

- Paperless-ngx runs as a Docker Compose stack (web, worker, and broker)
  on the docker-runtime VM using the official `ghcr.io/paperless-ngx/paperless-ngx`
  image; Redis is deployed as a sidecar in the same stack for task queuing
- Authentication is delegated to Keycloak via OIDC (ADR 0063); local
  accounts are disabled except for the break-glass admin account whose
  password is stored in OpenBao (ADR 0077)
- The service is published under the platform subdomain model (ADR 0021) at
  `docs.<domain>`; the REST API is at `docs.<domain>/api/`
- Paperless-ngx uses the shared PostgreSQL cluster (ADR 0042) with a
  dedicated `paperless` database
- The document media directory (original files, OCR text, thumbnails) is
  stored on a named Docker volume included in the backup scope (ADR 0086);
  the volume is on a storage path with sufficient capacity for the document
  corpus
- Secrets (database password, OIDC client credentials, secret key) are
  injected from OpenBao following ADR 0077

### API-first operation rules

- Document upload is performed exclusively via the Paperless-ngx REST API
  (`POST /api/documents/post_document/`); drag-and-drop through the web UI
  is not the canonical path for automated ingestion pipelines
- Windmill flows that produce documents (export reports, generated PDFs from
  Gotenberg ADR 0278, signed contracts) call the upload API to archive them
  immediately; documents are never left as transient files in MinIO without
  a Paperless-ngx record
- Document search is performed via the REST API (`GET /api/documents/?query=`)
  from Windmill and n8n automation flows; direct PostgreSQL full-text queries
  against the Paperless schema are prohibited
- Correspondents, document types, and tags are declared in the Ansible role's
  `defaults/main.yml` taxonomy manifest and applied idempotently via the
  Paperless-ngx REST API on each converge; the taxonomy is not managed
  exclusively through the web UI
- The Paperless-ngx API token for automation is stored in OpenBao and
  retrieved at Windmill script initialisation; it is never committed to
  source

### OCR and metadata rules

- Paperless-ngx is configured to run OCR on all uploaded PDFs and images
  using Tesseract; the OCR language list is set in the Ansible role and
  includes the platform's primary operating languages
- documents uploaded via API may include `correspondent`, `document_type`,
  `tags`, and `created` fields; if not provided, the Paperless-ngx
  classifier assigns them based on trained rules
- the document `archive_serial_number` field is used to correlate Paperless
  records with external identifiers (e.g. invoice numbers, contract IDs)
  from upstream systems

## Consequences

**Positive**

- Any document produced or received by the platform is addressable by a
  stable REST API endpoint (`/api/documents/{id}/download/`) rather than
  an opaque MinIO object key.
- Full-text and metadata search are a single HTTP call; automation flows
  can locate specific documents without directory browsing or SQL queries.
- The OCR layer makes scanned documents searchable; the platform's document
  corpus is fully indexed without a separate OCR pipeline.
- The taxonomy (correspondents, types, tags) is version-controlled in the
  Ansible role and reproducible after a fresh deploy.

**Negative / Trade-offs**

- Paperless-ngx's Tesseract OCR can be slow for large scanned PDFs; the
  worker is CPU-bound during OCR and competes with other workloads on the
  docker-runtime VM.
- Documents stored in Paperless-ngx are a second copy of originals already
  in MinIO for some workflows; a clear ownership policy is required to
  avoid divergence between the MinIO object and the Paperless archive.

## Boundaries

- Paperless-ngx manages the document lifecycle for human-readable documents
  (PDFs, scanned images, contracts); it is not a general binary object store.
  Raw media files, container images, and data exports remain in MinIO
  (ADR 0274).
- Paperless-ngx does not replace the RAG pipeline (ADR 0198, ADR 0275) for
  LLM-context retrieval; it manages the document archive and provides
  full-text keyword search, not semantic similarity search.
- Paperless-ngx is not a digital signature service; document signing is out
  of scope.
- The Paperless-ngx web UI is available for operator review and manual
  classification corrections; write operations through the UI that modify the
  taxonomy catalogue are treated as drift and reconciled on the next converge.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline
- ADR 0278: Gotenberg as the document-to-PDF rendering service

## References

- <https://docs.paperless-ngx.com/api/>
- <https://docs.paperless-ngx.com/usage/#rest-api>
