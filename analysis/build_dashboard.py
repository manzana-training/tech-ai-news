"""Genera dashboard.html con análisis del histórico de Tech AI News.

Lee `history/*.jsonl`, calcula:
- Items deduplicados (por id, ultima version gana)
- Extraccion de montos en USD (regex sobre titulo + rss_summary)
- Conteos por entidad y por topic
- Co-ocurrencias entidad-entidad
- Series semanales (entidades y topics)

Escribe un unico `dashboard.html` autocontenido (datos inline como JSON).
Sin servidor, sin DB. Abrir en el browser.

Uso:
    cd <repo-root>
    python analysis/build_dashboard.py
    # -> dashboard.html en la raiz del proyecto
"""

from __future__ import annotations

import datetime
import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = ROOT / "history"
TEMPLATE_FILE = Path(__file__).resolve().parent / "dashboard_template.html"
OUT_FILE = ROOT / "index.html"  # `index.html` so GitHub Pages serves it at /

# ---- Money extraction --------------------------------------------------------

# Captura "$1.2 billion", "$500M", "$3.5 bn", "$25 million"
# Requiere unidad (million/billion/trillion o M/B/T) para evitar capturar precios chicos.
_MONEY_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*"
    r"(trillion|billion|million|bn|tn|mn|[btm])\b",
    re.IGNORECASE,
)
_UNIT_MULT = {
    "trillion": 1e12, "tn": 1e12, "t": 1e12,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "million": 1e6, "mn": 1e6, "m": 1e6,
}


def extract_money(text: str) -> list[float]:
    """Devuelve lista de montos USD encontrados en el texto."""
    out: list[float] = []
    for m in _MONEY_RE.finditer(text):
        try:
            val = float(m.group(1).replace(",", "")) * _UNIT_MULT[m.group(2).lower()]
        except (ValueError, KeyError):
            continue
        if val >= 1e5:  # filtra ruido sub-100k
            out.append(val)
    return out


# ---- NLP-light: tokenizer + stopwords ----------------------------------------

# Stopwords en ingles + tech jerga que satura el top sin aportar senal.
# Filosofia: matar palabras genericas que dominan titulares de tech ("ai", "new",
# "model", "launch") asi la ranked list resalta terminos emergentes accionables.
_STOPWORDS = set("""
the a an and or but if then else when where why how what who whom which that this these those
is am are was were be been being have has had having do does did doing will would shall should
may might must can could of in on at by for to from with as into onto upon over under between
among through during before after about against without within along across behind below up down out
not no nor only just also too very so such same other another any all each every some most more less few
i you he she we they it me him her us them my your his their our its mine yours hers ours theirs
ll re ve d s t m
than here there while off back once again including its it's i'm don't won't didn't isn't aren't
yes maybe well let lets done both either neither yet far near close above beyond around throughout
made make makes making used using uses use way ways thing things stuff lot lots part parts side sides
year years month months week weeks day days hour hours minute minutes second seconds time times
""".split())

_TECH_STOPWORDS = set("""
ai artificial intelligence new model models release releases launch launches launched launching
tech technology technologies company companies firm firms startup startups report reports
said says new news article articles week year today now also still however even though although
according via per like much many big small large top best better good great
ceo cto vp chief executive officer president founder co-founder
data world way one two three first second three four five six seven eight nine ten
thing things make makes made making get gets getting got take takes took taking
come comes coming go goes going know knows knew knowing see sees seeing saw seen
think thinks thought thinking want wants wanted wanting use uses using used
look looks looking looked find finds finding found give gives gave given giving
need needs needed needing try tries tried trying call calls called calling
work works worked working show shows showed showing seem seems seemed help helps helped
new latest recent next previous following plans plan planning plans
should could would might may must can may
keep keeps kept keeping let lets letting put puts putting bring brings brought
say sayng says said tell tells told telling ask asks asked asking
post posted update updated updates roll rolled rolling deploy deployed deploying
report reported reports reporting article articles writes wrote written writing
million billion trillion mn bn tn deal deals round rounds raise raises raised raising
days day hours hour weekly daily monthly quarter quarterly via against
""".split())

# Boilerplate de Hacker News y otros feeds: "Article URL: https://...", "Points: 16",
# "# Comments: 11", "Comments URL: ...". Si no las matas, dominan el top.
# Tambien spam de newsletters de publishers ("Weekday newsletter provides a daily dose...").
_HN_BOILER_STOPWORDS = set("""
url comments comment points item items article articles www github http https
twitter facebook linkedin instagram youtube reddit
newsletter weekday edition download daily dose subscribe signed signup signing
copyright reserved rights free trial premium paywall
promo codes coupon discount sale
read more here see also story stories full
""".split())

_ALL_STOPWORDS = _STOPWORDS | _TECH_STOPWORDS | _HN_BOILER_STOPWORDS

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_WORD_RE = re.compile(r"\b[a-z][a-z]+(?:[-'][a-z]+)*\b")


def tokenize(text: str) -> list[str]:
    """Quita URLs, lower, regex de palabras, filtra stopwords y len < 3."""
    text = _URL_RE.sub(" ", text)
    return [
        w for w in _WORD_RE.findall(text.lower())
        if w not in _ALL_STOPWORDS and len(w) >= 3
    ]


def bigrams_of(tokens: list[str]) -> list[str]:
    """Pares consecutivos como string 'a b'."""
    return [f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)]


# ---- Load + dedup ------------------------------------------------------------


def load_items() -> list[dict]:
    by_id: dict[str, dict] = {}
    for path in sorted(glob.glob(str(HISTORY_DIR / "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    it = json.loads(line)
                except json.JSONDecodeError:
                    continue
                by_id[it["id"]] = it
    return list(by_id.values())


def load_editorial() -> dict | None:
    """Ultimo brief semanal de analysis/editorial/ (generado por build_editorial.py).

    Devuelve None si no hay ninguno — el dashboard se construye igual sin tab Brief.
    Si el webp referenciado no existe en disco, anula `image` (layout lo tolera).
    """
    editorial_dir = Path(__file__).resolve().parent / "editorial"
    candidates = sorted(editorial_dir.glob("*-W*.json"))
    if not candidates:
        return None
    try:
        ed = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if ed.get("image") and not (ROOT / ed["image"]).exists():
        ed["image"] = None
    return ed


def week_key(date_str: str) -> str:
    d = datetime.date.fromisoformat(date_str)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_label(week_str: str) -> str:
    """`2026-W17` -> `W17 · Apr 27 – May 3`."""
    y_str, w_str = week_str.split("-W")
    y, w = int(y_str), int(w_str)
    monday = datetime.date.fromisocalendar(y, w, 1)
    sunday = monday + datetime.timedelta(days=6)
    return f"W{w:02d} · {monday.strftime('%b %d')} – {sunday.strftime('%b %d')}"


# ---- Topic consolidation: 13 originales -> 6 categorias humanas --------------
# Aplicado al leer JSONL; NO se toca taxonomy.py ni la pipeline EC2.
# 6 categorias para vista publica. Research (chico, 12 items) se mergea en product
# porque ambos son "lo que los labs producen". Enterprise adoption (3 items, casi
# vacio) se mergea en funding porque ambos son flujo comercial.
TOPIC_MAP: dict[str, str] = {
    "model_release": "product",
    "product_launch": "product",
    "open_source": "product",
    "research_paper": "product",
    "benchmarks_evals": "product",
    "agents": "agents",
    "funding_ma": "funding",
    "enterprise_adoption": "funding",
    "infrastructure": "infra",
    "hardware": "infra",
    "regulation": "policy",
    "geopolitics": "policy",
    "security_incident": "security",
}
TOPIC_ORDER: list[str] = ["product", "agents", "funding", "infra", "policy", "security"]

# Glosario visible en el dashboard — clave: definicion corta para tooltip / strip.
# Mantener corto: cabe en una linea del strip (~25 chars max).
TOPIC_GLOSSARY: dict[str, str] = {
    "product": "Releases & launches",
    "agents": "Agentic AI & MCP",
    "funding": "Rounds, M&A, deals",
    "infra": "GPUs, chips, compute",
    "policy": "Regulation & geopolitics",
    "security": "Breaches & exploits",
}


def remap_topics(raw_topics: list[str]) -> list[str]:
    """Aplica TOPIC_MAP y deduplica. Topics desconocidos se descartan."""
    out: list[str] = []
    seen: set[str] = set()
    for t in raw_topics or []:
        mapped = TOPIC_MAP.get(t)
        if mapped and mapped not in seen:
            out.append(mapped)
            seen.add(mapped)
    return out


# ---- Build dashboard data ----------------------------------------------------


def build_data() -> dict:
    items = load_items()

    # Enrich with money + week + remap topics
    for it in items:
        text = f"{it.get('title') or ''} {it.get('rss_summary') or ''}"
        amounts = extract_money(text)
        it["money_amounts"] = amounts
        it["money_max"] = max(amounts) if amounts else 0.0
        it["week"] = week_key(it["digest_date"])
        it["topics"] = remap_topics(it.get("topics") or [])

    all_dates = sorted({it["digest_date"] for it in items})

    # Per-entity aggregates
    entity_count: Counter = Counter()
    entity_money: dict[str, float] = defaultdict(float)
    entity_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    entity_money_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for it in items:
        d = it["digest_date"]
        for e in it.get("entities") or []:
            entity_count[e] += 1
            entity_money[e] += it["money_max"]
            entity_daily[e][d] += 1
            if it["money_max"]:
                entity_money_daily[e][d] += it["money_max"]

    # Per-topic aggregates
    topic_count: Counter = Counter()
    topic_money: dict[str, float] = defaultdict(float)
    topic_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for it in items:
        d = it["digest_date"]
        for t in it.get("topics") or []:
            topic_count[t] += 1
            topic_money[t] += it["money_max"]
            topic_daily[t][d] += 1

    # Co-occurrence entidad-entidad
    co: Counter = Counter()
    for it in items:
        ents = sorted(set(it.get("entities") or []))
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                co[(ents[i], ents[j])] += 1

    # Series semanales (heatmap)
    weeks = sorted({it["week"] for it in items})
    entity_weekly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    topic_weekly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for it in items:
        wk = it["week"]
        for e in it.get("entities") or []:
            entity_weekly[e][wk] += 1
        for t in it.get("topics") or []:
            topic_weekly[t][wk] += 1

    # ---- NLP: unigramas + bigramas con document-frequency filter --------------
    n_items = len(items)
    word_df: Counter = Counter()
    word_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    bigram_df: Counter = Counter()
    bigram_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for it in items:
        text = f"{it.get('title') or ''} {it.get('rss_summary') or ''}"
        tokens = tokenize(text)
        bigs = bigrams_of(tokens)
        d = it["digest_date"]
        for w in set(tokens):
            word_df[w] += 1
            word_daily[w][d] += 1
        for b in set(bigs):
            bigram_df[b] += 1
            bigram_daily[b][d] += 1

    # Filtro df: min 3 (no ruido); max 40% para unigramas, 20% para bigramas
    max_df_w = max(3, int(n_items * 0.40))
    max_df_b = max(3, int(n_items * 0.20))

    top_words = sorted(
        [(w, c) for w, c in word_df.items() if 3 <= c <= max_df_w],
        key=lambda x: -x[1],
    )[:200]
    top_bigrams = sorted(
        [(b, c) for b, c in bigram_df.items() if 3 <= c <= max_df_b],
        key=lambda x: -x[1],
    )[:150]

    last_w = weeks[-1] if weeks else None
    prev_w = weeks[-2] if len(weeks) > 1 else None

    def week_total(daily_map: dict[str, int], wk: str | None) -> int:
        if wk is None:
            return 0
        return sum(c for d, c in daily_map.items() if week_key(d) == wk)

    word_rows = []
    for w, total in top_words:
        last = week_total(word_daily[w], last_w)
        prev = week_total(word_daily[w], prev_w)
        word_rows.append({"term": w, "total": total, "last": last, "prev": prev, "delta": last - prev})

    bigram_rows = []
    for b, total in top_bigrams:
        last = week_total(bigram_daily[b], last_w)
        prev = week_total(bigram_daily[b], prev_w)
        bigram_rows.append({"term": b, "total": total, "last": last, "prev": prev, "delta": last - prev})

    # Series diarias (arrays alineadas a all_dates) — para sparklines
    def to_int_series(m: dict[str, int]) -> list[int]:
        return [m.get(d, 0) for d in all_dates]

    def to_float_series(m: dict[str, float]) -> list[float]:
        return [m.get(d, 0.0) for d in all_dates]

    entity_series = {e: to_int_series(entity_daily[e]) for e in entity_count}
    entity_money_series = {
        e: to_float_series(entity_money_daily[e])
        for e in entity_money_daily if any(entity_money_daily[e].values())
    }
    topic_series = {t: to_int_series(topic_daily[t]) for t in topic_count}
    word_series = {w: to_int_series(word_daily[w]) for w, _ in top_words}
    bigram_series = {b: to_int_series(bigram_daily[b]) for b, _ in top_bigrams}

    # ---- Insights (auto-generated patterns) ----------------------------------
    # Used by the Highlights section at the top of the Search tab.

    last_week_items = [it for it in items if it["week"] == last_w] if last_w else []
    prev_week_items = [it for it in items if it["week"] == prev_w] if prev_w else []

    # Top mover entities/topics (week vs prev week, sorted by abs delta)
    def movers(weekly_map: dict, names) -> list[dict]:
        rows = []
        for n in names:
            last = weekly_map.get(n, {}).get(last_w, 0) if last_w else 0
            prev = weekly_map.get(n, {}).get(prev_w, 0) if prev_w else 0
            if last + prev == 0:
                continue
            rows.append({"name": n, "last": last, "prev": prev, "delta": last - prev})
        rows.sort(key=lambda x: -abs(x["delta"]))
        return rows

    entity_movers = movers(entity_weekly, entity_count.keys())
    topic_movers = movers(topic_weekly, topic_count.keys())

    # Top money article of last week
    top_money_item_lw = None
    if last_week_items:
        cand = max(last_week_items, key=lambda it: it["money_max"])
        if cand["money_max"] > 0:
            top_money_item_lw = {
                "title": cand["title"], "link": cand["link"], "date": cand["digest_date"],
                "src": cand["source"], "money": cand["money_max"],
                "entities": cand.get("entities") or [],
            }

    # Top funded topic last week
    topic_money_lw: dict[str, float] = defaultdict(float)
    for it in last_week_items:
        for t in it.get("topics") or []:
            topic_money_lw[t] += it["money_max"]
    top_funded_topic_lw = None
    if topic_money_lw:
        t, v = max(topic_money_lw.items(), key=lambda x: x[1])
        if v > 0:
            top_funded_topic_lw = {"topic": t, "money": v}

    # New entities (last week vs prev week)
    last_w_ents = {e for it in last_week_items for e in (it.get("entities") or [])}
    prev_w_ents = {e for it in prev_week_items for e in (it.get("entities") or [])}
    new_entities_lw = sorted(last_w_ents - prev_w_ents)

    # Most-connected entity (degree from co-occurrences)
    degree: Counter = Counter()
    for (a, b), w in co.items():
        degree[a] += 1
        degree[b] += 1
    most_connected = [{"name": e, "degree": d} for e, d in degree.most_common(5)]

    # Top emerging bigrams (highest positive delta, min total 5)
    emerging_bigrams = sorted(
        [r for r in bigram_rows if r["total"] >= 5],
        key=lambda r: -r["delta"],
    )[:8]

    insights = {
        "last_week": last_w,
        "prev_week": prev_w,
        "n_last_week": len(last_week_items),
        "n_prev_week": len(prev_week_items),
        "entity_movers": entity_movers[:10],
        "topic_movers": topic_movers[:10],
        "top_money_item": top_money_item_lw,
        "top_funded_topic": top_funded_topic_lw,
        "new_entities": new_entities_lw[:12],
        "most_connected": most_connected,
        "emerging_bigrams": emerging_bigrams,
    }

    # Entity × topic crosstab matrix (top 30 entities × topics)
    top_entity_names = [e for e, _ in entity_count.most_common(30)]
    # Use canonical TOPIC_ORDER (only topics actually present in data)
    present_topics = {t for it in items for t in (it.get("topics") or [])}
    all_topics_list = [t for t in TOPIC_ORDER if t in present_topics]
    ent_topic_matrix: dict[str, dict[str, int]] = {
        e: {t: 0 for t in all_topics_list} for e in top_entity_names
    }
    ent_topic_money: dict[str, dict[str, float]] = {
        e: {t: 0.0 for t in all_topics_list} for e in top_entity_names
    }
    for it in items:
        ents = it.get("entities") or []
        tops = it.get("topics") or []
        m = it["money_max"]
        for e in ents:
            if e in ent_topic_matrix:
                for t in tops:
                    ent_topic_matrix[e][t] += 1
                    if m:
                        ent_topic_money[e][t] += m

    # ---- Spotlight: top X by window (7d / 15d / 30d / all) -------------------
    # Para el tab Spotlight (antes Words). Sin unigramas; solo bigramas.
    date_max_obj = datetime.date.fromisoformat(all_dates[-1])
    windows = [("7D", 7), ("15D", 15), ("30D", 30), ("3M", 90), ("ALL", 10000)]
    spotlight: dict[str, dict] = {}
    for win_name, days in windows:
        cutoff = (date_max_obj - datetime.timedelta(days=days - 1)).isoformat()
        win_items = [it for it in items if it["digest_date"] >= cutoff]

        win_ent_count: Counter = Counter()
        win_ent_money: dict[str, float] = defaultdict(float)
        for it in win_items:
            for e in it.get("entities") or []:
                win_ent_count[e] += 1
                win_ent_money[e] += it["money_max"]

        win_topic_count: Counter = Counter()
        win_topic_money: dict[str, float] = defaultdict(float)
        for it in win_items:
            for t in it.get("topics") or []:
                win_topic_count[t] += 1
                win_topic_money[t] += it["money_max"]

        win_bigram_count: Counter = Counter()
        for it in win_items:
            text = f"{it.get('title') or ''} {it.get('rss_summary') or ''}"
            toks = tokenize(text)
            for b in set(bigrams_of(toks)):
                win_bigram_count[b] += 1

        spotlight[win_name] = {
            "n_items": len(win_items),
            "from_date": cutoff,
            "entities": [
                {"name": e, "count": c, "money": win_ent_money[e]}
                for e, c in win_ent_count.most_common(8)
            ],
            "topics": [
                {"name": t, "count": c, "money": win_topic_money[t]}
                for t, c in win_topic_count.most_common(8)
            ],
            "bigrams": [
                {"name": b, "count": c}
                for b, c in win_bigram_count.most_common(8)
                if c >= 2  # bigramas con al menos 2 menciones
            ],
        }

    # ---- Narrative line ------------------------------------------------------
    # Una frase auto-generada que responde "que paso esta semana" en 10 segundos.
    def fmt_money_py(v: float) -> str:
        if v >= 1e12: return f"${v/1e12:.1f}T"
        if v >= 1e9: return f"${v/1e9:.1f}B"
        if v >= 1e6: return f"${v/1e6:.0f}M"
        return f"${v/1e3:.0f}K"

    narrative_parts: list[str] = []
    up_topics = [m for m in topic_movers if m["delta"] > 0]
    down_topics = [m for m in topic_movers if m["delta"] < 0]
    if up_topics:
        m = up_topics[0]
        narrative_parts.append(f"<b>{m['name']}</b> accelerated (+{m['delta']})")
    if down_topics:
        m = down_topics[0]
        narrative_parts.append(f"<b>{m['name']}</b> cooled ({m['delta']})")
    if top_money_item_lw:
        narrative_parts.append(
            f"biggest deal: <b>{fmt_money_py(top_money_item_lw['money'])}</b> ({top_money_item_lw['title'][:60]}…)"
        )

    narrative = ""
    if narrative_parts:
        narrative = f"Last week ({last_w}): " + "; ".join(narrative_parts) + "."

    insights["narrative"] = narrative

    # Pack items para browser
    pack: list[dict] = []
    for i, it in enumerate(items):
        pack.append({
            "i": i,
            "date": it["digest_date"],
            "src": it["source"],
            "stype": it["source_type"],
            "title": it["title"],
            "link": it["link"],
            "sum": (it.get("rss_summary") or "")[:500],
            "dsum": it.get("digest_summary"),
            "topics": it.get("topics") or [],
            "entities": it.get("entities") or [],
            "region": it["region"],
            "sel": bool(it["selected_in_digest"]),
            "money": it["money_max"],
        })

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "editorial": load_editorial(),
        "items": pack,
        "stats": {
            "n_items": len(items),
            "n_curated": sum(1 for it in items if it["selected_in_digest"]),
            "n_entities": len(entity_count),
            "n_co_pairs": len(co),
            "n_words": len(word_rows),
            "n_bigrams": len(bigram_rows),
            "total_money": sum(it["money_max"] for it in items),
            "date_min": all_dates[0],
            "date_max": all_dates[-1],
        },
        "dates": all_dates,
        "weeks": weeks,
        "entity_count": dict(entity_count),
        "entity_money": {k: v for k, v in entity_money.items()},
        "topic_count": dict(topic_count),
        "topic_money": {k: v for k, v in topic_money.items()},
        "co": [{"a": a, "b": b, "w": w} for (a, b), w in co.items()],
        "entity_weekly": {e: dict(c) for e, c in entity_weekly.items()},
        "topic_weekly": {t: dict(c) for t, c in topic_weekly.items()},
        "entity_series": entity_series,
        "entity_money_series": entity_money_series,
        "topic_series": topic_series,
        "word_rows": word_rows,
        "bigram_rows": bigram_rows,
        "word_series": word_series,
        "bigram_series": bigram_series,
        "sources": sorted({it["source"] for it in items}),
        "topics_list": all_topics_list,
        "regions": sorted({it["region"] for it in items}),
        "insights": insights,
        "ent_topic_matrix": ent_topic_matrix,
        "ent_topic_money": ent_topic_money,
        "ent_topic_entities": top_entity_names,
        "ent_topic_topics": all_topics_list,
        "spotlight": spotlight,
        "topic_order": TOPIC_ORDER,
        "topic_glossary": TOPIC_GLOSSARY,
        "week_labels": {w: week_label(w) for w in weeks},
    }


# ---- Render ------------------------------------------------------------------


def render(data: dict) -> str:
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    # JSON seguro para embed (escapa </script>)
    blob = json.dumps(data, ensure_ascii=False, default=float).replace("</", "<\\/")
    return template.replace("__DATA__", blob)


def main() -> None:
    data = build_data()
    out = render(data)
    OUT_FILE.write_text(out, encoding="utf-8")
    s = data["stats"]
    print(f"Wrote {OUT_FILE}")
    print(f"  {s['n_items']} items ({s['n_curated']} curados) entre {s['date_min']} y {s['date_max']}")
    print(f"  {s['n_entities']} entidades, {s['n_co_pairs']} pares co-ocurrentes")
    print(f"  {s['n_words']} palabras + {s['n_bigrams']} bigramas filtrados")
    print(f"  Total $ extraido: ${s['total_money']/1e9:.1f}B")


if __name__ == "__main__":
    main()
