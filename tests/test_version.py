"""
Unit tests for scripts/version.py — Semantic Version Calculator.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.version import parse_semver, bump_version, determine_bump_type


class TestParseSemver:
    """Tests for parse_semver()."""

    def test_parse_standard_version(self):
        result = parse_semver('v1.2.3')
        assert result == (1, 2, 3)

    def test_parse_without_prefix(self):
        result = parse_semver('1.2.3')
        assert result == (1, 2, 3)

    def test_parse_zero_version(self):
        result = parse_semver('v0.0.0')
        assert result == (0, 0, 0)

    def test_parse_large_numbers(self):
        result = parse_semver('v10.20.30')
        assert result == (10, 20, 30)

    def test_parse_invalid_returns_zeros(self):
        result = parse_semver('not-a-version')
        assert result == (0, 0, 0)

    def test_parse_empty_string(self):
        result = parse_semver('')
        assert result == (0, 0, 0)

    def test_parse_none(self):
        result = parse_semver(None)
        assert result == (0, 0, 0)


class TestBumpVersion:
    """Tests for bump_version()."""

    def test_bump_patch(self):
        result = bump_version(1, 2, 3, 'patch')
        assert result == 'v1.2.4'

    def test_bump_minor(self):
        result = bump_version(1, 2, 3, 'minor')
        assert result == 'v1.3.0'

    def test_bump_major(self):
        result = bump_version(1, 2, 3, 'major')
        assert result == 'v2.0.0'

    def test_bump_minor_resets_patch(self):
        result = bump_version(1, 2, 5, 'minor')
        assert result == 'v1.3.0'

    def test_bump_major_resets_minor_and_patch(self):
        result = bump_version(1, 5, 3, 'major')
        assert result == 'v2.0.0'

    def test_bump_from_zero(self):
        result = bump_version(0, 0, 0, 'patch')
        assert result == 'v0.0.1'

    def test_bump_pre_release(self):
        result = bump_version(1, 2, 3, 'minor', pre_release='rc.1')
        assert result == 'v1.3.0-rc.1'

    def test_bump_unknown_defaults_to_patch(self):
        result = bump_version(1, 2, 3, 'unknown')
        assert result == 'v1.2.4'


class TestDetermineBumpType:
    """Tests for determine_bump_type()."""

    def test_breaking_change_returns_major(self, sample_commits):
        result = determine_bump_type(sample_commits)
        assert result == 'major'

    def test_feature_without_breaking_returns_minor(self):
        commits = [
            {'subject': 'feat(api): add new endpoint', 'hash': 'abc123',
             'author': 'dev', 'date': ''},
            {'subject': 'fix(ui): correct display', 'hash': 'def456',
             'author': 'dev', 'date': ''},
        ]
        result = determine_bump_type(commits)
        assert result == 'minor'

    def test_only_fixes_returns_patch(self):
        commits = [
            {'subject': 'fix(api): resolve timeout', 'hash': 'abc123',
             'author': 'dev', 'date': ''},
            {'subject': 'fix(ui): correct display', 'hash': 'def456',
             'author': 'dev', 'date': ''},
        ]
        result = determine_bump_type(commits)
        assert result == 'patch'

    def test_only_chores_returns_patch(self):
        commits = [
            {'subject': 'chore: update dependencies', 'hash': 'abc123',
             'author': 'dev', 'date': ''},
        ]
        result = determine_bump_type(commits)
        assert result == 'patch'

    def test_empty_commits_returns_patch(self):
        result = determine_bump_type([])
        assert result == 'patch'

    def test_perf_returns_patch(self):
        commits = [
            {'subject': 'perf(db): optimize queries', 'hash': 'abc123',
             'author': 'dev', 'date': ''},
        ]
        result = determine_bump_type(commits)
        assert result == 'patch'
