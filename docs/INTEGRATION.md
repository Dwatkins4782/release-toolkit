# Integration Guide

Step-by-step guide for adding the release-toolkit to an existing project.

## Prerequisites

- Python 3.11+
- Git with conventional commit format
- Access to Jira (or GitHub Issues)
- Kubernetes cluster with Helm 3
- CI/CD platform (GitLab CI or GitHub Actions)

## Step 1: Add as Git Submodule or Clone

### Option A: Git Submodule (recommended for GitLab)

```bash
git submodule add https://github.com/myorg/release-toolkit.git tools/release-toolkit
git submodule update --init
```

### Option B: Clone to Tools Directory

```bash
git clone https://github.com/myorg/release-toolkit.git tools/release-toolkit
echo "tools/release-toolkit" >> .gitignore
```

### Option C: Use CI Templates Only (GitLab)

```yaml
# In your .gitlab-ci.yml
include:
  - project: 'platform/release-toolkit'
    ref: main
    file:
      - '/ci-templates/release.gitlab-ci.yml'
      - '/ci-templates/qa-bridge.gitlab-ci.yml'
      - '/ci-templates/deploy.gitlab-ci.yml'
      - '/ci-templates/rollback.gitlab-ci.yml'
      - '/ci-templates/notify.gitlab-ci.yml'
```

## Step 2: Configure

1. Copy the config templates:

```bash
cp tools/release-toolkit/config/release-config.yaml config/release-config.yaml
cp tools/release-toolkit/config/conventional-commits.yaml config/conventional-commits.yaml
cp tools/release-toolkit/config/.env.example .env
```

2. Edit `config/release-config.yaml`:
   - Set your project name and repo URLs
   - Configure Jira project key and API endpoint
   - Set Docker registry URLs for each environment
   - Define Kubernetes namespaces
   - Add edge cluster store groups if applicable

3. Set environment variables (`.env` or CI/CD secrets):
   - `JIRA_API_TOKEN`, `JIRA_USER_EMAIL`, `JIRA_BASE_URL`
   - `SLACK_WEBHOOK_URL`
   - `DOCKER_REGISTRY_DEV`, `DOCKER_REGISTRY_PROD`
   - `DYNATRACE_API_TOKEN`, `GRAFANA_API_KEY`

## Step 3: Add to GitLab CI Pipeline

```yaml
stages:
  - validate
  - version
  - release-notes
  - tag-work-items
  - qa-bridge
  - deploy-staging
  - deploy-production
  - notify

include:
  - project: 'platform/release-toolkit'
    ref: main
    file: '/ci-templates/release.gitlab-ci.yml'

version:calculate:
  extends: .release_version

release-notes:generate:
  extends: .release_notes
  needs:
    - job: version:calculate
      artifacts: true

tag-items:
  extends: .release_tag_work_items
  needs:
    - job: version:calculate
      artifacts: true
```

## Step 4: Add to GitHub Actions

Copy `.github/workflows/release.yml` to your project, or reference the reusable workflow:

```yaml
name: Release
on:
  push:
    branches: [main]
jobs:
  release:
    uses: myorg/release-toolkit/.github/workflows/release.yml@main
    secrets: inherit
```

## Step 5: Add Helm Values

Copy environment-specific Helm values to your project:

```bash
mkdir -p k8s/helm-values
cp tools/release-toolkit/k8s/helm-values/values-*.yaml k8s/helm-values/
```

Edit each values file for your service configuration.

## Step 6: Verify

```bash
# Install dependencies
pip install -r tools/release-toolkit/requirements.txt

# Validate configs
python -c "import yaml; yaml.safe_load(open('config/release-config.yaml'))"

# Dry run version calculation
python tools/release-toolkit/scripts/version.py --bump auto --dry-run

# Dry run QA handoff
python tools/release-toolkit/scripts/prepare_qa_handoff.py \
  --version v1.0.0 --env qa --skip-deploy --skip-tests --skip-notify \
  --output-dir ./qa-artifacts
```

## Customization

### Custom Commit Types

Edit `config/conventional-commits.yaml` to add custom commit types:

```yaml
types:
  deploy:
    bump: patch
    section: "Deployments"
  hotfix:
    bump: patch
    section: "Hot Fixes"
```

### Custom Notification Templates

Override notification formatting by creating a `scripts/utils/notification_custom.py` that imports from the base module.

### Edge Cluster Configuration

For POS terminal deployments, configure store groups in `release-config.yaml`:

```yaml
edge_clusters:
  store_groups:
    - name: us-east-pilot
      wave: 1
      stores: ["STORE-0001", "STORE-0002"]
    - name: us-east-regional
      wave: 2
      pattern: "us-east-*"
```
