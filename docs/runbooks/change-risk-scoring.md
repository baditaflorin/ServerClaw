# Change Risk Scoring

ADR 0116 adds deterministic risk scoring to the `lv3 run <workflow>` path.

## Operator Use

- Use `lv3 run <workflow> --dry-run` to inspect the compiled intent, scoring context, numeric score, and approval gate before any Windmill call is made.
- A `HARD` gate requires `--approve-risk`.
- A `BLOCK` gate requires `--risk-override`.

## Tuning

- Adjust scoring weights in `config/risk-scoring-weights.yaml`.
- Adjust fallback target tiers, workflow defaults, and downstream counts in `config/risk-scoring-overrides.yaml`.
- Prefer changing overrides only when the canonical runtime signal does not exist yet. Remove the override once ADR 0117 or ADR 0120 provides the real signal.

## Calibration

- Run `uv run python config/windmill/scripts/calibrate-risk-scoring.py --repo-root . --lookback-days 30` to recompute scores for recent live-apply receipts.
- Add `--mattermost-webhook-url <url>` to post the summary to Mattermost.
- Empty risk buckets report `no data`; this is expected and should not be treated as a failure.
