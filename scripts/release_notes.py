#!/usr/bin/env python3
"""
Release Notes Generator
========================
Generates categorized release notes from conventional commits.

Usage:
    python scripts/release_notes.py                          # Markdown to stdout
    python scripts/release_notes.py --format json            # JSON output
    python scripts/release_notes.py --output CHANGELOG.md    # Append to changelog
    python scripts/release_notes.py --version v2.1.0         # Specify version explicitly

Output formats: md (Markdown), json, html
"""

import sys
import os
import argparse
import json
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.utils.config_loader import load_config
from scripts.utils.git_utils import (
    get_latest_tag, get_commits_since_tag, parse_conventional_commit,
    get_changed_files, detect_affected_services, get_diff_stats, get_contributors
)


# Commit type display labels and ordering
TYPE_LABELS = {
    'feat': ('Features', 'rocket'),
    'feature': ('Features', 'rocket'),
    'fix': ('Bug Fixes', 'bug'),
    'bugfix': ('Bug Fixes', 'bug'),
    'perf': ('Performance Improvements', 'zap'),
    'security': ('Security', 'lock'),
    'refactor': ('Code Refactoring', 'recycle'),
    'docs': ('Documentation', 'memo'),
    'test': ('Tests', 'white_check_mark'),
    'ci': ('CI/CD', 'construction_worker'),
    'build': ('Build System', 'hammer'),
    'chore': ('Chores', 'wrench'),
}

TYPE_ORDER = ['feat', 'feature', 'fix', 'bugfix', 'security', 'perf',
              'refactor', 'docs', 'test', 'ci', 'build', 'chore']


def categorize_commits(commits):
    """Parse and categorize commits by type."""
    categories = defaultdict(list)
    breaking_changes = []
    all_tickets = set()
    manual_test_items = []

    for commit in commits:
        parsed = parse_conventional_commit(commit['subject'])
        parsed['hash'] = commit['hash']
        parsed['author'] = commit.get('author', 'unknown')
        parsed['date'] = commit.get('date', '')

        commit_type = parsed['type']
        categories[commit_type].append(parsed)

        if parsed['breaking']:
            breaking_changes.append(parsed)

        all_tickets.update(parsed.get('tickets', []))

        if parsed.get('manual_test'):
            manual_test_items.append(parsed)

    return categories, breaking_changes, list(all_tickets), manual_test_items


def generate_markdown(version, categories, breaking_changes, tickets,
                       manual_test_items, affected_services, stats, contributors):
    """Generate Markdown release notes."""
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    lines = []

    lines.append(f"## [{version}] - {date_str}\n")

    # Summary stats
    total_commits = sum(len(v) for v in categories.values())
    lines.append(f"**{total_commits} commits** | "
                 f"**{stats.get('files_changed', 0)} files changed** | "
                 f"**+{stats.get('insertions', 0)} -{stats.get('deletions', 0)}**\n")

    # Affected services
    if affected_services:
        lines.append(f"**Affected Services:** {', '.join(affected_services)}\n")

    # Breaking changes (top priority)
    if breaking_changes:
        lines.append("### BREAKING CHANGES\n")
        for change in breaking_changes:
            scope = f"**{change['scope']}:** " if change['scope'] else ""
            ticket_refs = ' '.join(f"[{t}]" for t in change.get('tickets', []))
            lines.append(f"- {scope}{change['description']} {ticket_refs} "
                        f"(`{change['hash'][:7]}`)")
        lines.append("")

    # Categorized changes
    for commit_type in TYPE_ORDER:
        if commit_type not in categories:
            continue

        label, _ = TYPE_LABELS.get(commit_type, (commit_type.title(), ''))
        # Skip if this type was already shown in breaking changes
        non_breaking = [c for c in categories[commit_type] if not c['breaking']]
        if not non_breaking:
            continue

        lines.append(f"### {label}\n")
        for commit in non_breaking:
            scope = f"**{commit['scope']}:** " if commit['scope'] else ""
            ticket_refs = ' '.join(f"[{t}]" for t in commit.get('tickets', []))
            lines.append(f"- {scope}{commit['description']} {ticket_refs} "
                        f"(`{commit['hash'][:7]}`)")
        lines.append("")

    # Tickets referenced
    if tickets:
        lines.append("### Referenced Work Items\n")
        for ticket in sorted(tickets):
            lines.append(f"- {ticket}")
        lines.append("")

    # Manual test items
    if manual_test_items:
        lines.append("### Manual Testing Required\n")
        for item in manual_test_items:
            scope = f"[{item['scope']}] " if item['scope'] else ""
            lines.append(f"- [ ] {scope}{item['description']} (`{item['hash'][:7]}`)")
        lines.append("")

    # Contributors
    if contributors:
        lines.append("### Contributors\n")
        for contributor in contributors:
            lines.append(f"- {contributor['name']} ({contributor['email']})")
        lines.append("")

    return '\n'.join(lines)


def generate_json(version, categories, breaking_changes, tickets,
                   manual_test_items, affected_services, stats, contributors):
    """Generate JSON release notes (for QA bridge and API consumption)."""
    date_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    all_commits = []
    for type_name, commits in categories.items():
        for c in commits:
            all_commits.append({
                'type': c['type'],
                'scope': c['scope'],
                'description': c['description'],
                'hash': c['hash'][:7],
                'author': c.get('author', 'unknown'),
                'breaking': c.get('breaking', False),
                'tickets': c.get('tickets', []),
                'manual_test': c.get('manual_test', False),
            })

    return {
        'version': version,
        'date': date_str,
        'total_commits': len(all_commits),
        'affected_services': affected_services,
        'stats': stats,
        'breaking_changes': [
            {'description': c['description'], 'scope': c['scope'], 'hash': c['hash'][:7]}
            for c in breaking_changes
        ],
        'commits': all_commits,
        'tickets': sorted(tickets),
        'manual_test_items': [
            {'description': c['description'], 'scope': c['scope'], 'hash': c['hash'][:7]}
            for c in manual_test_items
        ],
        'contributors': contributors,
        'summary': {
            'features': len(categories.get('feat', []) + categories.get('feature', [])),
            'fixes': len(categories.get('fix', []) + categories.get('bugfix', [])),
            'performance': len(categories.get('perf', [])),
            'security': len(categories.get('security', [])),
            'other': sum(len(v) for k, v in categories.items()
                        if k not in ('feat', 'feature', 'fix', 'bugfix', 'perf', 'security')),
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Generate release notes')
    parser.add_argument('--version', type=str, default=None,
                        help='Release version (auto-detected from latest tag if not specified)')
    parser.add_argument('--format', choices=['md', 'json', 'html'], default='md',
                        help='Output format (default: md)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output file (prepend to CHANGELOG.md or write new file)')
    parser.add_argument('--config-dir', type=str, default=None,
                        help='Path to config directory')
    args = parser.parse_args()

    try:
        config = load_config(args.config_dir)
    except FileNotFoundError:
        config = {}

    # Determine version
    current_tag = get_latest_tag()
    version = args.version or current_tag or 'v0.1.0'

    # Get commits
    # If version was specified, get commits between previous tag and this one
    commits = get_commits_since_tag(current_tag)
    if not commits:
        print("No commits found for release notes.", file=sys.stderr)
        sys.exit(2)

    # Categorize commits
    categories, breaking_changes, tickets, manual_test_items = categorize_commits(commits)

    # Detect affected services
    changed_files = get_changed_files(current_tag) if current_tag else []
    affected_services = detect_affected_services(changed_files)

    # Get stats and contributors
    stats = get_diff_stats(current_tag) if current_tag else {}
    contributors = get_contributors(current_tag)

    # Generate output
    if args.format == 'json':
        output = generate_json(version, categories, breaking_changes, tickets,
                                manual_test_items, affected_services, stats, contributors)
        result = json.dumps(output, indent=2)
    elif args.format == 'md':
        result = generate_markdown(version, categories, breaking_changes, tickets,
                                    manual_test_items, affected_services, stats, contributors)
    else:
        result = generate_markdown(version, categories, breaking_changes, tickets,
                                    manual_test_items, affected_services, stats, contributors)

    # Write output
    if args.output:
        if args.output.endswith('CHANGELOG.md') and os.path.exists(args.output):
            # Prepend to existing changelog
            with open(args.output, 'r') as f:
                existing = f.read()
            with open(args.output, 'w') as f:
                f.write(result + '\n---\n\n' + existing)
            print(f"Release notes prepended to {args.output}")
        else:
            with open(args.output, 'w') as f:
                f.write(result)
            print(f"Release notes written to {args.output}")
    else:
        print(result)

    return 0


if __name__ == '__main__':
    sys.exit(main())
