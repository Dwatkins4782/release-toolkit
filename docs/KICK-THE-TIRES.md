# Kick the Tires — Hands-On Quick Start

Walk through every script in the toolkit in under 30 minutes. Each step uses `--dry-run` or local-only mode so nothing touches real infrastructure.

---

## Prerequisites

```bash
# Clone the repo
git clone https://github.com/Dwatkins4782/release-toolkit.git
cd release-toolkit

# Install Python dependencies
pip install -r requirements.txt

# Copy environment template (no real values needed for dry-run)
cp config/.env.example .env
```

---

## Step 1: Calculate a Semantic Version

What it does: Reads your Git commit history since the last tag and determines the next version (major, minor, or patch) based on conventional commit types.

```bash
# Auto-detect bump type from commit messages
python scripts/version.py --bump auto --dry-run --output version-summary.json

# Or force a specific bump
python scripts/version.py --bump minor --dry-run --output version-summary.json

# Or create a pre-release
python scripts/version.py --bump minor --pre-release rc.1 --dry-run --output version-summary.json
```

Check the output:

```bash
cat version-summary.json
# {
#   "version": "v1.1.0",
#   "previous_version": "v1.0.0",
#   "bump_type": "minor",
#   "features": 2,
#   "fixes": 1,
#   "breaking_changes": 0,
#   ...
# }
```

---

## Step 2: Generate Release Notes

What it does: Categorizes commits into Features, Bug Fixes, Performance, Breaking Changes, etc. Extracts Jira ticket references. Lists contributors.

```bash
# Markdown release notes
python scripts/release_notes.py --version v1.1.0 --format md --output release-notes-v1.1.0.md

# JSON (machine-readable, consumed by QA bridge)
python scripts/release_notes.py --version v1.1.0 --format json --output release-notes-v1.1.0.json
```

Check the output:

```bash
cat release-notes-v1.1.0.md
# Shows categorized changes, ticket links, contributor list
```

---

## Step 3: Preview Jira Ticket Tagging

What it does: Finds all Jira ticket IDs in commit messages, then labels them with the release version, adds a comment, sets the fix version, and optionally transitions their status.

```bash
# Dry run — shows what would happen without touching Jira
python scripts/tag_work_items.py --version v1.1.0 --dry-run --output tagged-items.json

# See which tickets would be tagged
cat tagged-items.json
```

---

## Step 4: QA Bridge Handoff (Dry Run)

What it does: The full QA handoff pipeline — generates a test manifest mapping changes to test suites, creates a QA checklist, snapshots feature toggles, and (in real mode) deploys to QA and triggers automated tests.

```bash
# Skip deploy, tests, and notifications — just generate artifacts
python scripts/prepare_qa_handoff.py \
  --version v1.1.0 \
  --env qa \
  --output-dir ./qa-artifacts \
  --skip-deploy \
  --skip-tests \
  --skip-notify

# Inspect the generated artifacts
ls qa-artifacts/
# release-manifest.json   — test suite mapping
# qa-checklist.md          — manual QA checklist
# feature-toggle-snapshot.json

cat qa-artifacts/qa-checklist.md
```

---

## Step 5: Multi-Repo Release Correlation

What it does: Clones/fetches configured sibling repos, collects their commits since last tag, finds shared Jira tickets across repos, and generates a risk assessment.

```bash
# Dry run correlation (will attempt to read configured repos)
python scripts/correlate_releases.py --version v1.1.0 --output correlation-report.json

cat correlation-report.json
# Shows: which tickets span multiple repos, total commits per repo, risk level
```

---

## Step 6: Feature Toggle Snapshot

What it does: Connects to LaunchDarkly or Split and captures the state of all feature flags at release time. Records which flags are on/off so QA knows what to test.

```bash
# Snapshot (uses mock data without real API key)
python scripts/feature_toggles.py --version v1.1.0 --action snapshot
```

---

## Step 7: Generate a Release Report

What it does: Produces an automated release report with DORA metrics (deployment frequency, lead time, change failure rate, MTTR), change summary by type, and a deployment readiness checklist. Designed to replace large coordination meetings.

```bash
python scripts/release_report.py --version v1.1.0 --format md --output release-report.md

cat release-report.md
# Executive summary table, DORA metrics, changes by type, readiness checklist
```

---

## Step 8: Docker Image Promotion (Dry Run)

What it does: Promotes Docker images from one registry to another (e.g., staging → prod) with SHA digest verification to ensure the exact image is promoted.

```bash
# Preview what would be promoted
bash scripts/promote_image.sh --version v1.1.0 --from staging --to prod --all --dry-run
```

---

## Step 9: Deploy Script (Dry Run)

What it does: Single-command Helm-based deployment to any environment. Supports rolling, canary, and blue-green strategies. Includes pre-deploy checks (production confirmation gate), post-deploy health verification, and rollback.

```bash
# Preview a staging deploy
bash scripts/deploy.sh --version v1.1.0 --env staging --strategy rolling --dry-run

# Preview a production canary deploy
bash scripts/deploy.sh --version v1.1.0 --env production --strategy canary --dry-run

# Preview an edge cluster deploy (wave 1 — pilot stores)
bash scripts/deploy.sh --version v1.1.0 --env production --edge --wave 1 --dry-run

# Preview a rollback
bash scripts/deploy.sh --rollback --env production --dry-run
```

---

## Step 10: Monitoring Scripts (Dry Run)

What it does: Pushes deployment events to Dynatrace and Grafana so release markers appear on monitoring dashboards for correlation with metrics.

```bash
# These will gracefully skip when API tokens are not set
bash monitoring/dynatrace-deployment-event.sh --version v1.1.0 --env production
# Output: "WARNING: DYNATRACE_BASE_URL not set — skipping Dynatrace event"

bash monitoring/grafana-annotations.sh --version v1.1.0 --env staging
# Output: "WARNING: GRAFANA_BASE_URL not set — skipping Grafana annotation"

# Post-deploy health check (skips when cluster is not reachable)
bash monitoring/post-deploy-health-check.sh --version v1.1.0 --env staging --observation 0
```

---

## Step 11: Rollout Monitor

What it does: Checks Deployment and DaemonSet health across a namespace. Reports ready/not-ready counts and optionally triggers automatic rollback.

```bash
# Preview the CLI help
bash k8s/rollout-monitor.sh --help

# Would run against a live cluster:
# bash k8s/rollout-monitor.sh --namespace pos-production --all --auto-rollback
```

---

## Step 12: Validate Configs

What it does: Parses all YAML configuration files to catch syntax errors before they break a pipeline.

```bash
make validate-configs
# release-config.yaml: OK
# conventional-commits.yaml: OK
# .gitlab-ci.yml: OK
```

---

## Step 13: Run Unit Tests

```bash
make test
# Runs: test_version.py, test_release_notes.py, test_correlate.py
```

---

## Step 14: Full Dry-Run Release Simulation

Runs the entire release pipeline locally without touching any external system:

```bash
make release-dry-run
# Executes in order:
#   1. version-dry-run     → Calculate version
#   2. changelog           → Generate release notes
#   3. tag-work-items-dry-run → Preview Jira tagging
#   4. qa-handoff-dry-run  → Generate QA artifacts
#   5. report              → Generate release report
```

---

## What's Next?

Once you've kicked the tires, connect real systems:

1. **Fill in `.env`** with real Jira, Slack, Docker registry, and K8s credentials
2. **Run without `--dry-run`** to create real tags and tag real tickets
3. **Include CI templates** in your project's `.gitlab-ci.yml` (see `docs/INTEGRATION.md`)
4. **Import Harness pipeline** from `harness/pipeline.yaml`
5. **Apply K8s manifests** with `kubectl apply -f k8s/namespace-setup.yaml`
