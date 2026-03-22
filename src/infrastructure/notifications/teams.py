"""Microsoft Teams webhook notifier for PipelineGuard alerts.

Delivers alert cards to a Teams channel via incoming webhook connector.
Uses Adaptive Cards format for rich formatting.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {"CRITICAL": "attention", "WARNING": "warning"}


@dataclass(frozen=True)
class TeamsAlertPayload:
    severity: str
    alert_type: str
    title: str
    description: str
    pipeline_name: str
    tenant_id: str
    alert_id: str


class TeamsNotifier:
    """Delivers PipelineGuard alerts to a Microsoft Teams channel."""

    def __init__(self, webhook_url: str, timeout: int = 5) -> None:
        if not webhook_url:
            raise ValueError("Teams webhook URL must not be empty")
        self._url = webhook_url
        self._timeout = timeout

    def send_alert(self, alert: TeamsAlertPayload) -> bool:
        color = SEVERITY_COLORS.get(alert.severity, "default")
        payload: dict[str, Any] = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Large",
                                "weight": "Bolder",
                                "text": alert.title,
                                "color": color,
                            },
                            {"type": "TextBlock", "text": alert.description, "wrap": True},
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Pipeline", "value": alert.pipeline_name},
                                    {"title": "Severity", "value": alert.severity},
                                    {"title": "Type", "value": alert.alert_type},
                                ],
                            },
                        ],
                    },
                }
            ],
        }
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                self._url, data=data, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return bool(resp.status < 400)
        except Exception:
            logger.exception("Teams delivery failed", extra={"alert_id": alert.alert_id})
            return False
