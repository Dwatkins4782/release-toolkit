#!/usr/bin/env bash
# =============================================================================
# Grafana Release Annotation — Mark Deployment on Dashboards
# =============================================================================
# Creates a Grafana annotation at deployment time, visible across all
# dashboards for release-to-metrics correlation.
#
# Usage:
#   ./monitoring/grafana-annotations.sh --version v2.1.0 --env production
#   ./monitoring/grafana-annotations.sh --version v2.1.0 --env staging --dashboard-id 42
#
# Requires:
#   GRAFANA_API_KEY (env var)
#   GRAFANA_BASE_URL (env var) — e.g., https://grafana.myorg.com
# =============================================================================

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
VERSION=""
ENVIRONMENT="production"
DASHBOARD_ID=""
PANEL_ID=""
TAGS="deployment,release"
GRAFANA_URL="${GRAFANA_BASE_URL:-}"
GRAFANA_KEY="${GRAFANA_API_KEY:-}"

# ── Parse Arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --version|-v)      VERSION="$2"; shift 2 ;;
        --env|-e)          ENVIRONMENT="$2"; shift 2 ;;
        --dashboard-id)    DASHBOARD_ID="$2"; shift 2 ;;
        --panel-id)        PANEL_ID="$2"; shift 2 ;;
        --tags)            TAGS="$2"; shift 2 ;;
        --grafana-url)     GRAFANA_URL="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --version <version> --env <environment> [--dashboard-id <id>]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Validation ───────────────────────────────────────────────────────────────
if [[ -z "${VERSION}" ]]; then
    echo "ERROR: --version is required"
    exit 1
fi

if [[ -z "${GRAFANA_URL}" ]]; then
    echo "WARNING: GRAFANA_BASE_URL not set — skipping Grafana annotation"
    exit 0
fi

if [[ -z "${GRAFANA_KEY}" ]]; then
    echo "WARNING: GRAFANA_API_KEY not set — skipping Grafana annotation"
    exit 0
fi

# ── Build Annotation Tags ───────────────────────────────────────────────────
IFS=',' read -ra TAG_ARRAY <<< "${TAGS}"
TAG_ARRAY+=("${ENVIRONMENT}" "${VERSION}")

TAGS_JSON=$(printf '"%s",' "${TAG_ARRAY[@]}")
TAGS_JSON="[${TAGS_JSON%,}]"

# ── Build Payload ────────────────────────────────────────────────────────────
TIMESTAMP_MS=$(date +%s)000
PIPELINE_URL="${CI_PIPELINE_URL:-${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}}"

ANNOTATION_TEXT="Release ${VERSION} deployed to ${ENVIRONMENT}"
if [[ -n "${PIPELINE_URL}" && "${PIPELINE_URL}" != "/" ]]; then
    ANNOTATION_TEXT="${ANNOTATION_TEXT}\n<a href=\"${PIPELINE_URL}\">View Pipeline</a>"
fi

PAYLOAD="{
  \"time\": ${TIMESTAMP_MS},
  \"tags\": ${TAGS_JSON},
  \"text\": \"${ANNOTATION_TEXT}\"
}"

# Add dashboard scope if specified
if [[ -n "${DASHBOARD_ID}" ]]; then
    PAYLOAD="{
  \"dashboardId\": ${DASHBOARD_ID},
  \"time\": ${TIMESTAMP_MS},
  \"tags\": ${TAGS_JSON},
  \"text\": \"${ANNOTATION_TEXT}\"
}"
fi

# ── Create Annotation ────────────────────────────────────────────────────────
echo "Creating Grafana annotation..."
echo "  Version:     ${VERSION}"
echo "  Environment: ${ENVIRONMENT}"
echo "  Tags:        ${TAGS_JSON}"

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${GRAFANA_URL}/api/annotations" \
    -H "Authorization: Bearer ${GRAFANA_KEY}" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}")

HTTP_CODE=$(echo "${RESPONSE}" | tail -1)
BODY=$(echo "${RESPONSE}" | sed '$d')

if [[ "${HTTP_CODE}" =~ ^2 ]]; then
    ANNOTATION_ID=$(echo "${BODY}" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
    echo "Grafana annotation created successfully (ID: ${ANNOTATION_ID:-unknown})"
    echo "Visible on all Grafana dashboards with matching tags"
else
    echo "WARNING: Grafana annotation failed (HTTP ${HTTP_CODE})"
    echo "Response: ${BODY}"
    exit 1
fi
