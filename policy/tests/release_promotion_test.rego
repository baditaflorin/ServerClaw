package lv3.release.promotion_test

import rego.v1
import data.lv3.release.promotion

base_input := {
  "approval": {
    "approved": true,
    "reasons": [],
  },
  "blocking_findings": {"count": 0},
  "vulnerability_gate": {
    "approved": true,
    "reasons": [],
  },
  "capacity_gate": {
    "approved": true,
    "reasons": [],
  },
  "service_id": "grafana",
  "smoke_gate": {
    "enforced": false,
    "failed_suite_ids": [],
    "missing_suite_ids": [],
    "reasons": [],
    "required_suite_ids": [],
  },
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
      "smoke_gate": {
        "enforced": true,
        "failed_suite_ids": [],
        "missing_suite_ids": ["staging-grafana-primary-path"],
        "reasons": ["staging smoke suites missing from staged receipt: staging-grafana-primary-path"],
        "required_suite_ids": ["staging-grafana-primary-path"],
      },
    },
  )
  decision.gate_decision == "rejected"
  decision.reasons[_] == "staging smoke suites missing from staged receipt: staging-grafana-primary-path"
}

test_promotion_policy_rejects_vulnerability_gate_failure if {
  decision := promotion.decision with input as object.union(
    base_input,
    {
      "vulnerability_gate": {
        "approved": false,
        "reasons": ["image windmill_runtime has 3 critical findings, above the budget 0"],
      },
    },
  )
  decision.gate_decision == "rejected"
  decision.reasons[_] == "image windmill_runtime has 3 critical findings, above the budget 0"
}
