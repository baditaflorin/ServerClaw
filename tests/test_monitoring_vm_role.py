from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "roles" / "monitoring_vm"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
TRACING_TASKS_PATH = ROLE_ROOT / "tasks" / "tracing.yml"
VERIFY_PATH = ROLE_ROOT / "tasks" / "verify.yml"
PLATFORM_DASHBOARD_TEMPLATE = ROLE_ROOT / "templates" / "lv3-platform-overview.json.j2"
MAIL_DASHBOARD_TEMPLATE = ROLE_ROOT / "templates" / "lv3-mail-platform.json.j2"
VM_DASHBOARD_TEMPLATE = ROLE_ROOT / "templates" / "lv3-vm-detail.json.j2"
LOKI_CANARY_SERVICE_TEMPLATE = ROLE_ROOT / "templates" / "loki-canary.service.j2"
LOKI_CONFIG_TEMPLATE = ROLE_ROOT / "templates" / "loki-config.yml.j2"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_defaults_define_public_grafana_url_from_service_topology() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    assert defaults["monitoring_grafana_public_url"] == (
        "https://{{ hostvars[groups['proxmox_hosts'][0]].lv3_service_topology.grafana.public_hostname }}"
    )


def test_defaults_include_loki_minio_contract() -> None:
    defaults = DEFAULTS_PATH.read_text()
    assert 'monitoring_loki_minio_schema_cutover_date: "2026-03-30"' in defaults
    assert "monitoring_loki_minio_access_key_id: lokichunks" in defaults
    assert ".local/monitoring/loki-minio-secret-key.txt" in defaults
    assert "monitoring_loki_minio_bucket_name: loki-chunks" in defaults
    assert "lv3_service_topology.minio.private_ip" in defaults


def test_defaults_expose_private_prometheus_remote_write_endpoint() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    template = (REPO_ROOT / "roles" / "monitoring_vm" / "templates" / "prometheus.service.j2").read_text()

    assert defaults["monitoring_prometheus_listen_address"] == "0.0.0.0:9090"
    assert defaults["monitoring_prometheus_remote_write_url"] == (
        "http://{{ hostvars[groups['proxmox_hosts'][0]].lv3_service_topology.grafana.private_ip }}:9090/api/v1/write"
    )
    assert "{{ monitoring_prometheus_listen_address }}" in template


def test_inventory_explicitly_pins_private_prometheus_bind_for_live_k6_replays() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())

    assert host_vars["monitoring_prometheus_listen_address"] == "0.0.0.0:9090"


def test_main_tasks_explicitly_disable_public_dashboards_and_embedding() -> None:
    tasks = load_tasks(TASKS_PATH)
    public_dashboards = next(task for task in tasks if task.get("name") == "Disable Grafana public dashboards")
    login_form = next(task for task in tasks if task.get("name") == "Keep the Grafana login form available for recovery")
    allow_embedding = next(task for task in tasks if task.get("name") == "Disable Grafana embedding")
    assert public_dashboards["community.general.ini_file"]["section"] == "public_dashboards"
    assert public_dashboards["community.general.ini_file"]["option"] == "enabled"
    assert public_dashboards["community.general.ini_file"]["value"] == "false"
    assert login_form["community.general.ini_file"]["section"] == "auth"
    assert login_form["community.general.ini_file"]["option"] == "disable_login_form"
    assert login_form["community.general.ini_file"]["value"] == "false"
    assert allow_embedding["community.general.ini_file"]["section"] == "security"
    assert allow_embedding["community.general.ini_file"]["option"] == "allow_embedding"
    assert allow_embedding["community.general.ini_file"]["value"] == "false"


def test_verify_tasks_check_public_dashboard_lockdown() -> None:
    tasks = load_tasks(VERIFY_PATH)
    redirect_check = next(
        task
        for task in tasks
        if task.get("name") == "Verify public Grafana dashboard URLs redirect unauthenticated viewers to login"
    )
    health_check = next(
        task for task in tasks if task.get("name") == "Verify the public Grafana health endpoint is not exposed"
    )
    headers_check = next(
        task for task in tasks if task.get("name") == "Verify Grafana version headers are stripped at the public edge"
    )
    assert redirect_check["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert redirect_check["ansible.builtin.uri"]["status_code"] == 302
    assert health_check["ansible.builtin.uri"]["status_code"] == 404
    assert headers_check["ansible.builtin.command"]["argv"][0] == "curl"


def test_main_tasks_require_loki_minio_secret() -> None:
    tasks = load_tasks(TASKS_PATH)
    names = {task["name"] for task in tasks}
    assert "Ensure the Loki MinIO secret key exists on the control machine" in names
    assert "Fail if the Loki MinIO secret key is missing locally" in names
    assert "Record the Loki MinIO secret key" in names


def test_capacity_dashboard_is_copied_imported_and_verified() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    main_tasks = load_tasks(TASKS_PATH)
    verify_tasks = load_tasks(VERIFY_PATH)

    copy_task = next(task for task in main_tasks if task.get("name") == "Copy LV3 capacity overview dashboard")
    import_task = next(task for task in main_tasks if task.get("name") == "Import LV3 capacity dashboard into Grafana")
    verify_task = next(task for task in verify_tasks if task.get("name") == "Verify LV3 capacity dashboard is provisioned")

    assert defaults["monitoring_grafana_capacity_dashboard_source_file"] == (
        "{{ monitoring_repo_root }}/config/grafana/dashboards/capacity-overview.json"
    )
    assert defaults["monitoring_grafana_capacity_dashboard_uid"] == "lv3-capacity-overview"
    assert copy_task["ansible.builtin.copy"]["src"] == "{{ monitoring_grafana_capacity_dashboard_source_file }}"
    assert import_task["ansible.builtin.uri"]["body"]["folderUid"] == "{{ monitoring_grafana_folder_uid }}"
    assert verify_task["ansible.builtin.uri"]["url"] == (
        "http://127.0.0.1:3000/api/dashboards/uid/{{ monitoring_grafana_capacity_dashboard_uid }}"
    )


def test_log_canary_dashboard_is_copied_imported_and_verified() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    main_tasks = load_tasks(TASKS_PATH)
    verify_tasks = load_tasks(VERIFY_PATH)

    copy_task = next(task for task in main_tasks if task.get("name") == "Copy LV3 log canary overview dashboard")
    import_task = next(task for task in main_tasks if task.get("name") == "Import LV3 log canary dashboard into Grafana")
    verify_task = next(task for task in verify_tasks if task.get("name") == "Verify LV3 log canary dashboard is provisioned")

    assert defaults["monitoring_grafana_log_canary_dashboard_source_file"] == (
        "{{ monitoring_repo_root }}/config/grafana/dashboards/log-canary-overview.json"
    )
    assert defaults["monitoring_grafana_log_canary_dashboard_uid"] == "lv3-log-canary-overview"
    assert copy_task["ansible.builtin.copy"]["src"] == "{{ monitoring_grafana_log_canary_dashboard_source_file }}"
    assert import_task["ansible.builtin.uri"]["body"]["folderUid"] == "{{ monitoring_grafana_folder_uid }}"
    assert verify_task["ansible.builtin.uri"]["url"] == (
        "http://127.0.0.1:3000/api/dashboards/uid/{{ monitoring_grafana_log_canary_dashboard_uid }}"
    )


def test_prometheus_template_scrapes_netdata_parent_exporter() -> None:
    template = (ROLE_ROOT / "templates" / "prometheus.yml.j2").read_text()

    assert "job_name: netdata" in template
    assert "/api/v1/allmetrics" in template
    assert "prometheus_all_hosts" in template


def test_prometheus_template_scrapes_loki_canary_metrics() -> None:
    template = (ROLE_ROOT / "templates" / "prometheus.yml.j2").read_text()

    assert "job_name: loki-canary" in template
    assert "127.0.0.1:{{ monitoring_loki_canary_metrics_port }}" in template


def test_prometheus_template_scrapes_postgres_audit_alloy_metrics() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    template = (ROLE_ROOT / "templates" / "prometheus.yml.j2").read_text()

    assert defaults["monitoring_postgres_audit_metrics_job_name"] == "postgres-audit-alloy"
    assert defaults["monitoring_postgres_audit_metrics_port"] == 12345
    assert "job_name: {{ monitoring_postgres_audit_metrics_job_name }}" in template
    assert "{{ monitoring_postgres_audit_metrics_target }}" in template
    assert "metric_relabel_configs:" in template
    assert "regex: loki_process_custom_(postgres_(audit_events_total|connection_authorized_total|unknown_connection_events_total))" in template
    assert "replacement: $1" in template


def test_verify_tasks_query_prometheus_without_escaped_job_label_quotes() -> None:
    verify_tasks = load_tasks(VERIFY_PATH)
    loki_scrape_task = next(
        task for task in verify_tasks if task.get("name") == "Verify Prometheus scrapes the Loki Canary target"
    )

    assert '\\"' not in loki_scrape_task["ansible.builtin.uri"]["url"]


def test_verify_tasks_keep_cross_guest_postgres_audit_scrape_outside_monitoring_role() -> None:
    verify_tasks = load_tasks(VERIFY_PATH)

    assert all(
        task.get("name") != "Verify Prometheus scrapes the PostgreSQL audit Alloy target" for task in verify_tasks
    )


def test_loki_canary_service_template_uses_push_mode_with_default_stream_labels() -> None:
    template = LOKI_CANARY_SERVICE_TEMPLATE.read_text()
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())

    assert "-push" in template
    assert "-metric-test-interval" in template
    assert "-labels=" not in template
    assert defaults["monitoring_loki_canary_log_selector"] == '{name="loki-canary",stream="stdout"}'


def test_tracing_tasks_render_and_wait_for_loki() -> None:
    tasks = load_tasks(TRACING_TASKS_PATH)
    lookup_group_task = next(task for task in tasks if task.get("name") == "Discover the installed Loki primary group")
    set_group_task = next(task for task in tasks if task.get("name") == "Record the installed Loki primary group")
    storage_task = next(task for task in tasks if task.get("name") == "Ensure Loki storage directories exist")
    render_task = next(task for task in tasks if task.get("name") == "Render Loki configuration")
    start_task = next(task for task in tasks if task.get("name") == "Enable and start Loki")
    wait_task = next(task for task in tasks if task.get("name") == "Wait for Loki readiness")

    assert lookup_group_task["ansible.builtin.command"]["argv"] == ["id", "-gn", "loki"]
    assert set_group_task["ansible.builtin.set_fact"]["monitoring_loki_group_name"] == (
        "{{ monitoring_loki_primary_group.stdout | trim }}"
    )
    assert storage_task["ansible.builtin.file"]["group"] == "{{ monitoring_loki_group_name }}"
    assert render_task["ansible.builtin.template"]["src"] == "loki-config.yml.j2"
    assert render_task["ansible.builtin.template"]["group"] == "{{ monitoring_loki_group_name }}"
    assert start_task["ansible.builtin.systemd"]["name"] == "loki"
    assert wait_task["ansible.builtin.uri"]["url"] == "{{ monitoring_loki_http_url }}/ready"


def test_loki_config_switches_to_s3_storage_on_cutover() -> None:
    template = LOKI_CONFIG_TEMPLATE.read_text()

    assert "object_store: s3" in template
    assert "bucketnames: {{ monitoring_loki_minio_bucket_name }}" in template
    assert "endpoint: {{ monitoring_loki_minio_endpoint }}" in template
    assert "secret_access_key: {{ monitoring_loki_minio_secret_key }}" in template
    assert "delete_request_store: s3" in template


def test_prometheus_template_scrapes_https_tls_blackbox_targets() -> None:
    template = (ROLE_ROOT / "templates" / "prometheus.yml.j2").read_text()

    assert "job_name: https-tls-blackbox" in template
    assert "{{ monitoring_prometheus_https_tls_targets_file }}" in template
    assert "__param_hostname" in template


def test_blackbox_template_defines_follow_redirect_tls_modules() -> None:
    template = (ROLE_ROOT / "templates" / "blackbox.yml.j2").read_text()

    assert "http_2xx_follow_redirects" in template
    assert "http_2xx_insecure_tls" in template
    assert "http_2xx_follow_redirects_insecure_tls" in template


def test_dashboard_templates_do_not_use_bare_jinja_null_literals() -> None:
    for template in (PLATFORM_DASHBOARD_TEMPLATE, MAIL_DASHBOARD_TEMPLATE, VM_DASHBOARD_TEMPLATE):
        assert " null" not in template.read_text()
