#!/usr/bin/env bash
# =============================================================================
# Single-Command Deploy & Rollback
# =============================================================================
# Deploy a release to any environment with a single command.
# Supports rolling, canary, and blue-green strategies.
# Includes POS terminal and edge Kubernetes cluster deployments.
#
# Usage:
#   ./scripts/deploy.sh --version v2.1.0 --env staging
#   ./scripts/deploy.sh --version v2.1.0 --env production --strategy canary
#   ./scripts/deploy.sh --rollback --env production
#   ./scripts/deploy.sh --version v2.1.0 --env production --edge --wave 1

set -euo pipefail

# ── Configuration ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT_DIR="$(dirname "$SCRIPT_DIR")"
HELM_RELEASE="${HELM_RELEASE_NAME:-pos-platform}"
HELM_CHART="${HELM_CHART_PATH:-${TOOLKIT_DIR}/charts/pos-platform}"
VALUES_DIR="${HELM_VALUES_DIR:-${TOOLKIT_DIR}/k8s/helm-values}"
DEPLOY_TIMEOUT="${DEPLOY_TIMEOUT:-600s}"

# ── Functions ──
get_namespace() {
    case "$1" in
        dev)        echo "pos-dev" ;;
        qa)         echo "pos-qa" ;;
        staging)    echo "pos-staging" ;;
        production) echo "pos-prod" ;;
        prod)       echo "pos-prod" ;;
        *)          echo "pos-$1" ;;
    esac
}

get_kubeconfig() {
    case "$1" in
        dev)        echo "${KUBECONFIG_DEV:-}" ;;
        qa)         echo "${KUBECONFIG_QA:-}" ;;
        staging)    echo "${KUBECONFIG_STAGING:-}" ;;
        production) echo "${KUBECONFIG_PROD:-}" ;;
        prod)       echo "${KUBECONFIG_PROD:-}" ;;
    esac
}

pre_deploy_checks() {
    local env="$1"
    local version="$2"

    echo "[Pre-Deploy] Running checks..."

    # Verify kubectl connectivity
    if ! kubectl cluster-info --request-timeout=5s &>/dev/null; then
        echo "  ERROR: Cannot connect to Kubernetes cluster"
        return 1
    fi
    echo "  Cluster connectivity: OK"

    # Verify namespace exists
    local ns
    ns=$(get_namespace "$env")
    if ! kubectl get namespace "$ns" &>/dev/null; then
        echo "  Creating namespace: $ns"
        kubectl create namespace "$ns" || true
    fi
    echo "  Namespace $ns: OK"

    # Verify Helm chart exists
    if [ -d "$HELM_CHART" ]; then
        echo "  Helm chart: OK ($HELM_CHART)"
    else
        echo "  WARNING: Helm chart directory not found: $HELM_CHART"
    fi

    # Production gate: require approval
    if [ "$env" = "production" ] || [ "$env" = "prod" ]; then
        echo ""
        echo "  *** PRODUCTION DEPLOYMENT ***"
        echo "  Version: $version"
        echo "  This will deploy to PRODUCTION."

        if [ "${CI:-}" != "true" ]; then
            read -p "  Type 'deploy' to confirm: " confirm
            if [ "$confirm" != "deploy" ]; then
                echo "  Deployment cancelled."
                return 1
            fi
        fi
    fi

    return 0
}

deploy_helm() {
    local version="$1"
    local env="$2"
    local strategy="$3"
    local dry_run="$4"

    local ns
    ns=$(get_namespace "$env")
    local values_file="${VALUES_DIR}/values-${env}.yaml"

    echo "[Deploy] Helm upgrade..."
    echo "  Release:   $HELM_RELEASE"
    echo "  Namespace: $ns"
    echo "  Version:   $version"
    echo "  Strategy:  $strategy"

    local helm_args=(
        "upgrade" "--install" "$HELM_RELEASE" "$HELM_CHART"
        "--namespace" "$ns"
        "--create-namespace"
        "--set" "image.tag=${version}"
        "--set" "metadata.release=${version}"
        "--set" "metadata.deployedAt=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        "--timeout" "$DEPLOY_TIMEOUT"
        "--wait"
    )

    # Add values file if it exists
    if [ -f "$values_file" ]; then
        helm_args+=("-f" "$values_file")
    fi

    # Strategy-specific flags
    case "$strategy" in
        canary)
            helm_args+=("--set" "strategy.type=canary" "--set" "strategy.canaryPercentage=10")
            ;;
        blue-green)
            helm_args+=("--set" "strategy.type=blueGreen")
            ;;
        rolling)
            helm_args+=("--set" "strategy.type=rolling" "--atomic")
            ;;
    esac

    if [ "$dry_run" = "true" ]; then
        helm_args+=("--dry-run")
        echo "  [DRY RUN]"
    fi

    helm "${helm_args[@]}"
    return $?
}

post_deploy_verify() {
    local env="$1"
    local version="$2"

    local ns
    ns=$(get_namespace "$env")

    echo "[Post-Deploy] Verifying deployment..."

    # Check rollout status
    local deployments
    deployments=$(kubectl get deployments -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

    for dep in $deployments; do
        echo "  Checking: $dep"
        if kubectl rollout status deployment/"$dep" -n "$ns" --timeout=120s &>/dev/null; then
            echo "    Status: Healthy"
        else
            echo "    Status: UNHEALTHY"
            return 1
        fi
    done

    # Run smoke test if available
    if [ -f "${TOOLKIT_DIR}/scripts/smoke-test.sh" ]; then
        echo "  Running smoke tests..."
        bash "${TOOLKIT_DIR}/scripts/smoke-test.sh" "$env" || {
            echo "  Smoke tests FAILED"
            return 1
        }
    fi

    echo "  Deployment verified successfully"
    return 0
}

rollback() {
    local env="$1"
    local ns
    ns=$(get_namespace "$env")

    echo "[Rollback] Rolling back in $env..."

    # Get previous revision
    local prev_rev
    prev_rev=$(helm history "$HELM_RELEASE" -n "$ns" --max 2 -o json 2>/dev/null | \
               python3 -c "import json,sys; h=json.load(sys.stdin); print(h[-2]['revision'] if len(h)>1 else h[0]['revision'])" 2>/dev/null || echo "")

    if [ -z "$prev_rev" ]; then
        echo "  ERROR: No previous revision found"
        return 1
    fi

    echo "  Rolling back to revision: $prev_rev"
    helm rollback "$HELM_RELEASE" "$prev_rev" -n "$ns" --wait --timeout "${DEPLOY_TIMEOUT}"

    echo "  Rollback complete. Verifying..."
    post_deploy_verify "$env" "rollback" || {
        echo "  WARNING: Post-rollback verification failed"
        return 1
    }

    # Send rollback notification
    echo "  Sending rollback notification..."
    python3 "${SCRIPT_DIR}/../scripts/utils/notification.py" 2>/dev/null || true

    return 0
}

deploy_edge_clusters() {
    local version="$1"
    local wave="$2"
    local dry_run="$3"

    echo "[Edge Deploy] Deploying to POS edge clusters (wave $wave)..."

    # Edge clusters are managed differently — apply manifests directly
    local edge_manifest="${TOOLKIT_DIR}/k8s/edge-cluster/edge-deployment.yaml"

    if [ ! -f "$edge_manifest" ]; then
        echo "  WARNING: Edge deployment manifest not found"
        return 0
    fi

    if [ "$dry_run" = "true" ]; then
        echo "  [DRY RUN] Would deploy to edge clusters wave $wave"
        return 0
    fi

    # Apply with version substitution
    sed "s|\${VERSION}|${version}|g" "$edge_manifest" | kubectl apply -f - || {
        echo "  ERROR: Edge deployment failed"
        return 1
    }

    echo "  Edge cluster deployment initiated (wave $wave)"
    return 0
}

# ── Argument Parsing ──
VERSION=""
ENV=""
STRATEGY="rolling"
DO_ROLLBACK=false
DRY_RUN=false
EDGE=false
WAVE=1

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)   VERSION="$2"; shift 2 ;;
        --env)       ENV="$2"; shift 2 ;;
        --strategy)  STRATEGY="$2"; shift 2 ;;
        --rollback)  DO_ROLLBACK=true; shift ;;
        --dry-run)   DRY_RUN=true; shift ;;
        --edge)      EDGE=true; shift ;;
        --wave)      WAVE="$2"; shift 2 ;;
        *)           echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$ENV" ]; then
    echo "Usage: $0 --version <ver> --env <env> [--strategy rolling|canary|blue-green]"
    echo "       $0 --rollback --env <env>"
    echo "       $0 --version <ver> --env <env> --edge --wave <n>"
    exit 1
fi

# Set kubeconfig if available
KUBE=$(get_kubeconfig "$ENV")
if [ -n "$KUBE" ] && [ -f "$KUBE" ]; then
    export KUBECONFIG="$KUBE"
fi

# ── Execute ──
echo "============================================="
echo "  DEPLOYMENT: ${ENV}"
echo "  Version:    ${VERSION:-rollback}"
echo "  Strategy:   ${STRATEGY}"
echo "============================================="

if [ "$DO_ROLLBACK" = true ]; then
    rollback "$ENV"
    exit $?
fi

if [ -z "$VERSION" ]; then
    echo "Error: --version required for deployment"
    exit 1
fi

# Pre-deploy checks
pre_deploy_checks "$ENV" "$VERSION" || exit 1

# Deploy via Helm
deploy_helm "$VERSION" "$ENV" "$STRATEGY" "$DRY_RUN" || {
    echo "Deployment failed. Consider rollback: $0 --rollback --env $ENV"
    exit 1
}

# Post-deploy verification
if [ "$DRY_RUN" = "false" ]; then
    post_deploy_verify "$ENV" "$VERSION" || {
        echo "Post-deploy verification failed. Rolling back..."
        rollback "$ENV"
        exit 1
    }
fi

# Edge cluster deployment
if [ "$EDGE" = true ]; then
    deploy_edge_clusters "$VERSION" "$WAVE" "$DRY_RUN"
fi

echo ""
echo "============================================="
echo "  DEPLOYMENT SUCCESSFUL"
echo "  Version: $VERSION"
echo "  Environment: $ENV"
echo "============================================="
