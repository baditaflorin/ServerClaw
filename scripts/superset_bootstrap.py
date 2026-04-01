#!/usr/bin/env python3
"""Bootstrap and verify the repo-managed Superset surface."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_TIMEOUT = 30
DATABASE_EXTRA = json.dumps(
    {
        "metadata_params": {},
        "engine_params": {},
        "metadata_cache_timeout": {},
        "schemas_allowed_for_file_upload": [],
    }
)


class SupersetBootstrapError(RuntimeError):
    """Raised when the Superset runtime does not match the managed contract."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Capture redirect responses without following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def read_secret(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise SupersetBootstrapError(f"{path} is empty")
    return value


def load_definition(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_opener(base_url: str, *, follow_redirects: bool = True) -> request.OpenerDirector:
    handlers: list[Any] = []
    if not follow_redirects:
        handlers.append(NoRedirectHandler())
    if base_url.startswith("https://"):
        handlers.append(request.HTTPSHandler(context=ssl.create_default_context()))
    return request.build_opener(*handlers)


def api_request(
    opener: request.OpenerDirector,
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
    return_json: bool = True,
) -> Any:
    headers = {"Accept": "application/json"}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(f"{base_url}{path}", data=payload, headers=headers, method=method)
    try:
        with opener.open(req, timeout=DEFAULT_TIMEOUT) as resp:
            status = resp.getcode()
            content = resp.read()
            if status not in expected_statuses:
                raise SupersetBootstrapError(f"{method} {path} returned {status}, expected {expected_statuses}")
            if not content:
                return None
            if return_json:
                return json.loads(content)
            return content.decode("utf-8")
    except error.HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        if exc.code in expected_statuses:
            if not content:
                return None
            if return_json:
                return json.loads(content)
            return content
        raise SupersetBootstrapError(f"{method} {path} returned {exc.code}: {content}") from exc


def check_health(base_url: str) -> None:
    opener = build_opener(base_url)
    health = api_request(opener, base_url, "GET", "/health", return_json=False)
    if health.strip() != "OK":
        raise SupersetBootstrapError(f"{base_url}/health did not return OK")


def login(base_url: str, username: str, password: str) -> str:
    opener = build_opener(base_url)
    response = api_request(
        opener,
        base_url,
        "POST",
        "/api/v1/security/login",
        body={"username": username, "password": password, "provider": "db", "refresh": True},
    )
    token = response.get("access_token")
    if not token:
        raise SupersetBootstrapError("Superset login did not return an access token")
    return str(token)


def list_api_names(base_url: str, token: str, path: str, field: str) -> set[str]:
    opener = build_opener(base_url)
    response = api_request(opener, base_url, "GET", path, token=token)
    result = response.get("result", [])
    return {str(item[field]) for item in result if field in item}


def ensure_local_imports():
    from superset.app import create_app
    from superset.connectors.sqla.models import SqlMetric, SqlaTable, TableColumn
    from superset.extensions import db
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    return create_app, db, Database, SqlaTable, TableColumn, SqlMetric, Slice, Dashboard


def build_dashboard_position(chart_id: int, chart_uuid: str, chart_title: str) -> dict[str, Any]:
    chart_node = "CHART-LV3-SUPERSET-LANDING"
    row_node = "ROW-LV3-SUPERSET-LANDING"
    return {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
        "GRID_ID": {"id": "GRID_ID", "type": "GRID", "children": [row_node], "parents": ["ROOT_ID"]},
        row_node: {
            "id": row_node,
            "type": "ROW",
            "children": [chart_node],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        chart_node: {
            "id": chart_node,
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_node],
            "meta": {
                "chartId": chart_id,
                "uuid": chart_uuid,
                "sliceName": chart_title,
                "width": 12,
                "height": 50,
            },
        },
    }


def build_dashboard_metadata() -> dict[str, Any]:
    return {
        "timed_refresh_immune_slices": [],
        "expanded_slices": {},
        "label_colors": {},
        "refresh_frequency": 0,
        "color_scheme": "",
    }


def build_chart_params(dataset_id: int) -> dict[str, Any]:
    return {
        "datasource": f"{dataset_id}__table",
        "viz_type": "table",
        "query_mode": "raw",
        "groupby": [],
        "all_columns": ["database_name"],
        "percent_metrics": [],
        "adhoc_filters": [],
        "order_by_cols": [["database_name", True]],
        "row_limit": 500,
        "server_page_length": 25,
        "order_desc": False,
        "table_timestamp_format": "smart_date",
        "show_cell_bars": False,
        "color_pn": False,
        "allow_render_html": False,
        "extra_form_data": {},
        "dashboards": [],
    }


def bootstrap_local(args: argparse.Namespace) -> int:
    create_app, db, Database, SqlaTable, TableColumn, SqlMetric, Slice, Dashboard = ensure_local_imports()
    definition = load_definition(args.definition_file)
    app = create_app()
    changes: list[str] = []

    with app.app_context():
        for item in definition["databases"]:
            database = db.session.query(Database).filter_by(database_name=item["name"]).one_or_none()
            if database is None:
                database = Database(database_name=item["name"])
                database.uuid = uuid.UUID(item["uuid"])
                db.session.add(database)
                changes.append(f"database:create:{item['name']}")
            database.set_sqlalchemy_uri(item["uri"])
            database.expose_in_sqllab = bool(item.get("expose_in_sqllab", True))
            database.allow_run_async = bool(item.get("allow_run_async", False))
            database.allow_ctas = bool(item.get("allow_ctas", False))
            database.allow_cvas = bool(item.get("allow_cvas", False))
            database.allow_dml = bool(item.get("allow_dml", False))
            database.allow_file_upload = bool(item.get("allow_csv_upload", False))
            database.impersonate_user = False
            database.extra = DATABASE_EXTRA
        db.session.commit()

        landing = definition["landing"]
        landing_database = (
            db.session.query(Database).filter_by(database_name=landing["database_name"]).one_or_none()
        )
        if landing_database is None:
            raise SupersetBootstrapError(f"Landing database {landing['database_name']} does not exist")

        dataset = (
            db.session.query(SqlaTable)
            .filter_by(database_id=landing_database.id, table_name=landing["dataset_name"])
            .one_or_none()
        )
        if dataset is None:
            dataset = SqlaTable(table_name=landing["dataset_name"], database=landing_database)
            dataset.uuid = uuid.UUID(landing["dataset_uuid"])
            db.session.add(dataset)
            changes.append(f"dataset:create:{landing['dataset_name']}")
        dataset.table_name = landing["dataset_name"]
        dataset.database = landing_database
        dataset.description = landing.get("dataset_description")
        dataset.sql = landing["dataset_sql"]
        dataset.schema = None
        dataset.catalog = None
        dataset.main_dttm_col = None
        dataset.params = None
        dataset.template_params = None
        dataset.filter_select_enabled = True
        dataset.fetch_values_predicate = None
        dataset.extra = "{}"
        dataset.normalize_columns = False
        dataset.always_filter_main_dttm = False
        dataset.columns.clear()
        for column_spec in landing["columns"]:
            dataset.columns.append(
                TableColumn(
                    column_name=column_spec["name"],
                    verbose_name=column_spec.get("verbose_name"),
                    type=column_spec.get("type"),
                    groupby=bool(column_spec.get("groupby", True)),
                    filterable=bool(column_spec.get("filterable", True)),
                    is_dttm=bool(column_spec.get("is_dttm", False)),
                    description=column_spec.get("description"),
                )
            )
        dataset.metrics.clear()
        for metric_spec in landing["metrics"]:
            dataset.metrics.append(
                SqlMetric(
                    metric_name=metric_spec["name"],
                    verbose_name=metric_spec.get("verbose_name"),
                    expression=metric_spec["expression"],
                    metric_type=None,
                    description=metric_spec.get("description"),
                    extra="{}",
                )
            )
        db.session.commit()

        chart = db.session.query(Slice).filter_by(slice_name=landing["chart_title"]).one_or_none()
        if chart is None:
            chart = Slice(slice_name=landing["chart_title"])
            chart.uuid = uuid.UUID(landing["chart_uuid"])
            db.session.add(chart)
            changes.append(f"chart:create:{landing['chart_title']}")
        chart.slice_name = landing["chart_title"]
        chart.datasource_id = dataset.id
        chart.datasource_type = "table"
        chart.datasource_name = dataset.table_name
        chart.viz_type = "table"
        chart.description = "Repo-managed landing table listing the PostgreSQL databases visible to Superset."
        chart.params = json.dumps(build_chart_params(dataset.id))
        chart.query_context = None
        db.session.commit()

        dashboard = db.session.query(Dashboard).filter_by(slug=landing["dashboard_slug"]).one_or_none()
        if dashboard is None:
            dashboard = Dashboard(slug=landing["dashboard_slug"])
            dashboard.uuid = uuid.UUID(landing["dashboard_uuid"])
            db.session.add(dashboard)
            changes.append(f"dashboard:create:{landing['dashboard_title']}")
        dashboard.dashboard_title = landing["dashboard_title"]
        dashboard.slug = landing["dashboard_slug"]
        dashboard.description = "Repo-managed landing dashboard for the LV3 Superset rollout."
        dashboard.css = ""
        dashboard.published = True
        dashboard.slices = [chart]
        dashboard.position_json = json.dumps(
            build_dashboard_position(chart.id, str(chart.uuid), landing["chart_title"])
        )
        dashboard.json_metadata = json.dumps(build_dashboard_metadata())
        db.session.commit()

    print(json.dumps({"changed": bool(changes), "changes": changes}))
    return 0


def verify_local(args: argparse.Namespace) -> int:
    create_app, db, Database, SqlaTable, _TableColumn, _SqlMetric, Slice, Dashboard = ensure_local_imports()
    definition = load_definition(args.definition_file)
    app = create_app()
    check_health(args.base_url)

    with app.app_context():
        actual_databases = {
            str(name)
            for (name,) in db.session.query(Database.database_name).all()
        }
        expected_databases = {str(item["name"]) for item in definition["databases"]}
        missing_databases = sorted(expected_databases - actual_databases)

        landing = definition["landing"]
        dataset = (
            db.session.query(SqlaTable)
            .join(Database)
            .filter(Database.database_name == landing["database_name"], SqlaTable.table_name == landing["dataset_name"])
            .one_or_none()
        )
        if dataset is None:
            raise SupersetBootstrapError(f"Managed landing dataset {landing['dataset_name']} is missing")

        chart = db.session.query(Slice).filter_by(slice_name=landing["chart_title"]).one_or_none()
        if chart is None:
            raise SupersetBootstrapError(f"Managed landing chart {landing['chart_title']} is missing")

        dashboard = db.session.query(Dashboard).filter_by(slug=landing["dashboard_slug"]).one_or_none()
        if dashboard is None:
            raise SupersetBootstrapError(f"Managed landing dashboard {landing['dashboard_title']} is missing")

        if missing_databases:
            raise SupersetBootstrapError(f"Missing managed datasource registrations: {', '.join(missing_databases)}")

        connected: list[str] = []
        for item in definition["databases"]:
            if not item.get("verify_connectivity", False):
                continue
            database = db.session.query(Database).filter_by(database_name=item["name"]).one()
            with database.get_sqla_engine(nullpool=True) as engine:
                with engine.connect() as connection:
                    connection.exec_driver_sql("SELECT 1")
            connected.append(item["name"])

        report = {
            "status": "ok",
            "database_count": len(expected_databases),
            "verified_connections": connected,
            "dataset": landing["dataset_name"],
            "chart": landing["chart_title"],
            "dashboard": landing["dashboard_title"],
        }
        if args.report_file:
            report_path = Path(args.report_file)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report))
    return 0


def verify_public(args: argparse.Namespace) -> int:
    check_health(args.base_url)

    no_redirect = build_opener(args.base_url, follow_redirects=False)
    req = request.Request(f"{args.base_url}/login/keycloak", method="GET")
    try:
        no_redirect.open(req, timeout=DEFAULT_TIMEOUT)
    except error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise SupersetBootstrapError(f"/login/keycloak returned unexpected status {exc.code}") from exc
        location = exc.headers.get("Location", "")
        if args.expected_sso_host not in location:
            raise SupersetBootstrapError(f"SSO redirect did not point at {args.expected_sso_host}: {location}")
    else:
        raise SupersetBootstrapError("/login/keycloak unexpectedly succeeded without redirecting")

    report: dict[str, Any] = {"status": "ok", "redirect_host": args.expected_sso_host}
    if args.admin_username and args.admin_password_file:
        password = read_secret(args.admin_password_file)
        token = login(args.base_url, args.admin_username, password)
        expected_postgres = json.loads(Path(args.expected_postgres_databases_file).read_text(encoding="utf-8"))
        expected_database_names = {
            f"{args.database_prefix}: {database_name}" for database_name in expected_postgres
        }
        expected_database_names.update(args.expected_extra_database)

        databases = list_api_names(args.base_url, token, "/api/v1/database/?q=(page:0,page_size:500)", "database_name")
        dashboards = list_api_names(args.base_url, token, "/api/v1/dashboard/?q=(page:0,page_size:500)", "dashboard_title")
        charts = list_api_names(args.base_url, token, "/api/v1/chart/?q=(page:0,page_size:500)", "slice_name")

        missing_databases = sorted(expected_database_names - databases)
        if missing_databases:
            raise SupersetBootstrapError(f"Public API verification missing databases: {', '.join(missing_databases)}")
        if args.expected_dashboard not in dashboards:
            raise SupersetBootstrapError(f"Public API verification missing dashboard {args.expected_dashboard}")
        if args.expected_chart not in charts:
            raise SupersetBootstrapError(f"Public API verification missing chart {args.expected_chart}")

        report.update(
            {
                "database_count": len(databases),
                "expected_database_count": len(expected_database_names),
                "dashboard": args.expected_dashboard,
                "chart": args.expected_chart,
            }
        )

    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap-local", help="Create or reconcile the managed Superset datasources and landing dashboard.")
    bootstrap_parser.add_argument("--definition-file", required=True)
    bootstrap_parser.set_defaults(func=bootstrap_local)

    verify_local_parser = subparsers.add_parser("verify-local", help="Verify the managed Superset datasources and landing dashboard locally.")
    verify_local_parser.add_argument("--base-url", required=True)
    verify_local_parser.add_argument("--definition-file", required=True)
    verify_local_parser.add_argument("--report-file")
    verify_local_parser.set_defaults(func=verify_local)

    verify_public_parser = subparsers.add_parser("verify-public", help="Verify the public Superset health, SSO redirect, and managed metadata objects.")
    verify_public_parser.add_argument("--base-url", required=True)
    verify_public_parser.add_argument("--expected-postgres-databases-file", required=True)
    verify_public_parser.add_argument("--database-prefix", required=True)
    verify_public_parser.add_argument("--expected-dashboard", required=True)
    verify_public_parser.add_argument("--expected-chart", required=True)
    verify_public_parser.add_argument("--expected-sso-host", required=True)
    verify_public_parser.add_argument("--admin-username")
    verify_public_parser.add_argument("--admin-password-file")
    verify_public_parser.add_argument("--expected-extra-database", action="append", default=[])
    verify_public_parser.add_argument("--report-file")
    verify_public_parser.set_defaults(func=verify_public)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SupersetBootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
