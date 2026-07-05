"""Genera el editorial ejecutivo semanal para el tab 00 Brief del dashboard.

Dos pasos, ambos con salida versionada en el repo:
  1. Claude Sonnet (Anthropic API) editorializa señales precalculadas del histórico
     -> analysis/editorial/<YYYY-Www>.json
  2. Flux 1.1 Pro (Replicate) genera la imagen hero 16:9
     -> assets/editorial/<YYYY-Www>.webp

Idempotente por semana ISO (del último día con datos): si el JSON de la semana ya
existe, no llama a ninguna API. `--force` regenera. La imagen es best-effort: si
falta REPLICATE_API_TOKEN o Flux falla, el brief queda sin imagen (image: null).

Uso:
    cd <repo-root>
    python analysis/build_editorial.py [--force]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dashboard import load_items, extract_money  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EDITORIAL_DIR = Path(__file__).resolve().parent / "editorial"
ASSETS_DIR = ROOT / "assets" / "editorial"

CREDENTIALS_ENV = Path("C:/Users/supip/.secrets/credentials.env")
REPLICATE_ENV_FALLBACK = Path(
    "C:/Users/supip/OneDrive/Documentos/Alejandria/manzana/sitio-web/.env.local"
)

TEXT_MODEL = "claude-sonnet-5"

# Estética del dashboard (Axioma relax: papel calido, tinta, un acento ocre).
IMAGE_PROMPT_BASE = (
    "Minimalist editorial illustration on warm ivory paper (#F4F2ED). {scene} "
    "Near-black ink linework with a single ochre accent (#9C6B2B). Abstract, "
    "restrained, generous negative space, print-quality, refined newspaper "
    "editorial feel. No text, no letters, no logos."
)

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "kicker": {
            "type": "string",
            "description": "Short eyebrow line above the headline, <= 8 words, no period",
        },
        "headline": {
            "type": "string",
            "description": "Front-page style headline, <= 12 words, no period",
        },
        "paragraph": {
            "type": "string",
            "description": "3-4 sentence executive summary of the week",
        },
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "4-5 bullets, each one signal + its so-what, <= 35 words each",
        },
        "image_prompt": {
            "type": "string",
            "description": (
                "One sentence describing an abstract visual scene/metaphor for the "
                "week's dominant story. Concrete shapes and composition only — no "
                "text, no logos, no brand names."
            ),
        },
    },
    "required": ["kicker", "headline", "paragraph", "bullets", "image_prompt"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You write the weekly executive brief for Tech AI News, a public \
editorial observatory that tracks AI/tech news flow (https://manzanatraining.com.mx/tech-ai-news/).

Audience: C-level executives and investors. They read this in 60 seconds to know what \
moved in AI/tech this week and why it matters.

Voice and rules:
- English. Concise, declarative, confident. No hype, no hedging, no filler.
- Editorialize: connect signals into a thesis, don't enumerate news.
- Every bullet = one signal + its "so what" for an operator or investor.
- All numbers you cite MUST come verbatim from the signals provided. Never invent or \
recompute figures.
- Never mention this brief, the dashboard, or the data pipeline. Write about the world.
- The headline should read like a front page: specific, thesis-driven, not clickbait.

You will receive precomputed signals: monthly topic rotation (share of tagged items), \
entity/topic momentum (daily rate last 14d vs prior 45d), the week's curated stories \
with summaries, and notable money figures. Weigh recency: the brief is about THIS week \
against the backdrop of the longer trend."""


def log(msg: str) -> None:
    print(f"[editorial] {msg}")


# ---- Env -----------------------------------------------------------------


def load_env() -> None:
    from dotenv import load_dotenv

    if CREDENTIALS_ENV.exists():
        load_dotenv(CREDENTIALS_ENV)
    if not os.environ.get("REPLICATE_API_TOKEN") and REPLICATE_ENV_FALLBACK.exists():
        load_dotenv(REPLICATE_ENV_FALLBACK)


# ---- Signals (deterministicos, sin LLM) ------------------------------------


def compute_signals(items: list[dict]) -> tuple[dict, datetime.date]:
    dated = [it for it in items if it.get("digest_date")]
    ref = max(datetime.date.fromisoformat(it["digest_date"]) for it in dated)

    def days_ago(it: dict) -> int:
        return (ref - datetime.date.fromisoformat(it["digest_date"])).days

    # Rotacion mensual de topics (share % de items etiquetados)
    by_month: dict[str, Counter] = {}
    tot_month: Counter = Counter()
    for it in dated:
        m = it["digest_date"][:7]
        for t in it.get("topics") or []:
            by_month.setdefault(m, Counter())[t] += 1
            tot_month[m] += 1
    months = sorted(by_month)[-7:]
    all_topics = Counter()
    for m in months:
        all_topics.update(by_month[m])
    topic_rotation = {
        t: {m: round(100 * by_month[m][t] / max(tot_month[m], 1), 1) for m in months}
        for t, _ in all_topics.most_common(10)
    }

    # Momentum: ritmo diario 14d vs 45d previos
    recent = [it for it in dated if days_ago(it) < 14]
    prior = [it for it in dated if 14 <= days_ago(it) < 59]

    def momentum(field: str, min_total: int) -> list[dict]:
        cr: Counter = Counter()
        cp: Counter = Counter()
        for it in recent:
            for v in it.get(field) or []:
                cr[v] += 1
        for it in prior:
            for v in it.get(field) or []:
                cp[v] += 1
        rows = []
        for v in set(cr) | set(cp):
            if cr[v] + cp[v] < min_total:
                continue
            r14, r45 = cr[v] / 14, cp[v] / 45
            rows.append(
                {
                    "name": v,
                    "per_day_last_14d": round(r14, 2),
                    "per_day_prior_45d": round(r45, 2),
                    "delta_pct": round(100 * (r14 - r45) / max(r45, 0.1)),
                }
            )
        rows.sort(key=lambda r: -r["delta_pct"])
        return rows

    # Curados de los ultimos 7 dias
    curated_week = sorted(
        (it for it in dated if days_ago(it) < 7 and it.get("selected_in_digest")),
        key=lambda it: (it["digest_date"], it.get("digest_rank") or 99),
    )
    curated = [
        {
            "date": it["digest_date"],
            "title": it["title"],
            "summary": it.get("digest_summary") or "",
        }
        for it in curated_week
    ]

    # $ notables de la semana (>= 1B en titulares curados de 14d)
    money = []
    for it in dated:
        if days_ago(it) < 14 and it.get("selected_in_digest"):
            amounts = extract_money(
                (it.get("title") or "") + " " + (it.get("rss_summary") or "")
            )
            big = [a for a in amounts if a >= 1e9]
            if big:
                money.append(
                    {"date": it["digest_date"], "title": it["title"],
                     "usd_billions": round(max(big) / 1e9, 1)}
                )
    money.sort(key=lambda m: -m["usd_billions"])

    signals = {
        "data_through": ref.isoformat(),
        "topic_rotation_monthly_share_pct": topic_rotation,
        "entity_momentum": momentum("entities", 15)[:14],
        "topic_momentum": momentum("topics", 12),
        "curated_stories_last_7d": curated,
        "notable_money_last_14d": money[:12],
    }
    return signals, ref


# ---- Texto (Anthropic) ------------------------------------------------------


def generate_brief(signals: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    # Sonnet 5 corre adaptive thinking por default y este cuenta contra
    # max_tokens — el headroom es para pensar, el JSON de salida es chico.
    response = client.messages.create(
        model=TEXT_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": BRIEF_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": (
                    "Signals for this week's brief:\n\n"
                    + json.dumps(signals, ensure_ascii=False, indent=1)
                    + "\n\nWrite the executive brief."
                ),
            }
        ],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"stop_reason inesperado: {response.stop_reason}")
    text = next(b.text for b in response.content if b.type == "text")
    brief = json.loads(text)
    if not (4 <= len(brief["bullets"]) <= 5):
        raise ValueError(f"expected 4-5 bullets, got {len(brief['bullets'])}")
    return brief


# ---- Imagen (Replicate / Flux) ----------------------------------------------


def generate_image(image_prompt: str, out_path: Path) -> bool:
    """Devuelve True si la imagen quedo escrita. Best-effort: nunca lanza."""
    import requests

    token = os.environ.get("REPLICATE_API_TOKEN")
    if not token:
        log("WARN: sin REPLICATE_API_TOKEN — brief sin imagen")
        return False
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        res = requests.post(
            "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro/predictions",
            headers=headers,
            json={
                "input": {
                    "prompt": IMAGE_PROMPT_BASE.format(scene=image_prompt.rstrip(". ") + "."),
                    "aspect_ratio": "16:9",
                    "output_format": "webp",
                    "output_quality": 90,
                }
            },
            timeout=30,
        )
        res.raise_for_status()
        pred = res.json()
        poll_url = pred["urls"]["get"]
        for _ in range(60):  # hasta ~2 min
            time.sleep(2)
            pred = requests.get(poll_url, headers=headers, timeout=30).json()
            if pred["status"] in ("succeeded", "failed", "canceled"):
                break
        if pred["status"] != "succeeded":
            log(f"WARN: Flux status={pred['status']} — brief sin imagen")
            return False
        output = pred["output"]
        url = output[0] if isinstance(output, list) else output
        img = requests.get(url, timeout=60)
        img.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img.content)
        log(f"imagen escrita: {out_path} ({len(img.content) // 1024} KB)")
        return True
    except Exception as e:  # noqa: BLE001 — best-effort deliberado
        log(f"WARN: fallo imagen ({e}) — brief sin imagen")
        return False


# ---- Main --------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="regenera aunque exista")
    args = parser.parse_args()

    load_env()
    items = load_items()
    if not items:
        log("WARN: history/ vacio — nada que hacer")
        return 0
    signals, ref = compute_signals(items)

    iso = ref.isocalendar()
    week = f"{iso[0]}-W{iso[1]:02d}"
    json_path = EDITORIAL_DIR / f"{week}.json"
    img_path = ASSETS_DIR / f"{week}.webp"

    if json_path.exists() and not args.force:
        log(f"{week} ya existe ({json_path.name}) — sin llamadas API. Usa --force para regenerar.")
        return 0

    monday = datetime.date.fromisocalendar(iso[0], iso[1], 1)
    date_range = f"Week of {monday.strftime('%b %d')} – {ref.strftime('%b %d, %Y')}"

    log(f"generando brief {week} (datos hasta {ref}) con {TEXT_MODEL}...")
    brief = generate_brief(signals)
    log(f'headline: "{brief["headline"]}"')

    has_image = generate_image(brief["image_prompt"], img_path)

    record = {
        "week": week,
        "week_label": week.replace("-W", " · Week "),
        "date_range": date_range,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%b %d, %Y"),
        "kicker": brief["kicker"],
        "headline": brief["headline"],
        "paragraph": brief["paragraph"],
        "bullets": brief["bullets"],
        "image": f"assets/editorial/{week}.webp" if has_image else None,
        "image_prompt": brief["image_prompt"],
    }
    EDITORIAL_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log(f"escrito {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
