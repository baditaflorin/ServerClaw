# Standby courier scratch capacity warning

The two-minute courier limits each source database to 448 MiB before taking its SQLite snapshot in a bounded 512 MiB no-swap filesystem. Previously the only warning appeared after a snapshot stopped succeeding, leaving no advance indication that a source was approaching the cap.

Each source now emits its measured regular-file size and its actual enforced limit on the existing source SSH stderr channel, before the memory and size checks. The builder extracts only validated numeric markers into its existing atomic textfile metrics. Source sizes remain visible when a receiver refuses a transfer or the source is already oversized. A private systemd runtime directory contains the short-lived diagnostics; its absence does not prevent a backup. Missing or malformed telemetry is exposed by a separate alert.

Prometheus warns at 75% of the reported limit for five minutes and escalates at 93% for two minutes. The missing-size rule is gated on the existing courier-run metric, so a Prometheus that does not scrape the courier does not fire a false alert. The existing stale-copy and missing-copy alerts continue to cover a stopped courier.

The sender, receiver and drill tests exercise successful and failed transfers, missing and duplicate telemetry, and an oversized source. Promtool checked the complete rule file and simulated healthy, warning, critical, recovery and missing-telemetry cases. Transaction fixtures checked successful installation and owned rollback for both the sender and rules.

PR 689 merged as `15480f8fa6465598af528c586a56b2f07a73091f` after its checks passed; merged-main pipeline 2430 passed. At 17:25 UTC the exact merged sender and service unit were installed under the existing courier lock, with private before-images; the timer remained active and the service was not restarted. The next scheduled run at 17:26 UTC verified both standby databases, published both sizes and limits, and removed its runtime directory. The five-minute encrypted backup also had two verified replicas.

The primary Prometheus scraped both source sizes and loaded all three alert rules healthy at 17:27 UTC. The other Prometheus does not scrape the courier and is not claimed as a second source for these warnings. The 75% and 93% thresholds give advance notice for gradual growth; a source can still jump past the limit between scheduled observations.
