# ServerClaw sanitized edge-route template

## Context

The sanitized ServerClaw snapshot carries an active `repo-intake` entry in its
subdomain exposure catalog, including the edge-auth contract. Its Tier A
Proxmox host template omitted the matching route, so the public Woodpecker
subdomain-catalog tests failed after publication.

## Change

Add the generic `repo-intake` host-topology route to the public template and
cover its hostname, enabled proxy edge, and service port in the publisher unit
tests. Classify publication templates so validation selects schema, generated
artifact, and service checks without unrelated Packer/OpenTofu roots. Keep real
domains and deployment-only values out of the template.

## Verification

The required publication verification is to generate the sanitized snapshot,
confirm its leak scan passes, and run the same subdomain-catalog checks used by
ServerClaw Woodpecker. The snapshot is merged only after the required
`ci/woodpecker/push/woodpecker` status is green.

## Status

In progress; ServerClaw PR #55 exposed the mismatch. The generic route and
regression test are implemented, and the publisher/subdomain tests pass
locally. Private PR CI and the refreshed public snapshot checks are pending.
No live service/runtime change is part of this workstream.
