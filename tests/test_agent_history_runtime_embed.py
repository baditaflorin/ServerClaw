"""Static guards for semantic search in the agent_history_runtime role (ADR 0494, ws-20261029-agent-history-embed-query).

The store embeds each search question through an embeddings endpoint on a Mac and takes the embedding worker's vectors through a
separate embed token. These tests render the real compose template and evaluate the real input assertions, so a rename in one place
that is not followed in the others fails here and not on the guest.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "agent_history_runtime"
POLICY = REPO / "config" / "tailscale" / "policy.hujson"
HOST_VARS = REPO / "inventory" / "host_vars" / "agent-history.yml"

# A tailnet address of the embeddings Mac, as the operator overlay would give it. Documentation range plus the CGNAT block.
TAILNET_URL = "http://100.89.103.45:8443"


def _env() -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    # the few Ansible filters, tests and functions the role's templates and assertions use
    env.tests["match"] = lambda value, pattern: re.match(pattern, str(value)) is not None
    env.filters["bool"] = lambda value: value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
    env.filters["basename"] = lambda value: str(value).rsplit("/", 1)[-1]
    env.globals["lookup"] = lambda *_args, **_kwargs: ""
    return env


def _defaults() -> dict[str, Any]:
    """The role defaults with their own {{ }} references rendered (platform variables stubbed)."""
    raw = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    env = _env()
    context: dict[str, Any] = {
        "compose_runtime_secret_root": "/run/lv3-secrets",
        "openbao_agent_image": "openbao/openbao:test",
        "platform_topology_host": "h",
        "hostvars": {"h": {"platform_port_assignments": {"openbao_http_port": 8201}}},
        # the one default that needs the platform's service topology filter: a dict, not a rendered string
        "agent_history_openbao_service_topology": {"private_ip": "10.10.10.92"},
    }
    for _ in range(4):  # defaults refer to each other: render until stable
        for name, value in raw.items():
            if name in context:
                continue
            if isinstance(value, str) and "{{" in value:
                try:
                    context[name] = env.from_string(value).render(**{**raw, **context})
                except jinja2.UndefinedError:
                    continue  # needs a variable rendered in a later round
            else:
                context[name] = value
    return {**raw, **context}


def _compose(**overrides: Any) -> str:
    context = {**_defaults(), "agent_history_store_image": "agent-store:0.1.0", **overrides}
    return _env().from_string((ROLE / "templates" / "docker-compose.yml.j2").read_text(encoding="utf-8")).render(**context)


def _store_command(rendered: str) -> list[str]:
    return yaml.safe_load(rendered)["services"]["store"]["command"]


def _assertion_failures(**overrides: Any) -> list[str]:
    """Evaluate every `that` expression of the role's input validation; return the ones that are false."""
    tasks = yaml.safe_load((ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    validate = next(t for t in tasks if t["name"] == "Validate agent-history runtime inputs")
    context = {**_defaults(), **overrides}
    env = _env()
    failures = []
    for expression in validate["ansible.builtin.assert"]["that"]:
        if not env.compile_expression(" ".join(expression.split()), undefined_to_none=False)(**context):
            failures.append(" ".join(expression.split()))
    return failures


def test_embed_token_is_always_passed_and_never_a_value() -> None:
    command = _store_command(_compose())
    assert "-embedTokenFile=/run/agent-history/embed-token" in command
    assert not [a for a in command if a.startswith("-embedUrl")], "no endpoint address is committed: semantic search is off by default"


def test_enabled_search_passes_every_flag_the_store_needs() -> None:
    command = _store_command(_compose(agent_history_embed_url=TAILNET_URL, agent_history_embed_model="bge-m3"))
    for flag in (
        f"-embedUrl={TAILNET_URL}",
        "-embedModel=bge-m3",
        "-embedApi=ollama",
        "-embedDimensions=1024",
        "-embedTimeout=2s",
        "-embedCacheSize=256",
    ):
        assert flag in command


def test_the_openbao_agent_renders_the_embed_token_and_the_store_waits_for_it() -> None:
    hcl = (ROLE / "templates" / "openbao-agent.hcl.j2").read_text(encoding="utf-8")
    assert "'src': 'embed-token.ctmpl', 'dest': 'embed-token'" in hcl
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "src: embed-token.ctmpl.j2" in tasks and "dest: embed-token.ctmpl" in tasks
    assert "embed-token" in (ROLE / "tasks" / "verify.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(_compose())
    assert "/run/agent-history/embed-token" in compose["services"]["openbao-agent"]["healthcheck"]["test"][1]


def test_the_embed_token_template_names_a_key_and_holds_no_value() -> None:
    text = (ROLE / "templates" / "embed-token.ctmpl.j2").read_text(encoding="utf-8")
    assert ".Data.data.{{ agent_history_openbao_keys.embed_tokens }}" in text
    assert _defaults()["agent_history_openbao_keys"]["embed_tokens"] == "embed_tokens"
    assert not re.search(r"[0-9a-f]{32}", text)


def test_defaults_validate() -> None:
    assert _assertion_failures() == []


@pytest.mark.parametrize(
    "url",
    [TAILNET_URL, "http://127.0.0.1:11434", "http://10.10.10.5:8443", "http://192.168.1.4:8443", "https://embed.example.net"],
)
def test_accepted_endpoint_addresses(url: str) -> None:
    assert _assertion_failures(agent_history_embed_url=url, agent_history_embed_model="bge-m3") == []


@pytest.mark.parametrize(
    "url",
    ["http://8.8.8.8:8443", "http://100.128.0.1:8443", "http://embed.example.net", "ftp://100.89.103.45", "http://user@100.89.103.45:8443"],
)
def test_refused_endpoint_addresses(url: str) -> None:
    assert _assertion_failures(agent_history_embed_url=url, agent_history_embed_model="bge-m3"), url


def test_an_endpoint_without_a_model_is_refused() -> None:
    assert _assertion_failures(agent_history_embed_url=TAILNET_URL, agent_history_embed_model="")


def test_the_embed_key_set_is_part_of_the_validated_keys() -> None:
    assert _assertion_failures(agent_history_openbao_keys={"db_password": "a", "read_tokens": "b", "write_tokens": "c", "metrics_token": "d"})


def test_every_new_variable_has_an_argument_spec() -> None:
    specs = yaml.safe_load((ROLE / "meta" / "argument_specs.yml").read_text(encoding="utf-8"))["argument_specs"]["main"]["options"]
    for name in _defaults():
        if name.startswith("agent_history_embed"):
            assert name in specs, name


def test_policy_opens_one_port_from_the_store_to_the_embeddings_mac() -> None:
    text = POLICY.read_text(encoding="utf-8")
    grant = re.search(
        r'\{\s*"src":\s*\["tag:agent-history"\],\s*"dst":\s*\["100\.89\.103\.45/32"\],\s*"ip":\s*\[([^\]]*)\],\s*\}', text
    )
    assert grant, "grant tag:agent-history -> mac14 is missing"
    assert [p.strip() for p in grant.group(1).split(",") if p.strip()] == ['"tcp:8443"']
    # nothing else uses tag:agent-history as a source
    assert len(re.findall(r'"src":\s*\[?\s*"tag:agent-history"', text)) == 2  # the grant and its test
    for denied in ("100.89.103.45:22", "100.89.103.45:11434", "100.89.103.45:443", "100.111.107.108:8443"):
        assert f'"{denied}"' in text


def test_the_guest_inventory_points_at_the_one_port_the_policy_opens() -> None:
    """The endpoint in the guest's host_vars must be exactly the Mac address and port of the policy grant, and must pass the role's assertions."""
    host_vars = yaml.safe_load(HOST_VARS.read_text(encoding="utf-8"))
    url = host_vars["agent_history_embed_url"]
    match = re.fullmatch(r"http://(100\.\d+\.\d+\.\d+):(\d+)", url)
    assert match, url
    text = POLICY.read_text(encoding="utf-8")
    assert f'"dst": ["{match.group(1)}/32"]' in text and f'"tcp:{match.group(2)}"' in text
    assert host_vars["agent_history_embed_model"] == "bge-m3"
    assert _assertion_failures(**host_vars) == []
