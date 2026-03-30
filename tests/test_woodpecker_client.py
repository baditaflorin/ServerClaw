from __future__ import annotations

from platform.ansible import woodpecker


class FakeGiteaClient:
    def __init__(self, applications):
        self.applications = list(applications)
        self.created: list[dict] = []
        self.updated: list[tuple[int, dict]] = []
        self.deleted: list[int] = []

    def list_oauth_applications(self):
        return list(self.applications)

    def create_oauth_application(self, payload):
        created = dict(payload, id=9, client_id="woodpecker-client", client_secret="woodpecker-secret")
        self.created.append(created)
        return created

    def update_oauth_application(self, application_id, payload):
        self.updated.append((application_id, payload))
        return payload

    def delete_oauth_application(self, application_id):
        self.deleted.append(application_id)


def test_api_candidates_try_both_current_and_legacy_prefixes() -> None:
    assert woodpecker._api_candidates("/user") == ["/user", "/api/user"]
    assert woodpecker._api_candidates("/api/user/token") == ["/user/token", "/api/user/token"]


def test_split_repository_full_name_rejects_invalid_values() -> None:
    try:
        woodpecker.split_repository_full_name("ops")
    except ValueError as exc:
        assert "owner/name" in str(exc)
    else:
        raise AssertionError("Expected split_repository_full_name to reject single-segment names")


def test_ensure_gitea_oauth_application_reuses_existing_credentials_when_present() -> None:
    client = FakeGiteaClient(
        [
            {
                "id": 4,
                "name": "LV3 Woodpecker",
                "redirect_uris": ["https://ci.lv3.org/authorize"],
                "confidential_client": True,
                "skip_secondary_authorization": True,
                "client_id": "existing-client",
            }
        ]
    )

    result = woodpecker.ensure_gitea_oauth_application(
        client,
        name="LV3 Woodpecker",
        redirect_uri="https://ci.lv3.org/authorize",
        existing_client_id="existing-client",
        existing_client_secret="existing-secret",
    )

    assert result == {
        "id": 4,
        "client_id": "existing-client",
        "client_secret": "existing-secret",
        "recreated": False,
    }
    assert client.updated == []
    assert client.deleted == []
    assert client.created == []


def test_ensure_gitea_oauth_application_recreates_when_secret_is_missing() -> None:
    client = FakeGiteaClient(
        [
            {
                "id": 4,
                "name": "LV3 Woodpecker",
                "redirect_uris": ["https://old.example/authorize"],
                "confidential_client": True,
                "skip_secondary_authorization": False,
            }
        ]
    )

    result = woodpecker.ensure_gitea_oauth_application(
        client,
        name="LV3 Woodpecker",
        redirect_uri="https://ci.lv3.org/authorize",
    )

    assert result["client_id"] == "woodpecker-client"
    assert result["client_secret"] == "woodpecker-secret"
    assert result["recreated"] is True
    assert client.updated == [
        (
            4,
            {
                "name": "LV3 Woodpecker",
                "redirect_uris": ["https://ci.lv3.org/authorize"],
                "confidential_client": True,
                "skip_secondary_authorization": True,
            },
        )
    ]
    assert client.deleted == [4]
    assert len(client.created) == 1


def test_request_candidates_fall_back_from_404_to_legacy_api_path() -> None:
    client = woodpecker.WoodpeckerClient("http://example.test", "token", verify_ssl=False)
    seen: list[str] = []

    def fake_request_once(path, *, method="GET", payload=None, expected_statuses=None, accept_json=True):
        seen.append(path)
        if path == "/user":
            raise woodpecker._HttpStatusError("GET /user returned HTTP 404", status=404, body="")
        return 200, {"login": "ops-gitea"}

    client._request_once = fake_request_once  # type: ignore[method-assign]

    assert client.get_user() == {"login": "ops-gitea"}
    assert seen == ["/user", "/api/user"]
