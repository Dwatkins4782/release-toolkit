"""
Notification Utilities — Slack and Teams message formatting and sending.
"""

import os
import json
import requests
from datetime import datetime


def send_slack(webhook_url, payload):
    """Send a message to Slack via incoming webhook."""
    if not webhook_url or webhook_url.startswith('${'):
        print("  Slack webhook not configured, skipping notification")
        return False

    response = requests.post(
        webhook_url,
        json=payload,
        headers={'Content-Type': 'application/json'},
        timeout=15,
    )
    return response.status_code == 200


def send_teams(webhook_url, payload):
    """Send an adaptive card to Microsoft Teams via webhook."""
    if not webhook_url or webhook_url.startswith('${'):
        print("  Teams webhook not configured, skipping notification")
        return False

    response = requests.post(
        webhook_url,
        json=payload,
        headers={'Content-Type': 'application/json'},
        timeout=15,
    )
    return response.status_code == 200


def format_release_notification(version, release_notes_summary, environment,
                                  pipeline_url="", affected_services=None):
    """Build a rich Slack notification for a release."""
    services_text = ", ".join(affected_services) if affected_services else "All services"
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Release {version} deployed to {environment.upper()}",
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Version:*\n`{version}`"},
                    {"type": "mrkdwn", "text": f"*Environment:*\n`{environment}`"},
                    {"type": "mrkdwn", "text": f"*Services:*\n{services_text}"},
                    {"type": "mrkdwn", "text": f"*Timestamp:*\n{timestamp}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Release Summary:*\n{release_notes_summary[:500]}"
                }
            },
        ]
    }

    if pipeline_url:
        payload["blocks"].append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Pipeline"},
                    "url": pipeline_url,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Release Notes"},
                    "url": f"{pipeline_url}/artifacts",
                },
            ]
        })

    return payload


def format_qa_handoff_notification(version, manifest, deploy_status,
                                     test_trigger_url="", checklist_url=""):
    """Build a QA-specific Slack notification with test details."""
    affected = manifest.get('affected_services', [])
    total_changes = manifest.get('total_commits', 0)
    manual_tests = manifest.get('manual_test_items', [])
    feature_toggles = manifest.get('feature_toggles_changed', [])

    manual_test_text = ""
    if manual_tests:
        items = [f"  - {item}" for item in manual_tests[:5]]
        manual_test_text = f"\n*Manual Tests Required ({len(manual_tests)}):*\n" + "\n".join(items)

    toggle_text = ""
    if feature_toggles:
        items = [f"  - `{t['name']}`: {t['state']}" for t in feature_toggles[:5]]
        toggle_text = f"\n*Feature Toggles Changed:*\n" + "\n".join(items)

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"QA Ready: Release {version} deployed to QA",
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Version:*\n`{version}`"},
                    {"type": "mrkdwn", "text": f"*Total Changes:*\n{total_changes} commits"},
                    {"type": "mrkdwn", "text": f"*Deploy Status:*\n{'Healthy' if deploy_status else 'Check Needed'}"},
                    {"type": "mrkdwn", "text": f"*Services:*\n{', '.join(affected) if affected else 'All'}"},
                ]
            },
        ]
    }

    if manual_test_text:
        payload["blocks"].append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": manual_test_text}
        })

    if toggle_text:
        payload["blocks"].append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": toggle_text}
        })

    # Action buttons
    elements = []
    if test_trigger_url:
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "View Test Results"},
            "url": test_trigger_url,
            "style": "primary",
        })
    if checklist_url:
        elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "QA Checklist"},
            "url": checklist_url,
        })
    elements.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "Rollback"},
        "url": f"#rollback-{version}",
        "style": "danger",
    })

    if elements:
        payload["blocks"].append({
            "type": "actions",
            "elements": elements
        })

    # Rollback command hint
    payload["blocks"].append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Rollback command: `make rollback VERSION={version} ENV=qa`"
            }
        ]
    })

    return payload


def format_rollback_notification(version, environment, reason=""):
    """Build a rollback alert notification."""
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"ROLLBACK: {version} rolled back in {environment.upper()}",
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reason:* {reason or 'Manual rollback triggered'}\n"
                            f"*Version:* `{version}`\n"
                            f"*Environment:* `{environment}`\n"
                            f"*Time:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
                }
            }
        ]
    }
    return payload
