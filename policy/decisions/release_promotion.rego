package lv3.release.promotion

import rego.v1

deny[msg] if {
  some reason in input.approval.reasons
  msg := reason
}

deny["staging receipt is older than 24 hours"] if {
  input.staging_receipt.age_hours > 24
}

deny["staging receipt verification is not clean"] if {
  not input.staging_receipt.verification_passed
}

deny[msg] if {
  some reason in input.smoke_gate.reasons
  msg := reason
}

deny[msg] if {
  input.blocking_findings.count > 0
  msg := sprintf(
    "open critical findings exist for service '%s'",
    [input.service_id],
  )
}

deny[msg] if {
  some reason in input.vulnerability_gate.reasons
  msg := reason
}

deny[msg] if {
  some reason in input.capacity_gate.reasons
  msg := reason
}

deny[msg] if {
  some reason in input.standby_gate.reasons
  msg := reason
}

deny[msg] if {
  not input.slo_gate.checked
  msg := sprintf("SLO gate could not evaluate: %s", [input.slo_gate.reason])
}

deny[msg] if {
  count(input.slo_gate.blocking_budget_messages) > 0
  msg := sprintf(
    "SLO error budget below 10%%: %s",
    [concat(", ", input.slo_gate.blocking_budget_messages)],
  )
}

gate_decision := "approved" if {
  count(deny) == 0
}

gate_decision := "rejected" if {
  count(deny) > 0
}

decision := {"gate_decision": gate_decision, "reasons": sort([msg | deny[msg]])}
