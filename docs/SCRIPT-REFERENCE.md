# Script Reference — Detailed Breakdown

Every script in the release-toolkit explained: what it does internally, when to use it, CLI arguments, and real-world use cases.

---

## Table of Contents

### Core Scripts
1. [version.py — Semantic Version Calculator](#1-versionpy--semantic-version-calculator)
2. [release_notes.py — Release Notes Generator](#2-release_notespy--release-notes-generator)
3. [tag_work_items.py — Work Item Tagger](#3-tag_work_itemspy--work-item-tagger)

### QA & Advanced Scripts
4. [prepare_qa_handoff.py — QA Bridge](#4-prepare_qa_handoffpy--qa-bridge)
5. [correlate_releases.py — Multi-Repo Correlator](#5-correlate_releasespy--multi-repo-correlator)
6. [feature_toggles.py — Feature Toggle Manager](#6-feature_togglespy--feature-toggle-manager)
7. [release_report.py — Automated Release Report](#7-release_reportpy--automated-release-report)

### Infrastructure Scripts
8. [promote_image.sh — Docker Image Promotion](#8-promote_imagesh--docker-image-promotion)
9. [deploy.sh — Kubernetes Deployment & Rollback](#9-deploysh--kubernetes-deployment--rollback)

### Monitoring Scripts
10. [dynatrace-deployment-event.sh — Dynatrace Event Push](#10-dynatrace-deployment-eventsh--dynatrace-event-push)
11. [grafana-annotations.sh — Grafana Release Annotation](#11-grafana-annotationssh--grafana-release-annotation)
12. [post-deploy-health-check.sh — Post-Deploy Health Validator](#12-post-deploy-health-checksh--post-deploy-health-validator)

### Kubernetes Scripts
13. [rollout-monitor.sh — Deployment Health Monitor](#13-rollout-monitorsh--deployment-health-monitor)

### Utility Modules
14. [utils/config_loader.py — Configuration Loader](#14-utilsconfig_loaderpy--configuration-loader)
15. [utils/git_utils.py — Git Operations Library](#15-utilsgit_utilspy--git-operations-library)
16. [utils/jira_client.py — Jira REST API Client](#16-utilsjira_clientpy--jira-rest-api-client)
17. [utils/notification.py — Notification Dispatcher](#17-utilsnotificationpy--notification-dispatcher)

---

# Core Scripts

---

## 1. version.py — Semantic Version Calculator

**Location:** `scripts/version.py`
**Language:** Python
**Dependencies:** `semver`, `pyyaml`

### What It Does

Reads your Git commit history since the last tag and automatically calculates the next semantic version based on conventional commit types. It follows the Semantic Versioning 2.0.0 specification:

- **`feat` commits** → bump **minor** (1.0.0 → 1.1.0)
- **`fix` commits** → bump **patch** (1.0.0 → 1.0.1)
- **`!` (breaking change)** → bump **major** (1.0.0 → 2.0.0)
- **`perf`, `chore`, `docs`, `refactor`** → bump **patch**

### How It Works Internally

```
Step 1: Find the latest Git tag (e.g., v1.2.3)
         ↓
Step 2: Get all commits since that tag
         ↓
Step 3: Parse each commit using conventional commit regex:
        r'^(\w+)(?:\(([^)]+)\))?(!)?:\s*(.+)'
        Extracts: type, scope, breaking flag, description
         ↓
Step 4: Determine bump type:
        - Any commit with "!" or "BREAKING CHANGE" → major
        - Any "feat" commit → minor
        - Everything else → patch
         ↓
Step 5: Apply bump to current version → new version
         ↓
Step 6: Write version-summary.json with metadata
        (commit count, features, fixes, breaking changes,
         affected services, contributors)
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--bump` | Bump type: `auto`, `major`, `minor`, `patch` | `auto` |
| `--dry-run` | Calculate without creating a Git tag | `false` |
| `--pre-release` | Pre-release suffix (e.g., `rc.1`, `beta.2`) | none |
| `--output` | Output JSON file path | `version-summary.json` |
| `--config-dir` | Path to config directory | auto-detected |

### When to Use It

- **Every release pipeline** — runs as the first step to determine the version
- **Before tagging** — to preview what the next version would be
- **In CI/CD** — the version output is passed to all downstream stages via dotenv artifacts

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Standard release** | `python scripts/version.py --bump auto` | Merge to main triggers a release. The script reads commit history and determines if it's a major, minor, or patch bump. |
| **Hotfix release** | `python scripts/version.py --bump patch` | Critical bug in production needs an emergency patch. Force a patch bump regardless of commit types. |
| **Preview next version** | `python scripts/version.py --bump auto --dry-run` | Before a sprint ends, the team wants to know what version the next release will be. Dry run calculates without tagging. |
| **Release candidate** | `python scripts/version.py --bump minor --pre-release rc.1` | Feature-complete but not yet validated. Creates v1.3.0-rc.1. QA tests this. When approved, run again without `--pre-release` to create v1.3.0. |
| **Breaking API change** | Commits include `feat(api)!: remove v1 endpoints` | The `!` flag auto-triggers a major bump (v1.x.x → v2.0.0). No manual override needed. |
| **Monorepo multi-service** | `python scripts/version.py --bump auto` | In a monorepo, the script detects which services were affected by looking at commit scopes and changed file paths, and includes that in the version summary. |

---

## 2. release_notes.py — Release Notes Generator

**Location:** `scripts/release_notes.py`
**Language:** Python
**Dependencies:** `pyyaml`, `jinja2`

### What It Does

Transforms raw Git commits into structured, human-readable release notes. Categorizes changes, extracts ticket references, identifies contributors, highlights breaking changes, and outputs in Markdown, JSON, or HTML format.

### How It Works Internally

```
Step 1: Get commits since last tag (via git_utils)
         ↓
Step 2: Parse each commit with conventional commit regex
         ↓
Step 3: Categorize into buckets:
        feat    → "Features"
        fix     → "Bug Fixes"
        perf    → "Performance"
        docs    → "Documentation"
        refactor → "Refactoring"
        chore   → "Chores"
        !       → "Breaking Changes" (additional bucket)
         ↓
Step 4: Extract ticket references:
        Regex: r'[A-Z]+-\d+' → ["POS-1234", "POS-5678"]
         ↓
Step 5: Collect contributors from commit authors
         ↓
Step 6: Generate output:
        Markdown → Formatted .md with sections, ticket links, contributors
        JSON     → Machine-readable for QA bridge consumption
        HTML     → For embedding in emails or dashboards
         ↓
Step 7: Optionally prepend to CHANGELOG.md
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version string | required |
| `--format` | Output format: `md`, `json`, `html` | `md` |
| `--output` | Output file path | stdout |
| `--config-dir` | Path to config directory | auto-detected |

### When to Use It

- **After version calculation** — generates the human-readable changelog
- **For QA handoff** — JSON format feeds into the QA bridge test manifest
- **For stakeholder communication** — Markdown or HTML for release announcements
- **For CHANGELOG.md maintenance** — automatically prepends new entries

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Sprint release notes** | `python scripts/release_notes.py --version v2.1.0 --format md --output release-notes.md` | End of sprint. Product owner and QA need to know what shipped. The Markdown output shows categorized changes with Jira ticket links. |
| **QA automation input** | `python scripts/release_notes.py --version v2.1.0 --format json --output release-notes.json` | QA bridge consumes the JSON to map changes to test suites. The JSON includes scopes, types, and ticket IDs that map to automated test tags. |
| **Stakeholder email** | `python scripts/release_notes.py --version v2.1.0 --format html` | Product marketing needs a formatted summary for the customer-facing release announcement. HTML format can be embedded directly in an email. |
| **Maintaining CHANGELOG** | `python scripts/release_notes.py --version v2.1.0 --format md --output CHANGELOG.md` | The script prepends the new release entry to the existing CHANGELOG.md, keeping a running history of all releases. |
| **Identifying risky changes** | Review the "Breaking Changes" section | Before deploying, the team reviews breaking changes to plan migration steps. The release notes explicitly call out any commit with the `!` flag. |

---

## 3. tag_work_items.py — Work Item Tagger

**Location:** `scripts/tag_work_items.py`
**Language:** Python
**Dependencies:** `requests`, `pyyaml`

### What It Does

Finds all Jira ticket IDs (or GitHub issue numbers) referenced in commit messages since the last tag, then tags each ticket with the release version. It can add labels, set the fix version, add a comment with the release details, and optionally transition the ticket status (e.g., "In Progress" → "Released").

### How It Works Internally

```
Step 1: Get commits since last tag
         ↓
Step 2: Extract ticket IDs using regex:
        Jira:   r'[A-Z]+-\d+'  → ["POS-1234", "POS-5678"]
        GitHub: r'#\d+'         → ["#42", "#108"]
         ↓
Step 3: Deduplicate ticket list
         ↓
Step 4: For each ticket (Jira provider):
        a) Add label: "release-v2.1.0"
        b) Set fix version: "v2.1.0" (creates version if needed)
        c) Add comment: "Included in release v2.1.0 — [pipeline link]"
        d) Transition status → "Released" (if --transition flag set)
         ↓
Step 5: For each issue (GitHub provider):
        a) Add label via `gh issue edit`
        b) Add comment via `gh issue comment`
         ↓
Step 6: Write results to output JSON
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version string | required |
| `--provider` | Ticket system: `jira`, `github` | `jira` |
| `--dry-run` | Preview without making API calls | `false` |
| `--transition` | Also transition ticket status | `false` |
| `--output` | Output JSON file path | `tagged-items.json` |

### When to Use It

- **After release notes are generated** — tags all referenced tickets
- **For release traceability** — auditors can search Jira for "release-v2.1.0" label
- **For automatic status updates** — stakeholders see tickets move to "Released" without manual work

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Standard release tagging** | `python scripts/tag_work_items.py --version v2.1.0` | Release is deployed. All 15 Jira tickets referenced in commits get labeled with "release-v2.1.0", commented with the pipeline link, and assigned fix version v2.1.0. |
| **Preview before tagging** | `python scripts/tag_work_items.py --version v2.1.0 --dry-run` | Release engineer reviews which tickets will be tagged before running the real command. Catches tickets that shouldn't be included. |
| **Tag and transition** | `python scripts/tag_work_items.py --version v2.1.0 --transition` | After production deployment is verified, tickets are automatically moved from "In QA" to "Released". Product owners immediately see the status change. |
| **GitHub Issues** | `python scripts/tag_work_items.py --version v2.1.0 --provider github` | Open-source project uses GitHub Issues instead of Jira. The script uses `gh` CLI to label and comment on issues. |
| **Compliance audit trail** | Run as part of every release pipeline | Banking regulators require proof that every code change is traceable to an approved work item. The tagging creates a permanent audit link between code, ticket, and release. |

---

# QA & Advanced Scripts

---

## 4. prepare_qa_handoff.py — QA Bridge

**Location:** `scripts/prepare_qa_handoff.py`
**Language:** Python
**Dependencies:** `pyyaml`, `requests`, `jinja2`

### What It Does

This is the key bridging script between the development team and the QA/test automation team. It performs a 6-step handoff process:

1. **Generates a test manifest** — maps code changes to test suites by analyzing commit scopes
2. **Deploys to QA environment** — Helm upgrade to the QA namespace
3. **Verifies deployment health** — checks pods are running and healthy
4. **Triggers automated test suites** — sends webhooks to test automation platforms
5. **Captures a feature toggle snapshot** — records which flags are on/off at release time
6. **Notifies the QA team** — sends a Slack/Teams message with artifacts and checklist

### How It Works Internally

```
Step 1: Load release config and commit data
         ↓
Step 2: Generate Test Manifest
        - Parse commits for scopes (e.g., "pos-terminal", "payment-gateway")
        - Map scopes to test suite IDs from config:
          scope "pos-terminal" → suite "POS-REGRESSION-001"
          scope "payment-gateway" → suite "PAYMENT-E2E-002"
        - Identify manual test items (tagged with "manual-test-required")
        - Calculate risk level (high if breaking changes, edge cluster changes)
         ↓
Step 3: Deploy to QA
        - Run: helm upgrade --install pos-platform ./charts/pos-platform
               --namespace pos-qa --values k8s/helm-values/values-qa.yaml
               --set image.tag=v2.1.0 --wait --atomic
         ↓
Step 4: Verify Deployment
        - kubectl rollout status deployment/pos-platform -n pos-qa
        - Check pod readiness and restart counts
         ↓
Step 5: Trigger Test Automation
        - POST webhook to test automation API with test manifest JSON
        - Each scope's test suite gets triggered independently
         ↓
Step 6: Generate QA Checklist (Markdown)
        - Breaking changes section (if any)
        - Manual test items
        - Edge cluster verification items
        - Rollback procedure
        - Sign-off section for QA lead
         ↓
Step 7: Capture Feature Toggle Snapshot
        - Query LaunchDarkly/Split API for current flag states
        - Save as JSON for QA to verify correct toggle behavior
         ↓
Step 8: Notify QA Team
        - Slack block message with:
          • Version and change summary
          • Manual test items count
          • Feature toggles changed
          • Links to pipeline artifacts
          • Rollback command hint
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version string | required |
| `--env` | Target environment | `qa` |
| `--output-dir` | Directory for output artifacts | `./qa-artifacts` |
| `--dry-run` | Generate artifacts only, no deploy/test/notify | `false` |
| `--skip-deploy` | Skip Helm deployment step | `false` |
| `--skip-tests` | Skip test automation trigger | `false` |
| `--skip-notify` | Skip Slack/Teams notification | `false` |

### When to Use It

- **After version bump and release notes** — the third stage of the release pipeline
- **When handing off to QA** — replaces manual "hey QA, it's ready" Slack messages
- **For compliance** — generates a formal test manifest and checklist document

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Full QA handoff** | `python scripts/prepare_qa_handoff.py --version v2.1.0 --env qa` | Sprint release is ready. The script deploys to QA, triggers 12 automated test suites, generates a checklist for 3 manual tests, captures 8 feature toggle states, and pings the QA Slack channel. The QA lead opens the checklist and starts working. |
| **Generate artifacts only** | `python scripts/prepare_qa_handoff.py --version v2.1.0 --env qa --skip-deploy --skip-tests --skip-notify` | Before a release, the release engineer wants to preview what QA will receive. Generates the test manifest and checklist without deploying or notifying anyone. |
| **Hotfix — fast-track QA** | `python scripts/prepare_qa_handoff.py --version v2.1.1 --env qa --skip-tests` | Critical bugfix needs to skip full regression. The script deploys to QA and generates the checklist (marking it as "hotfix — targeted testing only") but skips triggering the full automation suite. QA tests manually. |
| **Edge cluster release** | Check `release-manifest.json` → `edge_clusters_affected: true` | When the manifest detects changes to edge-cluster scopes, it adds edge-specific verification items to the QA checklist: "Verify POS terminal sync after deploy", "Check offline transaction buffer". |

---

## 5. correlate_releases.py — Multi-Repo Correlator

**Location:** `scripts/correlate_releases.py`
**Language:** Python
**Dependencies:** `pyyaml`, `requests`

### What It Does

When your platform spans multiple repositories (e.g., `pos-terminal-service`, `payment-gateway`, `catalog-service`), changes for a single feature often touch multiple repos. This script clones/fetches all configured sibling repos, collects their recent commits, finds shared Jira tickets across repos, and generates a cross-repository correlation report with risk assessment.

### How It Works Internally

```
Step 1: Read repository list from release-config.yaml
        repositories.services: [
          {name: "pos-terminal-service", repo_url: "..."},
          {name: "payment-gateway", repo_url: "..."},
          {name: "catalog-service", repo_url: "..."},
        ]
         ↓
Step 2: For each repo:
        - Clone (or fetch if already cloned) to /tmp/release-toolkit-repos/
        - Find latest tag
        - Get commits since last tag
        - Parse conventional commits
        - Extract ticket IDs
         ↓
Step 3: Correlate tickets across repos:
        shared_tickets = tickets that appear in 2+ repos
        Example: POS-1234 has commits in both pos-terminal-service
                 AND payment-gateway → it's a cross-repo change
         ↓
Step 4: Generate risk assessment:
        LOW:  No breaking changes, no shared tickets, <10 commits
        MED:  Shared tickets exist, or >10 commits, or edge changes
        HIGH: Breaking changes, or shared tickets with edge deploy
         ↓
Step 5: Output correlation report (JSON):
        {
          "release": "v2.1.0",
          "summary": {
            "total_repos": 3,
            "total_commits": 27,
            "shared_tickets": ["POS-1234", "POS-5678"],
            "unique_tickets": ["POS-1111", "POS-2222", ...]
          },
          "repos": [...per-repo details...],
          "risk_assessment": "medium"
        }
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version string | required |
| `--output` | Output JSON file path | `correlation-report.json` |
| `--config-dir` | Path to config directory | auto-detected |

### When to Use It

- **Before deploying a multi-service release** — to understand the blast radius
- **For release planning** — to identify cross-team coordination needs
- **For risk assessment** — shared tickets mean coordinated testing is required

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Sprint release coordination** | `python scripts/correlate_releases.py --version v2.1.0` | 3 teams made changes across 5 repos this sprint. The correlation report shows that POS-1234 (new payment method) has commits in `pos-terminal`, `payment-gateway`, AND `catalog-service`. This flags it as a cross-repo change that needs coordinated testing. |
| **Risk assessment** | Review `risk_assessment` field in report | The report shows "HIGH" risk because repo `payment-gateway` has a breaking API change AND shared tickets with `pos-terminal`. The release manager decides to do a phased rollout (pilot stores first). |
| **Identifying orphaned changes** | Review repos with commits but no shared tickets | `catalog-service` has 3 commits with no shared tickets — these are independent changes that can be released separately, reducing the blast radius. |
| **Release meeting prep** | `make correlate && cat correlation-report.json` | Instead of a 30-minute meeting where each team reports their changes, the report is auto-generated and distributed. Teams only meet to discuss the shared tickets flagged in the report. |

---

## 6. feature_toggles.py — Feature Toggle Manager

**Location:** `scripts/feature_toggles.py`
**Language:** Python
**Dependencies:** `requests`, `pyyaml`

### What It Does

Integrates with LaunchDarkly or Split.io to manage feature flags at release time. Three operations: snapshot the current state (for QA reference), activate flags tagged for this release, or deactivate flags being cleaned up.

### How It Works Internally

```
Step 1: Connect to feature toggle platform API
        (LaunchDarkly, Split, or mock for testing)
         ↓
Step 2: Based on --action:
        "snapshot" → Query all flags, filter by release tag,
                     save state to feature-toggle-snapshot.json
        "activate" → Find flags tagged "release-v2.1.0",
                     enable them in the target environment
        "deactivate" → Find flags tagged for cleanup,
                       disable them
         ↓
Step 3: Output results
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version string | required |
| `--action` | `snapshot`, `activate`, `deactivate` | `snapshot` |
| `--env` | Target environment for toggle changes | from config |
| `--config-dir` | Path to config directory | auto-detected |

### When to Use It

- **During QA handoff** — snapshot tells QA which flags are on/off
- **After production deploy** — activate new feature flags
- **During cleanup sprints** — deactivate and remove old flags

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **QA reference snapshot** | `python scripts/feature_toggles.py --version v2.1.0 --action snapshot` | QA needs to know which features are behind flags. The snapshot shows: "nfc_payments: ON in QA, OFF in prod", "loyalty_v2: OFF everywhere". QA tests with the correct toggle states. |
| **Post-deploy activation** | `python scripts/feature_toggles.py --version v2.1.0 --action activate` | After v2.1.0 is live in production and verified, the release engineer activates the 3 feature flags tagged for this release. NFC payments go live for all users. |
| **Flag cleanup** | `python scripts/feature_toggles.py --version v2.1.0 --action deactivate` | Old flags from v1.8.0 are fully rolled out and the code paths have been cleaned up. Deactivate the flags before removing them from the codebase. |
| **Incident rollback** | `python scripts/feature_toggles.py --version v2.1.0 --action deactivate` | A feature behind a flag is causing errors. Instead of rolling back the entire deployment, deactivate just that flag. Users immediately stop hitting the problematic code path. |

---

## 7. release_report.py — Automated Release Report

**Location:** `scripts/release_report.py`
**Language:** Python
**Dependencies:** `pyyaml`, `tabulate`

### What It Does

Generates an automated release report designed to replace large release coordination meetings. Includes an executive summary, DORA metrics (Deployment Frequency, Lead Time for Changes, Change Failure Rate, Mean Time to Recovery), change breakdown by type, and a deployment readiness checklist.

### How It Works Internally

```
Step 1: Collect release metadata
        - Version, date, commit count, contributors
         ↓
Step 2: Calculate DORA Metrics
        - Deployment Frequency: releases per week (from tag history)
        - Lead Time: time from first commit to tag creation
        - Change Failure Rate: % of releases with rollbacks
          (from tag annotations or Jira "rollback" labels)
        - MTTR: average time between failure and recovery
         ↓
Step 3: Categorize changes
        - Count features, fixes, perf improvements, chores
        - Flag breaking changes
        - List affected services
         ↓
Step 4: Build deployment readiness checklist
        ✅ All tests passing
        ✅ No critical security vulnerabilities
        ✅ Release notes reviewed
        ✅ QA sign-off received
        ⬜ Change request approved
        ⬜ Rollback plan documented
         ↓
Step 5: Output Markdown report
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version string | required |
| `--format` | Output format: `md`, `json` | `md` |
| `--output` | Output file path | stdout |

### When to Use It

- **Before release meetings** — distribute the report instead of presenting slides
- **For DORA metric tracking** — automated calculation every release
- **For compliance** — readiness checklist serves as a deployment approval artifact

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Replace coordination meeting** | `python scripts/release_report.py --version v2.1.0 --format md --output release-report.md` | Instead of a 45-minute meeting with 15 people, the report is auto-generated and posted to Confluence/Slack. Teams review async. Only blockers require a sync discussion. |
| **DORA metric dashboard** | Run every release, track metrics over time | Engineering leadership tracks DORA metrics quarterly. The report shows deployment frequency improved from 1/week to 3/week after adopting the toolkit. Lead time dropped from 5 days to 1.5 days. |
| **Audit documentation** | Archive reports alongside release artifacts | SOX auditors request evidence of release governance. The archived reports show that every release had a readiness checklist, DORA metrics, and documented change breakdown. |

---

# Infrastructure Scripts

---

## 8. promote_image.sh — Docker Image Promotion

**Location:** `scripts/promote_image.sh`
**Language:** Bash
**Dependencies:** Docker CLI, `skopeo` (optional)

### What It Does

Promotes Docker images from one registry to another (e.g., from staging to production) with SHA digest verification. Instead of rebuilding images for production (which could introduce drift), this script copies the exact tested image to the production registry.

### How It Works Internally

```
Step 1: Read source and target registries from config
        dev     → registry.dev.myorg.com
        staging → registry.staging.myorg.com
        prod    → registry.prod.myorg.com
         ↓
Step 2: For each service (or --all):
        a) Pull image from source: docker pull staging/pos-api:v2.1.0
        b) Get SHA digest: docker inspect --format='{{.Id}}'
        c) Retag: docker tag staging/pos-api:v2.1.0 prod/pos-api:v2.1.0
        d) Push: docker push prod/pos-api:v2.1.0
        e) Verify: compare digest at source and destination
         ↓
Step 3: Report promotion summary
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Image tag to promote | required |
| `--from` | Source environment: `dev`, `staging` | required |
| `--to` | Target environment: `staging`, `prod` | required |
| `--service` | Specific service name | all services |
| `--all` | Promote all configured services | `false` |
| `--dry-run` | Preview without pulling/pushing | `false` |

### When to Use It

- **After QA approval** — promote tested images from staging to prod
- **For image integrity** — digest verification ensures no tampering
- **In the pipeline** — between the staging deploy and production deploy stages

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Standard promotion** | `bash scripts/promote_image.sh --version v2.1.0 --from staging --to prod --all` | QA has signed off on staging. All 4 service images are promoted to the production registry. Digest verification confirms each image is byte-identical. |
| **Single service hotfix** | `bash scripts/promote_image.sh --version v2.1.1 --from staging --to prod --service payment-gateway` | Only the payment gateway needs a hotfix. Promote just that one service image, leaving others untouched. |
| **Preview promotion** | `bash scripts/promote_image.sh --version v2.1.0 --from staging --to prod --all --dry-run` | Before promoting, check which images will be moved and verify they exist in the source registry. |
| **Dev → Staging** | `bash scripts/promote_image.sh --version v2.1.0-rc.1 --from dev --to staging --all` | Pre-release candidate images are promoted from dev to staging for integration testing. |

---

## 9. deploy.sh — Kubernetes Deployment & Rollback

**Location:** `scripts/deploy.sh`
**Language:** Bash
**Dependencies:** `helm`, `kubectl`

### What It Does

Single-command deployment and rollback for the POS platform. Handles environment selection, Helm chart upgrades, deployment strategy (rolling/canary/blue-green), pre-deploy safety checks (production confirmation gate), post-deploy health verification, and edge cluster wave-based rollouts.

### How It Works Internally

```
Step 1: Parse arguments and resolve environment
        --env staging → namespace=pos-staging, values=values-staging.yaml
        --env production → namespace=pos-production, values=values-production.yaml
         ↓
Step 2: Pre-deploy checks
        - Verify kubectl can reach the cluster
        - Verify namespace exists
        - Production gate: require explicit confirmation
         ↓
Step 3: Execute deployment strategy
        "rolling" → helm upgrade --install --wait --atomic
        "canary"  → deploy 1 canary replica, monitor, then full rollout
        "blue-green" → deploy to inactive color, switch route
         ↓
Step 4: Post-deploy verification
        - kubectl rollout status (wait for all pods ready)
        - Check for crash loops (restartCount < threshold)
        - Health endpoint check (HTTP 200)
         ↓
Step 5: Edge cluster deployment (if --edge)
        - Read store groups from config
        - Deploy wave by wave (--wave 1/2/3)
        - Each wave runs rollout monitor after deploy
         ↓
Step 6: Rollback (if --rollback)
        - helm rollback <release> 0 --wait
        - Verify rollback succeeded
        - Notify team via Slack
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version to deploy | required (unless rollback) |
| `--env` | Target: `dev`, `staging`, `qa`, `production` | required |
| `--strategy` | Deploy strategy: `rolling`, `canary`, `blue-green` | `rolling` |
| `--rollback` | Rollback to previous revision | `false` |
| `--edge` | Deploy to edge clusters | `false` |
| `--wave` | Edge rollout wave: `1`, `2`, `3` | `1` |
| `--dry-run` | Preview without deploying | `false` |

### When to Use It

- **In the pipeline** — called by CI/CD stages for staging and production
- **Manual deploys** — when you need to deploy outside the pipeline
- **Emergency rollback** — single command to revert production

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Deploy to staging** | `bash scripts/deploy.sh --version v2.1.0 --env staging --strategy rolling` | Standard staging deployment. Helm rolling upgrade with `--atomic` (auto-rollback if unhealthy). Waits for all pods to be ready. |
| **Production canary** | `bash scripts/deploy.sh --version v2.1.0 --env production --strategy canary` | Deploy 1 canary pod (10% traffic), monitor for 2 minutes, verify health, then full rollout. If canary fails, auto-rollback. |
| **Edge pilot stores** | `bash scripts/deploy.sh --version v2.1.0 --env production --edge --wave 1` | Deploy to 5 pilot stores first. Monitor for 30 minutes before proceeding to wave 2 (regional). |
| **Emergency rollback** | `bash scripts/deploy.sh --rollback --env production` | Production error detected. Single command rolls back to the previous Helm revision. Slack notification sent automatically. |
| **Full edge rollout** | `bash scripts/deploy.sh --version v2.1.0 --env production --edge --wave 2` then `--wave 3` | After pilot stores are verified, expand to regional stores (wave 2) and then all stores (wave 3). |

---

# Monitoring Scripts

---

## 10. dynatrace-deployment-event.sh — Dynatrace Event Push

**Location:** `monitoring/dynatrace-deployment-event.sh`
**Language:** Bash
**Dependencies:** `curl`

### What It Does

Pushes a CUSTOM_DEPLOYMENT event to the Dynatrace Events API v2. This creates a deployment marker visible across all Dynatrace dashboards, allowing you to correlate release times with error rate spikes, latency changes, and other metrics.

### How It Works Internally

```
Step 1: Build entity selector
        - Default: type(PROCESS_GROUP)
        - With --services: tag("service:pos-api"),tag("service:payment-gateway")
         ↓
Step 2: Build event payload (JSON)
        {
          "eventType": "CUSTOM_DEPLOYMENT",
          "title": "Release v2.1.0 deployed to production",
          "entitySelector": "type(PROCESS_GROUP),tag(\"service:pos-api\")",
          "properties": {
            "dt.event.deployment.version": "v2.1.0",
            "Environment": "production",
            "Pipeline URL": "https://gitlab.com/...",
            ...
          }
        }
         ↓
Step 3: POST to Dynatrace Events API
        https://abc.live.dynatrace.com/api/v2/events/ingest
         ↓
Step 4: Verify HTTP 2xx response
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version | required |
| `--env` | Environment name | `production` |
| `--services` | Comma-separated service names | all |
| `--pipeline-url` | CI/CD pipeline URL | auto-detected from CI vars |

### When to Use It

- **Immediately after deployment** — creates a visible marker on all dashboards
- **For incident investigation** — "did the error spike start at the last deploy?"

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Standard deploy marker** | `bash monitoring/dynatrace-deployment-event.sh --version v2.1.0 --env production` | After deploying, push an event to Dynatrace. The operations team sees a deployment marker on their latency dashboard and can correlate any P99 spike with the exact release time. |
| **Service-specific marker** | `bash monitoring/dynatrace-deployment-event.sh --version v2.1.0 --env production --services "payment-gateway"` | Only the payment gateway was updated. The deployment event is scoped to just that service's process group in Dynatrace. |
| **Incident root cause** | Review Dynatrace deployment events timeline | During a production incident, the on-call engineer sees that a deployment happened 10 minutes before the error rate spiked. The event contains the pipeline URL for quick investigation. |

---

## 11. grafana-annotations.sh — Grafana Release Annotation

**Location:** `monitoring/grafana-annotations.sh`
**Language:** Bash
**Dependencies:** `curl`

### What It Does

Creates a Grafana annotation at the current timestamp, tagged with the release version and environment. Annotations appear as vertical lines on Grafana time-series dashboards, marking exactly when a deployment happened.

### How It Works Internally

```
Step 1: Build tag array: ["deployment", "release", "production", "v2.1.0"]
         ↓
Step 2: Build annotation payload
        {
          "time": 1705612800000,      // millisecond epoch
          "tags": ["deployment", "release", "production", "v2.1.0"],
          "text": "Release v2.1.0 deployed to production\n<a href='...'>View Pipeline</a>"
        }
         ↓
Step 3: POST to Grafana Annotations API
        https://grafana.myorg.com/api/annotations
         ↓
Step 4: Annotation visible on all dashboards that match the tags
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version | required |
| `--env` | Environment name | `production` |
| `--dashboard-id` | Scope to specific dashboard | all dashboards |
| `--tags` | Additional comma-separated tags | `deployment,release` |

### When to Use It

- **After every deployment** — creates the annotation for metrics correlation
- **For capacity planning** — see how deployments affect resource utilization over time

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Global annotation** | `bash monitoring/grafana-annotations.sh --version v2.1.0 --env production` | The annotation appears on every Grafana dashboard. The SRE team sees the deployment marker on CPU, memory, error rate, and latency panels simultaneously. |
| **Dashboard-scoped** | `bash monitoring/grafana-annotations.sh --version v2.1.0 --env staging --dashboard-id 42` | Only annotate the POS Platform staging dashboard. Keeps other dashboards clean from staging noise. |

---

## 12. post-deploy-health-check.sh — Post-Deploy Health Validator

**Location:** `monitoring/post-deploy-health-check.sh`
**Language:** Bash
**Dependencies:** `kubectl`, `curl`, `bc` (optional)

### What It Does

Waits for a configurable observation window after deployment, then runs three health checks in sequence: Kubernetes deployment status, application health endpoint, and Dynatrace error rate query. If any check fails and `--auto-rollback` is set, it automatically triggers a Helm rollback and notifies the team.

### How It Works Internally

```
Step 1: Wait for observation window (default 180 seconds)
        "Let the deployment settle before checking metrics"
         ↓
Step 2: Check Kubernetes deployment health
        - kubectl get deployment → desired vs ready replicas
        - Check for pod restarts > threshold (3)
         ↓
Step 3: Check application health endpoint
        - curl https://pos-api.myorg.com/health/ready
        - Retry up to 3 times with 5-second delay
        - Expect HTTP 200
         ↓
Step 4: Check Dynatrace error rate (if configured)
        - Query Dynatrace metrics API for service error rate
        - Compare against threshold (default 5%)
         ↓
Step 5: If any check fails:
        With --auto-rollback:
          → helm rollback → notify Slack → exit 1
        Without --auto-rollback:
          → print rollback command → exit 1
         ↓
Step 6: If all pass: exit 0
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--version` | Release version | required |
| `--env` | Environment | `production` |
| `--observation` | Wait time in seconds before checking | `180` |
| `--threshold` | Error rate threshold (percent) | `5` |
| `--auto-rollback` | Auto-rollback on failure | `false` |
| `--helm-release` | Helm release name | `pos-platform` |
| `--namespace` | Kubernetes namespace | auto from env |
| `--health-endpoint` | Health URL to check | auto from env |

### When to Use It

- **After every production deploy** — the final safety net
- **In the pipeline** — runs as a post-deploy stage with auto-rollback
- **For canary validation** — use a shorter observation window (30–60s) during canary phase

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Production safety net** | `bash monitoring/post-deploy-health-check.sh --version v2.1.0 --env production --auto-rollback` | After deploying, wait 3 minutes, then check pods (all 3/3 ready), health endpoint (HTTP 200), and Dynatrace error rate (2.1%, below 5% threshold). All pass — deployment is confirmed healthy. |
| **Fast canary check** | `bash monitoring/post-deploy-health-check.sh --version v2.1.0 --env production --observation 60 --threshold 3` | During canary phase, use a 60-second window and a tighter 3% error threshold. Catches problems faster. |
| **Auto-rollback on failure** | `bash monitoring/post-deploy-health-check.sh --version v2.1.0 --env production --auto-rollback` | 3 minutes after deploy, error rate is 12% (threshold is 5%). The script auto-triggers `helm rollback`, sends a Slack alert, and exits with error code. The pipeline marks the stage as failed. |
| **Staging validation** | `bash monitoring/post-deploy-health-check.sh --version v2.1.0 --env staging --observation 60` | Lighter check for staging — shorter observation window, no auto-rollback. Just report pass/fail. |

---

# Kubernetes Scripts

---

## 13. rollout-monitor.sh — Deployment Health Monitor

**Location:** `k8s/rollout-monitor.sh`
**Language:** Bash
**Dependencies:** `kubectl`, `helm`

### What It Does

Monitors the health of Kubernetes Deployments and DaemonSets in a namespace. Reports ready/not-ready counts, checks for excessive pod restarts, and optionally triggers automatic rollback if unhealthy workloads are detected.

### How It Works Internally

```
Step 1: Parse arguments (namespace, deployment name, or --all)
         ↓
Step 2: For each Deployment in namespace:
        - kubectl get deployment → desired vs ready replicas
        - Report: "✓ pos-api: 3/3 ready" or "✗ pos-api: 1/3 ready"
         ↓
Step 3: For each DaemonSet in namespace:
        - kubectl get daemonset → desired vs ready pods
        - Report: "✓ pos-terminal-agent: 8/8 ready"
         ↓
Step 4: Check pod restart counts
        - Warn if any pod has > 0 restarts
         ↓
Step 5: Summary
        "All workloads healthy" → exit 0
        "Unhealthy detected" → exit 1
         ↓
Step 6: If --auto-rollback and unhealthy:
        - helm rollback → exit
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--namespace, -n` | Kubernetes namespace | `pos-production` |
| `--deployment, -d` | Specific deployment to check | none |
| `--all` | Check all deployments + daemonsets | `false` |
| `--timeout, -t` | Rollout wait timeout (seconds) | `300` |
| `--auto-rollback` | Trigger rollback on failure | `false` |
| `--helm-release` | Helm release name for rollback | `pos-platform` |

### When to Use It

- **After deployment** — verify everything is healthy
- **In a CronJob** — continuous monitoring (see `k8s/edge-cluster/edge-rollout-monitor.yaml`)
- **Before promoting to next wave** — verify pilot stores before expanding

### Use Cases

| Use Case | Command | Scenario |
|----------|---------|----------|
| **Post-deploy check** | `bash k8s/rollout-monitor.sh --namespace pos-production --all` | After deploying, check that all 3 deployments and 1 daemonset are healthy. Output shows "4/4 healthy". |
| **Single deployment** | `bash k8s/rollout-monitor.sh --namespace pos-staging --deployment pos-api` | Check only the API deployment, ignoring other workloads in the namespace. |
| **Edge cluster health** | `bash k8s/rollout-monitor.sh --namespace pos-edge --all --auto-rollback` | Monitor edge cluster after wave 1 deployment. If the DaemonSet only has 5/8 pods ready, auto-rollback is triggered. |
| **Continuous monitoring** | Apply `k8s/edge-cluster/edge-rollout-monitor.yaml` CronJob | A CronJob runs this check every 5 minutes, pushes metrics to Prometheus Pushgateway, and alerts Slack if any workload is unhealthy. |

---

# Utility Modules

---

## 14. utils/config_loader.py — Configuration Loader

**Location:** `scripts/utils/config_loader.py`
**Language:** Python

### What It Does

Loads `release-config.yaml`, merges values with environment variables (`.env` file), and provides a unified configuration object to all other scripts. Searches parent directories for the config folder so scripts work from any subdirectory.

### Key Functions

| Function | Purpose |
|----------|---------|
| `load_config()` | Loads and returns the full config dict |
| `get_config_value(path)` | Dot-notation access: `get_config_value("jira.base_url")` |
| `find_config_dir()` | Walks up the directory tree to find `config/` |
| `_resolve_env_vars()` | Replaces `${ENV_VAR}` placeholders with actual values |

### When to Use It

- **In every other script** — imported as the first step to get configuration
- **When adding new scripts** — use `load_config()` instead of hardcoding values

---

## 15. utils/git_utils.py — Git Operations Library

**Location:** `scripts/utils/git_utils.py`
**Language:** Python

### What It Does

Wraps common Git operations used across the toolkit. All Git interactions go through this module for consistency and error handling.

### Key Functions

| Function | Purpose |
|----------|---------|
| `run_git(cmd)` | Execute a git command and return output |
| `get_latest_tag()` | Find the most recent semver tag |
| `get_commits_since_tag(tag)` | List all commits since a tag |
| `parse_conventional_commit(msg)` | Regex parse: returns `{type, scope, breaking, description}` |
| `get_changed_files(since_tag)` | List files changed since a tag |
| `detect_affected_services(files)` | Map changed files to service names |
| `create_tag(version, message)` | Create and push an annotated Git tag |
| `get_contributors(since_tag)` | Unique commit authors since tag |
| `get_diff_stats(since_tag)` | Insertions/deletions summary |

### When to Use It

- **In version.py** — to get commits and determine bump type
- **In release_notes.py** — to categorize commits
- **In any new script** — that needs Git commit data

---

## 16. utils/jira_client.py — Jira REST API Client

**Location:** `scripts/utils/jira_client.py`
**Language:** Python

### What It Does

A Jira REST API client with rate limiting and retry logic. Handles all Jira operations: reading issues, adding labels, posting comments, transitioning status, and managing fix versions.

### Key Methods

| Method | Purpose |
|--------|---------|
| `get_issue(key)` | Fetch issue details |
| `add_label(key, label)` | Add a label to an issue |
| `add_comment(key, body)` | Post a comment |
| `transition_issue(key, transition_id)` | Move issue to new status |
| `set_fix_version(key, version)` | Set fix version field |
| `_ensure_version(version)` | Create Jira version if it doesn't exist |
| `tag_release(key, version)` | Convenience: label + comment + fix version |
| `get_issues_in_sprint(sprint_id)` | Get all issues in a sprint |

### When to Use It

- **In tag_work_items.py** — for tagging tickets
- **In correlate_releases.py** — for looking up ticket details
- **In any script that needs Jira data**

---

## 17. utils/notification.py — Notification Dispatcher

**Location:** `scripts/utils/notification.py`
**Language:** Python

### What It Does

Sends rich notifications to Slack (Block Kit) and Microsoft Teams (Adaptive Cards). Pre-built message formatters for release deployments, QA handoffs, and rollback alerts.

### Key Functions

| Function | Purpose |
|----------|---------|
| `send_slack(webhook_url, payload)` | Send a Slack webhook message |
| `send_teams(webhook_url, payload)` | Send a Teams webhook message |
| `format_release_notification(version, env, ...)` | Build a release announcement message |
| `format_qa_handoff_notification(version, ...)` | Build a QA handoff message with manual test items, toggle changes, and action buttons |
| `format_rollback_notification(version, env, ...)` | Build a rollback alert message |

### When to Use It

- **In prepare_qa_handoff.py** — to notify the QA team
- **In deploy.sh** (via CI/CD templates) — to announce deployments
- **In any script that needs team notifications**
