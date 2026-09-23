"""Success/failure notifications for the DAG's notify task.

Standard library only, so it runs inside Airflow's own Python environment. Channels are
enabled by environment variables; with none set, the message is only logged.

    SLACK_WEBHOOK_URL                               Slack incoming webhook
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD  e.g. smtp.gmail.com / 587 / app password
    NOTIFY_EMAIL_TO                                 comma-separated recipients
"""
from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
import urllib.request


def send_slack(text: str, webhook_url: str) -> None:
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def send_email(subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ["SMTP_USER"]
    message["To"] = os.environ["NOTIFY_EMAIL_TO"]
    message.set_content(body)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)


def notify(subject: str, body: str) -> list[str]:
    """Send to every configured channel. A broken channel is logged, not raised, so it
    cannot hide the pipeline's real status."""
    print(f"{subject}\n{body}")
    sent = []
    channels = {
        "slack": (bool(os.getenv("SLACK_WEBHOOK_URL")), lambda: send_slack(f"*{subject}*\n{body}", os.environ["SLACK_WEBHOOK_URL"])),
        "email": (all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAIL_TO")), lambda: send_email(subject, body)),
    }
    for name, (enabled, send) in channels.items():
        if not enabled:
            continue
        try:
            send()
            sent.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN {name} notification failed: {exc}")
    return sent
