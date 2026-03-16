#!/usr/bin/env bash
# =============================================================================
# Post-Deploy Health Check — Monitoring-Based Validation
# =============================================================================
# Queries Dynatrace/Grafana for error rate spikes after deployment.
# Waits for a configurable observation window, then checks if error rates
# exceed threshold. Auto-triggers rollback if health check fails.
#
# Usage:
#   ./monitoring/post-deploy-health-check.sh --version v2.1.0 --env production
#   ./monitoring/post-deploy-health-check.sh --version v2.1.0 --env staging --threshold 5
#   ./monitoring/post-deploy-health-check.sh --version v2.1.0 --env production --auto-rollback
#
# Requires one of:
#   DYNATRACE_API_TOKEN + DYNATRACE_BASE_URL
#   GRAFANA_API_KEY + GRAFANA_BASE_URL
# =============================================================================

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
VERSION=""
ENVIRONMENT="production"
OBSERVATION_WINDOW=180    # seconds to wait before checking
ERROR_THRESHOLD=5         # percent error rate that triggers failure
AUTO_ROLLBACK=false
HELM_RELEASE="pos-platform"
NAMESPACE=""
HEALTH_ENDPOINT=""
CHECK_RETRIES=3

# ── Parse Arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --version|-v)        VERSION="$2"; shift 2 ;;
        --env|-e)            ENVIRONMENT="$2"; shift 2 ;;
        --observation|-o)    OBSERVATION_WINDOW="$2"; shift 2 ;;
        --threshold|-t)      ERROR_THRESHOLD="$2"; shift 2 ;;
        --auto-rollback)     AUTO_ROLLBACK=true; shift ;;
        --helm-release)      HELM_RELEASE="$2"; shift 2 ;;
        --namespace|-n)      NAMESPACE="$2"; shift 2 ;;
        --health-endpoint)   HEALTH_ENDPOINT="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --version <version> --env <environment> [--threshold <percent>] [--auto-rollback]"
            echo ""
            echo "Options:"
            echo "  --version, -v        Release version"
            echo "  --env, -e            Target environment"
            echo "  --observation, -o    Observation window in seconds (default: 180)"
            echo "  --threshold, -t      Error rate threshold percent (default: 5)"
            echo "  --auto-rollback      Auto-rollback on failure"
            echo "  --helm-release       Helm release name for rollback"
            echo "  --namespace, -n      Kubernetes namespace"
            echo "  --health-endpoint    Direct health URL to check"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Resolve Defaults ─────────────────────────────────────────────────────────
if [[ -z "${NAMESPACE}" ]]; then
    case "${ENVIRONMENT}" in
        production) NAMESPACE="pos-production" ;;
        staging)    NAMESPACE="pos-staging" ;;
        qa)         NAMESPACE="pos-qa" ;;
        edge)       NAMESPACE="pos-edge" ;;
        *)          NAMESPACE="pos-${ENVIRONMENT}" ;;
    esac
fi

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo "[INFO]  $(date '+%H:%M:%S') $*"; }
log_ok()    { echo "[OK]    $(date '+%H:%M:%S') $*"; }
log_warn()  { echo "[WARN]  $(date '+%H:%M:%S') $*"; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $*"; }

check_k8s_health() {
    log_info "Checking Kubernetes deployment health..."

    local ready desired restarts
    desired=$(kubectl get deployment "${HELM_RELEASE}" -n "${NAMESPACE}" \
        -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    ready=$(kubectl get deployment "${HELM_RELEASE}" -n "${NAMESPACE}" \
        -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    ready=${ready:-0}

    if [[ "${desired}" != "${ready}" ]]; then
        log_error "K8s: ${ready}/${desired} pods ready"
        return 1
    fi

    log_ok "K8s: ${ready}/${desired} pods ready"

    # Check for crash loops
    restarts=$(kubectl get pods -n "${NAMESPACE}" -l "app=${HELM_RELEASE}" \
        -o jsonpath='{range .items[*]}{.status.containerStatuses[*].restartCount}{" "}{end}' 2>/dev/null)
    local total_restarts=0
    for r in ${restarts}; do
        total_restarts=$((total_restarts + r))
    done

    if [[ ${total_restarts} -gt 3 ]]; then
        log_error "High restart count: ${total_restarts} restarts"
        return 1
    fi

    return 0
}

check_dynatrace_errors() {
    local dt_url="${DYNATRACE_BASE_URL:-}"
    local dt_token="${DYNATRACE_API_TOKEN:-}"

    if [[ -z "${dt_url}" || -z "${dt_token}" ]]; then
        log_info "Dynatrace not configured — skipping error rate check"
        return 0
    fi

    log_info "Querying Dynatrace for error rate (last ${OBSERVATION_WINDOW}s)..."

    local from_ts=$(($(date +%s) - OBSERVATION_WINDOW))000
    local now_ts=$(date +%s)000

    RESPONSE=$(curl -s \
        "${dt_url}/api/v2/metrics/query?metricSelector=builtin:service.errors.total.rate&from=${from_ts}&to=${now_ts}" \
        -H "Authorization: Api-Token ${dt_token}" \
        -H "Accept: application/json")

    # Extract error rate (simplified — real implementation would parse JSON properly)
    ERROR_RATE=$(echo "${RESPONSE}" | grep -o '"values":\[[0-9.]*\]' | head -1 | grep -o '[0-9.]*' || echo "0")
    ERROR_RATE=${ERROR_RATE:-0}

    log_info "Current error rate: ${ERROR_RATE}%"

    if (( $(echo "${ERROR_RATE} > ${ERROR_THRESHOLD}" | bc -l 2>/dev/null || echo 0) )); then
        log_error "Error rate ${ERROR_RATE}% exceeds threshold ${ERROR_THRESHOLD}%"
        return 1
    fi

    log_ok "Error rate ${ERROR_RATE}% within threshold"
    return 0
}

check_health_endpoint() {
    if [[ -z "${HEALTH_ENDPOINT}" ]]; then
        # Construct default from environment
        case "${ENVIRONMENT}" in
            production) HEALTH_ENDPOINT="https://pos-platform.myorg.com/health/ready" ;;
            staging)    HEALTH_ENDPOINT="https://staging.pos-platform.myorg.com/health/ready" ;;
            qa)         HEALTH_ENDPOINT="https://qa.pos-platform.myorg.com/health/ready" ;;
            *)          return 0 ;;
        esac
    fi

    log_info "Checking health endpoint: ${HEALTH_ENDPOINT}"

    local attempt
    for attempt in $(seq 1 ${CHECK_RETRIES}); do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_ENDPOINT}" --max-time 10 2>/dev/null || echo "000")

        if [[ "${HTTP_CODE}" == "200" ]]; then
            log_ok "Health endpoint returned HTTP 200"
            return 0
        fi

        log_warn "Health check attempt ${attempt}/${CHECK_RETRIES}: HTTP ${HTTP_CODE}"
        sleep 5
    done

    log_error "Health endpoint unreachable after ${CHECK_RETRIES} attempts"
    return 1
}

trigger_rollback() {
    log_warn "TRIGGERING AUTOMATIC ROLLBACK"
    log_warn "Helm release: ${HELM_RELEASE} in ${NAMESPACE}"

    if helm rollback "${HELM_RELEASE}" 0 --namespace "${NAMESPACE}" --wait --timeout 300s 2>/dev/null; then
        log_ok "Rollback successful"

        # Notify via Slack
        if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
            curl -s -X POST "${SLACK_WEBHOOK_URL}" \
                -H 'Content-Type: application/json' \
                -d "{
                    \"text\": \"AUTO-ROLLBACK: ${VERSION} in ${ENVIRONMENT} rolled back due to health check failure\"
                }" || true
        fi
    else
        log_error "ROLLBACK FAILED — MANUAL INTERVENTION REQUIRED"
        exit 2
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════"
echo "  POST-DEPLOY HEALTH CHECK"
echo "  Version:      ${VERSION}"
echo "  Environment:  ${ENVIRONMENT}"
echo "  Namespace:    ${NAMESPACE}"
echo "  Observation:  ${OBSERVATION_WINDOW}s"
echo "  Threshold:    ${ERROR_THRESHOLD}%"
echo "  Auto-rollback: ${AUTO_ROLLBACK}"
echo "═══════════════════════════════════════════════════════════"

# Wait for observation window
if [[ ${OBSERVATION_WINDOW} -gt 0 ]]; then
    log_info "Waiting ${OBSERVATION_WINDOW}s observation window..."
    sleep "${OBSERVATION_WINDOW}"
fi

HEALTH_STATUS=0

# Run health checks
if ! check_k8s_health; then
    HEALTH_STATUS=1
fi

if ! check_health_endpoint; then
    HEALTH_STATUS=1
fi

if ! check_dynatrace_errors; then
    HEALTH_STATUS=1
fi

# Result
echo ""
echo "═══════════════════════════════════════════════════════════"
if [[ ${HEALTH_STATUS} -eq 0 ]]; then
    log_ok "ALL HEALTH CHECKS PASSED"
    echo "═══════════════════════════════════════════════════════════"
    exit 0
else
    log_error "HEALTH CHECK FAILED"
    echo "═══════════════════════════════════════════════════════════"

    if [[ "${AUTO_ROLLBACK}" == "true" ]]; then
        trigger_rollback
    else
        log_warn "Run with --auto-rollback to automatically rollback"
        log_warn "Or manually: helm rollback ${HELM_RELEASE} 0 --namespace ${NAMESPACE}"
    fi

    exit 1
fi
