import datetime
from typing import Dict, List, Tuple

import requests


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> Tuple[bool, str]:
    """Send a Markdown-formatted message to a Telegram chat."""
    if not bot_token or not chat_id:
        return False, "Telegram Bot Token or Chat ID not configured."

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
    payload = {
        "chat_id": chat_id.strip(),
        "text": text,
        "parse_mode": "Markdown",
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
    msg = f"🔔 *Meroshare Bot Test Alert*\n\n✅ Your Telegram notifications are successfully configured!\n🕒 *Time:* {now}"
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
    """Format and dispatch a clean execution report to Telegram."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "📊 *Meroshare IPO Auto-Apply Summary*",
        f"🏢 *Company:* {company_name or 'Open Issue'}",
        f"🕒 *Run Time:* {now}",
        f"👥 *Total Accounts:* {total}",
        f"✅ *Successfully Applied:* {len(applied)}",
        f"⚠️ *Skipped / Already Done:* {len(skipped)}",
        f"❌ *Failed / Errors:* {len(failed)}",
        "",
    ]

    if applied:
        lines.append("✅ *Applied:*")
        for item in applied:
            lines.append(f"• {item.get('name')}: {item.get('kitta', '10')} kitta")
        lines.append("")

    if skipped:
        lines.append("⚠️ *Skipped:*")
        for item in skipped:
            lines.append(f"• {item.get('name')} ({item.get('reason', 'Already Applied')})")
        lines.append("")

    if failed:
        lines.append("❌ *Failed:*")
        for item in failed:
            lines.append(f"• {item.get('name')}: {item.get('error', 'Error')}")

    message = "\n".join(lines)
    return send_telegram_message(bot_token, chat_id, message)
