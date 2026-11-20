# Evidence-backed reconciliation of legacy workstreams

**Status:** Merged

**Scope:** Correct only legacy workstream records whose repository, merged PR,
and release state can be confirmed from repository history and GitHub.

## Starting snapshot

On 2026-11-20, the reconciliation report listed 160 records, 105 with
`status: in_progress`. All 105 lacked exact repository references. Forty-five
had at least one completion or release signal, but those signals overlap and
are not sufficient to change status.

After the evidence-backed updates and 99 reference backfills, the current
report lists 161 records, 102 `in_progress`, and 4 still missing repository
references. PR #717 merged the evidence-backed reconciliation; PR #718 records
this closeout. No
repository-linked in-progress workstream is missing a PR reference; the four
unlinked records remain pending source evidence.
The 102 remaining in-progress records include 98 with verified repository/PR
links and 4 that remain unlinked for manual evidence review.
Fifty-seven in-progress records still need manual review. Forty-two have one
or more completion/release signals; overlapping flags include 24 ready-to-merge,
12 live-applied, 11 all-tasks-complete, 2 released-version, and 32 reused-branch
signals. These flags remain review leads, not automatic closure criteria.

## Evidence and decisions

| Workstream | Direct evidence | Decision |
| --- | --- | --- |
| `ws-0448-postmortem-and-handoff` | PR [#76](https://github.com/baditaflorin/platform_server/pull/76) is merged and adds this exact shard and its postmortem. The postmortem records the underlying implementation as resolved in release 0.179.11 via PR #75. | Record this repository and PR #76, then mark the handoff workstream merged. Keep its reconciliation note in the pending canonical release lifecycle. |
| `ws-0463-atomic-receipt-write` | PR [#93](https://github.com/baditaflorin/platform_server/pull/93) is merged and adds this exact shard, the implementation, tests, ADR, and release 0.179.26. The release changelog names the workstream. | Record this repository and PR #93, then mark the workstream merged. The ADR's PR #71 link is the originating incident, not the fix PR. Keep the metadata correction in the pending canonical release lifecycle. |
| `ws-20261118-kamateratmp-build-pool-expansion` | PR [#705](https://github.com/baditaflorin/platform_server/pull/705) is merged with all Woodpecker checks green. Its completed live-apply receipt verifies the Tailscale SSH identity, CT108 Buildx context, Fleet Runner admission, Woodpecker expiry, and cache-only canary. | Advance the workstream to `live_applied` and clear its stale `ready_to_merge` flag. Keep its patch-release metadata pending and retain the trial until the sunset/teardown evidence is recorded. |

PR and release evidence is checked directly. A branch name or a PR link merely
mentioned in an incident note is not treated as proof that a workstream was
completed.

## Repository and PR reference backfill

The remaining 103 legacy records without repository references were checked
against Git history and GitHub. For 90, the merged PR's merge commit exactly
matches the commit that added the workstream shard. For 9 more, GitHub's
commit-to-PR association identifies one merged PR containing that exact shard
addition. Their repo and PR links are recorded in
[`ws-20261120-legacy-workstream-reconciliation-evidence.csv`](ws-20261120-legacy-workstream-reconciliation-evidence.csv).

These links confirm that `baditaflorin/platform_server` is a repository
associated with each record. They do not prove that the workstream is complete
or that it touched no other repository. One of the 99 linked records,
Kamateratmp, had separate live-apply evidence and was advanced to
`live_applied`; the other 98 remain `in_progress`. Four records had no
associated merged PR in the shard-add history:
`adr-0360-openbao-cert-hardening`, `ws-0414-cert-lifecycle-agent-tools`,
`ws-0417-attack-surface-hardening`, and `ws-realtime-dynamic-children`.

## Remaining work

The 98 other linked records remain `in_progress`; a merged PR that adds a
shard is repository/PR evidence, not proof that all work is complete. The two
status changes above have separate release and implementation evidence, and
the Kamateratmp status change has its completed live-apply receipt. The four
unlinked records remain unchanged pending stronger source evidence.

The reconciliation command remains read-only; this document is the audit
trail for the evidence-backed metadata updates in this workstream. The next
automation step should produce a draft reconciliation queue with evidence
references and human-reviewed status proposals; it must not auto-close the 98
still-open linked records or infer completion from a shard-add PR.
