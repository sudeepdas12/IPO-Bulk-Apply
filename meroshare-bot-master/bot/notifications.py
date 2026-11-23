import datetime
import html
import re
from typing import Dict, List, Tuple

import requests


def escape_telegram_markdown(text: str) -> str:
    """Escapes Telegram Markdown special characters to prevent HTTP 400 Bad Request."""
    if not text:
        return ""
    # Characters reserved in legacy Markdown: _, *, `, [
    # Escape them with a backslash if not intentionally formatting
    return re.sub(r"([_*`\[])", r"\\\1", str(text))


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> Tuple[bool, str]:
    """Send an HTML or Markdown-formatted message to a Telegram chat."""
    if not bot_token or not chat_id:
        return False, "Telegram Bot Token or Chat ID not configured."

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
    payload = {
        "chat_id": chat_id.strip(),
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("ok"):
            return True, "Notification sent successfully."
        return False, f"Telegram API error: {data.get('description', 'Unknown error')}"
    except Exception as e:
        return False, f"Failed to send Telegram message: {str(e)}"


def test_telegram_connection(bot_token: str, chat_id: str) -> Tuple[bool, str]:
    """Send a test message to verify Telegram bot setup."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"🔔 <b>Meroshare Bot Test Alert</b>\n\n✅ Your Telegram notifications are successfully configured!\n🕒 <b>Time:</b> {now}"
    return send_telegram_message(bot_token, chat_id, msg)


def send_run_summary(
    bot_token: str,
    chat_id: str,
    company_name: str,
    total: int,
    applied: List[Dict[str, str]],
    skipped: List[Dict[str, str]],
    failed: List[Dict[str, str]],
) -> Tuple[bool, str]:
    """Format and dispatch a clean execution report to Telegram using safe HTML formatting."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    comp = html.escape(company_name or "Open Issue")
    lines = [
        "📊 <b>Meroshare IPO Auto-Apply Summary</b>",
        f"🏢 <b>Company:</b> {comp}",
        f"🕒 <b>Run Time:</b> {now}",
        f"👥 <b>Total Accounts:</b> {total}",
        f"✅ <b>Successfully Applied:</b> {len(applied)}",
        f"⚠️ <b>Skipped / Already Done:</b> {len(skipped)}",
        f"❌ <b>Failed / Errors:</b> {len(failed)}",
        "",
    ]

    if applied:
        lines.append("✅ <b>Applied:</b>")
        for item in applied:
            name = html.escape(str(item.get("name", "")))
            kitta = html.escape(str(item.get("kitta", "10")))
            lines.append(f"• {name}: {kitta} kitta")
        lines.append("")

    if skipped:
        lines.append("⚠️ <b>Skipped:</b>")
        for item in skipped:
            name = html.escape(str(item.get("name", "")))
            reason = html.escape(str(item.get("reason", "Already Applied")))
            lines.append(f"• {name} ({reason})")
        lines.append("")

    if failed:
        lines.append("❌ <b>Failed:</b>")
        for item in failed:
            name = html.escape(str(item.get("name", "")))
            err = html.escape(str(item.get("error", "Error")))
            lines.append(f"• {name}: {err}")

    message = "\n".join(lines)
    return send_telegram_message(bot_token, chat_id, message)
