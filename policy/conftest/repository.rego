package main

import rego.v1

trusted_runner_prefixes := [
  "registry.example.com/check-runner/",
]

trusted_image(image) if {
  some prefix in trusted_runner_prefixes
  startswith(image, prefix)
}

has_nonempty_string(value) if {
  is_string(value)
  trim_space(value) != ""
}

deny contains msg if {
  some check_id, check in input.validation_gate
  check.severity != "error"
  msg := sprintf(
    "validation gate check %q must use severity %q",
    [check_id, "error"],
  )
}

deny contains msg if {
  some check_id, check in input.validation_gate
  timeout := object.get(check, "timeout_seconds", 0)
  timeout < 30
  msg := sprintf(
    "validation gate check %q timeout_seconds must be >= 30",
    [check_id],
  )
}

deny contains msg if {
  some check_id, check in input.validation_gate
  timeout := object.get(check, "timeout_seconds", 0)
  timeout > 900
  msg := sprintf(
    "validation gate check %q timeout_seconds must be <= 900",
    [check_id],
  )
}

deny contains msg if {
  some check_id, check in input.validation_gate
  image := object.get(check, "image", "")
  not trusted_image(image)
  msg := sprintf(
    "validation gate check %q uses untrusted image %q",
    [check_id, image],
  )
}

deny contains msg if {
  some check_id, check in input.validation_gate
  image := object.get(check, "image", "")
  contains(image, ":latest")
  msg := sprintf(
    "validation gate check %q must not use a latest-tagged image %q",
    [check_id, image],
  )
}

deny contains msg if {
  some check_id, check in input.check_runner_manifest
  timeout := object.get(check, "timeout_seconds", 0)
  timeout < 30
  msg := sprintf(
    "check runner %q timeout_seconds must be >= 30",
    [check_id],
  )
}

deny contains msg if {
  some check_id, check in input.check_runner_manifest
  timeout := object.get(check, "timeout_seconds", 0)
  timeout > 900
  msg := sprintf(
    "check runner %q timeout_seconds must be <= 900",
    [check_id],
  )
}

deny contains msg if {
  some check_id, check in input.check_runner_manifest
  image := object.get(check, "image", "")
  not trusted_image(image)
  msg := sprintf(
    "check runner %q uses untrusted image %q",
    [check_id, image],
  )
}

deny contains msg if {
  some check_id, check in input.check_runner_manifest
  image := object.get(check, "image", "")
  contains(image, ":latest")
  msg := sprintf(
    "check runner %q must not use a latest-tagged image %q",
    [check_id, image],
  )
}

deny contains msg if {
  some check_id, _check in input.validation_gate
  not object.get(input.validation_runner_contracts.lanes, check_id, null)
  msg := sprintf(
    "validation gate check %q must exist in config/validation-runner-contracts.json.lanes",
    [check_id],
  )
}

deny contains msg if {
  some command_id, command in input.build_server_config.commands
  runner_id := object.get(command, "runner_id", "")
  runner_id != ""
  not object.get(input.validation_runner_contracts.runners, runner_id, null)
  msg := sprintf(
    "build-server command %q references unknown runner_id %q",
    [command_id, runner_id],
  )
}

deny contains msg if {
  some command_id, command in input.build_server_config.commands
  fallback_runner_id := object.get(command, "local_fallback_runner_id", "")
  fallback_runner_id != ""
  not object.get(input.validation_runner_contracts.runners, fallback_runner_id, null)
  msg := sprintf(
    "build-server command %q references unknown local_fallback_runner_id %q",
    [command_id, fallback_runner_id],
  )
}

deny contains msg if {
  some command_id, command in input.build_server_config.commands
  validation_lanes := object.get(command, "validation_lanes", [])
  validation_lanes != "all-validation-gate-checks"
  some lane_id in validation_lanes
  not object.get(input.validation_runner_contracts.lanes, lane_id, null)
  msg := sprintf(
    "build-server command %q references unknown validation lane %q",
    [command_id, lane_id],
  )
}

deny contains msg if {
  some service in input.service_catalog.services
  service.exposure == "edge-published"
  not has_nonempty_string(object.get(service, "public_url", ""))
  msg := sprintf(
    "edge-published service %q must declare public_url",
    [service.id],
  )
}

deny contains msg if {
  some service in input.service_catalog.services
  service.exposure == "edge-published"
  not has_nonempty_string(object.get(service, "subdomain", ""))
  msg := sprintf(
    "edge-published service %q must declare subdomain",
    [service.id],
  )
}

deny contains msg if {
  some service in input.service_catalog.services
  service.exposure == "edge-published"
  production := object.get(object.get(service, "environments", {}), "production", {})
  object.get(production, "status", "") == "active"
  prod_url := object.get(production, "url", "")
  public_url := object.get(service, "public_url", "")
  has_nonempty_string(prod_url)
  has_nonempty_string(public_url)
  prod_url != public_url
  msg := sprintf(
    "edge-published service %q production url %q must match public_url %q",
    [service.id, prod_url, public_url],
  )
}

deny contains msg if {
  some workflow_id, workflow in input.workflow_catalog.workflows
  workflow.live_impact != "repo_only"
  not has_nonempty_string(object.get(workflow, "owner_runbook", ""))
  msg := sprintf(
    "mutating workflow %q must declare owner_runbook",
    [workflow_id],
  )
}

deny contains msg if {
  some workflow_id, workflow in input.workflow_catalog.workflows
  workflow.live_impact != "repo_only"
  count(object.get(workflow, "verification_commands", [])) == 0
  msg := sprintf(
    "mutating workflow %q must declare at least one verification command",
    [workflow_id],
  )
}

deny contains msg if {
  some workflow_id, workflow in input.workflow_catalog.workflows
  workflow.live_impact != "repo_only"
  entrypoint := object.get(workflow, "preferred_entrypoint", {})
  not has_nonempty_string(object.get(entrypoint, "command", ""))
  msg := sprintf(
    "mutating workflow %q must declare preferred_entrypoint.command",
    [workflow_id],
  )
}
