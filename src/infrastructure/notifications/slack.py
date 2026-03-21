"""Slack webhook notification delivery for PipelineGuard alerts.

Delivers alert payloads to a Slack channel via incoming webhooks.
Uses Block Kit for rich formatting with severity color coding.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {
    "CRITICAL": "#E01E5A",   # red
    "WARNING":  "#ECB22E",   # yellow
}

SEVERITY_EMOJI = {
    "CRITICAL": ":red_circle:",
    "WARNING":  ":large_yellow_circle:",
}

ALERT_TYPE_LABELS = {
    "SILENT_FAILURE":       "Silent Failure",
    "LATENCY_DRIFT":        "Latency Drift",
    "CONSECUTIVE_FAILURES": "Consecutive Failures",
}


@dataclass(frozen=True)
class AlertPayload:
    """Data needed to format a Slack alert message."""
    severity: str
    alert_type: str
    title: str
    description: str
    pipeline_name: str
    tenant_id: str
    alert_id: str


class SlackNotifier:
    """Delivers PipelineGuard alerts to a Slack channel via webhook.

    Usage::

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/...")
        notifier.send_alert(AlertPayload(...))
    """

    def __init__(self, webhook_url: str, timeout: int = 5) -> None:
        if not webhook_url:
            raise ValueError("Slack webhook URL must not be empty")
        self._webhook_url = webhook_url
        self._timeout = timeout

    def send_alert(self, alert: AlertPayload) -> bool:
        """Send an alert to Slack. Returns True on success, False on failure."""
        payload = self._build_payload(alert)
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                self._webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                success = resp.status == 200
                if not success:
                    logger.warning(
                        "Slack delivery failed",
                        extra={"status": resp.status, "alert_id": alert.alert_id},
                    )
                return success
        except Exception:
            logger.exception(
                "Slack notification error",
                extra={"alert_id": alert.alert_id},
            )
            return False

    def _build_payload(self, alert: AlertPayload) -> dict[str, Any]:
        color = SEVERITY_COLORS.get(alert.severity, "#808080")
        emoji = SEVERITY_EMOJI.get(alert.severity, ":white_circle:")
        label = ALERT_TYPE_LABELS.get(alert.alert_type, alert.alert_type)

        return {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{emoji} {alert.title}",
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": alert.description,
                            },
                        },
                        {
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Type:*\n{label}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Severity:*\n{alert.severity}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Pipeline:*\n{alert.pipeline_name}",
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Alert ID:*\n`{alert.alert_id[:8]}...`",
                                },
                            ],
                        },
                        {
                            "type": "divider",
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"PipelineGuard | Tenant `{alert.tenant_id[:8]}...`",
                                }
                            ],
                        },
                    ],
                }
            ]
        }


class NullNotifier:
    """No-op notifier used when no Slack webhook is configured."""

    def send_alert(self, alert: AlertPayload) -> bool:  # noqa: ARG002
        logger.debug("Null notifier: alert %s not delivered", alert.alert_id)
        return True
