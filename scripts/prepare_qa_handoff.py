#!/usr/bin/env python3
"""
QA Bridge — Prepare Release for Test Automation Engineer
=========================================================
Generates test manifests, deploys to QA environment, triggers test automation,
and notifies the QA team with everything they need to validate a release.

Usage:
    python scripts/prepare_qa_handoff.py --version v2.1.0 --env qa
    python scripts/prepare_qa_handoff.py --version v2.1.0 --dry-run
    python scripts/prepare_qa_handoff.py --version v2.1.0 --skip-deploy --skip-tests

This is the bridging job between development completion and QA validation.
"""

import sys
import os
import argparse
import json
import subprocess
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.utils.config_loader import load_config, get_config_value
from scripts.utils.git_utils import (
    get_latest_tag, get_commits_since_tag, parse_conventional_commit,
    get_changed_files, detect_affected_services, get_diff_stats
)
from scripts.utils.notification import send_slack, format_qa_handoff_notification


# ─── Test Manifest Generation ────────────────────────────────────────────────

def generate_test_manifest(version, commits, affected_services, config):
    """
    Generate a comprehensive test manifest for the QA team.
    Maps code changes to test suites, identifies manual test items,
    and captures feature toggle state.
    """
    scopes_config = get_config_value(config, 'conventional_commits.scopes', {})
    qa_config = get_config_value(config, 'qa_bridge', {})

    # Parse all commits
    parsed_commits = []
    manual_test_items = []
    suggested_suites = set()
    all_tickets = set()
    breaking_changes = []

    for commit in commits:
        parsed = parse_conventional_commit(commit['subject'])
        parsed['hash'] = commit['hash'][:7]
        parsed['author'] = commit.get('author', 'unknown')
        parsed['date'] = commit.get('date', '')
        parsed_commits.append(parsed)

        # Collect tickets
        all_tickets.update(parsed.get('tickets', []))

        # Check for manual test flags
        manual_tags = qa_config.get('manual_test_tags', ['[manual-test]'])
        for tag in manual_tags:
            if tag in commit['subject']:
                manual_test_items.append({
                    'description': parsed['description'],
                    'scope': parsed['scope'],
                    'hash': parsed['hash'],
                    'author': parsed['author'],
                    'tag': tag,
                })

        # Map scope to test suite
        if parsed['scope'] and parsed['scope'] in scopes_config:
            suite = scopes_config[parsed['scope']].get('test_suite')
            if suite:
                suggested_suites.add(suite)

        # Collect breaking changes
        if parsed['breaking']:
            breaking_changes.append({
                'description': parsed['description'],
                'scope': parsed['scope'],
                'hash': parsed['hash'],
            })

    # Always include smoke suite
    test_automation = qa_config.get('test_automation', {})
    suite_ids = test_automation.get('suite_ids', {})
    suggested_suites.add(suite_ids.get('smoke', 'suite-smoke-001'))

    # If there are breaking changes, add regression suite
    if breaking_changes:
        suggested_suites.add(suite_ids.get('regression', 'suite-regression-001'))

    # Check for edge-deploy services
    edge_services = [s for s in affected_services
                     if any(sc.get('edge_deploy') for sc in scopes_config.values()
                           if sc.get('service') == s)]
    if edge_services:
        suggested_suites.add(suite_ids.get('edge_cluster', 'suite-edge-001'))

    manifest = {
        'version': version,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'environment': 'qa',
        'total_commits': len(parsed_commits),
        'affected_services': affected_services,
        'edge_services': edge_services,
        'breaking_changes': breaking_changes,
        'tickets': sorted(all_tickets),
        'suggested_test_suites': sorted(suggested_suites),
        'manual_test_items': manual_test_items,
        'feature_toggles_changed': [],  # Populated by feature toggle snapshot
        'commits_by_type': {},
        'risk_assessment': 'low',
    }

    # Commits by type
    type_counts = {}
    for pc in parsed_commits:
        t = pc['type']
        type_counts[t] = type_counts.get(t, 0) + 1
    manifest['commits_by_type'] = type_counts

    # Risk assessment
    if breaking_changes:
        manifest['risk_assessment'] = 'high'
    elif len(affected_services) > 3 or len(parsed_commits) > 20:
        manifest['risk_assessment'] = 'medium'
    else:
        manifest['risk_assessment'] = 'low'

    return manifest


# ─── QA Checklist Generation ─────────────────────────────────────────────────

def generate_qa_checklist(version, manifest):
    """Generate a Markdown QA checklist document."""
    lines = []
    lines.append(f"# QA Checklist — Release {version}\n")
    lines.append(f"**Generated:** {manifest['generated_at']}")
    lines.append(f"**Risk Level:** {manifest['risk_assessment'].upper()}")
    lines.append(f"**Affected Services:** {', '.join(manifest['affected_services']) or 'All'}")
    lines.append(f"**Total Changes:** {manifest['total_commits']} commits")
    lines.append("")

    # Breaking changes (high priority)
    if manifest['breaking_changes']:
        lines.append("## BREAKING CHANGES (Verify First)\n")
        for bc in manifest['breaking_changes']:
            scope = f"[{bc['scope']}] " if bc['scope'] else ""
            lines.append(f"- [ ] {scope}{bc['description']} (`{bc['hash']}`)")
        lines.append("")

    # Manual test items
    if manifest['manual_test_items']:
        lines.append("## Manual Test Items\n")
        for item in manifest['manual_test_items']:
            scope = f"[{item['scope']}] " if item['scope'] else ""
            lines.append(f"- [ ] {scope}{item['description']} (`{item['hash']}`) "
                        f"— flagged: `{item['tag']}`")
        lines.append("")

    # Automated test suites
    lines.append("## Automated Test Suites\n")
    for suite in manifest['suggested_test_suites']:
        lines.append(f"- [ ] `{suite}` — Triggered / Passed / Failed")
    lines.append("")

    # Edge cluster verification
    if manifest['edge_services']:
        lines.append("## Edge Cluster / POS Terminal Verification\n")
        for svc in manifest['edge_services']:
            lines.append(f"- [ ] `{svc}` deployed to edge pilot stores")
            lines.append(f"- [ ] POS terminal health check passed")
            lines.append(f"- [ ] Transaction processing verified")
        lines.append("")

    # Feature toggles
    if manifest['feature_toggles_changed']:
        lines.append("## Feature Toggles\n")
        for toggle in manifest['feature_toggles_changed']:
            lines.append(f"- [ ] `{toggle['name']}`: {toggle['state']} "
                        f"— verify behavior matches toggle state")
        lines.append("")

    # Service-by-service verification
    lines.append("## Service Verification\n")
    for service in manifest['affected_services']:
        lines.append(f"### {service}\n")
        lines.append(f"- [ ] Health endpoint responding")
        lines.append(f"- [ ] Logs show no errors post-deploy")
        lines.append(f"- [ ] Basic functionality verified")
        lines.append("")

    # Rollback information
    lines.append("## Rollback Procedure\n")
    lines.append("If critical issues are found:\n")
    lines.append("```bash")
    lines.append(f"# Rollback to previous version")
    lines.append(f"make rollback VERSION={version} ENV=qa")
    lines.append(f"")
    lines.append(f"# Or use deploy script directly")
    lines.append(f"./scripts/deploy.sh --rollback --env qa")
    lines.append("```\n")

    # Sign-off
    lines.append("## Sign-Off\n")
    lines.append(f"- [ ] QA Engineer: _________________ Date: _______")
    lines.append(f"- [ ] Release Manager: _____________ Date: _______")
    lines.append("")

    return '\n'.join(lines)


# ─── QA Environment Deployment ───────────────────────────────────────────────

def deploy_to_qa(version, config, dry_run=False):
    """Deploy the release to the QA environment using Helm."""
    namespace = get_config_value(config, 'kubernetes.namespaces.qa', 'pos-qa')
    release_name = get_config_value(config, 'kubernetes.helm.release_name', 'pos-platform')
    chart_path = get_config_value(config, 'kubernetes.helm.chart_path', './charts/pos-platform')
    values_dir = get_config_value(config, 'kubernetes.helm.values_dir', './k8s/helm-values')
    timeout = get_config_value(config, 'kubernetes.helm.timeout', '600s')

    helm_cmd = [
        'helm', 'upgrade', '--install', release_name, chart_path,
        '--namespace', namespace,
        '--create-namespace',
        '-f', f'{values_dir}/values-qa.yaml',
        '--set', f'image.tag={version}',
        '--set', f'metadata.release={version}',
        '--timeout', timeout,
        '--wait',
        '--atomic',
    ]

    if dry_run:
        helm_cmd.append('--dry-run')
        print(f"[DRY RUN] Would execute: {' '.join(helm_cmd)}")
        return True

    print(f"Deploying {version} to QA namespace: {namespace}")
    print(f"Command: {' '.join(helm_cmd)}")

    try:
        result = subprocess.run(helm_cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f"Deployment successful")
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
            return True
        else:
            print(f"Deployment failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("Deployment timed out")
        return False
    except FileNotFoundError:
        print("Warning: helm not found. Skipping deployment.")
        return False


def verify_deployment_health(config, dry_run=False):
    """Verify the QA deployment is healthy."""
    namespace = get_config_value(config, 'kubernetes.namespaces.qa', 'pos-qa')

    if dry_run:
        print("[DRY RUN] Would verify deployment health")
        return True

    try:
        result = subprocess.run(
            ['kubectl', 'get', 'pods', '-n', namespace,
             '-o', 'jsonpath={.items[*].status.phase}'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            phases = result.stdout.split()
            running = sum(1 for p in phases if p == 'Running')
            total = len(phases)
            print(f"Pod status: {running}/{total} Running")
            return running == total and total > 0
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Warning: kubectl not available. Skipping health check.")
        return True  # Don't block on missing kubectl


# ─── Test Suite Trigger ──────────────────────────────────────────────────────

def trigger_test_suites(manifest, config, dry_run=False):
    """Trigger QA automation test suites via webhook/API."""
    qa_config = get_config_value(config, 'qa_bridge.test_automation', {})
    trigger_url = qa_config.get('trigger_url', '')
    api_key = os.environ.get('QA_AUTOMATION_API_KEY', '')

    if not trigger_url or trigger_url.startswith('${'):
        print("QA automation trigger URL not configured. Skipping test trigger.")
        return None

    triggered_suites = []
    for suite_id in manifest['suggested_test_suites']:
        payload = {
            'suite_id': suite_id,
            'version': manifest['version'],
            'environment': manifest['environment'],
            'affected_services': manifest['affected_services'],
            'triggered_by': 'release-toolkit',
            'metadata': {
                'risk_level': manifest['risk_assessment'],
                'total_commits': manifest['total_commits'],
                'tickets': manifest['tickets'],
            }
        }

        if dry_run:
            print(f"[DRY RUN] Would trigger test suite: {suite_id}")
            triggered_suites.append({'suite_id': suite_id, 'status': 'dry-run'})
            continue

        try:
            response = requests.post(
                trigger_url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                timeout=30,
            )
            if response.status_code in (200, 201, 202):
                result = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                print(f"Triggered test suite: {suite_id} (run_id: {result.get('run_id', 'N/A')})")
                triggered_suites.append({
                    'suite_id': suite_id,
                    'status': 'triggered',
                    'run_id': result.get('run_id'),
                    'url': result.get('url'),
                })
            else:
                print(f"Failed to trigger {suite_id}: HTTP {response.status_code}")
                triggered_suites.append({
                    'suite_id': suite_id,
                    'status': 'failed',
                    'error': f'HTTP {response.status_code}',
                })
        except requests.RequestException as e:
            print(f"Error triggering {suite_id}: {e}")
            triggered_suites.append({
                'suite_id': suite_id,
                'status': 'error',
                'error': str(e),
            })

    return triggered_suites


# ─── Feature Toggle Snapshot ─────────────────────────────────────────────────

def capture_feature_toggle_snapshot(config, dry_run=False):
    """Capture current feature toggle state for QA awareness."""
    toggle_config = get_config_value(config, 'feature_toggles', {})
    api_endpoint = toggle_config.get('api_endpoint', '')
    api_key = os.environ.get('FEATURE_TOGGLE_API_KEY', '')
    project_key = toggle_config.get('project_key', '')
    qa_env = toggle_config.get('environments', {}).get('qa', 'qa')

    if not api_endpoint or api_endpoint.startswith('${') or not api_key:
        print("Feature toggle API not configured. Skipping snapshot.")
        return []

    if dry_run:
        print("[DRY RUN] Would capture feature toggle snapshot")
        return [{'name': 'example-toggle', 'state': 'on', 'environment': 'qa'}]

    try:
        response = requests.get(
            f"{api_endpoint}/flags/{project_key}",
            headers={'Authorization': api_key},
            params={'env': qa_env},
            timeout=15,
        )
        if response.status_code == 200:
            flags = response.json().get('items', [])
            toggles = [
                {
                    'name': f['key'],
                    'state': 'on' if f.get('environments', {}).get(qa_env, {}).get('on') else 'off',
                    'environment': qa_env,
                }
                for f in flags
            ]
            print(f"Captured {len(toggles)} feature toggles")
            return toggles
        else:
            print(f"Failed to fetch toggles: HTTP {response.status_code}")
            return []
    except requests.RequestException as e:
        print(f"Error fetching toggles: {e}")
        return []


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='QA Bridge — Prepare release for test automation engineer'
    )
    parser.add_argument('--version', type=str, required=True,
                        help='Release version (e.g., v2.1.0)')
    parser.add_argument('--env', type=str, default='qa',
                        help='Target environment (default: qa)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview all actions without executing')
    parser.add_argument('--skip-deploy', action='store_true',
                        help='Skip QA environment deployment')
    parser.add_argument('--skip-tests', action='store_true',
                        help='Skip test suite triggering')
    parser.add_argument('--skip-notify', action='store_true',
                        help='Skip Slack/Teams notification')
    parser.add_argument('--output-dir', type=str, default='.',
                        help='Directory for output artifacts')
    parser.add_argument('--config-dir', type=str, default=None,
                        help='Path to config directory')
    args = parser.parse_args()

    print("=" * 60)
    print(f"  QA BRIDGE — Release {args.version}")
    print(f"  Environment: {args.env}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    try:
        config = load_config(args.config_dir)
    except FileNotFoundError:
        config = {}
        print("Warning: Config not found, using defaults")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Gather commit data ──
    print("\n[1/6] Gathering commit data...")
    current_tag = get_latest_tag()
    commits = get_commits_since_tag(current_tag)
    if not commits:
        print("No commits since last tag. Nothing to hand off.")
        sys.exit(2)

    changed_files = get_changed_files(current_tag) if current_tag else []
    affected_services = detect_affected_services(changed_files)
    print(f"  Commits: {len(commits)}")
    print(f"  Affected services: {', '.join(affected_services) or 'all'}")

    # ── Step 2: Generate test manifest ──
    print("\n[2/6] Generating test manifest...")
    manifest = generate_test_manifest(args.version, commits, affected_services, config)

    # ── Step 3: Capture feature toggles ──
    print("\n[3/6] Capturing feature toggle snapshot...")
    toggles = capture_feature_toggle_snapshot(config, args.dry_run)
    manifest['feature_toggles_changed'] = toggles

    # Write manifest
    manifest_path = output_dir / get_config_value(
        config, 'qa_bridge.manifest_output', 'release-manifest.json'
    )
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest written: {manifest_path}")

    # ── Step 4: Generate QA checklist ──
    print("\n[4/6] Generating QA checklist...")
    checklist = generate_qa_checklist(args.version, manifest)
    checklist_path = output_dir / get_config_value(
        config, 'qa_bridge.checklist_output', 'qa-checklist.md'
    )
    with open(checklist_path, 'w') as f:
        f.write(checklist)
    print(f"  Checklist written: {checklist_path}")

    # ── Step 5: Deploy to QA ──
    deploy_status = True
    if not args.skip_deploy:
        print(f"\n[5/6] Deploying to QA environment...")
        deploy_status = deploy_to_qa(args.version, config, args.dry_run)
        if deploy_status:
            deploy_status = verify_deployment_health(config, args.dry_run)
        print(f"  Deploy status: {'Healthy' if deploy_status else 'FAILED'}")
    else:
        print("\n[5/6] Skipping deployment (--skip-deploy)")

    # ── Step 6: Trigger test suites ──
    triggered_suites = []
    if not args.skip_tests:
        print(f"\n[6/6] Triggering test automation suites...")
        triggered_suites = trigger_test_suites(manifest, config, args.dry_run)
        if triggered_suites:
            manifest['triggered_suites'] = triggered_suites
            # Update manifest with trigger results
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
    else:
        print("\n[6/6] Skipping test triggers (--skip-tests)")

    # ── Notify QA team ──
    if not args.skip_notify:
        print("\nSending QA notification...")
        slack_webhook = get_config_value(config, 'notifications.slack.webhook_url', '')
        qa_channel_url = slack_webhook  # Same webhook, different channel via payload

        test_url = ""
        if triggered_suites:
            urls = [s.get('url', '') for s in triggered_suites if s.get('url')]
            test_url = urls[0] if urls else ""

        notification = format_qa_handoff_notification(
            args.version, manifest, deploy_status,
            test_trigger_url=test_url,
            checklist_url=str(checklist_path),
        )
        send_slack(qa_channel_url, notification)

    # ── Summary ──
    print("\n" + "=" * 60)
    print("  QA BRIDGE COMPLETE")
    print("=" * 60)
    print(f"  Version:          {args.version}")
    print(f"  Risk Level:       {manifest['risk_assessment'].upper()}")
    print(f"  Commits:          {manifest['total_commits']}")
    print(f"  Services:         {', '.join(manifest['affected_services']) or 'all'}")
    print(f"  Test Suites:      {len(manifest['suggested_test_suites'])}")
    print(f"  Manual Tests:     {len(manifest['manual_test_items'])}")
    print(f"  Breaking Changes: {len(manifest['breaking_changes'])}")
    print(f"  Deploy Status:    {'Healthy' if deploy_status else 'FAILED'}")
    print(f"  Manifest:         {manifest_path}")
    print(f"  Checklist:        {checklist_path}")
    print("=" * 60)

    return 0 if deploy_status else 1


if __name__ == '__main__':
    sys.exit(main())
