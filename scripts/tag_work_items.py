#!/usr/bin/env python3
"""
Work Item Tagger
================
Tags Jira issues (and GitHub Issues) referenced in release commits
with the release version, adds comments, and optionally transitions status.

Usage:
    python scripts/tag_work_items.py --version v2.1.0                # Tag all tickets
    python scripts/tag_work_items.py --version v2.1.0 --dry-run      # Preview only
    python scripts/tag_work_items.py --version v2.1.0 --transition   # Also transition status
    python scripts/tag_work_items.py --version v2.1.0 --provider github  # Use GitHub Issues
"""

import sys
import os
import argparse
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.utils.config_loader import load_config, get_config_value
from scripts.utils.git_utils import (
    get_latest_tag, get_commits_since_tag, parse_conventional_commit
)
from scripts.utils.jira_client import JiraClient


def extract_tickets(commits, provider='jira'):
    """Extract unique ticket references from commits."""
    tickets = {}
    for commit in commits:
        parsed = parse_conventional_commit(commit['subject'])
        for ticket in parsed.get('tickets', []):
            if ticket.startswith('#') and provider != 'github':
                continue
            if not ticket.startswith('#') and provider == 'github':
                continue

            if ticket not in tickets:
                tickets[ticket] = {
                    'key': ticket,
                    'commits': [],
                    'types': set(),
                    'scopes': set(),
                    'breaking': False,
                }
            tickets[ticket]['commits'].append({
                'hash': commit['hash'][:7],
                'subject': commit['subject'],
                'author': commit.get('author', 'unknown'),
            })
            tickets[ticket]['types'].add(parsed['type'])
            if parsed['scope']:
                tickets[ticket]['scopes'].add(parsed['scope'])
            if parsed['breaking']:
                tickets[ticket]['breaking'] = True

    # Convert sets to lists for JSON serialization
    for ticket in tickets.values():
        ticket['types'] = list(ticket['types'])
        ticket['scopes'] = list(ticket['scopes'])

    return tickets


def tag_jira_tickets(tickets, version, config, dry_run=False, transition=False):
    """Tag Jira tickets with release information."""
    jira = JiraClient(
        base_url=get_config_value(config, 'jira.base_url'),
        email=os.environ.get('JIRA_USER_EMAIL'),
        api_token=os.environ.get('JIRA_API_TOKEN'),
    )

    project_key = get_config_value(config, 'jira.project_key', 'POS')
    release_transition_id = get_config_value(config, 'jira.transition_ids.released', '61')

    results = {
        'version': version,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'total_tickets': len(tickets),
        'tagged': [],
        'skipped': [],
        'errors': [],
    }

    for key, ticket_info in tickets.items():
        print(f"\nProcessing: {key}")
        print(f"  Commits: {len(ticket_info['commits'])}")
        print(f"  Types: {', '.join(ticket_info['types'])}")

        if dry_run:
            print(f"  [DRY RUN] Would tag with: released-in-{version}")
            print(f"  [DRY RUN] Would set fix version: {version}")
            if transition:
                print(f"  [DRY RUN] Would transition to: Released")
            results['tagged'].append({
                'key': key,
                'status': 'dry-run',
                'actions': ['label', 'comment', 'fix-version'] +
                           (['transition'] if transition else []),
            })
            continue

        try:
            # Verify issue exists
            issue = jira.get_issue(key)
            if not issue:
                print(f"  SKIP: Issue {key} not found")
                results['skipped'].append({'key': key, 'reason': 'not found'})
                continue

            actions = []

            # Add release label
            label = f"released-in-{version}"
            if jira.add_label(key, label):
                print(f"  Added label: {label}")
                actions.append('label')

            # Set fix version
            if jira.set_fix_version(key, version, project_key):
                print(f"  Set fix version: {version}")
                actions.append('fix-version')

            # Add release comment
            commit_list = "\n".join(
                f"  - {c['hash']}: {c['subject']} ({c['author']})"
                for c in ticket_info['commits']
            )
            comment = (
                f"Included in release {version}\n\n"
                f"Commits:\n{commit_list}\n\n"
                f"Release pipeline: {os.environ.get('CI_PIPELINE_URL', 'N/A')}"
            )
            if jira.add_comment(key, comment):
                print(f"  Added release comment")
                actions.append('comment')

            # Transition to Released (if requested)
            if transition:
                if jira.transition_issue(key, release_transition_id):
                    print(f"  Transitioned to: Released")
                    actions.append('transition')

            results['tagged'].append({
                'key': key,
                'status': 'success',
                'actions': actions,
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            results['errors'].append({'key': key, 'error': str(e)})

    return results


def tag_github_issues(tickets, version, dry_run=False):
    """Tag GitHub issues with release information (via gh CLI)."""
    import subprocess

    results = {
        'version': version,
        'total_tickets': len(tickets),
        'tagged': [],
        'errors': [],
    }

    for key, ticket_info in tickets.items():
        issue_num = key.lstrip('#')
        print(f"\nProcessing: GitHub Issue #{issue_num}")

        if dry_run:
            print(f"  [DRY RUN] Would add label: release-{version}")
            print(f"  [DRY RUN] Would add comment with release info")
            results['tagged'].append({'key': key, 'status': 'dry-run'})
            continue

        try:
            # Add label
            subprocess.run(
                ['gh', 'issue', 'edit', issue_num, '--add-label', f'release-{version}'],
                capture_output=True, text=True, check=True
            )
            print(f"  Added label: release-{version}")

            # Add comment
            comment = (
                f"This issue was included in release **{version}**.\n\n"
                f"Commits: {len(ticket_info['commits'])}"
            )
            subprocess.run(
                ['gh', 'issue', 'comment', issue_num, '--body', comment],
                capture_output=True, text=True, check=True
            )
            print(f"  Added release comment")

            results['tagged'].append({'key': key, 'status': 'success'})

        except subprocess.CalledProcessError as e:
            print(f"  ERROR: {e.stderr}")
            results['errors'].append({'key': key, 'error': e.stderr})

    return results


def main():
    parser = argparse.ArgumentParser(description='Tag work items with release version')
    parser.add_argument('--version', type=str, required=True,
                        help='Release version (e.g., v2.1.0)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview tagging without making changes')
    parser.add_argument('--transition', action='store_true',
                        help='Also transition Jira issues to Released status')
    parser.add_argument('--provider', choices=['jira', 'github'], default='jira',
                        help='Issue tracker provider (default: jira)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output results to JSON file')
    parser.add_argument('--config-dir', type=str, default=None,
                        help='Path to config directory')
    args = parser.parse_args()

    try:
        config = load_config(args.config_dir)
    except FileNotFoundError:
        config = {}

    # Get commits since last tag
    current_tag = get_latest_tag()
    commits = get_commits_since_tag(current_tag)

    if not commits:
        print("No commits found. Nothing to tag.")
        sys.exit(2)

    # Extract tickets
    tickets = extract_tickets(commits, args.provider)
    if not tickets:
        print("No work item references found in commits.")
        print("Tip: Use conventional commit format with ticket refs, e.g.:")
        print("  feat(pos-terminal): add NFC payment support POS-1234")
        sys.exit(2)

    print(f"Found {len(tickets)} unique tickets in {len(commits)} commits")
    print(f"Provider: {args.provider}")
    if args.dry_run:
        print("MODE: DRY RUN (no changes will be made)")

    # Tag tickets
    if args.provider == 'jira':
        results = tag_jira_tickets(tickets, args.version, config,
                                    args.dry_run, args.transition)
    else:
        results = tag_github_issues(tickets, args.version, args.dry_run)

    # Print summary
    print(f"\n{'=' * 50}")
    print(f"TAGGING SUMMARY: {args.version}")
    print(f"{'=' * 50}")
    print(f"Total tickets: {results['total_tickets']}")
    print(f"Tagged: {len(results['tagged'])}")
    print(f"Errors: {len(results.get('errors', []))}")
    if results.get('skipped'):
        print(f"Skipped: {len(results['skipped'])}")

    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults written to: {args.output}")

    return 0 if not results.get('errors') else 1


if __name__ == '__main__':
    sys.exit(main())
