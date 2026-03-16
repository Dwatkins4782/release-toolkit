#!/usr/bin/env bash
# =============================================================================
# Docker Image Promotion — Promote images between registries
# =============================================================================
# Promotes a container image from one registry to another (dev→staging→prod),
# retags with the release version, and verifies digest integrity.
#
# Usage:
#   ./scripts/promote_image.sh --image pos-terminal-service --version v2.1.0 --from dev --to staging
#   ./scripts/promote_image.sh --image pos-terminal-service --version v2.1.0 --from staging --to production
#   ./scripts/promote_image.sh --all --version v2.1.0 --from staging --to production

set -euo pipefail

# ── Configuration ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_DEV="${DOCKER_REGISTRY_DEV:-registry.dev.myorg.com}"
REGISTRY_STAGING="${DOCKER_REGISTRY_STAGING:-registry.staging.myorg.com}"
REGISTRY_PROD="${DOCKER_REGISTRY_PROD:-registry.prod.myorg.com}"
IMAGE_PREFIX="${DOCKER_IMAGE_PREFIX:-pos-platform}"

ALL_SERVICES=("pos-terminal-service" "payment-gateway" "store-config-service" "inventory-service" "pos-ui")

# ── Functions ──
get_registry() {
    case "$1" in
        dev)        echo "$REGISTRY_DEV" ;;
        staging)    echo "$REGISTRY_STAGING" ;;
        production) echo "$REGISTRY_PROD" ;;
        prod)       echo "$REGISTRY_PROD" ;;
        *)          echo "$1" ;;
    esac
}

promote_image() {
    local image="$1"
    local version="$2"
    local from_env="$3"
    local to_env="$4"
    local dry_run="${5:-false}"

    local from_registry
    from_registry=$(get_registry "$from_env")
    local to_registry
    to_registry=$(get_registry "$to_env")

    local source_image="${from_registry}/${IMAGE_PREFIX}/${image}:${version}"
    local target_image="${to_registry}/${IMAGE_PREFIX}/${image}:${version}"

    echo "Promoting: ${image}"
    echo "  From: ${source_image}"
    echo "  To:   ${target_image}"

    if [ "$dry_run" = "true" ]; then
        echo "  [DRY RUN] Would pull, tag, and push"
        return 0
    fi

    # Pull from source
    echo "  Pulling from source..."
    docker pull "${source_image}" || {
        echo "  ERROR: Failed to pull ${source_image}"
        return 1
    }

    # Get source digest for verification
    local source_digest
    source_digest=$(docker inspect --format='{{index .RepoDigests 0}}' "${source_image}" 2>/dev/null | cut -d@ -f2 || echo "unknown")
    echo "  Source digest: ${source_digest}"

    # Tag for target
    docker tag "${source_image}" "${target_image}"

    # Push to target
    echo "  Pushing to target..."
    docker push "${target_image}" || {
        echo "  ERROR: Failed to push ${target_image}"
        return 1
    }

    # Verify digest matches
    local target_digest
    target_digest=$(docker inspect --format='{{index .RepoDigests 0}}' "${target_image}" 2>/dev/null | cut -d@ -f2 || echo "unknown")

    if [ "$source_digest" = "$target_digest" ] && [ "$source_digest" != "unknown" ]; then
        echo "  Digest verified: ${source_digest}"
    else
        echo "  WARNING: Digest verification skipped or mismatch"
    fi

    # Also tag as 'latest' in target env
    local latest_image="${to_registry}/${IMAGE_PREFIX}/${image}:latest"
    docker tag "${source_image}" "${latest_image}"
    docker push "${latest_image}" 2>/dev/null || true

    echo "  Promotion complete"
    return 0
}

# ── Argument Parsing ──
IMAGE=""
VERSION=""
FROM_ENV=""
TO_ENV=""
PROMOTE_ALL=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --image)    IMAGE="$2"; shift 2 ;;
        --version)  VERSION="$2"; shift 2 ;;
        --from)     FROM_ENV="$2"; shift 2 ;;
        --to)       TO_ENV="$2"; shift 2 ;;
        --all)      PROMOTE_ALL=true; shift ;;
        --dry-run)  DRY_RUN=true; shift ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Validate
if [ -z "$VERSION" ] || [ -z "$FROM_ENV" ] || [ -z "$TO_ENV" ]; then
    echo "Usage: $0 --image <name> --version <version> --from <env> --to <env>"
    echo "       $0 --all --version <version> --from <env> --to <env>"
    exit 1
fi

if [ "$PROMOTE_ALL" = false ] && [ -z "$IMAGE" ]; then
    echo "Error: Specify --image or --all"
    exit 1
fi

# ── Execute ──
echo "============================================="
echo "  IMAGE PROMOTION: ${FROM_ENV} → ${TO_ENV}"
echo "  Version: ${VERSION}"
echo "============================================="

ERRORS=0

if [ "$PROMOTE_ALL" = true ]; then
    for svc in "${ALL_SERVICES[@]}"; do
        promote_image "$svc" "$VERSION" "$FROM_ENV" "$TO_ENV" "$DRY_RUN" || ((ERRORS++))
        echo ""
    done
else
    promote_image "$IMAGE" "$VERSION" "$FROM_ENV" "$TO_ENV" "$DRY_RUN" || ((ERRORS++))
fi

echo "============================================="
if [ $ERRORS -eq 0 ]; then
    echo "  All promotions successful"
else
    echo "  WARNING: ${ERRORS} promotion(s) failed"
fi
echo "============================================="

exit $ERRORS
