# Operating the open-source discovery engine

The code defaults to OSS mode. The existing collectors are retained for rollback, not used as fallback. Setup does not start personal searches.

## Before using it

1. Reload backend and worker code in your own terminals when ready; reload the frontend if its development process did not pick up the changes. Do not start a second worker beside the existing worker. This implementation did not restart services.
2. Do not change Docker configuration or the backend's production dependency environment. The third-party tools use their existing isolated environments.
3. From the project root, run the read-only doctor if needed:

   `backend\venv\Scripts\python.exe backend\scripts\check_oss_collectors.py --json`

   Doctor does not search jobs or start services. The Sources tab's interpreter-presence check is lighter than doctor.
4. Open Jobs → Sources. Review the open-source tools, source scope and live verification labels. Connect selected sources or supply an exact supported ATS-host employer board URL. A saved source is still unverified until collection succeeds.
5. Review Preferences and filters. Search starts only when you click Search jobs. Leave it paused until you want to begin.

## During search

- Keep the single worker terminal and required databases available. Results arrive in batches; opening the Jobs page itself does not fetch jobs.
- Up to three source fetches run per batch; browser sources serialize. Source cooldowns can defer work. Source errors are shown in Sources and search status.
- ATS continuation reuses a public-source catalogue snapshot for up to one hour, fetching a bounded set of descriptions per batch. Expired snapshots restart safely. Other collectors do not claim a generic result cache.
- Relevance scores, thresholds and ranking are removed. Choose your experience from 0–10 years and whether to include unstated experience. Date options include 1 and 3 days; clicking Search jobs applies that date window to collection. Salary, sort and WFH controls remain available; unknown/estimated salary is included by default.
- Source collection does not apply for jobs. Review the original posting and use the existing resume/application workflow separately.

## Understanding incomplete results

- `never_checked`: a connection was saved but not collected.
- `partial`: a bounded window, excerpt or continuation; not the entire site.
- `blocked`, `permission_required`, `login_required`: access needs separate resolution; repeated requests do not fix it.
- `rate_limited`: wait for the source's cooldown.
- `changed_format` or `invalid_output`: a source profile/schema needs maintenance.
- `runtime_missing`: rerun doctor/setup for the isolated tool; do not install it into the web backend environment.
- `unsupported`: the selected upstream does not support that board or country/path. Verify the exact URL and library capability.

Some sources remain disabled due to documented access/runtime blockers. Installing all tools does not provide all websites automatically. The source ledger retains unresolved sites and employer programmes.

Pause/cancel signals running collectors across processes and prevents late ingestion. Individual source operations remain bounded; searches continue through paced batches while progress is possible, without the former 15-minute cutoff. Real source rate limits/access failures and fully repeated pages still stop or defer collection. A new explicit search starts fresh checkpoints while preserving real error cooldowns. See `SEARCH_PIPELINE_FIXES.md` for verification.

## Explicit rollback

An administrator can set both `JOB_DISCOVERY_ENGINE=legacy` and `JOB_LEGACY_ENABLED=true` in the user-managed service configuration and reload backend/worker. Legacy mode alone is insufficient. Only do this when you intentionally want the retained collectors back. In OSS mode their setup/toggle endpoints reject use even if old source rows still say enabled.

OSS connections and imported results are preserved across an engine switch. Tasks tagged for the wrong engine cannot execute. No database restore or deletion is needed. Remove the legacy opt-in and return the engine to `oss` to restore OSS mode.

## Dependency maintenance

Pins, locks and license notices remain under `oss-tools/`. Upgrade one tool in its isolated environment, run its fixtures and bounded source checks, then update the manifest. Do not run automatic pip upgrades at web-server startup. Never enable paid hosted API/cloud fallbacks to hide a source failure.
