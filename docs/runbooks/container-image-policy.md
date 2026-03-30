# Container Image Policy

## Purpose

This runbook defines how LV3 pins, scans, refreshes, and upgrades every managed container image covered by ADR 0068.

## Managed Sources

The machine-readable source of truth is [config/image-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/image-catalog.json).

Each entry records:

- the canonical image repository
- the approved tag
- the pinned `sha256` digest used on `linux/amd64`
- the last pin date
- the scan receipt path
- the converge targets that make the new pin live

Current scan receipts live under [receipts/image-scans](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/image-scans).

## Policy

1. Managed runtime images must use `image: repo:tag@sha256:digest`.
2. Managed build bases must use `FROM repo:tag@sha256:digest`.
3. `latest` is not allowed in the catalog or managed Compose inputs.
4. A new digest must have a Trivy receipt before it is committed.
5. Zero critical findings is the default gate. If the current official upstream image still reports critical CVEs, the catalog entry must carry a time-bounded exception with an owner and review date.
6. Managed converges read image refs from the catalog instead of hand-maintained per-role strings.
7. ADR 0269 exceptions must also record a justification, compensating controls,
   an expiry date, and an explicit remediation plan.

## Verification

Validate the catalog and receipts:

```bash
uvx --from pyyaml python scripts/validate_repository_data_models.py --validate
```

Check whether upstream tags have moved:

```bash
make check-image-freshness
```

Inspect the catalog directly:

```bash
python3 -c "import json; json.load(open('config/image-catalog.json'))"
```

## Upgrade Workflow

Preferred controller-side entry point:

```bash
make upgrade-container-image IMAGE_ID=windmill_runtime
```

The upgrade workflow does this:

1. resolves the current upstream digest for the catalog tag
2. scans the candidate ref with Trivy
3. writes a receipt under `receipts/image-scans/`
4. updates `config/image-catalog.json`
5. optionally runs the catalog's converge targets if `APPLY=true`

Dry-run example:

```bash
make upgrade-container-image IMAGE_ID=mail_platform_gateway_python_base
```

Write the updated catalog and rerun the affected converge path:

```bash
make upgrade-container-image IMAGE_ID=netbox_runtime WRITE=true APPLY=true
```

Allow a time-bounded exception when the official upstream image still reports critical CVEs:

```bash
make upgrade-container-image \
  IMAGE_ID=portainer_runtime \
  WRITE=true \
  EXCEPTION_OWNER="Platform operations" \
  EXCEPTION_EXPIRES_ON=2026-04-05 \
  EXCEPTION_JUSTIFICATION="Current upstream Portainer image still ships critical CVEs; keep the reviewed digest pinned until the next image cycle." \
  EXCEPTION_CONTROLS_JSON='["Digest pin prevents surprise upstream drift.","Service remains private-only while the upstream image is being remediated."]' \
  EXCEPTION_REMEDIATION_PLAN="Re-scan and refresh portainer_runtime before the exception expires."
```

## Windmill Surface

Windmill seeds `f/lv3/upgrade_container_image` as the governed operator-facing wrapper for this workflow.

That script expects a repo checkout path to exist on the worker host. The controller-side Python entry point remains the authoritative implementation because it owns the Git worktree, catalog mutation, and optional live apply.

## Initial Receipt Expectations

Each receipt records:

- the exact scanned image ref
- the scan date
- the Trivy image used for scanning
- the count of critical findings
- the count of high findings still present for operator review

Catalog exceptions record:

- why the image is still temporarily approved
- who owns the risk review
- which compensating controls bound the risk while the exception is open
- when the exception expires
- what remediation plan clears the exception before expiry

## Failure Rules

- If `make check-image-freshness` shows drift, do not update the digest without a new scan receipt.
- If Trivy reports any critical findings, do not commit the new digest without an explicit exception update in the catalog.
- If an apply target fails after a catalog update, revert the catalog change or complete the rollout before merging to `main`.
