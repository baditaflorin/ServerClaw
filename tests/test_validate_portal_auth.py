import copy
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import subdomain_catalog  # noqa: E402
import validate_portal_auth  # noqa: E402


class ValidatePortalAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = subdomain_catalog.load_subdomain_catalog()
        self.public_edge_defaults = subdomain_catalog.load_public_edge_defaults()

    def test_repo_portal_auth_validates(self) -> None:
        validate_portal_auth.validate_portal_auth(self.catalog, self.public_edge_defaults)

    def test_public_classification_requires_justification(self) -> None:
        broken = copy.deepcopy(self.catalog)
        broken["subdomains"][1]["justification"] = None

        with self.assertRaisesRegex(ValueError, "public auth classifications must include a non-empty justification"):
            validate_portal_auth.validate_portal_auth(broken, self.public_edge_defaults)

    def test_docs_portal_must_be_readonly_keycloak(self) -> None:
        broken = copy.deepcopy(self.catalog)
        docs_entry = next(entry for entry in broken["subdomains"] if entry["fqdn"] == "docs.lv3.org")
        docs_entry["auth_requirement"] = "public_informational"
        docs_entry["justification"] = "broken"

        with self.assertRaisesRegex(
            ValueError,
            "portal hostname 'docs.lv3.org' must declare auth_requirement='keycloak_oidc_readonly'",
        ):
            validate_portal_auth.validate_portal_auth(broken, self.public_edge_defaults)

    def test_protected_edge_hostname_must_stay_keycloak_gated(self) -> None:
        broken = copy.deepcopy(self.catalog)
        ops_entry = next(entry for entry in broken["subdomains"] if entry["fqdn"] == "ops.lv3.org")
        ops_entry["auth_requirement"] = "token_auth"

        with self.assertRaisesRegex(
            ValueError,
            "portal hostname 'ops.lv3.org' must declare auth_requirement='keycloak_oidc'",
        ):
            validate_portal_auth.validate_portal_auth(broken, self.public_edge_defaults)


if __name__ == "__main__":
    unittest.main()
