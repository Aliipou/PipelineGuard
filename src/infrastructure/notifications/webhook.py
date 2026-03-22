"""Generic webhook notifier for custom PipelineGuard integrations.

Delivers alert payloads to any HTTP endpoint as JSON, with HMAC-SHA256
signature for payload verification on the receiving end.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookPayload:
    severity: str
    alert_type: str
    title: str
    description: str
    pipeline_name: str
    tenant_id: str
    alert_id: str


class WebhookNotifier:
    """Delivers alert payloads to a generic HTTP webhook endpoint.

    Signs each payload with HMAC-SHA256 using the provided secret.
    The receiving endpoint should verify the X-PipelineGuard-Signature header.

    Usage::

        notifier = WebhookNotifier(
            url="https://your-service.example.com/pipelineguard-alerts",
            secret="your-signing-secret",
        )
        notifier.send_alert(payload)
    """

    def __init__(self, url: str, secret: str = "", timeout: int = 5) -> None:
        self._url = url
        self._secret = secret.encode()
        self._timeout = timeout

    def send_alert(self, alert: WebhookPayload) -> bool:
        body = json.dumps(
            {
                "severity": alert.severity,
                "alert_type": alert.alert_type,
                "title": alert.title,
                "description": alert.description,
                "pipeline_name": alert.pipeline_name,
                "tenant_id": alert.tenant_id,
                "alert_id": alert.alert_id,
            }
        ).encode()

        headers = {"Content-Type": "application/json"}
        if self._secret:
            sig = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
            headers["X-PipelineGuard-Signature"] = f"sha256={sig}"

        try:
            req = urllib.request.Request(self._url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return bool(resp.status < 400)
        except Exception:
            logger.exception("Webhook delivery failed", extra={"alert_id": alert.alert_id})
            return False
