"""
Unit tests for scripts/correlate_releases.py — Multi-Repo Release Correlator.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.correlate_releases import correlate_tickets, generate_correlation_report


class TestCorrelateTickets:
    """Tests for correlate_tickets()."""

    def test_finds_shared_tickets(self):
        repo_infos = [
            {
                'name': 'repo-a',
                'commits': [
                    {'tickets': ['POS-100', 'POS-200'], 'type': 'feat',
                     'scope': 'api', 'breaking': False, 'author': 'dev1'},
                ],
                'commit_count': 1,
            },
            {
                'name': 'repo-b',
                'commits': [
                    {'tickets': ['POS-100', 'POS-300'], 'type': 'fix',
                     'scope': 'ui', 'breaking': False, 'author': 'dev2'},
                ],
                'commit_count': 1,
            },
        ]
        shared, single = correlate_tickets(repo_infos)
        assert 'POS-100' in shared
        assert set(shared['POS-100']) == {'repo-a', 'repo-b'}
        assert 'POS-200' in single
        assert 'POS-300' in single

    def test_no_shared_tickets(self):
        repo_infos = [
            {
                'name': 'repo-a',
                'commits': [
                    {'tickets': ['POS-100'], 'type': 'feat',
                     'scope': 'api', 'breaking': False, 'author': 'dev1'},
                ],
                'commit_count': 1,
            },
            {
                'name': 'repo-b',
                'commits': [
                    {'tickets': ['POS-200'], 'type': 'fix',
                     'scope': 'ui', 'breaking': False, 'author': 'dev2'},
                ],
                'commit_count': 1,
            },
        ]
        shared, single = correlate_tickets(repo_infos)
        assert len(shared) == 0
        assert 'POS-100' in single
        assert 'POS-200' in single

    def test_handles_none_repos(self):
        repo_infos = [None, None]
        shared, single = correlate_tickets(repo_infos)
        assert len(shared) == 0
        assert len(single) == 0

    def test_handles_empty_commits(self):
        repo_infos = [
            {'name': 'repo-a', 'commits': [], 'commit_count': 0},
        ]
        shared, single = correlate_tickets(repo_infos)
        assert len(shared) == 0
        assert len(single) == 0

    def test_ticket_in_three_repos(self):
        repo_infos = [
            {'name': 'repo-a', 'commits': [{'tickets': ['POS-999'], 'type': 'feat', 'scope': '', 'breaking': False, 'author': 'd'}], 'commit_count': 1},
            {'name': 'repo-b', 'commits': [{'tickets': ['POS-999'], 'type': 'fix', 'scope': '', 'breaking': False, 'author': 'd'}], 'commit_count': 1},
            {'name': 'repo-c', 'commits': [{'tickets': ['POS-999'], 'type': 'chore', 'scope': '', 'breaking': False, 'author': 'd'}], 'commit_count': 1},
        ]
        shared, single = correlate_tickets(repo_infos)
        assert 'POS-999' in shared
        assert len(shared['POS-999']) == 3


class TestGenerateCorrelationReport:
    """Tests for generate_correlation_report()."""

    def test_report_structure(self, sample_config):
        repo_infos = [
            {
                'name': 'pos-terminal-service',
                'url': 'https://github.com/myorg/pos-terminal-service.git',
                'latest_tag': 'v1.9.0',
                'previous_tag': 'v1.8.2',
                'commits': [
                    {'hash': 'abc1234', 'subject': 'feat: add NFC', 'author': 'dev1',
                     'type': 'feat', 'scope': 'pos', 'tickets': ['POS-100'],
                     'breaking': False, 'date': ''},
                ],
                'commit_count': 1,
            },
        ]
        report = generate_correlation_report('v2.1.0', repo_infos, sample_config)

        assert report['release'] == 'v2.1.0'
        assert 'summary' in report
        assert 'repos' in report
        assert 'risk_assessment' in report
        assert report['summary']['total_repos'] == 1
        assert report['summary']['total_commits'] == 1

    def test_risk_assessment_low(self, sample_config):
        repo_infos = [
            {
                'name': 'repo-a',
                'url': '',
                'latest_tag': 'v1.0.1',
                'previous_tag': 'v1.0.0',
                'commits': [
                    {'hash': 'a', 'subject': 'fix: typo', 'author': 'd',
                     'type': 'fix', 'scope': '', 'tickets': [], 'breaking': False, 'date': ''},
                ],
                'commit_count': 1,
            },
        ]
        report = generate_correlation_report('v1.0.1', repo_infos, sample_config)
        assert report['risk_assessment'] == 'low'

    def test_risk_assessment_high_on_breaking(self, sample_config):
        repo_infos = [
            {
                'name': 'repo-a',
                'url': '',
                'latest_tag': 'v2.0.0',
                'previous_tag': 'v1.0.0',
                'commits': [
                    {'hash': 'a', 'subject': 'feat!: breaking change', 'author': 'd',
                     'type': 'feat', 'scope': '', 'tickets': [], 'breaking': True, 'date': ''},
                ],
                'commit_count': 1,
            },
        ]
        report = generate_correlation_report('v2.0.0', repo_infos, sample_config)
        assert report['risk_assessment'] == 'high'

    def test_handles_empty_repos(self, sample_config):
        report = generate_correlation_report('v1.0.0', [], sample_config)
        assert report['summary']['total_repos'] == 0
        assert report['summary']['total_commits'] == 0
