# System Architecture

Technical architecture of the release-toolkit pipeline, component interactions, and data flow.

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RELEASE PIPELINE                              │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ VALIDATE  │─→│  BUILD   │─→│ SECURITY │─→│ VERSION  │            │
│  │ lint+test │  │ Docker   │  │ Trivy    │  │ semver   │            │
│  └──────────┘  └──────────┘  │ Gitleaks │  │ calc     │            │
│                               └──────────┘  └────┬─────┘            │
│                                                   │                  │
│                    ┌──────────────────────────────┼──────┐           │
│                    ▼                              ▼      ▼           │
│              ┌──────────┐               ┌──────────┐ ┌────────┐     │
│              │ RELEASE  │               │ TAG WORK │ │  QA    │     │
│              │ NOTES    │               │ ITEMS    │ │ BRIDGE │     │
│              │ md+json  │               │ Jira     │ │ deploy │     │
│              └──────────┘               └──────────┘ │ test   │     │
│                                                      │ notify │     │
│                                                      └───┬────┘     │
│                                                          │          │
│                    ┌─────────────────────────────────────┤          │
│                    ▼                                     ▼          │
│              ┌──────────┐                          ┌──────────┐    │
│              │ DEPLOY   │                          │ DEPLOY   │    │
│              │ STAGING  │────── Manual Gate ───────→│PRODUCTION│    │
│              │ rolling  │                          │ canary   │    │
│              └──────────┘                          └────┬─────┘    │
│                                                         │          │
│                                          ┌──────────────┤          │
│                                          ▼              ▼          │
│                                    ┌──────────┐   ┌──────────┐    │
│                                    │  EDGE    │   │ NOTIFY   │    │
│                                    │ CLUSTERS │   │ Slack    │    │
│                                    │ wave 1-3 │   │ Teams    │    │
│                                    └──────────┘   └──────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Interaction

```
┌──────────────────────────────────────────────────────────────────┐
│                     RELEASE-TOOLKIT COMPONENTS                    │
│                                                                   │
│  ┌─────────────────────┐         ┌─────────────────────┐        │
│  │   config/            │         │   scripts/utils/     │        │
│  │  release-config.yaml │────────→│  config_loader.py   │        │
│  │  conventional-       │         │  git_utils.py       │        │
│  │    commits.yaml      │         │  jira_client.py     │        │
│  └─────────────────────┘         │  notification.py    │        │
│                                   └──────────┬──────────┘        │
│                                              │                    │
│  ┌───────────────────────────────────────────┼──────────────┐    │
│  │                  CORE SCRIPTS             │              │    │
│  │                                           ▼              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │    │
│  │  │ version.py   │  │release_notes │  │tag_work_items│  │    │
│  │  │              │  │   .py        │  │   .py        │  │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │    │
│  │         │                 │                  │          │    │
│  │  ┌──────┴──────────────────┴──────────────────┴───────┐ │    │
│  │  │              prepare_qa_handoff.py                  │ │    │
│  │  │  (orchestrates: deploy, manifest, test, notify)    │ │    │
│  │  └────────────────────────────────────────────────────┘ │    │
│  │                                                          │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │    │
│  │  │correlate_    │  │feature_      │  │release_      │  │    │
│  │  │ releases.py  │  │ toggles.py   │  │ report.py    │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                  INFRASTRUCTURE                           │    │
│  │  deploy.sh  •  promote_image.sh  •  rollout-monitor.sh  │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Git Commits (conventional format)
    │
    ▼
┌──────────────────┐
│ git_utils.py     │
│ parse commits    │
│ detect services  │
└────────┬─────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│version │ │release │ │tag_work│ │correlate│
│summary │ │notes   │ │items   │ │releases │
│ .json  │ │ .md    │ │results │ │report   │
└───┬────┘ │ .json  │ │ .json  │ │ .json   │
    │      └───┬────┘ └────────┘ └─────────┘
    │          │
    ▼          ▼
┌──────────────────┐
│ QA Bridge        │
│ - test manifest  │──→ QA Automation API
│ - qa checklist   │──→ Slack / Teams
│ - toggle snapshot│──→ Pipeline Artifacts
│ - deploy to QA   │──→ K8s QA Namespace
└──────────────────┘
         │
         ▼
┌──────────────────┐
│ Helm Deploy      │
│ staging → prod   │──→ Dynatrace Events
│ canary verify    │──→ Grafana Annotations
│ edge waves 1-3   │──→ Slack Notifications
└──────────────────┘
```

## External Integrations

| System | Purpose | Integration Method |
|--------|---------|-------------------|
| Jira | Ticket tagging, status transitions | REST API v3 |
| GitHub/GitLab | Source control, CI/CD triggers | Git CLI + API |
| Docker Registry | Image storage and promotion | Docker CLI |
| Kubernetes | Application deployment | kubectl + Helm 3 |
| Harness CD | Approval gates, canary verification | Harness YAML |
| Dynatrace | APM, deployment events | Events API v2 |
| Grafana | Dashboard annotations | Annotations API |
| Slack | Team notifications | Webhook (Block Kit) |
| Microsoft Teams | Team notifications | Webhook (Adaptive Cards) |
| LaunchDarkly/Split | Feature toggle management | REST API |

## Edge Cluster Topology

```
┌─────────────────────────────────────────────────┐
│              CLOUD (Central K8s)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ pos-api  │  │ payment  │  │ catalog  │     │
│  │ service  │  │ gateway  │  │ service  │     │
│  └──────────┘  └──────────┘  └──────────┘     │
└───────────────────────┬─────────────────────────┘
                        │ sync
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  WAVE 1      │ │  WAVE 2      │ │  WAVE 3      │
│  Pilot (5)   │ │  Regional    │ │  Full         │
│              │ │  (50-100)    │ │  (All)        │
│ ┌──────────┐ │ │              │ │              │
│ │ Store    │ │ │ ┌──────────┐ │ │ ┌──────────┐ │
│ │ Edge K8s │ │ │ │ Store    │ │ │ │ Store    │ │
│ │ ┌──────┐ │ │ │ │ Edge K8s │ │ │ │ Edge K8s │ │
│ │ │ POS  │ │ │ │ └──────────┘ │ │ └──────────┘ │
│ │ │Agent │ │ │ │              │ │              │
│ │ └──────┘ │ │ └──────────────┘ └──────────────┘
│ └──────────┘ │
└──────────────┘
```

Each edge cluster runs:
- **pos-edge-api** (Deployment): Store-level API service
- **pos-terminal-agent** (DaemonSet): One agent per POS terminal node
- **edge-rollout-monitor** (CronJob): Health monitoring every 5 minutes
