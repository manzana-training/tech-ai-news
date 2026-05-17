# Tech AI News — Editorial Observatory

A daily pipeline + static dashboard that tracks patterns in AI/tech news:
who is mentioned, what topics are heating up, where the money is flowing,
which entities are connecting to which.

**Live dashboard:** open `index.html` in any browser, or visit the GitHub Pages
deployment of this repo.

---

## What this is

Two things in one repo:

1. **A daily pipeline** (`news_digest.py`) that reads ~10 curated RSS sources,
   filters for AI/tech relevance, classifies locally (topics + entities + region),
   uses Claude Haiku to curate the top items, and ships a Spanish-language
   digest to a Telegram chat. Runs once a day on a small EC2 instance via cron.
2. **A static analytics dashboard** (`analysis/build_dashboard.py` →
   `index.html`) that reads the archived JSONL files in `history/` and
   surfaces patterns: entity co-mention graph, money flow sankey, weekly
   trends, topic affinity matrix, spotlight by time window.

The dashboard is a single self-contained HTML file (~2 MB) — no backend, no
database, no server. Just open it and explore.

---

## Stack

| Component | Role |
|---|---|
| Python 3.9+ | Pipeline + dashboard build |
| `feedparser` | RSS parsing |
| Claude Haiku 4.5 (Anthropic API) | Daily curation (~$0.45/month) |
| Telegram Bot API | Digest delivery |
| AWS EC2 + cron | Scheduling |
| Vanilla JS + vis-network + Google Fonts (Fraunces / Inter / IBM Plex Mono) | Dashboard |

No frameworks, no build step. The dashboard build is one Python script that
reads JSONL and writes one HTML file.

---

## What the dashboard answers

- **Search** — full-text over titles + summaries, filtered by date, topic,
  entity, region, source. Auto-generated narrative line + 6 highlight cards
  surface the week's pattern.
- **Graph** — vis-network of entity co-mentions. Click a node for full detail
  (mentions, $ accrued, topic breakdown, top co-mentions). Time window filter.
- **Money** — sankey of $ flow from entities to topics. Window selector
  (7D / 15D / 30D / 3M / ALL).
- **Spotlight** — top entity / topic / bigram per time window, with rest as
  ranked list.
- **Patterns** — entity × topic affinity heatmap + weekly trends.

---

## Topic taxonomy

The pipeline classifies items into 13 fine-grained topics. The dashboard
collapses these into 6 categories for display, mapped in
[`analysis/build_dashboard.py`](analysis/build_dashboard.py):

| Dashboard topic | Original pipeline topics |
|---|---|
| `product` | model_release, product_launch, open_source, research_paper, benchmarks_evals |
| `agents` | agents |
| `funding` | funding_ma, enterprise_adoption |
| `infra` | infrastructure, hardware |
| `policy` | regulation, geopolitics |
| `security` | security_incident |

The mapping lives in `TOPIC_MAP` at the top of `build_dashboard.py` and is
trivial to revise.

---

## Reproduce the dashboard locally

```bash
git clone https://github.com/<you>/tech-ai-news.git
cd tech-ai-news

python -m venv .venv
. .venv/bin/activate            # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

python analysis/build_dashboard.py
# Opens nothing automatically — open `index.html` in your browser.
```

The history JSONL files in `history/` are committed to the repo, so the
dashboard regenerates against the same data the live version uses. No API
keys needed for the dashboard build.

---

## Run your own pipeline

If you want to capture your own daily digest:

```bash
cp .env.example .env
# Edit .env with your own ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

python news_digest.py
# - Fetches last 24h from sources defined in sources.py
# - Classifies locally via taxonomy.py
# - Curates top 7-10 with Claude Haiku
# - Appends all items to history/YYYY-MM-DD.jsonl
# - Sends digest to your Telegram chat
```

To schedule it: see `deploy/crontab.example` (not in public repo — basic cron
line, run daily at the time of your choice). Total cost: ~$0.45 USD/month for
Claude API, free Telegram, free EC2 if on free tier.

---

## Historical backfill

The pipeline started persisting history on 2026-04-25. Earlier days can be
backfilled from the Hacker News Algolia API (the only source with public
historical access). Run:

```bash
python analysis/backfill_hn.py --start 2026-01-01 --end 2026-04-24
```

This creates a backup at `history.bak.<date>/` before any write, and skips
days that already exist. Each backfilled record carries `"backfill_source":
"hn-algolia"` for traceability. To revert:

```bash
rm -rf history && mv history.bak.<date> history
```

---

## Project structure

```
tech-ai-news/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── requirements.txt
├── index.html                     # the live dashboard
│
├── news_digest.py                 # daily pipeline entry point
├── sources.py                     # RSS whitelist + filter keywords
├── taxonomy.py                    # local classification rules
├── prompts.py                     # Claude curation prompts
├── telegram_client.py             # Telegram Bot API wrapper
│
├── analysis/
│   ├── build_dashboard.py         # reads history/, writes index.html
│   ├── dashboard_template.html    # HTML template with __DATA__ placeholder
│   └── backfill_hn.py             # historical HN backfill via Algolia
│
└── history/                       # JSONL per day (one item per line)
    ├── 2026-01-01.jsonl
    ├── …
    └── 2026-05-16.jsonl
```

---

## Design notes

The dashboard follows an editorial system called **Axioma**: cream `#F4F2ED`
+ ink `#0A0A0A`, Fraunces serif for titles, Inter for body, IBM Plex Mono
for labels. No rounded corners, no shadows, no gradients. One ochre accent
(`#9C6B2B`) used sparingly to mark "current week" in time series and the
dominant segment in stacked charts.

Visual choices that survived iteration:

- Sankey instead of pie chart for money flow (pies lie with >5 categories).
- Sparkbars instead of line charts (work better at 200px wide).
- Entity-entity graph from canonical taxonomy (a word co-occurrence graph
  is a hairball).
- Weekly heatmaps over rolling averages (22 days is too few for smoothing).

---

## License

MIT — see [LICENSE](LICENSE).

The article titles, links, and summaries archived in `history/` belong to
their original publishers. This repository archives only RSS-published
metadata under fair use for non-commercial pattern analysis.
