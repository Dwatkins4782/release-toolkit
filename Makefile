# =============================================================================
# POS Platform Release Toolkit — Makefile
# =============================================================================
# Local development commands for release automation. Each target wraps
# a Python script or shell command for convenience.
#
# Usage: make <target>
# =============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash
PYTHON := python3
VERSION ?= $(shell $(PYTHON) -c "import json; print(json.load(open('version-summary.json'))['version'])" 2>/dev/null || echo "v0.0.0")

# ── Version & Release Notes ──────────────────────────────────────────────────

.PHONY: version
version: ## Calculate next semantic version
	$(PYTHON) scripts/version.py --bump auto --output version-summary.json
	@echo "Version summary written to version-summary.json"

.PHONY: version-dry-run
version-dry-run: ## Calculate version (dry run, no tag)
	$(PYTHON) scripts/version.py --bump auto --dry-run --output version-summary.json

.PHONY: changelog
changelog: ## Generate release notes (Markdown + JSON)
	$(PYTHON) scripts/release_notes.py --version $(VERSION) --format md --output release-notes-$(VERSION).md
	$(PYTHON) scripts/release_notes.py --version $(VERSION) --format json --output release-notes-$(VERSION).json
	@echo "Release notes: release-notes-$(VERSION).md"

.PHONY: tag
tag: ## Create and push Git tag for current version
	@echo "Tagging $(VERSION)..."
	git tag -a $(VERSION) -m "Release $(VERSION)"
	git push origin $(VERSION)
	@echo "Tag $(VERSION) pushed"

# ── Work Items ───────────────────────────────────────────────────────────────

.PHONY: tag-work-items
tag-work-items: ## Tag Jira tickets with release version
	$(PYTHON) scripts/tag_work_items.py --version $(VERSION) --output tagged-items.json

.PHONY: tag-work-items-dry-run
tag-work-items-dry-run: ## Preview Jira ticket tagging (dry run)
	$(PYTHON) scripts/tag_work_items.py --version $(VERSION) --dry-run --output tagged-items.json

# ── QA Bridge ────────────────────────────────────────────────────────────────

.PHONY: qa-handoff
qa-handoff: ## Full QA handoff: deploy, manifest, tests, notify
	$(PYTHON) scripts/prepare_qa_handoff.py --version $(VERSION) --env qa --output-dir ./qa-artifacts

.PHONY: qa-handoff-dry-run
qa-handoff-dry-run: ## QA handoff dry run (skip deploy, tests, notify)
	$(PYTHON) scripts/prepare_qa_handoff.py --version $(VERSION) --env qa --output-dir ./qa-artifacts --skip-deploy --skip-tests --skip-notify

.PHONY: qa-manifest
qa-manifest: ## Generate QA test manifest only
	$(PYTHON) scripts/prepare_qa_handoff.py --version $(VERSION) --env qa --output-dir ./qa-artifacts --skip-deploy --skip-tests --skip-notify

# ── Deployment ───────────────────────────────────────────────────────────────

.PHONY: deploy-staging
deploy-staging: ## Deploy to staging environment
	bash scripts/deploy.sh --version $(VERSION) --env staging --strategy rolling

.PHONY: deploy-prod
deploy-prod: ## Deploy to production (canary strategy)
	bash scripts/deploy.sh --version $(VERSION) --env production --strategy canary

.PHONY: deploy-edge
deploy-edge: ## Deploy to edge clusters (wave 1 - pilot stores)
	bash scripts/deploy.sh --version $(VERSION) --env production --edge --wave 1

.PHONY: deploy-edge-full
deploy-edge-full: ## Deploy to all edge clusters (wave 2 + 3)
	bash scripts/deploy.sh --version $(VERSION) --env production --edge --wave 2
	bash scripts/deploy.sh --version $(VERSION) --env production --edge --wave 3

.PHONY: rollback
rollback: ## Emergency rollback production
	bash scripts/deploy.sh --rollback --env production

.PHONY: rollback-staging
rollback-staging: ## Rollback staging
	bash scripts/deploy.sh --rollback --env staging

# ── Docker Image Promotion ───────────────────────────────────────────────────

.PHONY: promote-staging
promote-staging: ## Promote Docker images to staging registry
	bash scripts/promote_image.sh --version $(VERSION) --from dev --to staging --all

.PHONY: promote-prod
promote-prod: ## Promote Docker images to production registry
	bash scripts/promote_image.sh --version $(VERSION) --from staging --to prod --all

# ── Cross-Repo Correlation ───────────────────────────────────────────────────

.PHONY: correlate
correlate: ## Cross-repo release correlation report
	$(PYTHON) scripts/correlate_releases.py --version $(VERSION) --output correlation-report.json

# ── Feature Toggles ──────────────────────────────────────────────────────────

.PHONY: toggle-snapshot
toggle-snapshot: ## Snapshot current feature toggle state
	$(PYTHON) scripts/feature_toggles.py --version $(VERSION) --action snapshot

.PHONY: toggle-activate
toggle-activate: ## Activate feature toggles tagged for this release
	$(PYTHON) scripts/feature_toggles.py --version $(VERSION) --action activate

# ── Reporting ────────────────────────────────────────────────────────────────

.PHONY: report
report: ## Generate automated release report
	$(PYTHON) scripts/release_report.py --version $(VERSION) --format md --output release-report.md
	@echo "Report: release-report.md"

# ── Monitoring ───────────────────────────────────────────────────────────────

.PHONY: health-check
health-check: ## Post-deploy health check for production
	bash monitoring/post-deploy-health-check.sh --version $(VERSION) --env production

.PHONY: annotate-grafana
annotate-grafana: ## Create Grafana release annotation
	bash monitoring/grafana-annotations.sh --version $(VERSION) --env production

.PHONY: annotate-dynatrace
annotate-dynatrace: ## Push Dynatrace deployment event
	bash monitoring/dynatrace-deployment-event.sh --version $(VERSION) --env production

# ── Development ──────────────────────────────────────────────────────────────

.PHONY: install
install: ## Install Python dependencies
	pip install -r requirements.txt

.PHONY: test
test: ## Run unit tests
	$(PYTHON) -m pytest tests/ -v --tb=short

.PHONY: test-coverage
test-coverage: ## Run tests with coverage
	$(PYTHON) -m pytest tests/ -v --cov=scripts --cov-report=html --cov-report=term

.PHONY: lint
lint: ## Lint all Python scripts
	pip install flake8 2>/dev/null; flake8 scripts/ --max-line-length=120 --ignore=E501,W503

.PHONY: validate-configs
validate-configs: ## Validate YAML configuration files
	$(PYTHON) -c "import yaml; yaml.safe_load(open('config/release-config.yaml')); print('release-config.yaml: OK')"
	$(PYTHON) -c "import yaml; yaml.safe_load(open('config/conventional-commits.yaml')); print('conventional-commits.yaml: OK')"
	$(PYTHON) -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('.gitlab-ci.yml: OK')"

.PHONY: clean
clean: ## Clean generated artifacts
	rm -f version-summary.json version.env
	rm -f release-notes-*.md release-notes-*.json
	rm -f release-report*.md tagged-items.json
	rm -f correlation-report.json gitleaks-report.json
	rm -rf qa-artifacts/ __pycache__/ .pytest_cache/

# ── Full Release (local simulation) ─────────────────────────────────────────

.PHONY: release-dry-run
release-dry-run: version-dry-run changelog tag-work-items-dry-run qa-handoff-dry-run report ## Full release pipeline (dry run)
	@echo "============================================="
	@echo "  DRY RUN COMPLETE: $(VERSION)"
	@echo "============================================="

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help message
	@echo "POS Platform Release Toolkit"
	@echo "============================"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
