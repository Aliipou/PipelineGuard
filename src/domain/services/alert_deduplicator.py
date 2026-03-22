"""Alert deduplication service to prevent notification spam.

When a pipeline fails repeatedly, PipelineGuard should not send
a new alert for every single execution. The deduplicator suppresses
duplicate alerts within a configurable cooldown window.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field


@dataclass
class AlertDeduplicator:
    """Prevents duplicate alerts for the same pipeline+type within a window.

    Usage::

        dedup = AlertDeduplicator(cooldown_seconds=300)  # 5 min cooldown

        if dedup.should_alert(pipeline_id="abc", alert_type="SILENT_FAILURE"):
            notifier.send_alert(...)
    """

    cooldown_seconds: float = 300.0
    _last_alert: dict[str, float] = field(default_factory=dict, repr=False)

    def should_alert(self, pipeline_id: str, alert_type: str) -> bool:
        """Returns True if a new alert should be sent, False if suppressed."""
        key = f"{pipeline_id}:{alert_type}"
        now = time.monotonic()
        last = self._last_alert.get(key, 0.0)
        if now - last >= self.cooldown_seconds:
            self._last_alert[key] = now
            return True
        return False

    def reset(self, pipeline_id: str, alert_type: str) -> None:
        """Reset the cooldown for a pipeline+type (e.g. when alert is acknowledged)."""
        key = f"{pipeline_id}:{alert_type}"
        self._last_alert.pop(key, None)
