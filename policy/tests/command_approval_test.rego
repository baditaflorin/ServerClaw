package lv3.command.approval_test

import rego.v1
import data.lv3.command.approval

base_input := {
  "approver_classes": ["human_operator"],
  "break_glass": false,
  "contract": {
    "approval_policy": "operator_approved",
    "evidence": {"live_apply_receipt_required": true},
    "workflow_id": "deploy-and-promote",
  },
  "policy": {
    "allow_break_glass": false,
    "allow_self_approval": false,
    "allowed_approver_classes": ["human_operator"],
    "allowed_requester_classes": ["human_operator", "agent"],
    "minimum_approvals": 1,
    "require_preflight": true,
    "require_receipt_plan": true,
    "require_validation": true,
  },
  "preflight_passed": true,
  "receipt_planned": true,
  "requester_class": "human_operator",
  "self_approve": false,
  "validation_passed": true,
  "workflow": {
    "lifecycle_status": "active",
    "preferred_entrypoint": {"command": "make promote"},
  },
}

test_command_policy_allows_clean_request if {
  decision := approval.decision with input as base_input
  decision.approved
  count(decision.reasons) == 0
  decision.workflow_id == "deploy-and-promote"
}

test_command_policy_rejects_missing_validation if {
  decision := approval.decision with input as object.union(base_input, {"validation_passed": false})
  not decision.approved
  decision.reasons[_] == "repository validation has not been marked passed"
}

test_command_policy_rejects_disallowed_requester if {
  mutated := object.union(
    base_input,
    {
      "requester_class": "service_identity",
      "approver_classes": ["human_operator"],
    },
  )
  decision := approval.decision with input as mutated
  not decision.approved
  decision.reasons[_] == "requester_class 'service_identity' is not allowed by policy 'operator_approved'"
}
