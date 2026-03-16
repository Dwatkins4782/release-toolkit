"""
Jira REST API Client — Manages work items for release tracking.
"""

import os
import json
import time
import requests
from requests.auth import HTTPBasicAuth


class JiraClient:
    """Jira REST API client for release automation."""

    def __init__(self, base_url=None, email=None, api_token=None):
        self.base_url = (base_url or os.environ.get('JIRA_BASE_URL', '')).rstrip('/')
        self.email = email or os.environ.get('JIRA_USER_EMAIL', '')
        self.api_token = api_token or os.environ.get('JIRA_API_TOKEN', '')
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        self.rate_limit_delay = 0.5  # seconds between API calls

    def _request(self, method, endpoint, data=None):
        """Make an authenticated request to Jira API."""
        url = f"{self.base_url}/rest/api/3/{endpoint}"
        response = requests.request(
            method, url,
            headers=self.headers,
            auth=self.auth,
            json=data,
            timeout=30,
        )
        time.sleep(self.rate_limit_delay)

        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"  Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after)
            return self._request(method, endpoint, data)

        return response

    def get_issue(self, key):
        """Fetch a Jira issue by key."""
        response = self._request('GET', f'issue/{key}')
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            print(f"  Warning: Failed to fetch {key}: {response.status_code}")
            return None

    def add_label(self, key, label):
        """Add a label to a Jira issue."""
        data = {
            "update": {
                "labels": [{"add": label}]
            }
        }
        response = self._request('PUT', f'issue/{key}', data)
        return response.status_code == 204

    def add_comment(self, key, comment_text):
        """Add a comment to a Jira issue."""
        data = {
            "body": {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": comment_text
                            }
                        ]
                    }
                ]
            }
        }
        response = self._request('POST', f'issue/{key}/comment', data)
        return response.status_code == 201

    def transition_issue(self, key, transition_id):
        """Transition a Jira issue to a new status."""
        data = {
            "transition": {
                "id": str(transition_id)
            }
        }
        response = self._request('POST', f'issue/{key}/transitions', data)
        return response.status_code == 204

    def set_fix_version(self, key, version_name, project_key):
        """Set the fix version on a Jira issue (creates version if needed)."""
        # Ensure version exists
        self._ensure_version(project_key, version_name)

        data = {
            "update": {
                "fixVersions": [{"add": {"name": version_name}}]
            }
        }
        response = self._request('PUT', f'issue/{key}', data)
        return response.status_code == 204

    def _ensure_version(self, project_key, version_name):
        """Create a Jira project version if it doesn't exist."""
        response = self._request('GET', f'project/{project_key}/versions')
        if response.status_code == 200:
            versions = response.json()
            if any(v['name'] == version_name for v in versions):
                return True

        # Create the version
        data = {
            "name": version_name,
            "project": project_key,
            "released": False,
        }
        response = self._request('POST', 'version', data)
        return response.status_code == 201

    def get_issues_in_sprint(self, board_id, sprint_id=None):
        """Get all issues in a sprint."""
        if sprint_id:
            endpoint = f'sprint/{sprint_id}/issue'
        else:
            endpoint = f'board/{board_id}/sprint?state=active'

        # Agile API uses different base path
        url = f"{self.base_url}/rest/agile/1.0/{endpoint}"
        response = requests.get(
            url, headers=self.headers, auth=self.auth, timeout=30
        )
        if response.status_code == 200:
            return response.json().get('issues', [])
        return []

    def tag_release(self, key, version, dry_run=False):
        """
        Full release tagging workflow for a single issue:
        1. Add release label
        2. Set fix version
        3. Add release comment
        4. Optionally transition to 'Released'
        """
        results = {'key': key, 'actions': [], 'errors': []}

        if dry_run:
            results['actions'] = [
                f"Would add label: released-in-{version}",
                f"Would set fix version: {version}",
                f"Would add release comment",
            ]
            return results

        label = f"released-in-{version}"
        if self.add_label(key, label):
            results['actions'].append(f"Added label: {label}")
        else:
            results['errors'].append(f"Failed to add label: {label}")

        comment = (
            f"This issue was included in release {version}. "
            f"Release notes and deployment details available in the release pipeline."
        )
        if self.add_comment(key, comment):
            results['actions'].append("Added release comment")
        else:
            results['errors'].append("Failed to add comment")

        return results
