"""Email (SMTP) Notification Plugin.

Sends HTML issue alert emails via aiosmtplib with STARTTLS support.
Credentials are never logged.
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from infersight.config import EmailConfig
from infersight.plugins.base import Issue, NotificationPlugin, Severity

logger = logging.getLogger(__name__)

_SEVERITY_COLOR: dict[Severity, str] = {
    Severity.INFO: "#3b82f6",
    Severity.WARNING: "#f59e0b",
    Severity.CRITICAL: "#ef4444",
}


def _build_html(issue: Issue) -> str:
    color = _SEVERITY_COLOR.get(issue.severity, "#6b7280")
    rows = "".join(
        f"<tr><td style='padding:4px 8px;font-weight:bold'>{k}</td>"
        f"<td style='padding:4px 8px'>{v}</td></tr>"
        for k, v in issue.supporting_metrics.items()
    )
    return f"""
<html><body style="font-family:sans-serif;color:#111">
  <div style="border-left:4px solid {color};padding:12px 16px;background:#f9fafb">
    <h2 style="margin:0 0 8px 0;color:{color}">
      [{issue.severity.value.upper()}] {issue.issue_type}
    </h2>
    <p><strong>Deployment:</strong> {issue.deployment_id}</p>
    <p><strong>Detected:</strong> {issue.detected_at.isoformat()}</p>
    <p>{issue.description}</p>
  </div>
  <h3>Supporting metrics</h3>
  <table style="border-collapse:collapse;font-size:13px">
    <tbody>{rows}</tbody>
  </table>
</body></html>
""".strip()


class EmailNotificationPlugin(NotificationPlugin):
    """Sends issue alert emails over SMTP with STARTTLS."""

    def __init__(self, config: EmailConfig) -> None:
        self._cfg = config

    @property
    def channel_name(self) -> str:
        return "email"

    def _below_threshold(self, issue: Issue) -> bool:
        order = [Severity.INFO, Severity.WARNING, Severity.CRITICAL]
        try:
            threshold = Severity(self._cfg.severity_threshold)
        except ValueError:
            threshold = Severity.WARNING
        return order.index(issue.severity) < order.index(threshold)

    async def notify(self, issue: Issue) -> None:
        if not self._cfg.enabled:
            return
        if self._below_threshold(issue):
            return
        if not self._cfg.to_addresses:
            logger.warning("Email to_addresses is empty — skipping notification")
            return
        if not self._cfg.smtp_host:
            logger.warning("Email smtp_host is not configured — skipping notification")
            return

        subject = (
            f"[InferSight {issue.severity.value.upper()}] "
            f"{issue.issue_type} on {issue.deployment_id}"
        )
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._cfg.from_address or "infersight@localhost"
        msg["To"] = ", ".join(self._cfg.to_addresses)
        msg.attach(MIMEText(issue.description, "plain"))
        msg.attach(MIMEText(_build_html(issue), "html"))

        password = self._cfg.smtp_password.get_secret_value()
        try:
            await aiosmtplib.send(
                msg,
                hostname=self._cfg.smtp_host,
                port=self._cfg.smtp_port,
                username=self._cfg.smtp_user or None,
                password=password or None,
                start_tls=True,
            )
            logger.info(
                "Email notification sent",
                extra={"issue_id": issue.issue_id, "recipients": len(self._cfg.to_addresses)},
            )
        except Exception:
            logger.exception(
                "Failed to send email notification",
                extra={"issue_id": issue.issue_id, "deployment_id": issue.deployment_id},
            )
