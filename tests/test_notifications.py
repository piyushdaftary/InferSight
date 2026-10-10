"""Tests for notification delivery, routing, and durable deduplication."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from infersight.config import AlertingConfig, PagerdutyConfig, SlackConfig
from infersight.plugins.base import Issue, NotificationPlugin, Severity
from infersight.plugins.notifications.alert_router import AlertRouter
from infersight.plugins.notifications.pagerduty import PagerDutyNotificationPlugin
from infersight.plugins.notifications.slack import SlackNotificationPlugin
from infersight.storage.sqlite import SQLiteBackend


def issue(*, cleared: bool = False) -> Issue:
    """Build a representative alert payload."""
    return Issue(
        issue_id="queue-saturation",
        issue_type="queue_saturation",
        severity=Severity.CRITICAL,
        deployment_id="deployment-a",
        detected_at=datetime.now(UTC),
        cleared_at=datetime.now(UTC) if cleared else None,
        supporting_metrics={"queue_depth": 12},
        description="Queue is saturated.",
        plugin_name="queue_saturation",
    )


class RecordingClient:
    """Minimal async HTTP client that captures an outgoing JSON payload."""

    def __init__(self, captured: list[tuple[str, dict[str, object]]]) -> None:
        self.captured = captured

    async def __aenter__(self) -> RecordingClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, object]) -> httpx.Response:
        self.captured.append((url, json))
        return httpx.Response(202, request=httpx.Request("POST", url))


@pytest.mark.asyncio
async def test_slack_formats_issue_and_dashboard_link(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "infersight.plugins.notifications.slack.httpx.AsyncClient",
        lambda **_: RecordingClient(captured),
    )

    plugin = SlackNotificationPlugin(
        SlackConfig(enabled=True, webhook_url="https://slack.example/webhook"),
        dashboard_url="https://infersight.example",
    )
    await plugin.notify(issue())

    assert captured[0][0] == "https://slack.example/webhook"
    assert "CRITICAL" in str(captured[0][1]["text"])
    assert "https://infersight.example/issues" in str(captured[0][1]["text"])


@pytest.mark.asyncio
async def test_pagerduty_sends_trigger_and_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "infersight.plugins.notifications.pagerduty.httpx.AsyncClient",
        lambda **_: RecordingClient(captured),
    )
    plugin = PagerDutyNotificationPlugin(
        PagerdutyConfig(enabled=True, routing_key="routing-key", severity_threshold="info")
    )

    await plugin.notify(issue())
    await plugin.notify(issue(cleared=True))

    assert captured[0][1]["event_action"] == "trigger"
    assert captured[1][1]["event_action"] == "resolve"
    assert captured[0][1]["dedup_key"] == "queue-saturation:deployment-a"


class CountingPlugin(NotificationPlugin):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def channel_name(self) -> str:
        return "counting"

    async def notify(self, _: Issue) -> None:
        self.calls += 1


@pytest.mark.asyncio
async def test_router_persists_deduplication_and_clears_on_resolution(tmp_path: Path) -> None:
    """A second router instance honours SQLite dispatch state until resolution."""
    async with SQLiteBackend(str(tmp_path / "infersight.db")) as storage:
        first_router = AlertRouter(
            AlertingConfig(deduplication_window_seconds=300), storage=storage
        )
        first_channel = CountingPlugin()
        first_router.add_channel(first_channel)
        await first_router.dispatch(issue())
        assert first_channel.calls == 1

        resumed_router = AlertRouter(
            AlertingConfig(deduplication_window_seconds=300), storage=storage
        )
        resumed_channel = CountingPlugin()
        resumed_router.add_channel(resumed_channel)
        await resumed_router.dispatch(issue())
        assert resumed_channel.calls == 0

        await resumed_router.dispatch(issue(cleared=True))
        await resumed_router.dispatch(issue())
        assert resumed_channel.calls == 2
