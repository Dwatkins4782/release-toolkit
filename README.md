# POS Platform Release Toolkit

Automated end-to-end release engineering for POS (Point of Sale) platform deployments. Covers semantic versioning, release notes generation, Jira ticket tagging, QA bridging, multi-repo correlation, Helm-based K8s deployments, edge cluster rollouts, and automated release reporting.

## Architecture

```
 ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
 │  GitHub/  │───→│ CI/CD    │───→│ Registry │───→│ K8s      │
 │  GitLab   │    │ Pipeline │    │ (Docker) │    │ Clusters │
 └──────────┘    └────┬─────┘    └──────────┘    └────┬─────┘
                      │                                │
          ┌───────────┼───────────┐          ┌────────┼────────┐
          ▼           ▼           ▼          ▼        ▼        ▼
    ┌──────────┐ ┌──────────┐ ┌────────┐ ┌───────┐ ┌───────┐ ┌──────┐
    │ Version  │ │ Release  │ │ Jira   │ │  QA   │ │Staging│ │ Prod │
    │ Calc     │ │ Notes    │ │ Tagger │ │Bridge │ │Deploy │ │Deploy│
    └──────────┘ └──────────┘ └────────┘ └───────┘ └───────┘ └──────┘
                                                               │
                                                        ┌──────┼──────┐
                                                        ▼      ▼      ▼
                                                     ┌──────┐┌──────┐┌──────┐
                                                     │Edge  ││Edge  ││Edge  │
                                                     │Wave 1││Wave 2││Wave 3│
                                                     │Pilot ││Region││ Full │
                                                     └──────┘└──────┘└──────┘
```

## Quick Start

```bash
# Install dependencies
make install

# Calculate next version from conventional commits
make version

# Generate release notes
make changelog

# Preview Jira ticket tagging (dry run)
make tag-work-items-dry-run

# Full dry-run release simulation
make release-dry-run
```

## Pipeline Stages

| Stage | Description | Tool |
|-------|-------------|------|
| 1. Validate | Lint, test, commit format check | pytest, flake8 |
| 2. Build | Docker build for changed services | Docker |
| 3. Security Scan | Vulnerability + secret scanning | Trivy, Gitleaks |
| 4. Version | Semantic version calculation | version.py |
| 5. Release Notes | Changelog generation (MD/JSON) | release_notes.py |
| 6. Tag Work Items | Jira ticket labeling + transitions | tag_work_items.py |
| 7. QA Bridge | Deploy to QA, test manifest, notify | prepare_qa_handoff.py |
| 8. Deploy Staging | Helm rolling deploy to staging | deploy.sh, Helm |
| 9. Deploy Production | Canary deploy + edge clusters | deploy.sh, Helm |
| 10. Notify | Slack/Teams release announcement | notification.py |

## Key Commands

```bash
# Version Management
make version              # Calculate next semver
make tag                  # Create and push Git tag

# Release Notes
make changelog            # Generate MD + JSON release notes

# Work Item Tracking
make tag-work-items       # Tag Jira tickets with release version

# QA Bridge
make qa-handoff           # Full QA handoff (deploy + manifest + notify)
make qa-manifest          # Generate test manifest only

# Deployment
make deploy-staging       # Deploy to staging (rolling)
make deploy-prod          # Deploy to production (canary)
make deploy-edge          # Deploy to pilot edge stores
make rollback             # Emergency production rollback

# Cross-Repo Intelligence
make correlate            # Multi-repo release correlation

# Monitoring
make health-check         # Post-deploy health validation
make annotate-grafana     # Grafana release annotation
make annotate-dynatrace   # Dynatrace deployment event

# Reporting
make report               # Automated release report with DORA metrics
```

## Configuration

Edit `config/release-config.yaml` to customize:

- Project name and repo URLs
- Jira project key, API endpoint, transition IDs
- Docker registry URLs (dev/staging/prod)
- Kubernetes namespaces and Helm chart paths
- Edge cluster store groups and rollout waves
- Notification channels (Slack/Teams webhooks)
- Feature toggle system endpoint
- Monitoring endpoints (Dynatrace, Grafana)

Copy `config/.env.example` to `.env` and fill in secrets:

```bash
cp config/.env.example .env
# Edit .env with your API tokens
```

## CI/CD Integration

### GitLab CI

Include reusable templates in your project:

```yaml
include:
  - project: 'platform/release-toolkit'
    ref: main
    file: '/ci-templates/release.gitlab-ci.yml'
  - project: 'platform/release-toolkit'
    ref: main
    file: '/ci-templates/qa-bridge.gitlab-ci.yml'
  - project: 'platform/release-toolkit'
    ref: main
    file: '/ci-templates/deploy.gitlab-ci.yml'
```

### GitHub Actions

The `.github/workflows/release.yml` workflow triggers on push to main or manual dispatch with configurable version bump type and dry-run mode.

### Harness CD

Import `harness/pipeline.yaml` into Harness for approval-gated deployments with canary verification and auto-rollback.

## Project Structure

```
release-toolkit/
├── config/              # Central configuration (YAML)
├── scripts/             # Core automation scripts (Python)
│   ├── version.py       # Semantic version calculator
│   ├── release_notes.py # Release notes generator
│   ├── tag_work_items.py# Jira/GitHub issue tagger
│   ├── prepare_qa_handoff.py  # QA bridge
│   ├── correlate_releases.py  # Multi-repo correlator
│   ├── feature_toggles.py     # Feature toggle management
│   ├── release_report.py      # DORA metrics reporting
│   ├── deploy.sh              # K8s deployment + rollback
│   ├── promote_image.sh       # Docker image promotion
│   └── utils/                 # Shared utilities
├── ci-templates/        # Reusable GitLab CI templates
├── k8s/                 # Kubernetes manifests & Helm values
│   ├── helm-values/     # Per-environment value overrides
│   └── edge-cluster/    # Edge (in-store) K8s manifests
├── harness/             # Harness CD pipeline definitions
├── monitoring/          # Dynatrace, Grafana, health checks
├── docs/                # Integration guide, runbook, architecture
└── tests/               # Unit tests
```

## Running Tests

```bash
make test                 # Run all tests
make test-coverage        # Run with coverage report
make lint                 # Lint Python scripts
make validate-configs     # Validate YAML configurations
```

## Documentation

- [Integration Guide](docs/INTEGRATION.md) — Adding release-toolkit to existing projects
- [Runbook](docs/RUNBOOK.md) — Operational runbook for rollout events
- [Architecture](docs/ARCHITECTURE.md) — System architecture and data flow
