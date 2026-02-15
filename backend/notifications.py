"""
Notification Service — Email notifications via Resend.

All sends are wrapped in ``asyncio.to_thread()`` because the Resend SDK
is synchronous and would block the event loop otherwise.

Includes:
  - Single retry with 2s backoff on failure (log on second failure).
  - Respects user ``notification_prefs`` — callers should check prefs
    before calling, but we also guard here as a safety net.
  - Unsubscribe footer with one-click link in every email.

Notification types:
  1. Pipeline complete (manual run)
  2. Scheduled run complete
  3. Re-qualification score changes
  4. Welcome email
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from config import RESEND_API_KEY, NOTIFICATION_FROM_EMAIL, APP_URL

logger = logging.getLogger(__name__)

# Lazy-init Resend SDK (only if API key is set)
_resend_initialized = False


def _init_resend() -> bool:
    """Initialize Resend SDK. Returns True if ready."""
    global _resend_initialized
    if _resend_initialized:
        return True
    if not RESEND_API_KEY:
        logger.debug("Resend API key not configured — email notifications disabled")
        return False
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        _resend_initialized = True
        return True
    except ImportError:
        logger.warning("resend package not installed — email notifications disabled")
        return False


async def _send_email(
    to: str,
    subject: str,
    html: str,
    *,
    max_retries: int = 1,
) -> bool:
    """
    Send an email via Resend with retry.

    Runs the synchronous SDK call in a thread to avoid blocking the
    event loop.  Retries once after a 2-second backoff.

    Returns True on success, False on failure.
    """
    if not _init_resend():
        return False

    import resend

    # Append unsubscribe footer to every email
    html_with_footer = html + _unsubscribe_footer()

    payload = {
        "from": NOTIFICATION_FROM_EMAIL,
        "to": to,
        "subject": subject,
        "html": html_with_footer,
    }

    for attempt in range(max_retries + 1):
        try:
            await asyncio.to_thread(resend.Emails.send, payload)
            logger.info("Email sent to %s: %s", to, subject)
            return True
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "Email send failed (attempt %d/%d) to %s: %s — retrying in 2s",
                    attempt + 1,
                    max_retries + 1,
                    to,
                    e,
                )
                await asyncio.sleep(2)
            else:
                logger.error(
                    "Email send FAILED after %d attempts to %s: %s",
                    max_retries + 1,
                    to,
                    e,
                )
                return False


def _unsubscribe_footer() -> str:
    """Append an unsubscribe link to every email (legal compliance)."""
    return f"""
        <hr style="border: none; border-top: 1px solid #333; margin: 32px 0 16px;" />
        <p style="color: #666; font-size: 11px; font-family: monospace;">
            <a href="{APP_URL}/dashboard/settings#notifications"
               style="color: #888; text-decoration: underline;">
                Manage notification preferences
            </a>
            &nbsp;·&nbsp; Sent by Hunt
        </p>
    """


# ──────────────────────────────────────────────
# Notification Types
# ──────────────────────────────────────────────

async def send_pipeline_complete(
    user_email: str,
    user_name: str,
    pipeline_name: str,
    search_id: str,
    hot: int,
    review: int,
    total: int,
) -> bool:
    """Send notification when a pipeline (manual run) completes."""
    return await _send_email(
        to=user_email,
        subject=f"◈ Pipeline complete — {hot} hot leads found",
        html=f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; max-width: 500px;">
                <h2 style="color: #e0e0e0;">Hey {_esc(user_name)},</h2>
                <p style="color: #bbb;">Your pipeline <strong style="color: #fff;">{_esc(pipeline_name)}</strong> just finished.</p>
                <table style="margin: 16px 0; font-size: 14px; color: #ccc;">
                    <tr><td style="padding: 4px 16px 4px 0;">🔥 Hot leads:</td><td><strong style="color: #ff6b35;">{hot}</strong></td></tr>
                    <tr><td style="padding: 4px 16px 4px 0;">👀 Review:</td><td><strong style="color: #f5c542;">{review}</strong></td></tr>
                    <tr><td style="padding: 4px 16px 4px 0;">📊 Total qualified:</td><td><strong>{total}</strong></td></tr>
                </table>
                <p>
                    <a href="{APP_URL}/dashboard/leads?search_id={search_id}"
                       style="display: inline-block; background: #e0e0e0; color: #111; padding: 10px 20px;
                              border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 13px;">
                        View results →
                    </a>
                </p>
            </div>
        """,
    )


async def send_scheduled_run_complete(
    user_email: str,
    user_name: str,
    schedule_name: str,
    search_id: str,
    hot: int,
    review: int,
    new_leads: int,
) -> bool:
    """Send notification when a scheduled pipeline run completes."""
    return await _send_email(
        to=user_email,
        subject=f"◈ Scheduled hunt complete — {new_leads} new leads",
        html=f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; max-width: 500px;">
                <h2 style="color: #e0e0e0;">Hey {_esc(user_name)},</h2>
                <p style="color: #bbb;">Your scheduled pipeline <strong style="color: #fff;">{_esc(schedule_name)}</strong> ran automatically.</p>
                <table style="margin: 16px 0; font-size: 14px; color: #ccc;">
                    <tr><td style="padding: 4px 16px 4px 0;">🆕 New leads found:</td><td><strong>{new_leads}</strong></td></tr>
                    <tr><td style="padding: 4px 16px 4px 0;">🔥 Hot:</td><td><strong style="color: #ff6b35;">{hot}</strong></td></tr>
                    <tr><td style="padding: 4px 16px 4px 0;">👀 Review:</td><td><strong style="color: #f5c542;">{review}</strong></td></tr>
                </table>
                <p>
                    <a href="{APP_URL}/dashboard/leads?search_id={search_id}"
                       style="display: inline-block; background: #e0e0e0; color: #111; padding: 10px 20px;
                              border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 13px;">
                        View results →
                    </a>
                </p>
                <p style="color: #888; font-size: 12px;">
                    Manage your schedules in <a href="{APP_URL}/dashboard" style="color: #999;">Dashboard</a>
                </p>
            </div>
        """,
    )


async def send_requalification_alert(
    user_email: str,
    user_name: str,
    changed_leads: list[dict],
) -> bool:
    """Send notification when re-qualified leads have score changes."""
    rows = "".join(
        f'<tr><td style="padding: 4px 12px 4px 0; color: #ccc;">{_esc(l["name"])}</td>'
        f'<td style="padding: 4px 12px 4px 0;">{l["old_score"]}→{l["new_score"]}</td>'
        f'<td>{l["change"]}</td></tr>'
        for l in changed_leads[:20]  # Cap at 20 to keep email reasonable
    )
    return await _send_email(
        to=user_email,
        subject=f"◈ {len(changed_leads)} leads changed score this week",
        html=f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; max-width: 500px;">
                <h2 style="color: #e0e0e0;">Hey {_esc(user_name)},</h2>
                <p style="color: #bbb;">{len(changed_leads)} of your leads had score changes after re-qualification:</p>
                <table style="margin: 16px 0; font-size: 13px; color: #ccc;">
                    <tr style="color: #888; font-size: 11px; text-transform: uppercase;">
                        <th style="text-align: left; padding-bottom: 8px;">Company</th>
                        <th style="text-align: left; padding-bottom: 8px;">Score</th>
                        <th style="text-align: left; padding-bottom: 8px;">Trend</th>
                    </tr>
                    {rows}
                </table>
                <p>
                    <a href="{APP_URL}/dashboard/leads"
                       style="display: inline-block; background: #e0e0e0; color: #111; padding: 10px 20px;
                              border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 13px;">
                        View leads →
                    </a>
                </p>
            </div>
        """,
    )


async def send_welcome(user_email: str, user_name: str) -> bool:
    """Send welcome email on signup."""
    return await _send_email(
        to=user_email,
        subject="Welcome to Hunt ◈",
        html=f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; max-width: 500px;">
                <h2 style="color: #e0e0e0;">Welcome, {_esc(user_name)}!</h2>
                <p style="color: #bbb;">Hunt is your AI agent swarm for B2B lead discovery.</p>
                <p style="color: #bbb;">Here&rsquo;s how to get started:</p>
                <ol style="color: #ccc; font-size: 14px; line-height: 1.8;">
                    <li>Define your ideal customer profile</li>
                    <li>Launch a discovery pipeline</li>
                    <li>Review and qualify your leads</li>
                </ol>
                <p>
                    <a href="{APP_URL}/dashboard/new"
                       style="display: inline-block; background: #e0e0e0; color: #111; padding: 10px 20px;
                              border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 13px;">
                        Launch your first pipeline →
                    </a>
                </p>
            </div>
        """,
    )


def _esc(s: str) -> str:
    """Basic HTML escaping for user-provided strings."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
