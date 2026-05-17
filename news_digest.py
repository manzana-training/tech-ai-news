"""Tech AI News — digest diario.

Flujo: lee RSS → filtra 24h → deduplica → Claude Haiku cura/resume → Telegram.
Corre por cron en EC2. Ver deploy/README.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
from anthropic import Anthropic
from dotenv import load_dotenv

from prompts import CURATION_SYSTEM, CURATION_USER_TEMPLATE
from sources import SOURCES, TECH_AI_KEYWORDS
from taxonomy import classify
from telegram_client import escape_html, send_message

# ---- Carga de config ---------------------------------------------------------

_CENTRAL_SECRETS_WINDOWS = Path.home() / ".secrets" / "credentials.env"
_CENTRAL_SECRETS_UNIX = Path.home() / ".env"

# Prod (EC2): ~/.env  —  Dev (Windows): %USERPROFILE%\.secrets\credentials.env
if _CENTRAL_SECRETS_WINDOWS.exists():
    load_dotenv(_CENTRAL_SECRETS_WINDOWS)
elif _CENTRAL_SECRETS_UNIX.exists():
    load_dotenv(_CENTRAL_SECRETS_UNIX)

# Override con .env local del proyecto
load_dotenv(Path(__file__).parent / ".env", override=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "24"))
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_ADMIN_CHAT_ID")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("digest")


# ---- Modelo de datos ---------------------------------------------------------


@dataclass
class Item:
    source: str
    source_type: str
    title: str
    link: str
    summary: str
    published: datetime

    def fingerprint(self) -> str:
        normalized = re.sub(r"\W+", "", self.title.lower())[:120]
        return hashlib.md5(normalized.encode()).hexdigest()


# ---- Ingesta -----------------------------------------------------------------


def fetch_items() -> list[Item]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items: list[Item] = []
    for src in SOURCES:
        try:
            feed = feedparser.parse(src["url"])
        except Exception as e:
            log.warning("fetch failed %s: %s", src["name"], e)
            continue

        for entry in feed.entries:
            published = _parse_date(entry)
            if published is None or published < cutoff:
                continue

            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            summary = _strip_html(entry.get("summary") or entry.get("description") or "")[:500]
            if not title or not link:
                continue

            if src.get("mixed") and not _is_tech_ai(title + " " + summary):
                continue

            items.append(Item(src["name"], src.get("type", "publisher"), title, link, summary, published))

    log.info("fetched %d items from %d sources", len(items), len(SOURCES))
    return _dedupe(items)


def _parse_date(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        tm = entry.get(field)
        if tm:
            return datetime(*tm[:6], tzinfo=timezone.utc)
    return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


_KEYWORD_RES = [re.compile(p, re.I) for p in TECH_AI_KEYWORDS]


def _is_tech_ai(text: str) -> bool:
    return any(p.search(text) for p in _KEYWORD_RES)


def _dedupe(items: list[Item]) -> list[Item]:
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x.published, reverse=True):
        fp = it.fingerprint()
        if fp in seen:
            continue
        seen.add(fp)
        out.append(it)
    log.info("deduped to %d items", len(out))
    return out


# ---- Curacion con Claude -----------------------------------------------------


def curate(items: list[Item], classified: list[dict]) -> list[dict]:
    if not items:
        return []

    def _tags(cls: dict) -> str:
        topics = ",".join(cls.get("topics") or []) or "-"
        ents = ",".join(cls.get("entities") or []) or "-"
        region = cls.get("region") or "-"
        return f"topics={topics} entities={ents} region={region}"

    listing = "\n".join(
        f"[{i}] {it.source} | {it.title} | {it.summary[:200]} | {_tags(classified[i])}"
        for i, it in enumerate(items)
    )
    user_msg = CURATION_USER_TEMPLATE.format(lookback_hours=LOOKBACK_HOURS, items=listing)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        system=CURATION_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("claude devolvio JSON invalido: %s\nraw: %s", e, raw[:500])
        return []

    selected = []
    for sel in data.get("selected", []):
        idx = sel.get("index")
        summary = (sel.get("summary") or "").strip()
        if idx is None or not (0 <= idx < len(items)) or not summary:
            continue
        it = items[idx]
        selected.append({"index": idx, "source": it.source, "title": it.title, "link": it.link, "summary": summary})

    log.info("claude selecciono %d noticias", len(selected))
    return selected


# ---- Persistencia historica --------------------------------------------------


def persist_history(items: list[Item], classified: list[dict], selected: list[dict]) -> None:
    """Appendea todos los items del dia a history/YYYY-MM-DD.jsonl.

    Schema por linea (ver CLAUDE.md):
      id, fetched_at, published_at, digest_date, source, source_type,
      title, link, rss_summary, lang,
      topics, entities, region,
      selected_in_digest, digest_rank, digest_summary
    """
    history_dir = Path(__file__).parent / "history"
    history_dir.mkdir(exist_ok=True)

    now_utc = datetime.now(timezone.utc)
    digest_date = now_utc.strftime("%Y-%m-%d")
    fetched_at = now_utc.isoformat()

    # Mapa idx -> {rank, summary} para los seleccionados.
    selected_by_idx: dict[int, dict] = {}
    for rank, sel in enumerate(selected, 1):
        idx = sel.get("index")
        if idx is None:
            continue
        selected_by_idx[idx] = {"rank": rank, "summary": sel["summary"]}

    out_path = history_dir / f"{digest_date}.jsonl"
    with out_path.open("a", encoding="utf-8") as f:
        for i, (item, cls) in enumerate(zip(items, classified)):
            sel = selected_by_idx.get(i)
            record = {
                "id": item.fingerprint(),
                "fetched_at": fetched_at,
                "published_at": item.published.isoformat(),
                "digest_date": digest_date,
                "source": item.source,
                "source_type": item.source_type,
                "title": item.title,
                "link": item.link,
                "rss_summary": item.summary,
                "lang": "en",
                "topics": cls["topics"],
                "entities": cls["entities"],
                "region": cls["region"],
                "selected_in_digest": sel is not None,
                "digest_rank": sel["rank"] if sel else None,
                "digest_summary": sel["summary"] if sel else None,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info("persisted %d items to history/%s", len(items), out_path.name)


# ---- Formato Telegram --------------------------------------------------------


def format_message(selected: list[dict]) -> str:
    if not selected:
        return "<b>Tech AI News</b>\n\nSin noticias relevantes en las ultimas horas."

    today = datetime.now().strftime("%d %b %Y")
    lines = [f"<b>Tech AI News - {today}</b>", ""]
    for i, it in enumerate(selected, 1):
        title = escape_html(it["title"])
        source = escape_html(it["source"])
        summary = escape_html(it["summary"])
        lines.append(f'{i}. <a href="{it["link"]}"><b>{title}</b></a>')
        lines.append(f"   <i>{source}</i>")
        lines.append(f"   {summary}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---- Entry point -------------------------------------------------------------


def main() -> int:
    missing = [k for k, v in {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID (o TELEGRAM_ADMIN_CHAT_ID)": TELEGRAM_CHAT_ID,
    }.items() if not v]
    if missing:
        log.error("faltan variables: %s", ", ".join(missing))
        return 1

    items = fetch_items()
    if not items:
        log.warning("no items fetched — nada que mandar")
        return 0

    classified = [classify(it.title, it.summary, it.source_type) for it in items]

    try:
        selected = curate(items, classified)
    except Exception as e:
        log.error("curate fallo: %s — se persiste sin seleccion", e)
        selected = []

    try:
        persist_history(items, classified, selected)
    except Exception as e:
        log.error("persist_history fallo: %s — se sigue con telegram igual", e)

    message = format_message(selected)
    send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message, parse_mode="HTML")
    log.info("digest enviado a chat %s", TELEGRAM_CHAT_ID)
    return 0


if __name__ == "__main__":
    sys.exit(main())
