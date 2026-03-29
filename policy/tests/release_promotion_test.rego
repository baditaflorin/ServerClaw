package lv3.release.promotion_test

import rego.v1
import data.lv3.release.promotion

base_input := {
  "approval": {
    "approved": true,
    "reasons": [],
  },
  "blocking_findings": {"count": 0},
  "capacity_gate": {
    "approved": true,
    "reasons": [],
  },
  "stage_smoke_gate": {
    "declared": true,
    "matched_suite_ids": ["default-primary-smoke"],
    "reason": "",
  },
  "service_id": "grafana",
  "slo_gate": {
    "blocking_budget_messages": [],
    "checked": true,
    "reason": "",
  },
  "staging_receipt": {
    "age_hours": 2,
    "verification_passed": true,
  },
  "standby_gate": {
    "approved": true,
    "reasons": [],
  },
}

test_promotion_policy_allows_clean_gate if {
  decision := promotion.decision with input as base_input
  decision.gate_decision == "approved"
  count(decision.reasons) == 0
}

test_promotion_policy_rejects_stale_receipt if {
  decision := promotion.decision with input as object.union(
    base_input,
    {"staging_receipt": {"age_hours": 30, "verification_passed": true}},
  )
  decision.gate_decision == "rejected"
  decision.reasons[_] == "staging receipt is older than 24 hours"
}

test_promotion_policy_rejects_slo_budget_breach if {
  decision := promotion.decision with input as object.union(
    base_input,
    {
      "slo_gate": {
        "blocking_budget_messages": ["grafana-availability (4.00% remaining)"],
        "checked": true,
        "reason": "",
      },
    },
  )
  decision.gate_decision == "rejected"
  decision.reasons[_] == "SLO error budget below 10%: grafana-availability (4.00% remaining)"
}

test_promotion_policy_rejects_missing_stage_smoke_suite if {
  decision := promotion.decision with input as object.union(
    base_input,
    {
      "stage_smoke_gate": {
        "declared": false,
        "matched_suite_ids": [],
        "reason": "service 'grafana' does not declare an active staging smoke suite",
      },
    },
  )
  decision.gate_decision == "rejected"
  decision.reasons[_] == "service 'grafana' does not declare an active staging smoke suite"
}
