## Summary

<!-- What does this PR do? 1-3 bullet points. -->

## Type of change

- [ ] Bug fix
- [ ] New feature / service
- [ ] Refactoring (no functional change)
- [ ] Documentation
- [ ] CI/CD / tooling
- [ ] Release (`[release]` in title — enforces release-readiness checks)

## Checklist

- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] ADR created or updated (if architectural decision involved)
- [ ] Role defaults use `{{ platform_domain }}` / `{{ platform_operator_email }}` — no hardcoded operator values
- [ ] No secrets or credentials in committed files
- [ ] Tests pass (`make validate`)

## Release checklist (for `[release]` PRs)

<!-- Skip this section for non-release PRs. These are enforced by CI when
     the PR title contains [release] (ADR 0420). -->

- [ ] `VERSION` bumped (`echo "X.Y.Z" > VERSION`)
- [ ] `changelog.md` entry added under `## Unreleased`
- [ ] Release notes generated: `uv run --with pyyaml python scripts/generate_release_notes.py --version X.Y.Z --released-on $(date +%Y-%m-%d) --write`
- [ ] Root summaries refreshed: `uv run --with pyyaml python scripts/generate_release_notes.py --write-root-summaries`
- [ ] Platform manifest regenerated: `uvx --python 3.12 --with pyyaml --with jsonschema --with requests --with jinja2 python scripts/platform_manifest.py --write`
- [ ] Discovery artifacts regenerated: `python scripts/generate_discovery_artifacts.py --write`
- [ ] ADR index regenerated (if ADRs changed): `python scripts/generate_adr_index.py --write`

## Test plan

<!-- How was this tested? Docker dev, production, manual verification? -->
