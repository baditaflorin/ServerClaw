from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_configure_edge_publication_builds_shared_static_artifacts_first() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "configure-edge-publication:\n\t$(MAKE) preflight WORKFLOW=configure-edge-publication\n\tuvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate\n\t$(MAKE) generate-changelog-portal docs\n" in makefile


def test_route_dns_assertion_ledger_runs_public_endpoint_admission_before_apply() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "route-dns-assertion-ledger:\n\t$(MAKE) preflight WORKFLOW=route-dns-assertion-ledger\n\tuvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate\n" in makefile
