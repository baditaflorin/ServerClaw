package lv3.command.approval

import rego.v1

allowed_identity_classes := [
  "agent",
  "break_glass",
  "human_operator",
  "service_identity",
]

deny[msg] if {
  input.workflow.lifecycle_status != "active"
  msg := sprintf(
    "workflow '%s' is '%s', not active",
    [input.contract.workflow_id, input.workflow.lifecycle_status],
  )
}

deny[msg] if {
  requester := input.requester_class
  not requester in allowed_identity_classes
  msg := sprintf(
    "requester_class must be one of %v",
    [allowed_identity_classes],
  )
}

deny[msg] if {
  requester := input.requester_class
  requester in allowed_identity_classes
  not requester in input.policy.allowed_requester_classes
  msg := sprintf(
    "requester_class '%s' is not allowed by policy '%s'",
    [requester, input.contract.approval_policy],
  )
}

deny[msg] if {
  count(input.approver_classes) < input.policy.minimum_approvals
  msg := sprintf(
    "policy '%s' requires at least %d approval(s)",
    [input.contract.approval_policy, input.policy.minimum_approvals],
  )
}

deny[msg] if {
  some approver in input.approver_classes
  not approver in allowed_identity_classes
  msg := sprintf(
    "approver_class '%s' must be one of %v",
    [approver, allowed_identity_classes],
  )
}

deny[msg] if {
  some approver in input.approver_classes
  approver in allowed_identity_classes
  not approver in input.policy.allowed_approver_classes
  msg := sprintf(
    "approver_class '%s' is not allowed by policy '%s'",
    [approver, input.contract.approval_policy],
  )
}

deny[msg] if {
  input.self_approve
  not input.policy.allow_self_approval
  msg := sprintf(
    "policy '%s' does not allow self approval",
    [input.contract.approval_policy],
  )
}

deny[msg] if {
  input.break_glass
  not input.policy.allow_break_glass
  msg := sprintf(
    "policy '%s' does not allow break-glass execution",
    [input.contract.approval_policy],
  )
}

deny["preflight has not been marked passed"] if {
  input.policy.require_preflight
  not input.preflight_passed
}

deny["repository validation has not been marked passed"] if {
  input.policy.require_validation
  not input.validation_passed
}

deny["receipt planning has not been marked complete"] if {
  input.policy.require_receipt_plan
  not input.receipt_planned
}

decision := {"approved": count(deny) == 0, "entrypoint": input.workflow.preferred_entrypoint.command, "receipt_required": input.contract.evidence.live_apply_receipt_required, "reasons": sort([msg | deny[msg]]), "workflow_id": input.contract.workflow_id}
