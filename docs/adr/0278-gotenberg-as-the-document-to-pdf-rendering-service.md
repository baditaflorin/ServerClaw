# ADR 0278: Gotenberg As The Document-To-PDF Rendering Service

- Status: Accepted
- Implementation Status: Live on production from main
- Implemented In Repo Version: 0.177.92
- Implemented In Platform Version: 0.130.61
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

Several platform workflows need to produce PDF output:

- Windmill scheduled reports summarising metric trends or SLO status
- n8n automations that generate signed dispatch letters or compliance summaries
- ServerClaw (ADR 0254) sessions that draft structured documents the user
  wants to export as files
- Outline (ADR 0199) pages that need to be shared with parties who cannot
  access the internal wiki

Today these workflows either output Markdown or HTML and leave the PDF
rendering to the end user, or they skip document output entirely. There is
no shared service that converts HTML templates, Office documents, or Markdown
into PDFs programmatically.

Gotenberg is a CPU-only, stateless Docker microservice that exposes a REST
API for document conversion. It wraps Chromium (headless, no GPU) for HTML
and Markdown to PDF, and LibreOffice (headless) for Office format conversion.
Both renderers are bundled in the same container image.

## Decision

We will deploy **Gotenberg** as the shared document-to-PDF rendering service.

### Deployment rules

- Gotenberg runs as a Docker Compose service on the docker-runtime VM
- It is internal-only; no NGINX public route is issued
- The service is stateless; it requires no database, no volume, and no secrets
- API access is restricted to the guest network; inter-service authentication
  is handled by the API gateway route (ADR 0095) at the caller side

### Rendering contract

- HTML to PDF: callers POST a self-contained HTML file or a URL resolvable on
  the guest network; Gotenberg renders it with headless Chromium
- Markdown to PDF: callers POST a Markdown file; Gotenberg converts it to HTML
  then to PDF
- Office to PDF: callers POST a DOCX, XLSX, PPTX, or ODF file; Gotenberg
  converts it with headless LibreOffice
- all rendered PDFs are returned synchronously in the HTTP response body;
  the caller is responsible for storing the result in MinIO (ADR 0274) or
  wherever persistence is needed

### Caller conventions

- Windmill scripts call Gotenberg using the internal hostname and treat the
  call as a pure function: input document in, PDF bytes out
- n8n uses the HTTP Request node pointed at the internal Gotenberg endpoint
- no service should embed Chromium or LibreOffice locally to perform rendering
  that Gotenberg can handle

## Consequences

**Positive**

- PDF generation becomes a shared, stateless utility with a single upgrade
  surface instead of per-workflow bundled renderers.
- Workflows that produce HTML reports can trivially produce PDF versions of
  the same output without additional logic.
- Headless Chromium inside Gotenberg is CPU-only and does not require a
  display server, GPU, or elevated container privileges.

**Negative / Trade-offs**

- Chromium's memory footprint during rendering can spike; the Compose service
  must have a memory limit that accounts for concurrent rendering requests.
- Complex CSS layouts with custom web fonts may not render identically to
  browser output; callers are responsible for testing their templates against
  Gotenberg's renderer.

## Boundaries

- Gotenberg is a rendering utility only; it does not store documents, manage
  templates, or hold any workflow state.
- Gotenberg does not replace Apache Tika (ADR 0275) for text extraction;
  Tika reads existing documents, Gotenberg creates new PDFs.
- Gotenberg is not used for high-volume batch processing; it is a
  synchronous per-request renderer suited to operator and automation workloads.

## Related ADRs

- ADR 0095: API gateway as the unified platform entry point
- ADR 0151: n8n as the external app connector fabric
- ADR 0199: Outline as the living knowledge wiki
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline

## References

- <https://gotenberg.dev/docs/getting-started/introduction>
