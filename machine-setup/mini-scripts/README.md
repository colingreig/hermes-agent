# Mini-local scripts (canonical copies)

These scripts run on the Mac mini at `~/.hermes/scripts/` but live **outside**
the mini's git-tracked release/runtime-current deploy path (see
`hermes_cli/gateway.py` / `hermes update`) — nothing in this repo's deploy
pipeline provisions, copies, or regenerates `~/.hermes/scripts/*`. That
independence is normally fine, but it also means these files have no backup
story beyond the mini's own `.bak-*` files and whatever restic snapshot
happens to be current.

The 2026-07-19 mini home-directory data-loss incident (see ClickUp 86e2ddcpb)
proved that gap real: the `op_sdk_resolve.py` resilience patch (300s cache +
retry/backoff + serve-stale, added 2026-07-13 after a ~13h 1Password
daily-quota lockout) was silently lost in the wipe/recovery and nobody
noticed until this task re-verified it (86e2a99q9, 2026-07-21).

**Convention going forward:** any `~/.hermes/scripts/*` file (`.py` or `.sh`)
that fixes a production incident gets a canonical copy committed here, in git,
so it survives even a full home-directory loss — not just a
`~/.hermes/local-patches` copy (that directory itself was lost in the same
incident).

To restore a script after any kind of mini data loss:

```bash
scp machine-setup/mini-scripts/<file> mac-mini-h.tail51ec1b.ts.net:~/.hermes/scripts/<file>
mini-run -- 'python3 -m py_compile ~/.hermes/scripts/<file>'  # sanity check
```

Diff against the live file periodically (`ssh mini cat ~/.hermes/scripts/<file>`
vs this copy) to catch drift — nothing currently automates that check.

## Files

- `op_sdk_resolve.py` — resolves `op://` secret references for
  `gateway_secrets_wrap.sh` and cron/sentinel scripts. **Connect-first since
  2026-07-24**: prefers a locally-run 1Password Connect server (see
  `op-connect/`) and falls back to the cloud service-account SDK only when
  Connect is down or a ref is outside the Connect token's vault scope — this
  moves routine resolution off the rate-limited cloud account. Verified live:
  the gateway boot fetches all 142 secrets from both vaults through Connect
  (`127.0.0.1:8080`) with zero cloud calls.
  Restored 2026-07-21 with the HERMES-PATCH 31 resilience layer (cache,
  retry/backoff, serve-stale, id-fast-path) re-added from the original spec
  in ClickUp 86e2a99q9 after the 2026-07-19 loss; live-verified (142/142
  secrets resolved, cache hit confirmed on a second run, 0700/0600 perms).
  Hardened for ClickUp 86e2a2paz on 2026-07-23: auth/unauthorized/invalid/
  forbidden/expired/token markers take precedence over transient-looking text;
  transient failures use three bounded jittered retries around 5/15/45 seconds;
  exhausted transient failures serve stale only when every requested value has
  complete usable cache data, otherwise they retain the CLI's exact FATAL/exit-1
  contract. Importable `resolve_refs()` consumers now use the same retry/cache
  path, while stdout remains byte-compatible `KEY="value"` shell input.
- `sentinel_run.sh` — launchd runner for Ignite Sentinel. De-clusters its
  1Password resolve with a random delay in the inclusive 0–120 second window.
  `SENTINEL_START_DELAY_MAX_SECONDS=0 SENTINEL_SMOKE_ONLY=1` performs the
  secrets-resolution smoke without running the monitor or emitting Slack.
- `degraded_secrets_monitor.py` — detects repeated secret-resolution failures
  and unresolved placeholders. Its SDK subprocess uses the immutable
  `~/.hermes/runtime-current/venv/bin/python` path, not the removed mutable
  `~/.hermes/hermes-agent/venv/bin/python` checkout.
- `tests/test_op_sdk_resolve.py` — fully mocked resolver contract harness:
  transient-then-success, exhausted transient without stale, mixed auth +
  timeout precedence, complete stale fallback, and stdout quoting bytes.
- `tests/test_sentinel_run.sh` — validates the 0–120 second delay contract and
  executes a fake-HOME, Slack-silent sentinel smoke.
- `tests/test_op_sdk_consumers.sh` — verifies canonical/live resolver byte
  identity plus the sentinel, degraded-monitor, and marketplace consumer paths.
- `verify-hermes-patches.sh` — idempotent guard/health-check for the 12 legacy
  hand-patches (now all formally merged to main) plus ~30 other live-deploy
  sentinels (GH App token, marketplace sync cron, validator model chain,
  skills freshness, DB-publish lane, etc). Fixed 2026-07-22 (ClickUp 86e2e7z2h)
  to stop hardcoding the pre-2026-07-19 mutable `$HOME/.hermes/hermes-agent`
  checkout — `REPO` now resolves `$HOME/.hermes/runtime-current` (the current
  immutable release). Since the original `.patch` diff files were lost in the
  same 2026-07-19 wipe and are unrecoverable, patch verification is now
  sentinel-first (grep a load-bearing string in the live release) rather than
  `git apply --reverse --check` against a file that no longer exists; a `.patch`
  file, if one is ever added back to `~/.hermes/local-patches`, still gets the
  git-apply re-application path. Before this fix the script exited at `cd
  "$REPO"` before reaching ANY of its ~30 other checks — those were silently
  unverifiable since 2026-07-19, not merely "assumed green".
- `offbox_restic_backup.py` — nightly restic backup of `~/.hermes` to
  Cloudflare R2. `BACKUP_TARGETS` added `~/.hermes/memories` 2026-07-22
  (ClickUp 86e2e870p) after discovering it had never been in scope — the
  2026-07-19 wipe permanently lost Hermes's entire MEMORY.md/USER.md
  personalization with zero restic snapshot history to restore from, at any
  point. This closes the gap for future incidents; it does not recover what
  was already lost (see 86e2e870p for the reseed decision, separately pending
  Colin's input). Failure alerts are signature-deduplicated in
  `~/.hermes/state/offbox-backup-monitor.json`; the initial failure and
  recovery advance that state only after Hermes confirms Slack delivery, so
  an unavailable transport remains retryable.
- `tests/test_offbox_restic_backup.py` — verifies delivery-aware failure and
  recovery persistence through the real Hermes-send boundary.
- `research_exec.py` — bounded pre-write content research stage. It resolves
  `SCRAPINGBEE_API_KEY` through Hermes's in-memory lazy 1Password resolver,
  searches and fetches a small source set, and treats every fetched byte as
  untrusted data. Analysis uses a fixed direct Anthropic Messages API request:
  no tool declarations, tool choice, MCP connectors, container, filesystem,
  shell, browser, agent runtime, or action interpreter. The tool-capable
  `opencode_exec.py --dangerously-skip-permissions` path is explicitly forbidden
  for fetched content. Only text response blocks become the brief; tool-use
  blocks are ignored and produce a flag-and-ship fallback. Its independent
  `content_pipeline.research.enabled` switch in `~/.hermes/config.yaml`
  defaults on; any key/API/paywall/bot/analyzer failure is flag-and-ship and
  leaves the writer able to continue.
  Execution receipts go to `~/.hermes/logs/research-served.jsonl` without the
  API key, query text, fetched content, or generated brief.
- `research_stage_monitor.py` — independent served-ledger liveness check. It
  reports recent enabled attempts, successful serves, degraded attempts, and
  served rate; it exits 2 for a missing/degraded enabled-stage window.
- `content-research-baseline.json` — phase-1 pre-rollout metrics snapshot,
  including the audited 1/3 content-gate execution rate and the historical
  0/29 Sonnet serve comparator, with unknown historical metrics explicitly
  marked uninstrumented rather than inferred.
- `tests/test_research_stage.py` — verifies secret-safe auth, strict untrusted
  data boundaries, the analyzer request's zero-tool surface, refusal to
  interpret tool-use responses, bounded HTTP reads, flag-and-ship fallback,
  cannibalization context, content-free receipts, and monitor thresholds.
