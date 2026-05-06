"""
telegram_bot.py
---------------
Thin wrapper around the Telegram Bot API.
Uses HTML parse mode; auto-splits messages that exceed the 4096-char limit.
"""

import requests
import logging
import time

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSG_LEN = 4096


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Send a single message. Returns True on success."""
    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def send_digest(token: str, chat_id: str, sections: list[str]) -> None:
    """
    Send a list of pre-formatted message sections.
    Each section is sent as a separate message.
    Sections longer than MAX_MSG_LEN are further split on newline boundaries.
    """
    for section in sections:
        chunks = _split_message(section)
        for chunk in chunks:
            ok = send_message(token, chat_id, chunk)
            if not ok:
                logger.warning(f"Failed to send chunk: {chunk[:80]}...")
            time.sleep(0.4)  # Telegram rate limit: ~30 messages/sec, be conservative


def _split_message(text: str) -> list[str]:
    """Split a message into chunks ≤ MAX_MSG_LEN, breaking on newlines."""
    if len(text) <= MAX_MSG_LEN:
        return [text]
    chunks = []
    lines = text.split("\n")
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > MAX_MSG_LEN:
            if current:
                chunks.append(current.rstrip("\n"))
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip("\n"))
    return chunks
