"""Backfill historico de Hacker News via Algolia API.

Recupera items front-page de HN dia por dia, los pasa por el MISMO filtro
TECH_AI_KEYWORDS y la MISMA clasificacion (taxonomy.classify) que la pipeline
diaria, y escribe a `history/YYYY-MM-DD.jsonl` en el formato exacto que produce
`news_digest.py` (mismos campos, mismo schema).

NO toca Claude. NO toca Telegram. NO toca la pipeline de produccion en EC2.

Reversibilidad: antes de la primera escritura crea un backup completo de `history/`
en `history.bak.YYYY-MM-DD/`. Para revertir:

    rm -rf history && mv history.bak.<fecha> history

Por defecto solo backfillea fechas que NO existen en `history/` para evitar
mezclar con la data de produccion. La pipeline real arranco a persistir el
2026-04-25, asi que el rango natural es 2026-01-01 -> 2026-04-24 (114 dias).

Uso:
    python analysis/backfill_hn.py                       # full range 2026-01-01..2026-04-24
    python analysis/backfill_hn.py --start 2026-03-01    # desde fecha custom
    python analysis/backfill_hn.py --end 2026-01-31      # hasta fecha custom
    python analysis/backfill_hn.py --dry-run             # NO escribe; solo reporta
    python analysis/backfill_hn.py --start 2026-04-20 --dry-run    # smoke test
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import re
import shutil
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sources import TECH_AI_KEYWORDS  # type: ignore  # noqa: E402
from taxonomy import classify          # type: ignore  # noqa: E402

HISTORY = ROOT / "history"
ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"

# Filtro idéntico al de la pipeline (news_digest._is_tech_ai)
_KEYWORD_RES = [re.compile(p, re.I) for p in TECH_AI_KEYWORDS]


def is_tech_ai(text: str) -> bool:
    return any(p.search(text) for p in _KEYWORD_RES)


def fingerprint_id(title: str) -> str:
    """Mismo md5 normalizado que la pipeline."""
    return hashlib.md5(title.lower().strip().encode("utf-8")).hexdigest()


def backup_history(stamp: str) -> Path:
    """Backup completo de history/ -> history.bak.YYYY-MM-DD/.

    Idempotente: si ya existe el backup de hoy, no lo sobrescribe.
    """
    bak = ROOT / f"history.bak.{stamp}"
    if bak.exists():
        logging.info("backup already exists, skipping: %s", bak.name)
        return bak
    if not HISTORY.exists():
        logging.warning("history/ does not exist; nothing to back up")
        return bak
    logging.info("creating backup: %s/ -> %s/", HISTORY.name, bak.name)
    shutil.copytree(HISTORY, bak)
    return bak


MIN_POINTS = 30  # proxy "llego al front page" — el tag `front_page` de Algolia no funciona


def fetch_day(date: datetime.date) -> list[dict]:
    """Trae items HN del dia UTC con points >= MIN_POINTS (paginado).

    El tag `front_page` de Algolia no esta poblado (devuelve 0). Usamos
    `tags=story` con filtro points>=30, que aproxima los items que llegaron
    al front page (slot mas bajo del front page suele tener ~30-50 puntos).

    Algolia limita a 1000 hits/query con paginacion 100x10.
    """
    start_ts = int(datetime.datetime.combine(date, datetime.time.min, datetime.timezone.utc).timestamp())
    end_ts = start_ts + 86400
    out: list[dict] = []
    page = 0
    while True:
        try:
            r = requests.get(
                ALGOLIA,
                params={
                    "tags": "story",
                    "numericFilters": (
                        f"created_at_i>={start_ts},created_at_i<{end_ts},"
                        f"points>={MIN_POINTS}"
                    ),
                    "hitsPerPage": 100,
                    "page": page,
                },
                timeout=30,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            logging.warning("algolia fetch failed for %s page %d: %s", date, page, e)
            break
        data = r.json()
        hits = data.get("hits", [])
        if not hits:
            break
        out.extend(hits)
        nb_pages = data.get("nbPages", 1)
        if page + 1 >= nb_pages:
            break
        page += 1
        time.sleep(0.4)
    return out


def hit_to_record(hit: dict, fetched_at: str, digest_date: str) -> dict | None:
    """Convierte un hit Algolia al schema de produccion. None si lo descartamos."""
    title = (hit.get("title") or "").strip()
    if not title:
        return None
    url = (hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}").strip()
    points = hit.get("points") or 0
    num_comments = hit.get("num_comments") or 0

    # Formato del rss_summary identico al hnrss.org/frontpage que usa la pipeline
    summary = (
        f"Article URL: {url}\n"
        f"Comments URL: https://news.ycombinator.com/item?id={hit['objectID']}\n"
        f"Points: {points}\n# Comments: {num_comments}"
    )

    # MISMO filtro que la pipeline (HN es source mixed=True)
    if not is_tech_ai(title + " " + summary):
        return None

    classification = classify(title, summary, "community")

    return {
        "id": fingerprint_id(title),
        "fetched_at": fetched_at,
        "published_at": hit.get("created_at"),
        "digest_date": digest_date,
        "source": "Hacker News (top)",
        "source_type": "community",
        "title": title,
        "link": url,
        "rss_summary": summary,
        "lang": "en",
        "topics": classification["topics"],
        "entities": classification["entities"],
        "region": classification["region"],
        "selected_in_digest": False,
        "digest_rank": None,
        "digest_summary": None,
        "backfill_source": "hn-algolia",  # marker para trazabilidad / cleanup
    }


def write_day(date: datetime.date, records: list[dict]) -> int:
    """Escribe records al JSONL de ese dia. Salta si el archivo ya existe."""
    out_file = HISTORY / f"{date.isoformat()}.jsonl"
    if out_file.exists():
        logging.info("skip %s (file exists, prod data)", date)
        return 0
    HISTORY.mkdir(exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


def date_range(start: datetime.date, end: datetime.date):
    d = start
    while d <= end:
        yield d
        d += datetime.timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01", help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", default="2026-04-24", help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--dry-run", action="store_true", help="no escribe, solo reporta")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    start = datetime.date.fromisoformat(args.start)
    end = datetime.date.fromisoformat(args.end)
    if start > end:
        logging.error("start > end")
        sys.exit(1)

    today = datetime.date.today().isoformat()
    if not args.dry_run:
        backup_history(today)

    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    total_raw, total_filtered, total_written = 0, 0, 0
    days_processed = 0

    for d in date_range(start, end):
        out_file = HISTORY / f"{d.isoformat()}.jsonl"
        if out_file.exists():
            logging.info("%s : skip (already exists)", d)
            continue

        hits = fetch_day(d)
        raw_count = len(hits)
        total_raw += raw_count

        records: list[dict] = []
        seen_ids: set[str] = set()
        for hit in hits:
            rec = hit_to_record(hit, fetched_at, d.isoformat())
            if rec is None:
                continue
            if rec["id"] in seen_ids:
                continue
            seen_ids.add(rec["id"])
            records.append(rec)

        total_filtered += len(records)
        days_processed += 1

        if args.dry_run:
            logging.info("%s : %3d raw -> %2d filtered (DRY)", d, raw_count, len(records))
        else:
            written = write_day(d, records)
            total_written += written
            logging.info("%s : %3d raw -> %2d filtered -> %2d written", d, raw_count, len(records), written)

    logging.info(
        "DONE — %d days processed · %d raw HN items · %d passed tech-ai filter · %d written%s",
        days_processed, total_raw, total_filtered, total_written,
        " (DRY RUN)" if args.dry_run else "",
    )


if __name__ == "__main__":
    main()
