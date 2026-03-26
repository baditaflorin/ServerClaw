from __future__ import annotations

from platform.ansible import semaphore


class FakeClient:
    def __init__(self, *, projects=None, repositories=None, inventories=None, templates=None):
        self.projects = projects or []
        self.repositories = repositories or {}
        self.inventories = inventories or {}
        self.templates = templates or {}
        self.updated: list[tuple[str, int, dict]] = []
        self.created: list[tuple[str, dict]] = []

    def list_projects(self, *, use_bearer=True):
        return self.projects

    def create_project(self, payload, *, use_bearer=True):
        created = dict(payload, id=7)
        self.created.append(("project", created))
        return created

    def update_project(self, project_id, payload, *, use_bearer=True):
        self.updated.append(("project", project_id, payload))
        return payload

    def list_repositories(self, project_id, *, use_bearer=True):
        return self.repositories.get(project_id, [])

    def create_repository(self, project_id, payload, *, use_bearer=True):
        created = dict(payload, id=9)
        self.created.append(("repository", created))
        return created

    def update_repository(self, project_id, repository_id, payload, *, use_bearer=True):
        self.updated.append(("repository", repository_id, payload))
        return payload

    def list_inventories(self, project_id, *, use_bearer=True):
        return self.inventories.get(project_id, [])

    def create_inventory(self, project_id, payload, *, use_bearer=True):
        created = dict(payload, id=11)
        self.created.append(("inventory", created))
        return created

    def update_inventory(self, project_id, inventory_id, payload, *, use_bearer=True):
        self.updated.append(("inventory", inventory_id, payload))
        return payload

    def list_templates(self, project_id, *, use_bearer=True):
        return self.templates.get(project_id, [])

    def create_template(self, project_id, payload, *, use_bearer=True):
        created = dict(payload, id=13)
        self.created.append(("template", created))
        return created

    def update_template(self, project_id, template_id, payload, *, use_bearer=True):
        self.updated.append(("template", template_id, payload))
        return payload


def test_ensure_project_updates_only_when_values_change() -> None:
    client = FakeClient(projects=[{"id": 3, "name": "LV3 Semaphore", "type": "", "alert": False, "max_parallel_tasks": 0}])
    result = semaphore.ensure_project(
        client,
        {"name": "LV3 Semaphore", "type": "", "alert": False, "max_parallel_tasks": 2},
    )

    assert result["max_parallel_tasks"] == 2
    assert client.updated == [("project", 3, {"name": "LV3 Semaphore", "type": "", "alert": False, "max_parallel_tasks": 2, "id": 3})]


def test_find_none_key_id_uses_builtin_none_key() -> None:
    key_id = semaphore.find_none_key_id(
        [
            {"id": 2, "name": "SSH", "type": "ssh"},
            {"id": 5, "name": "None", "type": "none"},
        ]
    )

    assert key_id == 5


def test_ensure_repository_inventory_and_template_use_name_matching() -> None:
    client = FakeClient(
        repositories={1: [{"id": 2, "name": "repo", "project_id": 1, "git_url": "/srv/repo", "git_branch": "main", "ssh_key_id": 1}]},
        inventories={1: [{"id": 4, "name": "localhost", "project_id": 1, "inventory": "inventory/semaphore-localhost.yml", "ssh_key_id": 1, "type": "file"}]},
        templates={1: [{"id": 6, "name": "Semaphore Self-Test", "project_id": 1, "playbook": "playbooks/semaphore-self.yml", "arguments": "[]", "app": "ansible", "inventory_id": 4, "repository_id": 2, "task_params": {"allow_debug": False}}]},
    )

    repository = semaphore.ensure_repository(
        client,
        1,
        {"name": "repo", "git_url": "/srv/repo", "git_branch": "main", "ssh_key_id": 1},
    )
    inventory = semaphore.ensure_inventory(
        client,
        1,
        {"name": "localhost", "inventory": "inventory/semaphore-localhost.yml", "ssh_key_id": 1, "type": "file"},
    )
    template = semaphore.ensure_template(
        client,
        1,
        {
            "name": "Semaphore Self-Test",
            "playbook": "playbooks/semaphore-self.yml",
            "arguments": "[]",
            "app": "ansible",
            "inventory_id": 4,
            "repository_id": 2,
            "task_params": {"allow_debug": False},
        },
    )

    assert repository["id"] == 2
    assert inventory["id"] == 4
    assert template["id"] == 6
    assert client.updated == []


def test_ensure_template_updates_when_inventory_changes() -> None:
    client = FakeClient(
        templates={1: [{"id": 6, "name": "Semaphore Self-Test", "project_id": 1, "playbook": "playbooks/semaphore-self.yml", "arguments": "[]", "app": "ansible", "inventory_id": 4, "repository_id": 2, "task_params": {"allow_debug": False}}]}
    )

    semaphore.ensure_template(
        client,
        1,
        {
            "name": "Semaphore Self-Test",
            "playbook": "playbooks/semaphore-self.yml",
            "arguments": "[]",
            "app": "ansible",
            "inventory_id": 8,
            "repository_id": 2,
            "task_params": {"allow_debug": False},
        },
    )

    assert client.updated == [
        (
            "template",
            6,
            {
                "name": "Semaphore Self-Test",
                "playbook": "playbooks/semaphore-self.yml",
                "arguments": "[]",
                "app": "ansible",
                "inventory_id": 8,
                "repository_id": 2,
                "task_params": {"allow_debug": False},
                "project_id": 1,
                "id": 6,
            },
        )
    ]


def test_create_api_token_accepts_created_status() -> None:
    client = semaphore.SemaphoreClient("http://example.test", verify_ssl=False)

    def fake_request(path, *, method="GET", payload=None, use_bearer=False, expected_statuses=None, accept_json=True):
        assert path == "/api/user/tokens"
        assert method == "POST"
        assert payload == {}
        assert expected_statuses == {201}
        return 201, {"id": "token-123"}

    client._request = fake_request  # type: ignore[method-assign]

    assert client.create_api_token() == "token-123"


def test_update_project_accepts_no_content_status() -> None:
    client = semaphore.SemaphoreClient("http://example.test", verify_ssl=False)
    payload = {"id": 1, "name": "LV3 Semaphore", "type": "", "alert": False, "max_parallel_tasks": 0}

    def fake_request(path, *, method="GET", payload=None, use_bearer=False, expected_statuses=None, accept_json=True):
        assert path == "/api/project/1"
        assert method == "PUT"
        assert expected_statuses == {200, 204}
        return 204, None

    client._request = fake_request  # type: ignore[method-assign]

    assert client.update_project(1, payload) == payload
