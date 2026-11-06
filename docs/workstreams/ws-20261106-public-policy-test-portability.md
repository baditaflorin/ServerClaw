# Public policy-tool test portability

The public snapshot intentionally excludes the deployment tailnet policy and
its lockout guard. Three test modules read the policy during import, so public
CI stopped before running the portable tests. Wrapper and installer fixtures
also tried to copy those excluded files.

Direct deployment-policy assertions now load lazily or skip only when the
excluded input is absent. The pure parser, edit, PR-flow, wrapper and installer
cases keep running against a small synthetic policy built from documentation
addresses and the tested module's role constants. Existing private policy and
guard bytes remain the first choice; private deployment assertions keep their
original inputs and checks. No live policy is exported.

A subprocess regression creates a test checkout without config/tailscale,
collects all six affected modules, and executes seven portable cases while
checking that exactly four selected deployment-only assertions skip. Separate
checks preserve existing input bytes and modes and pin the synthetic fixture
to documentation address ranges. The regression runs in Woodpecker.

Validation: all 128 affected tests pass with the private deployment inputs.
The complete six-module suite also runs without config/tailscale: 119 pass
and exactly nine direct deployment-policy assertions skip. The six new
regressions pass. Plane registration was attempted; this fresh checkout has
no private Plane authentication overlay, so the Git shard is the fallback.

The policy-specific CI step also keeps its full private check when the policy
exists, fails if a private source checkout loses that policy, and omits only
that check in a sanitized snapshot. Its generic parser/reconciler tests still
run in every case. A three-case shell regression pins those boundaries.
