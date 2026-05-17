"""Wrapper minimo del Telegram Bot API."""

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4000  # Telegram limit is 4096, dejamos margen


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    """Manda un mensaje. Si excede el limite, parte en chunks respetando saltos de linea."""
    chunks = _chunk(text, MAX_MESSAGE_LEN)
    for chunk in chunks:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
        resp.raise_for_status()


def _chunk(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    out, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > max_len:
            out.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        out.append(buf)
    return out


def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
