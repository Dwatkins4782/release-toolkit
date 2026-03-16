#!/usr/bin/env python3
"""
Feature Toggle Manager
=======================
Snapshot, activate, or deactivate feature toggles at release time.
Integrates with LaunchDarkly, Split, or Unleash APIs.

Usage:
    python scripts/feature_toggles.py --version v2.1.0 --action snapshot
    python scripts/feature_toggles.py --version v2.1.0 --action activate --flags flag1,flag2
    python scripts/feature_toggles.py --version v2.1.0 --action deactivate --flags flag1
"""

import sys
import os
import argparse
import json
import requests
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.utils.config_loader import load_config, get_config_value


class FeatureToggleClient:
    """Generic feature toggle API client."""

    def __init__(self, config):
        toggle_config = get_config_value(config, 'feature_toggles', {})
        self.provider = toggle_config.get('provider', 'launchdarkly')
        self.api_endpoint = toggle_config.get('api_endpoint', '')
        self.api_key = os.environ.get('FEATURE_TOGGLE_API_KEY', '')
        self.project_key = toggle_config.get('project_key', '')
        self.environments = toggle_config.get('environments', {})
        self.headers = {
            'Authorization': self.api_key,
            'Content-Type': 'application/json',
        }

    def snapshot(self, environment='qa'):
        """Get current state of all feature flags for an environment."""
        env_key = self.environments.get(environment, environment)

        if not self.api_endpoint or not self.api_key:
            print("Feature toggle API not configured.")
            return self._mock_snapshot()

        try:
            url = f"{self.api_endpoint}/flags/{self.project_key}"
            response = requests.get(
                url, headers=self.headers,
                params={'env': env_key}, timeout=15
            )
            if response.status_code == 200:
                items = response.json().get('items', [])
                return [
                    {
                        'key': flag['key'],
                        'name': flag.get('name', flag['key']),
                        'state': 'on' if flag.get('environments', {}).get(
                            env_key, {}).get('on') else 'off',
                        'environment': environment,
                        'last_modified': flag.get('environments', {}).get(
                            env_key, {}).get('lastModified', ''),
                        'tags': flag.get('tags', []),
                    }
                    for flag in items
                ]
            else:
                print(f"API returned {response.status_code}")
                return []
        except requests.RequestException as e:
            print(f"Error fetching toggles: {e}")
            return []

    def update_flag(self, flag_key, environment, state, dry_run=False):
        """Enable or disable a feature flag."""
        env_key = self.environments.get(environment, environment)

        if dry_run:
            print(f"  [DRY RUN] Would set {flag_key} to {state} in {environment}")
            return True

        if not self.api_endpoint or not self.api_key:
            print(f"  Feature toggle API not configured. Skipping {flag_key}.")
            return False

        try:
            url = f"{self.api_endpoint}/flags/{self.project_key}/{flag_key}"
            patch_data = [{
                'op': 'replace',
                'path': f'/environments/{env_key}/on',
                'value': state == 'on',
            }]
            response = requests.patch(
                url, headers={**self.headers, 'Content-Type': 'application/json'},
                json=patch_data, timeout=15
            )
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"  Error updating {flag_key}: {e}")
            return False

    def _mock_snapshot(self):
        """Return mock data when API is not configured."""
        return [
            {'key': 'new-checkout-flow', 'name': 'New Checkout Flow',
             'state': 'on', 'environment': 'qa', 'tags': ['pos-terminal']},
            {'key': 'nfc-payment-v2', 'name': 'NFC Payment V2',
             'state': 'off', 'environment': 'qa', 'tags': ['payment']},
            {'key': 'inventory-sync-realtime', 'name': 'Real-time Inventory Sync',
             'state': 'on', 'environment': 'qa', 'tags': ['inventory']},
        ]


def main():
    parser = argparse.ArgumentParser(description='Manage feature toggles for releases')
    parser.add_argument('--version', type=str, required=True,
                        help='Release version')
    parser.add_argument('--action', choices=['snapshot', 'activate', 'deactivate'],
                        required=True, help='Action to perform')
    parser.add_argument('--flags', type=str, default=None,
                        help='Comma-separated flag keys (for activate/deactivate)')
    parser.add_argument('--env', type=str, default='qa',
                        help='Target environment (default: qa)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without making changes')
    parser.add_argument('--output', type=str, default=None,
                        help='Output snapshot to JSON file')
    parser.add_argument('--config-dir', type=str, default=None,
                        help='Path to config directory')
    args = parser.parse_args()

    try:
        config = load_config(args.config_dir)
    except FileNotFoundError:
        config = {}

    client = FeatureToggleClient(config)

    if args.action == 'snapshot':
        print(f"Capturing feature toggle snapshot for {args.env}...")
        toggles = client.snapshot(args.env)
        print(f"Found {len(toggles)} feature toggles:")
        for t in toggles:
            print(f"  {t['key']}: {t['state']} (tags: {', '.join(t.get('tags', []))})")

        if args.output:
            snapshot = {
                'version': args.version,
                'environment': args.env,
                'captured_at': datetime.utcnow().isoformat() + 'Z',
                'toggles': toggles,
            }
            with open(args.output, 'w') as f:
                json.dump(snapshot, f, indent=2)
            print(f"Snapshot written to: {args.output}")

    elif args.action in ('activate', 'deactivate'):
        if not args.flags:
            print("Error: --flags required for activate/deactivate")
            sys.exit(1)

        state = 'on' if args.action == 'activate' else 'off'
        flag_keys = [f.strip() for f in args.flags.split(',')]

        print(f"{'Activating' if state == 'on' else 'Deactivating'} "
              f"{len(flag_keys)} flags in {args.env}...")

        for flag_key in flag_keys:
            success = client.update_flag(flag_key, args.env, state, args.dry_run)
            status = 'OK' if success else 'FAILED'
            print(f"  {flag_key} -> {state}: {status}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
