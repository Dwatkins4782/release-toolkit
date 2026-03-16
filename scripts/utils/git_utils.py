"""
Git Utilities — Parsing commits, managing tags, detecting changes.
"""

import re
import subprocess
import json
from datetime import datetime


def run_git(args, cwd=None):
    """Execute a git command and return stdout."""
    cmd = ["git"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def get_latest_tag(prefix="v"):
    """Find the most recent semver tag."""
    try:
        tags = run_git(["tag", "--list", f"{prefix}*", "--sort=-v:refname"])
        if not tags:
            return None
        return tags.split('\n')[0]
    except RuntimeError:
        return None


def get_commits_since_tag(tag=None, format_str=None):
    """Get all commits since the given tag (or all commits if no tag)."""
    if format_str is None:
        format_str = "%H|%s|%an|%ae|%aI"

    if tag:
        log_range = f"{tag}..HEAD"
    else:
        log_range = "HEAD"

    try:
        output = run_git(["log", log_range, f"--pretty=format:{format_str}", "--no-merges"])
    except RuntimeError:
        return []

    if not output:
        return []

    commits = []
    for line in output.split('\n'):
        if not line.strip():
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            commits.append({
                'hash': parts[0],
                'subject': parts[1],
                'author': parts[2],
                'email': parts[3],
                'date': parts[4],
            })
        elif len(parts) >= 2:
            commits.append({
                'hash': parts[0],
                'subject': parts[1],
                'author': parts[2] if len(parts) > 2 else 'unknown',
                'email': parts[3] if len(parts) > 3 else '',
                'date': parts[4] if len(parts) > 4 else '',
            })
    return commits


def parse_conventional_commit(message):
    """
    Parse a conventional commit message.
    Format: type(scope): description
    Returns: {'type': str, 'scope': str|None, 'description': str, 'breaking': bool, 'tickets': list}
    """
    pattern = r'^(\w+)(?:\(([^)]+)\))?(!)?:\s*(.+)$'
    match = re.match(pattern, message)

    result = {
        'type': 'chore',
        'scope': None,
        'description': message,
        'breaking': False,
        'tickets': [],
    }

    if match:
        result['type'] = match.group(1).lower()
        result['scope'] = match.group(2)
        result['breaking'] = match.group(3) == '!'
        result['description'] = match.group(4)

    # Check for BREAKING CHANGE in message body
    if 'BREAKING CHANGE' in message or 'BREAKING-CHANGE' in message:
        result['breaking'] = True

    # Extract Jira ticket references (e.g., POS-1234, INFRA-567)
    ticket_pattern = r'([A-Z]{2,10}-\d+)'
    result['tickets'] = re.findall(ticket_pattern, message)

    # Extract GitHub issue references (e.g., #123)
    github_pattern = r'#(\d+)'
    github_issues = re.findall(github_pattern, message)
    result['tickets'].extend([f"#{num}" for num in github_issues])

    # Check for manual test tags
    result['manual_test'] = bool(re.search(r'\[manual-test\]|\[pos-hardware\]|\[edge-verify\]', message))

    return result


def get_changed_files(from_ref, to_ref="HEAD"):
    """Get list of changed files between two refs."""
    try:
        output = run_git(["diff", "--name-only", f"{from_ref}...{to_ref}"])
        return [f for f in output.split('\n') if f.strip()] if output else []
    except RuntimeError:
        return []


def detect_affected_services(changed_files, service_paths=None):
    """Detect which services are affected based on changed file paths."""
    if service_paths is None:
        service_paths = {
            'services/pos-terminal': 'pos-terminal-service',
            'services/payment': 'payment-gateway',
            'services/store-config': 'store-config-service',
            'services/inventory': 'inventory-service',
            'services/pos-ui': 'pos-ui',
            'charts/': 'helm-charts',
            'k8s/': 'kubernetes-manifests',
            'scripts/': 'automation-scripts',
        }

    affected = set()
    for filepath in changed_files:
        for path_prefix, service_name in service_paths.items():
            if filepath.startswith(path_prefix):
                affected.add(service_name)
                break
    return list(affected)


def create_tag(version, message=None, push=True):
    """Create an annotated git tag and optionally push it."""
    if message is None:
        message = f"Release {version}"

    run_git(["tag", "-a", version, "-m", message])

    if push:
        run_git(["push", "origin", version])

    return version


def get_commit_count(from_ref=None, to_ref="HEAD"):
    """Count commits between two refs."""
    if from_ref:
        output = run_git(["rev-list", "--count", f"{from_ref}..{to_ref}"])
    else:
        output = run_git(["rev-list", "--count", to_ref])
    return int(output)


def get_diff_stats(from_ref, to_ref="HEAD"):
    """Get diff statistics (files changed, insertions, deletions)."""
    try:
        output = run_git(["diff", "--shortstat", f"{from_ref}...{to_ref}"])
        stats = {'files_changed': 0, 'insertions': 0, 'deletions': 0}
        if output:
            files_match = re.search(r'(\d+) files? changed', output)
            ins_match = re.search(r'(\d+) insertions?', output)
            del_match = re.search(r'(\d+) deletions?', output)
            if files_match:
                stats['files_changed'] = int(files_match.group(1))
            if ins_match:
                stats['insertions'] = int(ins_match.group(1))
            if del_match:
                stats['deletions'] = int(del_match.group(1))
        return stats
    except RuntimeError:
        return {'files_changed': 0, 'insertions': 0, 'deletions': 0}


def get_contributors(from_ref=None, to_ref="HEAD"):
    """Get unique contributors between two refs."""
    if from_ref:
        log_range = f"{from_ref}..{to_ref}"
    else:
        log_range = to_ref

    try:
        output = run_git(["log", log_range, "--pretty=format:%an|%ae", "--no-merges"])
        contributors = {}
        for line in output.split('\n'):
            if '|' in line:
                name, email = line.split('|', 1)
                contributors[email] = name
        return [{'name': name, 'email': email} for email, name in contributors.items()]
    except RuntimeError:
        return []
