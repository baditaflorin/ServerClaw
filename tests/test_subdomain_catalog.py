import copy
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import service_catalog  # noqa: E402
import subdomain_catalog  # noqa: E402


class SubdomainCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = subdomain_catalog.load_subdomain_catalog()
        self.service_catalog = service_catalog.load_service_catalog()
        self.host_vars = subdomain_catalog.load_host_vars()
        self.public_edge_defaults = subdomain_catalog.load_public_edge_defaults()

    def test_repo_catalog_validates(self) -> None:
        subdomain_catalog.validate_subdomain_catalog(
            self.catalog,
            self.service_catalog,
            self.host_vars,
            self.public_edge_defaults,
        )

        reserved_prefixes = {item["prefix"] for item in self.catalog["reserved_prefixes"]}
        self.assertIn("docs", reserved_prefixes)
        self.assertIn("ops", reserved_prefixes)
        self.assertIn("mail", reserved_prefixes)

    def test_missing_edge_route_entry_fails(self) -> None:
        broken_catalog = copy.deepcopy(self.catalog)
        broken_catalog["subdomains"] = [
            entry
            for entry in broken_catalog["subdomains"]
            if entry["fqdn"] != "grafana.lv3.org"
        ]

        with self.assertRaisesRegex(
            ValueError,
            "repo-managed NGINX routes missing from the subdomain catalog",
        ):
            subdomain_catalog.validate_subdomain_catalog(
                broken_catalog,
                self.service_catalog,
                self.host_vars,
                self.public_edge_defaults,
            )

    def test_reserved_prefix_requires_allowlist(self) -> None:
        broken_catalog = copy.deepcopy(self.catalog)
        broken_catalog["subdomains"][0]["fqdn"] = "internal.lv3.org"

        with self.assertRaisesRegex(
            ValueError,
            "uses reserved prefix 'internal' without an explicit allowlist entry",
        ):
            subdomain_catalog.validate_subdomain_catalog(
                broken_catalog,
                self.service_catalog,
                self.host_vars,
                self.public_edge_defaults,
            )

    def test_provision_check_rejects_unrouted_edge_hostname(self) -> None:
        edge_route_hostnames = subdomain_catalog.collect_edge_route_hostnames(
            self.host_vars,
            self.public_edge_defaults,
        )
        entry = subdomain_catalog.get_subdomain_entry(
            self.catalog,
            "grafana.staging.lv3.org",
        )

        with self.assertRaisesRegex(
            ValueError,
            "no repo-managed NGINX route exists yet",
        ):
            subdomain_catalog.validate_provisionable_subdomain(entry, edge_route_hostnames)

    def test_ops_route_mode_is_edge(self) -> None:
        edge_route_hostnames = subdomain_catalog.collect_edge_route_hostnames(
            self.host_vars,
            self.public_edge_defaults,
        )
        entry = subdomain_catalog.get_subdomain_entry(self.catalog, "ops.lv3.org")

        self.assertEqual(
            subdomain_catalog.validate_provisionable_subdomain(entry, edge_route_hostnames),
            "edge",
        )

    def test_docs_route_mode_is_edge(self) -> None:
        edge_route_hostnames = subdomain_catalog.collect_edge_route_hostnames(
            self.host_vars,
            self.public_edge_defaults,
        )
        entry = subdomain_catalog.get_subdomain_entry(self.catalog, "docs.lv3.org")

        self.assertEqual(
            subdomain_catalog.validate_provisionable_subdomain(entry, edge_route_hostnames),
            "edge",
        )

    def test_status_page_route_mode_is_edge(self) -> None:
        edge_route_hostnames = subdomain_catalog.collect_edge_route_hostnames(
            self.host_vars,
            self.public_edge_defaults,
        )
        entry = subdomain_catalog.get_subdomain_entry(self.catalog, "status.lv3.org")

        self.assertEqual(
            subdomain_catalog.validate_provisionable_subdomain(entry, edge_route_hostnames),
            "edge",
        )


if __name__ == "__main__":
    unittest.main()
