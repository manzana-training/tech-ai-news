#!/usr/bin/env python3
"""Copia las imagenes del tab 00 Brief a brief-gallery/ con nombre legible.

Cada semana genera assets/editorial/<YYYY-Www>.webp (arte Flux) + su JSON con el
headline. Este script las junta en brief-gallery/ nombradas
`<YYYY-Www> - <headline>.webp` para poder hojearlas como galeria.

Idempotente: solo copia lo que falta o cambio. Lo llama analysis/refresh.sh al
final de cada refresh, y se puede correr suelto para backfill:
    python analysis/sync_gallery.py
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITORIAL_DIR = ROOT / "analysis" / "editorial"
IMAGE_DIR = ROOT / "assets" / "editorial"
GALLERY_DIR = ROOT / "brief-gallery"

# Chars ilegales en nombres de archivo Windows: \ / : * ? " < > |
_ILLEGAL = re.compile(r'[\\/:*?"<>|]')


def safe_name(week: str, headline: str) -> str:
    clean = _ILLEGAL.sub("", headline).strip().rstrip(".")
    clean = re.sub(r"\s+", " ", clean)
    return f"{week} - {clean}.webp"


def main() -> int:
    GALLERY_DIR.mkdir(exist_ok=True)
    copied = 0
    for jf in sorted(EDITORIAL_DIR.glob("*.json")):
        data = json.loads(jf.read_text(encoding="utf-8"))
        week = data.get("week") or jf.stem
        headline = data.get("headline") or week
        src = IMAGE_DIR / f"{week}.webp"
        if not src.exists():
            continue  # brief sin imagen (best-effort) — nada que copiar
        dst = GALLERY_DIR / safe_name(week, headline)
        # Idempotente: salta si ya existe con el mismo tamano
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            continue
        # Limpia versiones viejas del mismo week (si cambio el headline)
        for old in GALLERY_DIR.glob(f"{week} - *.webp"):
            if old != dst:
                old.unlink()
        shutil.copy2(src, dst)
        print(f"  + {dst.name}")
        copied += 1
    total = len(list(GALLERY_DIR.glob("*.webp")))
    print(f"brief-gallery/: {total} imagenes ({copied} nuevas/actualizadas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
