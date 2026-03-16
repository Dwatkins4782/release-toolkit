#!/usr/bin/env python3
"""
Release Report Generator
=========================
Generates automated release reports that replace large coordination meetings.
Aggregates data from Git, Jira, CI/CD pipelines, and deployment status.

Usage:
    python scripts/release_report.py --version v2.1.0
    python scripts/release_report.py --version v2.1.0 --format html --output report.html
    python scripts/release_report.py --version v2.1.0 --format json
"""

import sys
import os
import argparse
import json
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.utils.config_loader import load_config, get_config_value
from scripts.utils.git_utils import (
    get_latest_tag, get_commits_since_tag, parse_conventional_commit,
    get_changed_files, detect_affected_services, get_diff_stats,
    get_contributors, get_commit_count
)


def calculate_dora_metrics(commits, previous_tag):
    """Calculate DORA metrics from commit data."""
    if not commits:
        return {}

    # Lead time: time from first commit to now
    dates = [c.get('date', '') for c in commits if c.get('date')]
    if dates:
        try:
            first_commit = min(dates)
            lead_time_str = first_commit
        except (ValueError, TypeError):
            lead_time_str = 'unknown'
    else:
        lead_time_str = 'unknown'

    return {
        'deployment_frequency': 'on-demand',
        'lead_time_for_changes': lead_time_str,
        'change_failure_rate': 'N/A (post-release metric)',
        'mean_time_to_recovery': 'N/A (post-release metric)',
        'commits_in_release': len(commits),
    }


def generate_markdown_report(version, data):
    """Generate a Markdown release report."""
    lines = []
    lines.append(f"# Release Report: {version}\n")
    lines.append(f"**Generated:** {data['generated_at']}")
    lines.append(f"**Previous Version:** {data['previous_version'] or 'N/A'}")
    lines.append(f"**Risk Assessment:** {data['risk_assessment'].upper()}\n")

    # Executive Summary
    lines.append("## Executive Summary\n")
    summary = data['summary']
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Commits | {summary['total_commits']} |")
    lines.append(f"| Features | {summary['features']} |")
    lines.append(f"| Bug Fixes | {summary['fixes']} |")
    lines.append(f"| Breaking Changes | {summary['breaking_changes']} |")
    lines.append(f"| Files Changed | {summary['files_changed']} |")
    lines.append(f"| Insertions | +{summary['insertions']} |")
    lines.append(f"| Deletions | -{summary['deletions']} |")
    lines.append(f"| Contributors | {summary['contributor_count']} |")
    lines.append(f"| Work Items | {summary['ticket_count']} |")
    lines.append(f"| Affected Services | {', '.join(summary['affected_services']) or 'All'} |")
    lines.append("")

    # DORA Metrics
    if data.get('dora_metrics'):
        lines.append("## DORA Metrics\n")
        dora = data['dora_metrics']
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        for key, value in dora.items():
            label = key.replace('_', ' ').title()
            lines.append(f"| {label} | {value} |")
        lines.append("")

    # Changes by Type
    lines.append("## Changes by Type\n")
    for type_name, count in sorted(data['changes_by_type'].items(),
                                      key=lambda x: -x[1]):
        bar = '#' * min(count, 30)
        lines.append(f"- **{type_name}**: {count} {bar}")
    lines.append("")

    # Work Items
    if data.get('tickets'):
        lines.append("## Referenced Work Items\n")
        for ticket in sorted(data['tickets']):
            lines.append(f"- {ticket}")
        lines.append("")

    # Contributors
    if data.get('contributors'):
        lines.append("## Contributors\n")
        for contrib in data['contributors']:
            lines.append(f"- {contrib['name']} ({contrib['email']})")
        lines.append("")

    # Deployment Readiness
    lines.append("## Deployment Readiness Checklist\n")
    lines.append(f"- [{'x' if not data['summary']['breaking_changes'] else ' '}] "
                f"No breaking changes (or migration plan documented)")
    lines.append(f"- [ ] Release notes reviewed")
    lines.append(f"- [ ] QA sign-off complete")
    lines.append(f"- [ ] Staging deployment verified")
    lines.append(f"- [ ] Rollback procedure tested")
    lines.append(f"- [ ] Monitoring alerts configured")
    lines.append(f"- [ ] Change request approved (ServiceNow)")
    lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Generate release report')
    parser.add_argument('--version', type=str, required=True,
                        help='Release version')
    parser.add_argument('--format', choices=['md', 'json', 'html'], default='md',
                        help='Output format')
    parser.add_argument('--output', type=str, default=None,
                        help='Output file path')
    parser.add_argument('--config-dir', type=str, default=None,
                        help='Path to config directory')
    args = parser.parse_args()

    try:
        config = load_config(args.config_dir)
    except FileNotFoundError:
        config = {}

    # Gather data
    current_tag = get_latest_tag()
    commits = get_commits_since_tag(current_tag)

    if not commits:
        print("No commits found for report.")
        sys.exit(2)

    # Parse commits
    changes_by_type = defaultdict(int)
    all_tickets = set()
    breaking_count = 0
    features = 0
    fixes = 0

    for commit in commits:
        parsed = parse_conventional_commit(commit['subject'])
        changes_by_type[parsed['type']] += 1
        all_tickets.update(parsed.get('tickets', []))
        if parsed['breaking']:
            breaking_count += 1
        if parsed['type'] in ('feat', 'feature'):
            features += 1
        if parsed['type'] in ('fix', 'bugfix'):
            fixes += 1

    # Get stats
    stats = get_diff_stats(current_tag) if current_tag else {}
    contributors = get_contributors(current_tag)
    changed_files = get_changed_files(current_tag) if current_tag else []
    affected_services = detect_affected_services(changed_files)
    dora = calculate_dora_metrics(commits, current_tag)

    # Risk assessment
    risk = 'low'
    if breaking_count > 0:
        risk = 'high'
    elif len(commits) > 20 or len(affected_services) > 3:
        risk = 'medium'

    # Build report data
    data = {
        'version': args.version,
        'previous_version': current_tag,
        'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'risk_assessment': risk,
        'summary': {
            'total_commits': len(commits),
            'features': features,
            'fixes': fixes,
            'breaking_changes': breaking_count,
            'files_changed': stats.get('files_changed', 0),
            'insertions': stats.get('insertions', 0),
            'deletions': stats.get('deletions', 0),
            'contributor_count': len(contributors),
            'ticket_count': len(all_tickets),
            'affected_services': affected_services,
        },
        'changes_by_type': dict(changes_by_type),
        'tickets': sorted(all_tickets),
        'contributors': contributors,
        'dora_metrics': dora,
    }

    # Generate output
    if args.format == 'json':
        result = json.dumps(data, indent=2)
    else:
        result = generate_markdown_report(args.version, data)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(result)
        print(f"Release report written to: {args.output}")
    else:
        print(result)

    return 0


if __name__ == '__main__':
    sys.exit(main())
