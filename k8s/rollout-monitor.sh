#!/usr/bin/env bash
# =============================================================================
# Deployment Rollout Health Checker
# =============================================================================
# Monitors a Helm-deployed application's rollout status, validates health
# endpoints, and optionally triggers rollback on failure.
#
# Usage:
#   ./k8s/rollout-monitor.sh --namespace pos-staging --deployment pos-platform
#   ./k8s/rollout-monitor.sh --namespace pos-production --deployment pos-platform --auto-rollback
#   ./k8s/rollout-monitor.sh --namespace pos-edge --all
# =============================================================================

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
NAMESPACE="pos-production"
DEPLOYMENT=""
TIMEOUT=300
HEALTH_ENDPOINT="/health/ready"
HEALTH_PORT=8080
CHECK_INTERVAL=10
AUTO_ROLLBACK=false
CHECK_ALL=false
HELM_RELEASE="pos-platform"

# ── Parse Arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace|-n)    NAMESPACE="$2"; shift 2 ;;
        --deployment|-d)   DEPLOYMENT="$2"; shift 2 ;;
        --timeout|-t)      TIMEOUT="$2"; shift 2 ;;
        --health-endpoint) HEALTH_ENDPOINT="$2"; shift 2 ;;
        --health-port)     HEALTH_PORT="$2"; shift 2 ;;
        --auto-rollback)   AUTO_ROLLBACK=true; shift ;;
        --all)             CHECK_ALL=true; shift ;;
        --helm-release)    HELM_RELEASE="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --namespace <ns> --deployment <name> [--auto-rollback]"
            echo ""
            echo "Options:"
            echo "  --namespace, -n      Kubernetes namespace"
            echo "  --deployment, -d     Deployment name to monitor"
            echo "  --timeout, -t        Timeout in seconds (default: 300)"
            echo "  --health-endpoint    Health check path (default: /health/ready)"
            echo "  --auto-rollback      Auto-rollback on failure"
            echo "  --all                Monitor all deployments in namespace"
            echo "  --helm-release       Helm release name for rollback"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo "[INFO]  $(date '+%H:%M:%S') $*"; }
log_ok()    { echo "[OK]    $(date '+%H:%M:%S') $*"; }
log_warn()  { echo "[WARN]  $(date '+%H:%M:%S') $*"; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $*"; }

check_deployment() {
    local deploy_name=$1
    local ns=$2

    log_info "Checking: ${deploy_name} in ${ns}"

    # Wait for rollout
    if ! kubectl rollout status "deployment/${deploy_name}" \
        --namespace "${ns}" --timeout="${TIMEOUT}s" 2>/dev/null; then
        log_error "Rollout failed for ${deploy_name}"
        return 1
    fi

    # Verify pod health
    local desired ready
    desired=$(kubectl get deployment "${deploy_name}" -n "${ns}" \
        -o jsonpath='{.spec.replicas}')
    ready=$(kubectl get deployment "${deploy_name}" -n "${ns}" \
        -o jsonpath='{.status.readyReplicas}')
    ready=${ready:-0}

    if [[ "${desired}" != "${ready}" ]]; then
        log_error "${deploy_name}: ${ready}/${desired} pods ready"
        return 1
    fi

    log_ok "${deploy_name}: ${ready}/${desired} pods ready"

    # Check for recent restarts
    local restarts
    restarts=$(kubectl get pods -n "${ns}" -l "app=${deploy_name}" \
        -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}' 2>/dev/null)
    local total_restarts=0
    for r in ${restarts}; do
        total_restarts=$((total_restarts + r))
    done

    if [[ ${total_restarts} -gt 0 ]]; then
        log_warn "${deploy_name}: ${total_restarts} container restarts detected"
    fi

    return 0
}

check_daemonsets() {
    local ns=$1
    local failed=0

    for ds in $(kubectl get daemonsets -n "${ns}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        local desired ready
        desired=$(kubectl get daemonset "${ds}" -n "${ns}" -o jsonpath='{.status.desiredNumberScheduled}')
        ready=$(kubectl get daemonset "${ds}" -n "${ns}" -o jsonpath='{.status.numberReady}')
        ready=${ready:-0}

        if [[ "${desired}" != "${ready}" ]]; then
            log_error "${ds} (DaemonSet): ${ready}/${desired} ready"
            failed=1
        else
            log_ok "${ds} (DaemonSet): ${ready}/${desired} ready"
        fi
    done

    return ${failed}
}

rollback() {
    log_warn "Initiating rollback for ${HELM_RELEASE} in ${NAMESPACE}..."
    if helm rollback "${HELM_RELEASE}" 0 --namespace "${NAMESPACE}" --wait --timeout 300s; then
        log_ok "Rollback successful"
    else
        log_error "Rollback failed — manual intervention required"
        exit 2
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════"
echo "  ROLLOUT HEALTH MONITOR"
echo "  Namespace: ${NAMESPACE}"
echo "  Timeout:   ${TIMEOUT}s"
echo "  Auto-rollback: ${AUTO_ROLLBACK}"
echo "═══════════════════════════════════════════════════════════"

FAILED=0

if [[ "${CHECK_ALL}" == "true" ]]; then
    # Check all deployments in namespace
    for deploy in $(kubectl get deployments -n "${NAMESPACE}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        if ! check_deployment "${deploy}" "${NAMESPACE}"; then
            FAILED=1
        fi
    done
    # Also check DaemonSets
    if ! check_daemonsets "${NAMESPACE}"; then
        FAILED=1
    fi
elif [[ -n "${DEPLOYMENT}" ]]; then
    if ! check_deployment "${DEPLOYMENT}" "${NAMESPACE}"; then
        FAILED=1
    fi
else
    log_error "Specify --deployment <name> or --all"
    exit 1
fi

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
if [[ ${FAILED} -eq 0 ]]; then
    log_ok "All workloads healthy"
    echo "═══════════════════════════════════════════════════════════"
    exit 0
else
    log_error "Unhealthy workloads detected"
    echo "═══════════════════════════════════════════════════════════"

    if [[ "${AUTO_ROLLBACK}" == "true" ]]; then
        rollback
    else
        log_warn "Run with --auto-rollback to auto-rollback, or:"
        log_warn "  helm rollback ${HELM_RELEASE} 0 --namespace ${NAMESPACE}"
    fi

    exit 1
fi
