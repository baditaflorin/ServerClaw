import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_configure_edge_publication_builds_shared_static_artifacts_first() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert (
        "configure-edge-publication:\n\t$(MAKE) preflight WORKFLOW=configure-edge-publication\n\t$(MAKE) generate-platform-vars\n\tuvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --write-registry --validate\n\t$(MAKE) generate-changelog-portal docs\n"
        in makefile
    )


def test_converge_matrix_synapse_builds_and_validates_edge_publication_prerequisites() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert (
        "converge-matrix-synapse:\n\t$(MAKE) preflight WORKFLOW=converge-matrix-synapse\n\tuvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate\n\t$(MAKE) generate-edge-static-sites\n"
        in makefile
    )


def test_converge_keycloak_bootstrap_materializes_shared_edge_generated_portals() -> None:
    workflows = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))["workflows"]

    assert workflows["converge-keycloak"]["preflight"]["bootstrap_manifest_ids"] == ["shared-edge-generated-portals"]


def test_route_dns_assertion_ledger_runs_public_endpoint_admission_before_apply() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert (
        "route-dns-assertion-ledger:\n\t$(MAKE) preflight WORKFLOW=route-dns-assertion-ledger\n\tuvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate\n"
        in makefile
    )
