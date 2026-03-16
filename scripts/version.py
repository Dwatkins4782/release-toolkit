#!/usr/bin/env python3
"""
Semantic Version Calculator
===========================
Calculates the next semantic version based on conventional commits since the last tag.

Usage:
    python scripts/version.py                    # Auto-detect bump from commits
    python scripts/version.py --bump minor       # Force a minor bump
    python scripts/version.py --dry-run          # Preview without creating tag
    python scripts/version.py --pre-release rc   # Create pre-release (e.g., v2.1.0-rc.1)

Exit codes:
    0 — Success
    1 — Error
    2 — No commits since last tag (nothing to release)
"""

import sys
import os
import argparse
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.utils.config_loader import load_config, get_config_value
from scripts.utils.git_utils import (
    get_latest_tag, get_commits_since_tag, parse_conventional_commit,
    create_tag, get_changed_files, detect_affected_services, get_diff_stats
)


def parse_semver(tag):
    """Parse a semver tag (e.g., 'v1.2.3') into components."""
    tag = tag.lstrip('v')
    # Handle pre-release (e.g., 1.2.3-rc.1)
    pre_release = None
    if '-' in tag:
        tag, pre_release = tag.split('-', 1)
    parts = tag.split('.')
    return {
        'major': int(parts[0]) if len(parts) > 0 else 0,
        'minor': int(parts[1]) if len(parts) > 1 else 0,
        'patch': int(parts[2]) if len(parts) > 2 else 0,
        'pre_release': pre_release,
    }


def bump_version(current, bump_type, pre_release=None):
    """Calculate the next version based on bump type."""
    ver = parse_semver(current) if current else {'major': 0, 'minor': 0, 'patch': 0, 'pre_release': None}

    if bump_type == 'major':
        ver['major'] += 1
        ver['minor'] = 0
        ver['patch'] = 0
    elif bump_type == 'minor':
        ver['minor'] += 1
        ver['patch'] = 0
    elif bump_type == 'patch':
        ver['patch'] += 1

    version = f"v{ver['major']}.{ver['minor']}.{ver['patch']}"

    if pre_release:
        # Find the next pre-release number
        pre_num = 1
        if ver.get('pre_release') and ver['pre_release'].startswith(pre_release):
            try:
                pre_num = int(ver['pre_release'].split('.')[-1]) + 1
            except (ValueError, IndexError):
                pass
        version += f"-{pre_release}.{pre_num}"

    return version


def determine_bump_type(commits, config=None):
    """Analyze conventional commits to determine the appropriate version bump."""
    if not commits:
        return None

    has_breaking = False
    has_feature = False
    has_fix = False
    parsed_commits = []

    for commit in commits:
        parsed = parse_conventional_commit(commit['subject'])
        parsed['hash'] = commit['hash']
        parsed['author'] = commit['author']
        parsed_commits.append(parsed)

        if parsed['breaking']:
            has_breaking = True
        if parsed['type'] in ('feat', 'feature'):
            has_feature = True
        if parsed['type'] in ('fix', 'bugfix', 'perf', 'refactor', 'security'):
            has_fix = True

    if has_breaking:
        return 'major', parsed_commits
    elif has_feature:
        return 'minor', parsed_commits
    elif has_fix:
        return 'patch', parsed_commits
    else:
        return 'patch', parsed_commits  # Default to patch for any changes


def generate_version_summary(version, bump_type, parsed_commits, current_tag,
                               affected_services, stats):
    """Generate a JSON summary of the version calculation."""
    summary = {
        'version': version,
        'previous_version': current_tag or 'none',
        'bump_type': bump_type,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'commit_count': len(parsed_commits),
        'affected_services': affected_services,
        'stats': stats,
        'breakdown': {
            'features': len([c for c in parsed_commits if c['type'] in ('feat', 'feature')]),
            'fixes': len([c for c in parsed_commits if c['type'] in ('fix', 'bugfix')]),
            'performance': len([c for c in parsed_commits if c['type'] == 'perf']),
            'breaking_changes': len([c for c in parsed_commits if c['breaking']]),
            'other': len([c for c in parsed_commits if c['type'] not in
                         ('feat', 'feature', 'fix', 'bugfix', 'perf')]),
        },
        'tickets': list(set(
            ticket for c in parsed_commits for ticket in c.get('tickets', [])
        )),
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description='Calculate next semantic version')
    parser.add_argument('--bump', choices=['major', 'minor', 'patch', 'auto'],
                        default='auto', help='Version bump type (default: auto)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview version without creating tag')
    parser.add_argument('--pre-release', type=str, default=None,
                        help='Pre-release identifier (e.g., rc, beta, alpha)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output version summary to JSON file')
    parser.add_argument('--config-dir', type=str, default=None,
                        help='Path to config directory')
    args = parser.parse_args()

    try:
        config = load_config(args.config_dir)
    except FileNotFoundError:
        config = {}

    # Get current version
    current_tag = get_latest_tag()
    print(f"Current version: {current_tag or 'none (first release)'}")

    # Get commits since last tag
    commits = get_commits_since_tag(current_tag)
    if not commits:
        print("No commits since last tag. Nothing to release.")
        sys.exit(2)

    print(f"Commits since last tag: {len(commits)}")

    # Determine bump type
    if args.bump == 'auto':
        bump_result = determine_bump_type(commits, config)
        if bump_result is None:
            print("No releasable commits found.")
            sys.exit(2)
        bump_type, parsed_commits = bump_result
    else:
        bump_type = args.bump
        parsed_commits = [parse_conventional_commit(c['subject']) for c in commits]
        for i, pc in enumerate(parsed_commits):
            pc['hash'] = commits[i]['hash']
            pc['author'] = commits[i]['author']

    # Calculate new version
    new_version = bump_version(current_tag, bump_type, args.pre_release)
    print(f"Bump type: {bump_type}")
    print(f"New version: {new_version}")

    # Detect affected services
    changed_files = get_changed_files(current_tag) if current_tag else []
    affected_services = detect_affected_services(changed_files)
    if affected_services:
        print(f"Affected services: {', '.join(affected_services)}")

    # Get diff stats
    stats = get_diff_stats(current_tag) if current_tag else {}

    # Generate summary
    summary = generate_version_summary(
        new_version, bump_type, parsed_commits, current_tag,
        affected_services, stats
    )

    # Output summary
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"Version summary written to: {args.output}")

    # Create tag (unless dry-run)
    if args.dry_run:
        print(f"\n[DRY RUN] Would create tag: {new_version}")
        print(json.dumps(summary, indent=2))
    else:
        tag_message = (
            f"Release {new_version}\n\n"
            f"Commits: {len(commits)}\n"
            f"Bump: {bump_type}\n"
            f"Services: {', '.join(affected_services) if affected_services else 'all'}\n"
            f"Tickets: {', '.join(summary['tickets']) if summary['tickets'] else 'none'}"
        )
        try:
            create_tag(new_version, tag_message, push=True)
            print(f"\nTag {new_version} created and pushed successfully.")
        except RuntimeError as e:
            # Tag locally if push fails (no remote configured)
            try:
                create_tag(new_version, tag_message, push=False)
                print(f"\nTag {new_version} created locally (push skipped: {e}).")
            except RuntimeError as e2:
                print(f"\nError creating tag: {e2}")
                sys.exit(1)

    # Print version for CI/CD consumption (last line = parseable output)
    print(f"\nVERSION={new_version}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
