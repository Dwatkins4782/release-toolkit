#!/usr/bin/env bash
# =============================================================================
# Dynatrace Deployment Event — Push Release Metadata
# =============================================================================
# Pushes a deployment event to Dynatrace Events API v2, tagging the
# deployment with version, environment, affected services, and pipeline URL.
# Visible on all Dynatrace dashboards for release correlation.
#
# Usage:
#   ./monitoring/dynatrace-deployment-event.sh \
#     --version v2.1.0 \
#     --env production \
#     --services "pos-service,payment-gateway"
#
# Requires:
#   DYNATRACE_API_TOKEN (env var)
#   DYNATRACE_BASE_URL (env var) — e.g., https://abc12345.live.dynatrace.com
# =============================================================================

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
VERSION=""
ENVIRONMENT="production"
SERVICES=""
PIPELINE_URL="${CI_PIPELINE_URL:-${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}}"
DT_BASE_URL="${DYNATRACE_BASE_URL:-}"
DT_API_TOKEN="${DYNATRACE_API_TOKEN:-}"

# ── Parse Arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --version|-v)     VERSION="$2"; shift 2 ;;
        --env|-e)         ENVIRONMENT="$2"; shift 2 ;;
        --services|-s)    SERVICES="$2"; shift 2 ;;
        --pipeline-url)   PIPELINE_URL="$2"; shift 2 ;;
        --dt-url)         DT_BASE_URL="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --version <version> --env <environment> [--services <svc1,svc2>]"
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

if [[ -z "${DT_BASE_URL}" ]]; then
    echo "WARNING: DYNATRACE_BASE_URL not set — skipping Dynatrace event"
    exit 0
fi

if [[ -z "${DT_API_TOKEN}" ]]; then
    echo "WARNING: DYNATRACE_API_TOKEN not set — skipping Dynatrace event"
    exit 0
fi

# ── Build Entity Selector ───────────────────────────────────────────────────
ENTITY_SELECTOR="type(PROCESS_GROUP)"
if [[ -n "${SERVICES}" ]]; then
    # Build tag-based selector for each service
    IFS=',' read -ra SVC_ARRAY <<< "${SERVICES}"
    TAG_FILTER=""
    for svc in "${SVC_ARRAY[@]}"; do
        svc=$(echo "${svc}" | xargs)  # trim whitespace
        if [[ -n "${TAG_FILTER}" ]]; then
            TAG_FILTER="${TAG_FILTER},tag(\"service:${svc}\")"
        else
            TAG_FILTER="tag(\"service:${svc}\")"
        fi
    done
    ENTITY_SELECTOR="type(PROCESS_GROUP),${TAG_FILTER}"
fi

# ── Build Event Payload ──────────────────────────────────────────────────────
TIMESTAMP_MS=$(date +%s000)

PAYLOAD=$(cat <<EOF
{
  "eventType": "CUSTOM_DEPLOYMENT",
  "title": "Release ${VERSION} deployed to ${ENVIRONMENT}",
  "entitySelector": "${ENTITY_SELECTOR}",
  "properties": {
    "dt.event.deployment.name": "POS Platform Release",
    "dt.event.deployment.version": "${VERSION}",
    "dt.event.deployment.project": "pos-platform",
    "Environment": "${ENVIRONMENT}",
    "Release Version": "${VERSION}",
    "Services": "${SERVICES:-all}",
    "Pipeline URL": "${PIPELINE_URL}",
    "Deployed By": "${GITLAB_USER_NAME:-${GITHUB_ACTOR:-ci-bot}}",
    "Timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  },
  "timeout": 60
}
EOF
)

# ── Push Event ───────────────────────────────────────────────────────────────
echo "Pushing deployment event to Dynatrace..."
echo "  Version:     ${VERSION}"
echo "  Environment: ${ENVIRONMENT}"
echo "  Services:    ${SERVICES:-all}"

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${DT_BASE_URL}/api/v2/events/ingest" \
    -H "Authorization: Api-Token ${DT_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}")

HTTP_CODE=$(echo "${RESPONSE}" | tail -1)
BODY=$(echo "${RESPONSE}" | sed '$d')

if [[ "${HTTP_CODE}" =~ ^2 ]]; then
    echo "Dynatrace deployment event created successfully (HTTP ${HTTP_CODE})"
    echo "Event visible on Dynatrace dashboards for ${ENVIRONMENT}"
else
    echo "WARNING: Dynatrace event push failed (HTTP ${HTTP_CODE})"
    echo "Response: ${BODY}"
    exit 1
fi
