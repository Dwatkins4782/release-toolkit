#!/usr/bin/env python3
"""
Multi-Repo Release Correlator
===============================
Correlates changes across multiple GitHub/GitLab repositories that
comprise a single platform release. Identifies shared Jira tickets,
maps services to deployment targets, and generates a cross-repo manifest.

Usage:
    python scripts/correlate_releases.py --version v2.1.0
    python scripts/correlate_releases.py --version v2.1.0 --repos repo1,repo2,repo3
    python scripts/correlate_releases.py --version v2.1.0 --output correlation-report.json

Reduces dependency on large release coordination meetings by providing
automated cross-repo release intelligence.
"""

import sys
import os
import argparse
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.utils.config_loader import load_config, get_config_value
from scripts.utils.git_utils import parse_conventional_commit


def get_repo_release_info(repo_url, repo_name, temp_dir, since_tag=None):
    """Clone/fetch a repo and extract release information."""
    repo_dir = Path(temp_dir) / repo_name

    print(f"  Fetching: {repo_name}...")

    try:
        if repo_dir.exists():
            subprocess.run(
                ['git', 'fetch', '--tags'], cwd=str(repo_dir),
                capture_output=True, text=True, timeout=60
            )
        else:
            subprocess.run(
                ['git', 'clone', '--depth', '100', repo_url, str(repo_dir)],
                capture_output=True, text=True, timeout=120
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"  Warning: Could not fetch {repo_name}")
        return None

    # Get latest tag
    try:
        result = subprocess.run(
            ['git', 'tag', '--list', 'v*', '--sort=-v:refname'],
            capture_output=True, text=True, cwd=str(repo_dir)
        )
        tags = [t for t in result.stdout.strip().split('\n') if t]
        latest_tag = tags[0] if tags else None
        previous_tag = tags[1] if len(tags) > 1 else None
    except Exception:
        latest_tag = None
        previous_tag = None

    # Get commits since last tag (or since_tag if specified)
    ref_from = since_tag or previous_tag
    log_range = f"{ref_from}..HEAD" if ref_from else "HEAD"

    try:
        result = subprocess.run(
            ['git', 'log', log_range, '--pretty=format:%H|%s|%an|%aI', '--no-merges'],
            capture_output=True, text=True, cwd=str(repo_dir)
        )
        commits = []
        for line in result.stdout.strip().split('\n'):
            if '|' in line:
                parts = line.split('|', 3)
                parsed = parse_conventional_commit(parts[1])
                commits.append({
                    'hash': parts[0][:7],
                    'subject': parts[1],
                    'author': parts[2],
                    'date': parts[3] if len(parts) > 3 else '',
                    'type': parsed['type'],
                    'scope': parsed['scope'],
                    'tickets': parsed['tickets'],
                    'breaking': parsed['breaking'],
                })
    except Exception:
        commits = []

    return {
        'name': repo_name,
        'url': repo_url,
        'latest_tag': latest_tag,
        'previous_tag': previous_tag,
        'commits': commits,
        'commit_count': len(commits),
    }


def correlate_tickets(repo_infos):
    """Find tickets that appear across multiple repositories."""
    ticket_to_repos = defaultdict(list)

    for repo in repo_infos:
        if not repo:
            continue
        repo_tickets = set()
        for commit in repo['commits']:
            for ticket in commit.get('tickets', []):
                repo_tickets.add(ticket)
        for ticket in repo_tickets:
            ticket_to_repos[ticket].append(repo['name'])

    shared_tickets = {
        ticket: repos for ticket, repos in ticket_to_repos.items()
        if len(repos) > 1
    }

    single_repo_tickets = {
        ticket: repos[0] for ticket, repos in ticket_to_repos.items()
        if len(repos) == 1
    }

    return shared_tickets, single_repo_tickets


def generate_correlation_report(version, repo_infos, config):
    """Generate a comprehensive cross-repo correlation report."""
    shared_tickets, single_tickets = correlate_tickets(repo_infos)

    # Determine affected edge clusters
    edge_repos = []
    services_config = get_config_value(config, 'repositories.services', [])
    for repo in repo_infos:
        if not repo:
            continue
        for svc_config in services_config:
            if svc_config['name'] == repo['name'] and svc_config.get('edge_deploy'):
                if repo['commits']:
                    edge_repos.append(repo['name'])

    # Count breaking changes across all repos
    total_breaking = sum(
        len([c for c in repo['commits'] if c.get('breaking')])
        for repo in repo_infos if repo
    )

    # Aggregate contributors
    all_contributors = set()
    for repo in repo_infos:
        if repo:
            for commit in repo['commits']:
                all_contributors.add(commit.get('author', 'unknown'))

    report = {
        'release': version,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'repos': {},
        'summary': {
            'total_repos': len([r for r in repo_infos if r]),
            'total_commits': sum(r['commit_count'] for r in repo_infos if r),
            'total_breaking_changes': total_breaking,
            'total_tickets': len(shared_tickets) + len(single_tickets),
            'shared_tickets_count': len(shared_tickets),
            'contributors': sorted(all_contributors),
            'edge_cluster_affected': len(edge_repos) > 0,
            'affected_edge_services': edge_repos,
        },
        'shared_tickets': {
            ticket: {'repos': repos, 'cross_service': True}
            for ticket, repos in shared_tickets.items()
        },
        'single_repo_tickets': single_tickets,
        'risk_assessment': 'low',
    }

    # Per-repo details
    for repo in repo_infos:
        if not repo:
            continue
        report['repos'][repo['name']] = {
            'from': repo['previous_tag'] or 'initial',
            'to': repo['latest_tag'] or 'HEAD',
            'commits': repo['commit_count'],
            'breaking_changes': len([c for c in repo['commits'] if c.get('breaking')]),
            'types': dict(defaultdict(int, {
                c['type']: sum(1 for x in repo['commits'] if x['type'] == c['type'])
                for c in repo['commits']
            })),
        }

    # Risk assessment
    if total_breaking > 0 or len(shared_tickets) > 5:
        report['risk_assessment'] = 'high'
    elif len(edge_repos) > 0 or report['summary']['total_commits'] > 30:
        report['risk_assessment'] = 'medium'

    return report


def print_report_summary(report):
    """Print a human-readable summary of the correlation report."""
    print("\n" + "=" * 60)
    print(f"  CROSS-REPO RELEASE CORRELATION: {report['release']}")
    print("=" * 60)

    print(f"\n  Repositories:      {report['summary']['total_repos']}")
    print(f"  Total Commits:     {report['summary']['total_commits']}")
    print(f"  Breaking Changes:  {report['summary']['total_breaking_changes']}")
    print(f"  Work Items:        {report['summary']['total_tickets']}")
    print(f"  Shared Tickets:    {report['summary']['shared_tickets_count']}")
    print(f"  Risk Level:        {report['risk_assessment'].upper()}")
    print(f"  Edge Clusters:     {'YES' if report['summary']['edge_cluster_affected'] else 'No'}")

    print(f"\n  Per-Repository Breakdown:")
    print(f"  {'Repository':<30} {'From':<12} {'To':<12} {'Commits':<10} {'Breaking':<10}")
    print(f"  {'-'*74}")
    for name, info in report['repos'].items():
        print(f"  {name:<30} {info['from']:<12} {info['to']:<12} "
              f"{info['commits']:<10} {info['breaking_changes']:<10}")

    if report['shared_tickets']:
        print(f"\n  Cross-Service Tickets (span multiple repos):")
        for ticket, info in report['shared_tickets'].items():
            print(f"    {ticket}: {', '.join(info['repos'])}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Correlate releases across repos')
    parser.add_argument('--version', type=str, required=True,
                        help='Release version (e.g., v2.1.0)')
    parser.add_argument('--repos', type=str, default=None,
                        help='Comma-separated repo names (default: from config)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output correlation report to JSON file')
    parser.add_argument('--config-dir', type=str, default=None,
                        help='Path to config directory')
    args = parser.parse_args()

    try:
        config = load_config(args.config_dir)
    except FileNotFoundError:
        config = {}

    # Determine repos to correlate
    if args.repos:
        repo_names = [r.strip() for r in args.repos.split(',')]
        services = get_config_value(config, 'repositories.services', [])
        repos = [
            {'name': name, 'repo_url': next(
                (s['repo_url'] for s in services if s['name'] == name), ''
            )}
            for name in repo_names
        ]
    else:
        repos = get_config_value(config, 'repositories.services', [])

    if not repos:
        print("No repositories configured. Use --repos or configure in release-config.yaml")
        sys.exit(1)

    print(f"Correlating {len(repos)} repositories for release {args.version}...")

    # Fetch and analyze each repo
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_infos = []
        for repo in repos:
            info = get_repo_release_info(
                repo.get('repo_url', ''), repo['name'], temp_dir
            )
            repo_infos.append(info)

    # Generate correlation report
    report = generate_correlation_report(args.version, repo_infos, config)

    # Print summary
    print_report_summary(report)

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nCorrelation report written to: {args.output}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
