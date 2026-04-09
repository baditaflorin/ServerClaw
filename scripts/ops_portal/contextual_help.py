from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


GLOSSARY: dict[str, dict[str, str]] = {
    "Live apply": {
        "definition": "A repo-managed production converge that is verified with receipts and evidence instead of an undocumented manual change.",
        "surface": "shared",
    },
    "Drift": {
        "definition": "A meaningful difference between the committed platform contract and the currently observed runtime state.",
        "surface": "shared",
    },
    "Runtime assurance": {
        "definition": "A per-service verification view that shows whether required routes, journeys, and receipts still pass on the live platform.",
        "surface": "shared",
    },
    "Maintenance window": {
        "definition": "A declared period of planned work that suppresses expected noise without removing the audit trail or hiding the change.",
        "surface": "shared",
    },
    "Handoff": {
        "definition": "Passing the current task, evidence, and blocked state to another operator or agent without relying on hidden chat context.",
        "surface": "shared",
    },
    "Recovery tier": {
        "definition": "The declared recovery expectation for a service, including the tolerated blast radius and urgency of restoration.",
        "surface": "services",
    },
    "Exposure": {
        "definition": "How a surface is published, such as edge-published, private-only, informational-only, or edge-static.",
        "surface": "services",
    },
    "Implementation Status": {
        "definition": "Whether an ADR is only accepted as design, implemented in the repository, verified on the live platform, or both.",
        "surface": "architecture",
    },
    "Platform version": {
        "definition": "The version marker used only after merged work is actually applied and verified on the live platform from main.",
        "surface": "architecture",
    },
    "Promotion": {
        "definition": "A staged change that passed its declared gate evidence before being replayed on production.",
        "surface": "history",
    },
    "Mutation audit": {
        "definition": "The durable record of a governed action, including who triggered it, what changed, and the resulting outcome.",
        "surface": "history",
    },
}


def glossary_entries(*terms: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for term in terms:
        definition = GLOSSARY.get(term)
        if definition is None:
            continue
        entries.append({"term": term, "definition": definition["definition"]})
    return entries


def glossary_reference_rows() -> list[dict[str, str]]:
    return [
        {
            "term": term,
            "definition": payload["definition"],
            "surface": payload["surface"],
        }
        for term, payload in sorted(GLOSSARY.items())
    ]


def site_path_to_browser_href(base_url: str, site_path: str | Path) -> str:
    path = Path(site_path)
    if str(path).startswith(("http://", "https://")):
        return str(path)
    if path.suffix == ".json":
        normalized = "/" + path.as_posix().lstrip("/")
    elif path.name == "index.md":
        parent = path.parent.as_posix().strip("/")
        normalized = "/" if not parent else f"/{parent}/"
    else:
        normalized = f"/{path.with_suffix('').as_posix().lstrip('/')}/"
    if not base_url:
        return normalized
    return f"{base_url.rstrip('/')}{normalized}"


def help_reference(
    label: str,
    *,
    kind: str,
    site_path: str | Path | None = None,
    href: str | None = None,
    base_url: str = "",
) -> dict[str, str]:
    resolved_href = href or site_path_to_browser_href(base_url, site_path or "")
    return {"label": label, "href": resolved_href, "kind": kind}


def build_ops_portal_help(docs_base_url: str) -> dict[str, Any]:
    return {
        "title": "Contextual Help",
        "summary": (
            "Use this portal to inspect live state, launch governed operator actions, "
            "and jump to the owning docs without improvising inside product-native UIs."
        ),
        "audience": ["Operators", "Administrators"],
        "sections": [
            {
                "label": "Overview",
                "href": "#overview",
                "summary": "Check service health, runtime assurance, and the current declared-to-live picture first.",
            },
            {
                "label": "Deployments",
                "href": "#deployments",
                "summary": "Watch the browser-side event stream after deploy, restart, secret, or runbook actions.",
            },
            {
                "label": "Agents",
                "href": "#agents",
                "summary": "Review live coordination sessions before assuming another actor is idle or safe to interrupt.",
            },
            {
                "label": "Drift",
                "href": "#drift",
                "summary": "Use the drift panel when the live platform disagrees with the committed contract.",
            },
            {
                "label": "Runbooks",
                "href": "#runbooks",
                "summary": "Launch the canonical procedure instead of translating docs into ad hoc runtime commands.",
            },
        ],
        "glossary": glossary_entries(
            "Live apply",
            "Runtime assurance",
            "Drift",
            "Maintenance window",
            "Handoff",
        ),
        "references": [
            help_reference(
                "Platform Operations Portal",
                kind="runbook",
                site_path="runbooks/platform-operations-portal.md",
                base_url=docs_base_url,
            ),
            help_reference(
                "Ops Portal Down",
                kind="runbook",
                site_path="runbooks/ops-portal-down.md",
                base_url=docs_base_url,
            ),
            help_reference(
                "Reference Glossary",
                kind="reference",
                site_path="reference/glossary.md",
                base_url=docs_base_url,
            ),
            help_reference(
                "ADR 0313",
                kind="adr",
                site_path="architecture/decisions/0313-contextual-help-glossary-and-escalation-drawer.md",
                base_url=docs_base_url,
            ),
        ],
        "escalation": {
            "backout": (
                "If a live action feels unsafe, stop before retrying it in another UI. "
                "Prefer a read-only health check, then move into the owning runbook."
            ),
            "runbook": help_reference(
                "Platform Operations Portal",
                kind="runbook",
                site_path="runbooks/platform-operations-portal.md",
                base_url=docs_base_url,
            ),
            "handoff": (
                "Capture the current section, affected service, latest receipt or error text, "
                "and any maintenance-window context before handing off."
            ),
        },
    }


STATIC_OPS_PAGE_HELP: dict[str, dict[str, Any]] = {
    "index.html": {
        "summary": "This generated landing page summarizes the current estate and links you into the static operator map.",
        "glossary": ("Live apply", "Drift", "Recovery tier", "Handoff"),
    },
    "environments/index.html": {
        "summary": "Use this page to compare production and staging topology without logging into the live runtime.",
        "glossary": ("Exposure", "Maintenance window", "Handoff"),
    },
    "vms/index.html": {
        "summary": "Use this page to verify which VMs exist, what role each one plays, and which services they host.",
        "glossary": ("Recovery tier", "Live apply", "Handoff"),
    },
    "subdomains/index.html": {
        "summary": "Use this page to confirm which hostname points where before changing publication or certificates.",
        "glossary": ("Exposure", "Live apply", "Handoff"),
    },
    "runbooks/index.html": {
        "summary": "This page is the directory of canonical operator procedures and the safest place to start a governed task.",
        "glossary": ("Live apply", "Handoff"),
    },
    "adrs/index.html": {
        "summary": "This page separates accepted design contracts from verified implementation truth so operators do not misread intent as live state.",
        "glossary": ("Implementation Status", "Platform version", "Handoff"),
    },
    "agents/index.html": {
        "summary": "This page summarizes agent-facing tools and the latest coordination snapshot committed into the repository.",
        "glossary": ("Mutation audit", "Handoff"),
    },
}


def build_static_ops_page_help(page_path: str, docs_base_url: str = "https://docs.localhost") -> dict[str, Any]:
    payload = STATIC_OPS_PAGE_HELP.get(page_path, STATIC_OPS_PAGE_HELP["index.html"])
    return {
        "title": "Contextual Help",
        "summary": payload["summary"],
        "audience": ["Operators", "Contributors"],
        "glossary": glossary_entries(*payload["glossary"]),
        "references": [
            help_reference(
                "Platform Operations Portal",
                kind="runbook",
                site_path="runbooks/platform-operations-portal.md",
                base_url=docs_base_url,
            ),
            help_reference(
                "Reference Glossary",
                kind="reference",
                site_path="reference/glossary.md",
                base_url=docs_base_url,
            ),
            help_reference(
                "ADR 0313",
                kind="adr",
                site_path="architecture/decisions/0313-contextual-help-glossary-and-escalation-drawer.md",
                base_url=docs_base_url,
            ),
        ],
        "escalation": {
            "backout": "Do not treat the static snapshot as proof of a successful live replay; verify the owning runtime before changing production.",
            "runbook": help_reference(
                "Platform Operations Portal",
                kind="runbook",
                site_path="runbooks/platform-operations-portal.md",
                base_url=docs_base_url,
            ),
            "handoff": "Record the page, the stale or surprising value you saw, and the source receipt or catalog path before handing off.",
        },
    }


CHANGELOG_PAGE_HELP: dict[str, dict[str, Any]] = {
    "index.html": {
        "summary": "Use this page to review cross-platform rollout history before deciding whether a change is already live or still branch-local.",
        "glossary": ("Live apply", "Promotion", "Mutation audit", "Handoff"),
    },
    "services/index.html": {
        "summary": "Use this page to find which services changed recently before opening a service-specific history page.",
        "glossary": ("Live apply", "Promotion", "Handoff"),
    },
    "promotions/index.html": {
        "summary": "Use this page to review staging-to-production promotions and their gate evidence before replaying the same path again.",
        "glossary": ("Promotion", "Mutation audit", "Handoff"),
    },
}


def build_changelog_page_help(page_path: str, docs_base_url: str = "https://docs.localhost") -> dict[str, Any]:
    if page_path.startswith("service/"):
        payload = {
            "summary": "Use this service timeline to confirm what changed, when it changed, and whether the latest receipt matches the current runtime.",
            "glossary": ("Live apply", "Promotion", "Mutation audit", "Handoff"),
        }
    elif page_path.startswith("environment/"):
        payload = {
            "summary": "Use this environment timeline to separate production history from staging receipts before replaying another change.",
            "glossary": ("Live apply", "Promotion", "Mutation audit", "Handoff"),
        }
    else:
        payload = CHANGELOG_PAGE_HELP.get(page_path, CHANGELOG_PAGE_HELP["index.html"])
    return {
        "title": "Contextual Help",
        "summary": payload["summary"],
        "audience": ["Operators", "Contributors"],
        "glossary": glossary_entries(*payload["glossary"]),
        "references": [
            help_reference(
                "Deployment History Portal",
                kind="runbook",
                site_path="runbooks/deployment-history-portal.md",
                base_url=docs_base_url,
            ),
            help_reference(
                "Reference Glossary",
                kind="reference",
                site_path="reference/glossary.md",
                base_url=docs_base_url,
            ),
            help_reference(
                "ADR 0313",
                kind="adr",
                site_path="architecture/decisions/0313-contextual-help-glossary-and-escalation-drawer.md",
                base_url=docs_base_url,
            ),
        ],
        "escalation": {
            "backout": "If the timeline is ambiguous, stop before replaying another deploy and verify the owning receipt plus current runtime state.",
            "runbook": help_reference(
                "Deployment History Portal",
                kind="runbook",
                site_path="runbooks/deployment-history-portal.md",
                base_url=docs_base_url,
            ),
            "handoff": "Capture the exact receipt, branch, service, and outcome you were inspecting before handing off.",
        },
    }


def _docs_root_reference(label: str, site_path: str | Path, kind: str) -> dict[str, str]:
    return help_reference(label, kind=kind, site_path=site_path)


def _service_name(service: Mapping[str, Any] | None, title: str) -> str:
    if service and isinstance(service.get("name"), str) and str(service["name"]).strip():
        return str(service["name"]).strip()
    return title


def build_docs_page_help(
    *,
    target_path: Path,
    title: str,
    service: Mapping[str, Any] | None = None,
    runbook_href: str | None = None,
    runbook_title: str | None = None,
    adr_href: str | None = None,
    adr_id: str | None = None,
) -> dict[str, Any]:
    references = [
        _docs_root_reference("Reference Glossary", "reference/glossary.md", "reference"),
        _docs_root_reference("Runbook Index", "runbooks/index.md", "runbook"),
        _docs_root_reference("Architecture Index", "architecture/index.md", "adr"),
    ]
    summary = "Use this page as contextual reference while you work in the platform."
    glossary_terms = ("Live apply", "Handoff")
    escalation_backout = (
        "If this page leaves any doubt, stop before making live changes and return to the owning runbook or ops portal."
    )
    escalation_runbook = _docs_root_reference("Platform Operations Portal", "runbooks/platform-operations-portal.md", "runbook")
    audience = ["Operators", "Contributors"]

    if target_path == Path("index.md"):
        summary = "Start here when you need the documented map of services, runbooks, release notes, and generated reference pages."
        glossary_terms = ("Live apply", "Implementation Status", "Handoff")
        references.insert(0, _docs_root_reference("Services Directory", "services/index.md", "reference"))
    elif target_path.parts[:1] == ("services",):
        audience = ["Operators", "Administrators"]
        if target_path.name == "index.md":
            summary = "Use this directory to find the canonical service page before changing runtime state or publication."
            glossary_terms = ("Exposure", "Recovery tier", "Live apply")
            references.insert(0, _docs_root_reference("Port Reference", "reference/ports.md", "reference"))
            references.insert(1, _docs_root_reference("Subdomain Reference", "reference/subdomains.md", "reference"))
        else:
            service_name = _service_name(service, title)
            summary = f"Use this page to understand how {service_name} is published, where it runs, and which docs govern it."
            glossary_terms = ("Exposure", "Recovery tier", "Live apply", "Handoff")
            references.insert(0, _docs_root_reference("Port Reference", "reference/ports.md", "reference"))
            references.insert(1, _docs_root_reference("Subdomain Reference", "reference/subdomains.md", "reference"))
            if runbook_href and runbook_title:
                references.insert(0, {"label": runbook_title, "href": runbook_href, "kind": "runbook"})
                escalation_runbook = {"label": runbook_title, "href": runbook_href, "kind": "runbook"}
            if adr_href and adr_id:
                references.insert(1, {"label": f"ADR {adr_id}", "href": adr_href, "kind": "adr"})
            escalation_backout = (
                "Do not mutate the service through a product-native admin screen unless the owning runbook explicitly requires it. "
                "Return to the declared procedure first."
            )
    elif target_path.parts[:1] == ("runbooks",):
        summary = "This page is a canonical operator procedure. Follow it instead of inventing shell steps from memory."
        glossary_terms = ("Live apply", "Handoff")
        audience = ["Operators"]
        escalation_backout = (
            "Stop at the last confirmed safe step boundary, keep the current system state unchanged, and resume only with the owning runbook or a handoff."
        )
    elif target_path.parts[:2] == ("architecture", "decisions"):
        summary = "This page explains the architectural decision and its implementation status. Treat it as guidance, not as automatic approval to change live state."
        glossary_terms = ("Implementation Status", "Platform version", "Handoff")
        references.insert(0, _docs_root_reference("Services Directory", "services/index.md", "reference"))
        escalation_backout = "If the ADR and the live system disagree, trust the current verified runbook and receipts until mainline truth is updated."
    elif target_path == Path("architecture/index.md"):
        summary = "Use this index to find the owning ADR before assuming a behavior is canonical."
        glossary_terms = ("Implementation Status", "Platform version", "Handoff")
    elif target_path == Path("architecture/dependency-graph.md"):
        summary = "Use this page to understand service dependencies and likely blast radius before a rollout or recovery action."
        glossary_terms = ("Recovery tier", "Drift", "Handoff")
        references.insert(0, _docs_root_reference("Services Directory", "services/index.md", "reference"))
    elif target_path.parts[:1] == ("reference",):
        audience = ["Operators", "Contributors"]
        if target_path == Path("reference/glossary.md"):
            summary = "Use this page as the canonical quick-reference for platform vocabulary that appears across the first-party browser surfaces."
            glossary_terms = ("Live apply", "Drift", "Runtime assurance", "Handoff")
        else:
            summary = "Use this generated reference page when you need canonical catalog data without reverse-engineering it from templates."
            glossary_terms = ("Exposure", "Recovery tier", "Handoff")
    elif target_path.parts[:1] == ("api",):
        summary = "Use this page to inspect the published API contract and supported browser-facing integration routes."
        glossary_terms = ("Live apply", "Handoff")
        references.insert(0, _docs_root_reference("Services Directory", "services/index.md", "reference"))
    elif target_path.parts[:1] == ("releases",) or target_path == Path("changelog.md"):
        summary = "Use this page to separate merged repository truth from unreleased notes and historical rollout evidence."
        glossary_terms = ("Live apply", "Promotion", "Handoff")
        references.insert(0, _docs_root_reference("Deployment History Portal", "runbooks/deployment-history-portal.md", "runbook"))

    return {
        "title": "Contextual Help",
        "summary": summary,
        "audience": audience,
        "glossary": glossary_entries(*glossary_terms),
        "references": references,
        "escalation": {
            "backout": escalation_backout,
            "runbook": escalation_runbook,
            "handoff": "Share the page URL, the question you were trying to answer, and the exact mismatch or failure before handing off.",
        },
    }
