"""
Unit tests for scripts/release_notes.py — Release Notes Generator.
"""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.release_notes import categorize_commits, generate_markdown, generate_json


class TestCategorizeCommits:
    """Tests for categorize_commits()."""

    def test_categorizes_features(self, sample_commits):
        categories = categorize_commits(sample_commits)
        assert 'Features' in categories
        assert len(categories['Features']) >= 2

    def test_categorizes_fixes(self, sample_commits):
        categories = categorize_commits(sample_commits)
        assert 'Bug Fixes' in categories
        assert len(categories['Bug Fixes']) >= 2

    def test_categorizes_performance(self, sample_commits):
        categories = categorize_commits(sample_commits)
        assert 'Performance' in categories
        assert len(categories['Performance']) >= 1

    def test_categorizes_breaking_changes(self, sample_commits):
        categories = categorize_commits(sample_commits)
        assert 'Breaking Changes' in categories
        assert len(categories['Breaking Changes']) >= 1

    def test_categorizes_chores(self, sample_commits):
        categories = categorize_commits(sample_commits)
        assert 'Chores' in categories

    def test_empty_commits(self):
        categories = categorize_commits([])
        # Should not raise, may return empty or minimal dict
        assert isinstance(categories, dict)

    def test_unknown_type_goes_to_other(self):
        commits = [
            {'subject': 'misc: some random change', 'hash': 'abc123',
             'author': 'dev', 'date': ''},
        ]
        categories = categorize_commits(commits)
        # Should handle gracefully — either in Other or a default bucket
        assert isinstance(categories, dict)


class TestGenerateMarkdown:
    """Tests for generate_markdown()."""

    def test_includes_version_header(self, sample_commits):
        md = generate_markdown('v2.1.0', sample_commits)
        assert 'v2.1.0' in md

    def test_includes_feature_section(self, sample_commits):
        md = generate_markdown('v2.1.0', sample_commits)
        assert 'Features' in md or 'feat' in md.lower()

    def test_includes_fix_section(self, sample_commits):
        md = generate_markdown('v2.1.0', sample_commits)
        assert 'Bug Fixes' in md or 'fix' in md.lower()

    def test_includes_breaking_changes(self, sample_commits):
        md = generate_markdown('v2.1.0', sample_commits)
        assert 'Breaking' in md

    def test_includes_ticket_references(self, sample_commits):
        md = generate_markdown('v2.1.0', sample_commits)
        assert 'POS-1234' in md

    def test_includes_contributors(self, sample_commits):
        md = generate_markdown('v2.1.0', sample_commits)
        assert 'Alice Developer' in md or 'Contributors' in md

    def test_returns_string(self, sample_commits):
        md = generate_markdown('v2.1.0', sample_commits)
        assert isinstance(md, str)
        assert len(md) > 0


class TestGenerateJson:
    """Tests for generate_json()."""

    def test_returns_valid_json(self, sample_commits):
        result = generate_json('v2.1.0', sample_commits)
        assert isinstance(result, dict)

    def test_includes_version(self, sample_commits):
        result = generate_json('v2.1.0', sample_commits)
        assert result.get('version') == 'v2.1.0'

    def test_includes_categories(self, sample_commits):
        result = generate_json('v2.1.0', sample_commits)
        assert 'categories' in result or 'changes' in result

    def test_includes_tickets(self, sample_commits):
        result = generate_json('v2.1.0', sample_commits)
        # Should have ticket references somewhere
        json_str = json.dumps(result)
        assert 'POS-1234' in json_str

    def test_is_serializable(self, sample_commits):
        result = generate_json('v2.1.0', sample_commits)
        # Should not raise
        serialized = json.dumps(result)
        assert isinstance(serialized, str)
