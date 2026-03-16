# Operational Runbook — POS Platform Releases

Operational procedures for release rollout, validation, rollback, and incident response.

## Pre-Release Checklist

| # | Check | Command | Owner |
|---|-------|---------|-------|
| 1 | All tests passing | `make test` | Dev |
| 2 | Security scan clean | Trivy/Gitleaks in pipeline | DevOps |
| 3 | Version calculated | `make version` | Release Eng |
| 4 | Release notes reviewed | `make changelog` | PM / Release Eng |
| 5 | Jira tickets tagged | `make tag-work-items-dry-run` | Release Eng |
| 6 | Feature toggles verified | `make toggle-snapshot` | Dev |
| 7 | QA handoff complete | `make qa-handoff` | QA Lead |
| 8 | Staging deployment verified | `make deploy-staging` | Release Eng |
| 9 | Cross-repo correlation reviewed | `make correlate` | Release Eng |
| 10 | Change request approved | ServiceNow / Slack | Change Mgmt |

## Standard Release Procedure

### Phase 1: Version & Notes (Automated)

Pipeline stages 1–5 run automatically on merge to main:
1. Validate (lint + test)
2. Build Docker images for changed services
3. Security scan (Trivy + Gitleaks)
4. Calculate semantic version from conventional commits
5. Generate release notes (Markdown + JSON)

### Phase 2: QA Bridge (Automated)

Pipeline stage 7:
1. Deploy to QA namespace via Helm
2. Generate test manifest (JSON) mapping changes to test suites
3. Trigger automated test suite via webhook
4. Generate QA checklist (Markdown)
5. Notify QA team via Slack with artifacts links

### Phase 3: Staging Deploy (Automated)

Pipeline stage 8:
1. Helm rolling upgrade to staging namespace
2. Wait for rollout completion (timeout: 600s)
3. Run smoke tests against staging endpoints
4. Push Dynatrace deployment event
5. Create Grafana annotation

### Phase 4: Production Deploy (Manual Gate)

Pipeline stage 9 requires manual approval:

```bash
# Option A: Via pipeline UI — click "Play" on deploy:production job
# Option B: Via CLI
make deploy-prod
```

Production deployment follows canary strategy:
1. Deploy canary (10% traffic) — 1 replica
2. Monitor canary for 120 seconds
3. Verify canary pod health
4. Full rolling upgrade to all replicas
5. Clean up canary deployment
6. Post-deploy health check

### Phase 5: Edge Cluster Rollout (Manual, Phased)

Edge clusters deploy in 3 waves:

```bash
# Wave 1: Pilot stores (5-10 stores)
make deploy-edge

# Monitor pilot stores for 30+ minutes
make health-check

# Wave 2: Regional expansion
make deploy-edge-full   # Waves 2 + 3
```

| Wave | Scope | Stores | Wait |
|------|-------|--------|------|
| 1 | Pilot | 5–10 | 30 min |
| 2 | Regional | 50–100 | 2 hours |
| 3 | Full rollout | All | — |

## Rollback Procedures

### Standard Rollback (Production)

```bash
# Helm rollback to previous revision
make rollback

# Verify rollback
kubectl rollout status deployment/pos-platform -n pos-production
```

### Edge Cluster Rollback

```bash
# Rollback all edge clusters
bash scripts/deploy.sh --rollback --env production --edge

# Verify edge health
bash k8s/rollout-monitor.sh --namespace pos-edge --all
```

### Emergency Rollback (Pipeline)

1. Go to GitLab CI/CD → Pipelines
2. Find latest pipeline
3. Click "Play" on `rollback:production` job
4. Monitor Slack for rollback notification

### Rollback Triggers

Automatic rollback triggers if:
- Canary pod health check fails during deployment
- Error rate exceeds 5% threshold (Dynatrace)
- Health endpoint returns non-200 for 3 consecutive checks

## Monitoring During Rollout

### Key Dashboards

| Dashboard | URL | What to Watch |
|-----------|-----|---------------|
| Grafana: POS Overview | grafana.myorg.com/d/pos-overview | Error rate, latency |
| Dynatrace: Services | abc.live.dynatrace.com/ui/services | Failure rate |
| Grafana: Edge Clusters | grafana.myorg.com/d/edge-health | Pod health, sync status |

### Key Metrics to Monitor

| Metric | Threshold | Action |
|--------|-----------|--------|
| Error rate (5xx) | > 5% | Investigate, rollback if sustained |
| P99 latency | > 2x baseline | Investigate |
| Pod restarts | > 3 in 5 min | Investigate |
| Edge sync failures | > 10% stores | Pause wave rollout |

### Health Check Commands

```bash
# K8s deployment status
kubectl rollout status deployment/pos-platform -n pos-production

# Pod health
kubectl get pods -n pos-production -l app=pos-platform

# Post-deploy automated check
make health-check

# Edge rollout status
bash k8s/rollout-monitor.sh --namespace pos-edge --all
```

## Incident Response During Failed Release

### Severity Classification

| Severity | Definition | Response |
|----------|-----------|----------|
| SEV-1 | Production outage, POS transactions blocked | Immediate rollback |
| SEV-2 | Degraded performance, partial functionality | Investigate then rollback |
| SEV-3 | Minor issue, workaround available | Fix forward or rollback |

### SEV-1 Response

1. **Immediate**: Trigger rollback — `make rollback`
2. **Notify**: Slack alert auto-sent on rollback
3. **Verify**: Confirm rollback successful with health checks
4. **Edge**: If edge clusters affected — `bash scripts/deploy.sh --rollback --env production --edge`
5. **Postmortem**: Schedule within 48 hours

### Communication Template

```
RELEASE INCIDENT: [VERSION]
Status: [INVESTIGATING / MITIGATING / RESOLVED]
Impact: [Description of user impact]
Timeline:
  - [HH:MM] Release deployed
  - [HH:MM] Issue detected
  - [HH:MM] Rollback initiated
  - [HH:MM] Rollback complete
Next steps: [Action items]
```
