from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
    monkeypatch.setenv("LV3_REPO_ROOT", str(repo_root))
    import replaceability_scorecards

    return importlib.reload(replaceability_scorecards)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_repo(root: Path) -> None:
    write_json(
        root / "config" / "replaceability-review-catalog.json",
        {
            "$schema": "docs/schema/replaceability-review-catalog.schema.json",
            "schema_version": "1.0.0",
            "policy": {
                "adr": "0212",
                "scope": "critical_integrated_product_adr",
                "notes": ["test"],
            },
            "critical_product_adrs": [
                {
                    "adr": "0042",
                    "capability_id": "internal_trust_authority",
                    "product_id": "step_ca",
                    "critical_surface": "ssh_and_internal_tls_issuance",
                    "capability_definition_refs": ["docs/adr/0205-capability-contracts-before-product-selection.md"],
                }
            ],
        },
    )
    write_text(
        root / "docs" / "adr" / "0205-capability-contracts-before-product-selection.md",
        "# ADR 0205: Capability Contracts Before Product Selection\n",
    )
    write_text(
        root / "docs" / "adr" / "0042-step-ca-for-ssh-and-internal-tls.md",
        """# ADR 0042: step-ca For SSH And Internal TLS

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.45.0
- Implemented In Platform Version: 0.22.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Replaceability Scorecard

- Capability Definition: `internal_trust_authority` anchored in ADR 0205.
- Contract Fit: strong fit for short-lived SSH and internal TLS issuance.
- Data Export / Import: CA config and issued artifacts can be exported and reimported into a replacement authority.
- Migration Complexity: medium because every SSH and TLS trust path must be reissued in order.
- Proprietary Surface Area: low and mostly limited to operational defaults.
- Approved Exceptions: none.
- Fallback / Downgrade: retain controller-local SSH keys and break-glass trust anchors during migration.
- Observability / Audit Continuity: certificate issuance and revocation events remain observable through repo-managed logs and receipts.

## Vendor Exit Plan

- Reevaluation Triggers: upstream abandonment, missing required auth methods, or unacceptable CA recovery gaps.
- Portable Artifacts: CA configuration, root and intermediate materials, issued-cert inventories, SSH principals, and trust bundles.
- Migration Path: stand up the replacement CA in parallel, trust both issuers briefly, reissue host and user certs, then retire step-ca.
- Alternative Product: Smallstep Certificate Manager or HashiCorp Vault PKI.
- Owner: platform security.
- Review Cadence: quarterly.
""",
    )


def test_catalog_and_sections_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_repo(tmp_path)
    module = load_module(monkeypatch, tmp_path)

    catalog = module.load_replaceability_review_catalog()
    reports = module.validate_replaceability_sections(catalog)

    assert len(reports) == 1
    assert reports[0].adr == "0042"
    assert reports[0].owner == "platform security."


def test_missing_required_field_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_repo(tmp_path)
    adr_path = tmp_path / "docs" / "adr" / "0042-step-ca-for-ssh-and-internal-tls.md"
    adr_path.write_text(
        adr_path.read_text(encoding="utf-8").replace(
            "- Alternative Product: Smallstep Certificate Manager or HashiCorp Vault PKI.\n",
            "",
        ),
        encoding="utf-8",
    )
    module = load_module(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="Alternative Product"):
        module.validate_replaceability_sections(module.load_replaceability_review_catalog())


def test_markdown_report_lists_governed_adrs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_repo(tmp_path)
    module = load_module(monkeypatch, tmp_path)

    report = module.render_markdown_report(module.load_replaceability_review_catalog())

    assert "| `0042` | `step_ca` | `internal_trust_authority` |" in report
