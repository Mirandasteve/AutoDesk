"""
AutoDesk - Email notification service
=====================================

Sends the three notification events required by the SRS (section 18):

1. **Ticket created**  -> the employee who raised it, confirming the AI result
2. **Status updated**  -> the employee who raised it
3. **Ticket routed**   -> every active agent of the owning support team

Design constraints
------------------
* **Email must never break the request.** ``MAIL_FAIL_SILENTLY`` is on, and
  every send is wrapped in try/except, so a missing SMTP server degrades to a
  logged warning instead of a failed ticket submission (SRS section 18).
* **Disabled by default in development.** ``MAIL_ENABLED=False`` in ``.env``
  keeps the console quiet. Set it to ``True`` and fill in ``MAIL_SERVER`` etc.
  to send real mail.
* **No secrets in code.** Every setting comes from the Flask config, which is
  populated from environment variables.

All templates are plain text plus a minimal HTML body, so they render in any
mail client without an external template engine.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from flask import current_app
from flask_mail import Message

from app.extensions import mail

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
def is_enabled() -> bool:
    """``True`` when Flask-Mail is configured and switched on."""
    try:
        return bool(current_app.config.get("MAIL_ENABLED"))
    except RuntimeError:
        return False


def _config(key: str, default: Any = None) -> Any:
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


def _sender() -> str:
    return _config("MAIL_DEFAULT_SENDER") or "AutoDesk IT Helpdesk <no-reply@autodesk.local>"


def _split(addresses: Optional[Sequence[str]]) -> List[str]:
    """Normalise a list/CSV-ish value into a clean list of addresses."""
    if not addresses:
        return []
    if isinstance(addresses, str):
        addresses = [part for part in addresses.split(",")]
    return [str(a).strip() for a in addresses if str(a).strip()]


# ---------------------------------------------------------------------------
# Low-level send
# ---------------------------------------------------------------------------
def send_email(
    subject: str,
    recipients: Iterable[str],
    body_text: str,
    body_html: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Send one message. Never raises.

    Returns a small result dict so callers (and tests) can assert on what
    happened without inspecting Flask-Mail internals::

        {"sent": True, "recipients": [...], "error": None}
    """
    recipients = _split(list(recipients))
    cc = _split(cc)

    if not is_enabled():
        logger.info("[mail:disabled] would send %r to %s", subject, ", ".join(recipients))
        return {"sent": False, "skipped": True, "recipients": recipients, "error": None}

    if not recipients:
        logger.warning("[mail] %r had no recipients; nothing sent", subject)
        return {"sent": False, "skipped": True, "recipients": [], "error": "no-recipients"}

    try:
        message = Message(
            subject=subject,
            recipients=recipients,
            body=body_text,
            html=body_html,
            sender=_sender(),
            cc=cc or None,
        )
        mail.send(message)
        logger.info("[mail:sent] %r -> %s", subject, ", ".join(recipients))
        return {"sent": True, "skipped": False, "recipients": recipients, "error": None}

    except Exception as exc:
        # Ticket submission must succeed even when SMTP is unreachable.
        logger.warning(
            "[mail:failed] %r could not be delivered (%s: %s)",
            subject,
            type(exc).__name__,
            exc,
        )
        return {
            "sent": False,
            "skipped": False,
            "recipients": recipients,
            "error": f"{type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
def _priority_badge(priority: str) -> str:
    colours = {
        "Critical": "#b91c1c",
        "High": "#c2410c",
        "Medium": "#a16207",
        "Low": "#15803d",
    }
    return colours.get(priority, "#334155")


def _layout(title: str, intro: str, rows: Sequence[tuple], footer: str) -> str:
    """Build a small, self-contained HTML email body."""
    trs = "\n".join(
        f'      <tr><td style="padding:6px 12px 6px 0;color:#64748b;font-size:14px;'
        f'white-space:nowrap">{label}</td>'
        f'<td style="padding:6px 0;color:#0f172a;font-size:14px;font-weight:600">'
        f"{value}</td></tr>"
        for label, value in rows
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f1f5f9;font-family:Segoe UI,Helvetica,Arial,sans-serif">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;
              border:1px solid #e2e8f0;overflow:hidden">
    <div style="background:#1e293b;padding:20px 28px">
      <span style="color:#f8fafc;font-size:18px;font-weight:700">AutoDesk</span>
      <span style="color:#94a3b8;font-size:13px;margin-left:8px">IT Helpdesk</span>
    </div>
    <div style="padding:28px">
      <h2 style="margin:0 0 12px;color:#0f172a;font-size:18px">{title}</h2>
      <p style="margin:0 0 18px;color:#475569;font-size:14px;line-height:1.6">{intro}</p>
      <table style="width:100%;border-collapse:collapse;border-top:1px solid #e2e8f0;
                    padding-top:8px">
{trs}
      </table>
      <p style="margin:24px 0 0;color:#64748b;font-size:12px;line-height:1.6">{footer}</p>
    </div>
  </div>
</body></html>"""


def _text_layout(title: str, intro: str, rows: Sequence[tuple], footer: str) -> str:
    width = max((len(label) for label, _ in rows), default=0)
    lines = [
        f"{label.ljust(width)} : {value}" for label, value in rows
    ]
    return "\n".join([title, "=" * len(title), "", intro, "", *lines, "", footer, ""])


# ---------------------------------------------------------------------------
# Ticket email events
# ---------------------------------------------------------------------------
def send_ticket_created_email(user, ticket, prediction: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Event 1 - the employee receives confirmation plus the AI analysis result.

    This is the email that proves the classification was real: it quotes the
    category, the confidence and the routed team straight from the ticket row.
    """
    prediction = prediction or {}
    confidence = prediction.get("confidence")
    confidence_text = f"{float(confidence) * 100:.1f}%" if confidence is not None else "n/a"

    rows = [
        ("Ticket ID", f"#{ticket.id}"),
        ("Subject", ticket.title),
        ("Category", f"{ticket.category} (AI, confidence {confidence_text})"),
        ("Priority", ticket.priority),
        ("Assigned team", ticket.assigned_team),
        ("Status", ticket.status),
        ("SLA target", f"{_sla_text(ticket)}"),
    ]
    intro = (
        "Your support request has been received and analysed automatically. "
        "The details below were produced by the AutoDesk AI triage pipeline."
    )
    subject = f"[AutoDesk] Ticket #{ticket.id} received - {ticket.category} / {ticket.priority}"

    return send_email(
        subject,
        recipients=[user.email],
        body_text=_text_layout(
            f"Ticket #{ticket.id} received", intro, rows, _footer(ticket)
        ),
        body_html=_layout(
            f"Ticket #{ticket.id} received", intro, rows, _footer(ticket)
        ),
    )


def send_status_update_email(user, ticket, previous_status: str, new_status: str) -> Dict[str, Any]:
    """Event 2 - the employee is told their ticket moved forward."""
    rows = [
        ("Ticket ID", f"#{ticket.id}"),
        ("Subject", ticket.title),
        ("Previous status", previous_status),
        ("New status", f"<strong>{new_status}</strong>"),
        ("Priority", ticket.priority),
        ("Assigned team", ticket.assigned_team),
    ]
    if new_status == "Resolved" and ticket.resolved_at:
        rows.append(("Resolved at", _iso(ticket.resolved_at)))
    if ticket.resolution_notes:
        notes = ticket.resolution_notes
        rows.append(("Resolution notes", notes if len(notes) <= 400 else notes[:397] + "..."))

    intro = (
        "There is an update on your support request."
        if new_status != "Resolved"
        else "Your support request has been resolved. Thank you for your patience."
    )
    subject = f"[AutoDesk] Ticket #{ticket.id} updated to {new_status}"

    return send_email(
        subject,
        recipients=[user.email],
        body_text=_text_layout(
            f"Ticket #{ticket.id} is now {new_status}", intro, rows, _footer(ticket)
        ),
        body_html=_layout(
            f"Ticket #{ticket.id} is now {new_status}", intro, rows, _footer(ticket)
        ),
    )


def send_team_routing_email(
    team: str,
    ticket,
    agents: Sequence[Any],
    priority: str = "",
) -> Dict[str, Any]:
    """
    Event 3 - the owning support team is paged for a newly routed ticket.

    Only agents whose ``team`` matches are notified; a ticket for the Network
    Team never emails the Software Team.
    """
    recipients = [agent.email for agent in agents if getattr(agent, "email", None)]
    if not recipients:
        logger.info("[mail] no agents on %s; skipping routing alert for #%s", team, ticket.id)
        return {"sent": False, "skipped": True, "recipients": [], "error": "no-agents"}

    priority = priority or ticket.priority
    rows = [
        ("Ticket ID", f"#{ticket.id}"),
        ("Subject", ticket.title),
        ("Category", ticket.category),
        ("Priority", f"<span style='color:{_priority_badge(priority)}'>{priority}</span>"),
        ("Assigned team", ticket.assigned_team),
        ("Status", ticket.status),
        ("SLA target", _sla_text(ticket)),
        ("Raised by", f"{ticket.creator.name} ({ticket.creator.email})" if ticket.creator else "n/a"),
    ]
    intro = (
        "A new ticket has been classified and routed to your team by the "
        "AutoDesk AI triage pipeline. Please review it in the agent dashboard."
    )
    subject = f"[AutoDesk] New {priority}-priority {ticket.category} ticket #{ticket.id}"

    # CC the administrators so leadership visibility does not depend on SMTP
    # group addresses being configured.
    admins = _split(_config("MAIL_ADMIN_RECIPIENTS"))

    return send_email(
        subject,
        recipients=recipients,
        cc=admins,
        body_text=_text_layout(
            f"New ticket #{ticket.id} for {team}", intro, rows, _footer(ticket)
        ),
        body_html=_layout(
            f"New ticket #{ticket.id} for {team}", intro, rows, _footer(ticket)
        ),
    )


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------
def _iso(value) -> str:
    from datetime import timezone

    if value is None:
        return "n/a"
    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _sla_text(ticket) -> str:
    """Human-readable SLA deadline, or a dash when it is not computable."""
    due = getattr(ticket, "sla_due_at", None)
    return _iso(due) if due else "n/a"


def _footer(ticket) -> str:
    return (
        "This message was generated automatically by AutoDesk, the IT ticket "
        "classification and routing system. Please do not reply to this email; "
        f"use the helpdesk portal to follow ticket #{ticket.id}."
    )
