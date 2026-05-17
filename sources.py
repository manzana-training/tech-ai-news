"""RSS whitelist. Editable sin tocar logica.

Campo `type`: publisher (prensa) | lab_blog (laboratorios IA) | community (foros/agregadores).
Se usa para taxonomia (region heuristica) y analisis posterior.
"""

SOURCES = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "type": "publisher", "mixed": False},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "type": "publisher", "mixed": False},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "type": "publisher", "mixed": True},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "type": "publisher", "mixed": False},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "type": "publisher", "mixed": True},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/", "type": "publisher", "mixed": False},
    # /category/ai/feed/ esta abandonado desde 2026-01-22; el feed principal /feed/ sigue vivo
    # y filtramos por TECH_AI_KEYWORDS para quedarnos con lo relevante.
    {"name": "VentureBeat", "url": "https://venturebeat.com/feed/", "type": "publisher", "mixed": True},
    # Anthropic descontinuo su RSS publico (verificado 2026-05-10: 404 en ~10 URLs comunes,
    # ningun <link rel="alternate"> en /news). Si vuelven a publicarlo, descomentar.
    # {"name": "Anthropic", "url": "https://www.anthropic.com/news/rss.xml", "type": "lab_blog", "mixed": False},
    {"name": "OpenAI", "url": "https://openai.com/blog/rss.xml", "type": "lab_blog", "mixed": False},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "type": "lab_blog", "mixed": False},
    {"name": "Hacker News (top)", "url": "https://hnrss.org/frontpage", "type": "community", "mixed": True},
]

# Keywords para filtrar feeds mixtos (The Verge, Wired, HN, VentureBeat).
# Patrones regex case-insensitive. Usar \b para evitar substring matches
# (sin \b "ai" matchea "Michael", "Brain", "Mattress", "Repair", etc.,
# inflando el pipeline con falsos positivos que Claude despues descarta).
TECH_AI_KEYWORDS = [
    r"\bai\b", r"\bartificial intelligence\b", r"\bmachine learning\b", r"\bml\b",
    r"\bllms?\b", r"\bgpt\b", r"\bclaude\b", r"\banthropic\b", r"\bopenai\b",
    r"\bgemini\b", r"\bdeepmind\b", r"\bchatgpt\b", r"\bcopilot\b",
    r"\bagents?\b", r"\bagentic\b",
    r"\bneural\b", r"\btransformer\b", r"\bgenerative\b",
    r"\bstartups?\b", r"\bfunding\b", r"\bipo\b", r"\bacquisitions?\b",
    r"\bchips?\b", r"\bsemiconductors?\b", r"\bnvidia\b", r"\bamd\b", r"\btsmc\b",
    r"\bquantum\b", r"\brobotics?\b", r"\bautonomous\b",
    r"\bapple\b", r"\bgoogle\b", r"\bmicrosoft\b", r"\bmeta\b", r"\bamazon\b",
    r"\bcybersecurity\b", r"\bvulnerabilit(y|ies)\b", r"\bbreach\b",
    r"\bapis?\b", r"\bsdks?\b", r"\bframeworks?\b", r"\bopen[-\s]source\b",
]
