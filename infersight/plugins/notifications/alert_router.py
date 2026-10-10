"""Alert Router.

Dispatches Issue objects to configured NotificationPlugin instances
based on severity thresholds. Maintains in-memory deduplication state
with a TTL keyed on (issue_id, deployment_id).

Usage::

    router = AlertRouter(config.alerting)
    router.add_channel(SlackNotificationPlugin(config.alerting.slack, ...))
    router.add_channel(PagerDutyNotificationPlugin(config.alerting.pagerduty))
    router.add_channel(EmailNotificationPlugin(config.alerting.email))

    await router.dispatch(issue)
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from infersight.config import AlertingConfig
from infersight.plugins.base import Issue, NotificationPlugin, Severity
from infersight.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_SEVERITY_ORDER: list[Severity] = [Severity.INFO, Severity.WARNING, Severity.CRITICAL]


class AlertRouter:
    """Routes issues to notification channels with deduplication."""

    def __init__(self, config: AlertingConfig, storage: StorageBackend | None = None) -> None:
        self._cfg = config
        self._storage = storage
        self._channels: list[NotificationPlugin] = []
        # (issue_id, deployment_id) -> last dispatch epoch (monotonic)
        self._dedup: dict[tuple[str, str], float] = {}

    def add_channel(self, plugin: NotificationPlugin) -> None:
        """Register a notification channel."""
        self._channels.append(plugin)

    def _meets_min_severity(self, issue: Issue) -> bool:
        try:
            min_sev = Severity(self._cfg.min_severity)
        except ValueError:
            min_sev = Severity.WARNING
        return _SEVERITY_ORDER.index(issue.severity) >= _SEVERITY_ORDER.index(min_sev)

    async def _is_duplicate(self, issue: Issue) -> bool:
        """Return True if this issue was already dispatched within the dedup window."""
        key = (issue.issue_id, issue.deployment_id)
        last = self._dedup.get(key)
        if last is not None and (time.monotonic() - last) < self._cfg.deduplication_window_seconds:
            return True

        storage = self._storage
        if storage is None:
            return False
        return await storage.alert_was_dispatched(
            issue.issue_id,
            issue.deployment_id,
            datetime.now(UTC) - timedelta(seconds=self._cfg.deduplication_window_seconds),
        )

    async def _record(self, issue: Issue) -> None:
        self._dedup[(issue.issue_id, issue.deployment_id)] = time.monotonic()
        if self._storage is not None:
            await self._storage.record_alert_dispatch(
                issue.issue_id, issue.deployment_id, datetime.now(UTC)
            )

    async def clear_dedup(self, issue_id: str, deployment_id: str) -> None:
        """Remove a dedup entry — call when an issue clears so it can re-alert."""
        self._dedup.pop((issue_id, deployment_id), None)
        if self._storage is not None:
            await self._storage.clear_alert_dispatch(issue_id, deployment_id)

    async def dispatch(self, issue: Issue) -> None:
        """Send the issue to all registered channels, respecting filters and dedup."""
        if not self._meets_min_severity(issue):
            logger.debug(
                "Issue below min_severity — skipped",
                extra={"issue_id": issue.issue_id, "severity": issue.severity},
            )
            return

        # Resolve events (cleared_at set) always pass through to allow auto-resolution
        is_resolve = issue.cleared_at is not None

        if not is_resolve and await self._is_duplicate(issue):
            logger.debug(
                "Issue suppressed by deduplication window",
                extra={
                    "issue_id": issue.issue_id,
                    "deployment_id": issue.deployment_id,
                    "window_seconds": self._cfg.deduplication_window_seconds,
                },
            )
            return

        if not is_resolve:
            await self._record(issue)
        else:
            # Clear dedup state so a recurrence re-alerts after resolution
            await self.clear_dedup(issue.issue_id, issue.deployment_id)

        for channel in self._channels:
            try:
                await channel.notify(issue)
            except Exception:
                # Channels must not propagate — but belt-and-suspenders
                logger.exception(
                    "Unexpected exception from notification channel",
                    extra={"channel": channel.channel_name, "issue_id": issue.issue_id},
                )
