# DomainScope Drive data room refresh (CT108)

The Google Drive folder "DomainScope Data Room" (27 documents, 12 subfolders, owner operator@example.com) quotes two live
figures as sentences: the domains catalogued and the share of them smart search covers. A daily job on the builder brings those
sentences to the current generated `/data/metrics/data-room/latest.json` on the cron host, and changes nothing else. What it
does and does not touch is in that repository: `docs/investor/drive-refresh.md`, the manifest `docs/investor/drive-refresh.manifest.json`
and the tool `src/cmd/drive-refresh`.

## What runs where

| Piece | Where | What it does |
|---|---|---|
| `domainscope-drive-refresh.timer` | CT108 (`config/systemd/`) | daily 07:30 UTC (+ up to 10 min), no catch-up run after a boot; clear of the 01:30Z backup stop |
| `domainscope-drive-refresh.service` | CT108 (`config/systemd/`) | oneshot as root, `flock`, exit 1 = a document failed (the metrics say which), exit 3 = the run could not start |
| `/usr/local/bin/domainscope-drive-refresh-run` | CT108 (`scripts/domainscope-drive-refresh-run`) | validates the current aggregate, fetches the reviewed tool and manifest from origin/main into `/var/lib/domainscope-drive-refresh/repo`, builds `drive-refresh`, reads the key into stdin, runs it with `-apply` |
| `/usr/local/lib/domainscope-drive-refresh/figures.py` | CT108 (`scripts/domainscope-drive-figures.py`) | fixed read-only SSH command to the existing cron container; 30-second read deadline, 1 MiB limit, JSON/count/date validation and the same eight-day freshness limit before any credential read |
| `domainscope_drive_refresh.prom` | CT108 `/var/lib/prometheus-node-exporter/textfile/` | `ok`, `last_success_timestamp_seconds` (carried through failed runs), `last_run_timestamp_seconds`, `docs_failed`, `docs_changed`, `replacements` |
| `config/prometheus/rules/domainscope-drive-refresh.yml` | monitoring VM | `DomainScopeDriveRefreshFailing` (last run not ok, 30 min), `DomainScopeDriveRefreshStale` (no good run for 49 h or no series for 7 days) |

## Access

Set `DSDRIVE_FIGURES_HOST` in `/etc/default/domainscope-drive-refresh` to the cron host's existing approved SSH target.
For example, `DSDRIVE_FIGURES_HOST=report-host.example.com`. The target runs only
`docker exec domainscope-cron cat /data/metrics/data-room/latest.json`. A failed, oversized, stale or invalid export fails the run;
there is no fallback to the committed snapshot. The validated local copy is owner-only and replaced atomically. An explicit
`DSDRIVE_FIGURES_FILE` can select a local aggregate for an offline check; it receives identical validation.
The SSH host key must already be trusted (`StrictHostKeyChecking=yes`). Both the aggregate generation time and the shared catalogue
`as_of` date must be within eight days; future catalogue dates are refused, so a daily render cannot make stale input figures look current.

- Google Cloud project `domainscope-drive-refresh` (`inspired-vault-512922-b1`), Drive, Docs and Sheets APIs enabled.
- Service account `domainscope-drive-refresh@inspired-vault-512922-b1.iam.gserviceaccount.com`: no project roles; **Editor on the one
  Drive folder** and nothing else (the folder's permission list holds the owner and this account).
- Its JSON key is the fleet vault entry `domainscope-drive-sa-key` (consumer `url-categorizer-api`), read with
  `bash /root/bin/fv.sh raw domainscope-drive-sa-key` into the tool's standard input. Never an argument, an environment variable or a file;
  nothing prints it. Rotate it in the Cloud console (IAM and admin, Service accounts, Keys): create a new key, `fv.sh put` it under the same
  name, delete the old key.

## Install, update, remove

```bash
scripts/domainscope-drive-refresh-install.sh            # wrapper to /usr/local/bin, units to /etc/systemd/system (replaced files kept as .bak-<UTC>)
scripts/domainscope-drive-refresh-install.sh --enable   # also enable the timer and run one DRY RUN now (prints the changes, writes nothing)
scripts/domainscope-drive-refresh-install.sh --status   # timer, last result, journal tail, metrics
```

Only files identical to origin/main are installed. Configure the figures host before enabling the timer. The wrapper builds the tool from origin/main on every run, so merging a change to
`src/cmd/drive-refresh` is its deploy. Install `config/prometheus/rules/domainscope-drive-refresh.yml` on the monitoring VM as
`/etc/prometheus/rules/domainscope-drive-refresh.yml` (the monitoring_vm role ships it; `promtool check rules`, then a HUP of Prometheus).

A hand run must also provide the configured host: `DSDRIVE_APPLY=0 DSDRIVE_FIGURES_HOST=report-host.example.com /usr/local/bin/domainscope-drive-refresh-run`
is a dry run (no metrics, no alerts); without the apply variable it
applies. Stop it: `systemctl disable --now domainscope-drive-refresh.timer` (the stale alert fires after two days: silence it or remove the
rule file). Remove it: disable the timer, delete the two units, the wrapper, `/var/lib/domainscope-drive-refresh` and the `.prom` file.

The wrapper also accepts `--dry-run`, which overrides an apply setting in an EnvironmentFile. The installer's `--enable` check uses a transient
unit with that flag and the normal EnvironmentFile; it does not rely on the system manager passing a temporary environment variable to a service.

## When it alerts

- `DomainScopeDriveRefreshFailing`: `journalctl -u domainscope-drive-refresh.service -n 80`. "current figures unavailable" names an SSH, size, freshness or schema failure; fix the source export or scheduler, then retry. The live aggregate may be current while the periodically committed snapshot is old. A document `[error]` names the Google error
  (a person edited it during the run: the next run retries; a 403 means the sharing was changed). `[no-match]` means a document no longer
  holds a figure sentence (someone rewrote it): put the sentence back or move the file to `skip` in the manifest. "data-room.json is N h old":
  the live scheduler's aggregate is stale; nothing in Drive was changed. "go build failed": main is broken or a toolchain could not
  be fetched.
- `DomainScopeDriveRefreshStale`: `systemctl status domainscope-drive-refresh.timer`; the builder or its node exporter may be down.
- Undo a run: in Drive, File, Version history, restore the version before the change (each document keeps its own history). The run
  changes only the phrases the journal lists.

## Why it is shaped this way

The Claude connectors for Drive, Docs and Sheets were not available to the unattended session (they were connected under another Google
account than the one that owns the folder), so the refresh runs as a service account the fleet owns. Daily, not weekly, because the
run is a no-op when nothing moved and `data-room.json` reaches `main` some hours after the Monday job. The dated 10-07 snapshots and
investor deck v2.3 are skipped on purpose (manifest `skip`, with a reason each).
