"""PagerDuty Events API v2 notification plugin."""

from __future__ import annotations

import logging

import httpx

from infersight.config import PagerdutyConfig
from infersight.plugins.base import Issue, NotificationPlugin, Severity

logger = logging.getLogger(__name__)
_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


class PagerDutyNotificationPlugin(NotificationPlugin):
    """Send trigger and resolve events to PagerDuty without propagating failures."""

    def __init__(self, config: PagerdutyConfig) -> None:
        self._config = config

    @property
    def channel_name(self) -> str:
        return "pagerduty"

    async def notify(self, issue: Issue) -> None:
        if not self._config.enabled or self._below_threshold(issue):
            return
        routing_key = self._config.routing_key.get_secret_value()
        if not routing_key:
            logger.warning("PagerDuty routing key is not configured; skipping notification")
            return
        payload = {
            "routing_key": routing_key,
            "event_action": "resolve" if issue.cleared_at else "trigger",
            "dedup_key": f"{issue.issue_id}:{issue.deployment_id}",
            "payload": {
                "summary": f"{issue.issue_type} on {issue.deployment_id}: {issue.description}",
                "source": "infersight",
                "severity": issue.severity.value,
                "custom_details": issue.supporting_metrics,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(_EVENTS_URL, json=payload)
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to send PagerDuty event", extra={"issue_id": issue.issue_id})

    def _below_threshold(self, issue: Issue) -> bool:
        order = [Severity.INFO, Severity.WARNING, Severity.CRITICAL]
        try:
            threshold = Severity(self._config.severity_threshold)
        except ValueError:
            threshold = Severity.CRITICAL
        return order.index(issue.severity) < order.index(threshold)
