"""
Pytest fixtures for release-toolkit tests.
"""

import os
import sys
import pytest
import tempfile
import json

# Ensure scripts are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def sample_commits():
    """Sample conventional commits for testing."""
    return [
        {
            'hash': 'abc1234',
            'subject': 'feat(pos-terminal): add NFC payment support POS-1234',
            'author': 'Alice Developer',
            'date': '2024-01-15T10:30:00-05:00',
        },
        {
            'hash': 'def5678',
            'subject': 'fix(payment-gateway): resolve timeout on refunds POS-1235',
            'author': 'Bob Engineer',
            'date': '2024-01-15T11:00:00-05:00',
        },
        {
            'hash': 'ghi9012',
            'subject': 'feat(api): implement batch order endpoint POS-1236',
            'author': 'Alice Developer',
            'date': '2024-01-16T09:00:00-05:00',
        },
        {
            'hash': 'jkl3456',
            'subject': 'perf(pos-terminal): optimize transaction processing',
            'author': 'Charlie Ops',
            'date': '2024-01-16T14:00:00-05:00',
        },
        {
            'hash': 'mno7890',
            'subject': 'fix(ui): correct currency formatting in receipts',
            'author': 'Dana Designer',
            'date': '2024-01-17T08:30:00-05:00',
        },
        {
            'hash': 'pqr1234',
            'subject': 'feat(edge-cluster)!: migrate to gRPC protocol POS-1237',
            'author': 'Eve Architect',
            'date': '2024-01-17T15:00:00-05:00',
        },
        {
            'hash': 'stu5678',
            'subject': 'chore: update dependencies',
            'author': 'Bob Engineer',
            'date': '2024-01-18T09:00:00-05:00',
        },
    ]


@pytest.fixture
def sample_config():
    """Sample release-config.yaml as dict."""
    return {
        'project': {
            'name': 'pos-platform',
            'default_branch': 'main',
        },
        'versioning': {
            'scheme': 'semver',
            'tag_prefix': 'v',
        },
        'jira': {
            'base_url': 'https://myorg.atlassian.net',
            'project_key': 'POS',
            'transition_ids': {
                'released': '61',
            },
        },
        'repositories': {
            'services': [
                {
                    'name': 'pos-terminal-service',
                    'repo_url': 'https://github.com/myorg/pos-terminal-service.git',
                    'path_prefix': 'services/pos-terminal',
                    'edge_deploy': True,
                },
                {
                    'name': 'payment-gateway',
                    'repo_url': 'https://github.com/myorg/payment-gateway.git',
                    'path_prefix': 'services/payment-gateway',
                    'edge_deploy': False,
                },
            ],
        },
    }


@pytest.fixture
def temp_dir():
    """Temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_version_summary():
    """Sample version-summary.json content."""
    return {
        'version': 'v2.1.0',
        'previous_version': 'v2.0.0',
        'bump_type': 'minor',
        'total_commits': 7,
        'features': 3,
        'fixes': 2,
        'breaking_changes': 1,
        'affected_services': ['pos-terminal', 'payment-gateway', 'api', 'edge-cluster'],
        'generated_at': '2024-01-18T12:00:00Z',
    }
