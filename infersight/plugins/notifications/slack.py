"""Slack webhook notification plugin."""

from __future__ import annotations

import logging

import httpx

from infersight.config import SlackConfig
from infersight.plugins.base import Issue, NotificationPlugin, Severity

logger = logging.getLogger(__name__)

_EMOJI = {
    Severity.INFO: ":information_source:",
    Severity.WARNING: ":warning:",
    Severity.CRITICAL: ":rotating_light:",
}


class SlackNotificationPlugin(NotificationPlugin):
    """Send issue alerts to an incoming Slack webhook without raising on failure."""

    def __init__(self, config: SlackConfig, dashboard_url: str = "") -> None:
        self._config = config
        self._dashboard_url = dashboard_url.rstrip("/")

    @property
    def channel_name(self) -> str:
        return "slack"

    async def notify(self, issue: Issue) -> None:
        if not self._config.enabled or self._below_threshold(issue):
            return
        webhook_url = self._config.webhook_url.get_secret_value()
        if not webhook_url:
            logger.warning("Slack webhook URL is not configured; skipping notification")
            return

        action = "resolved" if issue.cleared_at else "detected"
        message = (
            f"{_EMOJI[issue.severity]} *{issue.severity.value.upper()}* issue {action}: "
            f"*{issue.issue_type}* on `{issue.deployment_id}`\n{issue.description}"
        )
        if self._dashboard_url:
            message += f"\n<{self._dashboard_url}/issues|View issues in InferSight>"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(webhook_url, json={"text": message})
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception(
                "Failed to send Slack notification", extra={"issue_id": issue.issue_id}
            )

    def _below_threshold(self, issue: Issue) -> bool:
        order = [Severity.INFO, Severity.WARNING, Severity.CRITICAL]
        try:
            threshold = Severity(self._config.severity_threshold)
        except ValueError:
            threshold = Severity.WARNING
        return order.index(issue.severity) < order.index(threshold)
