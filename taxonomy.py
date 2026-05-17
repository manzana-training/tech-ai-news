"""Clasificacion local de items de noticias.

Sin llamadas a APIs externas: solo regex + diccionarios.
Filosofia: preferir falsos negativos sobre falsos positivos.
Si un patron no esta seguro, no lo agregues. Las reglas se afinan con el
historico (los JSONL son reprocesables).

Uso:
    from taxonomy import classify
    result = classify(title, summary, source_type)
    # -> {"topics": [...], "entities": [...], "region": "us"}
"""

from __future__ import annotations

import re

# ---- Topics: vocabulario cerrado, multi-label --------------------------------

# Helpers para reusar grupos. Verbo de release + nombre/tipo de modelo cerca.
_RELEASE_VERB = (
    r"(launch(es|ed|ing)?|releas(es|ed|ing)?|introduc(es|ed|ing)?|"
    r"unveil(s|ed|ing)?|announc(es|ed|ing)?|debut(s|ed|ing)?|ship(s|ped|ping)?)"
)
_MODEL_NOUN = r"(model|llm|gpt-?\d|claude|gemini|llama|mistral|deepseek|grok|qwen|phi-?\d|gemma)"

# Cada topic se chequea aplicando sus regex contra `title + "\n" + summary`.
# Si CUALQUIER regex matchea, el topic se asigna.
TOPIC_PATTERNS: dict[str, list[re.Pattern]] = {
    "model_release": [
        # Verbo + (hasta 60 chars) + nombre, en cualquier orden.
        # Conservador: requiere ambos para evitar disparar con menciones sueltas.
        re.compile(rf"\b{_RELEASE_VERB}\b.{{0,60}}\b{_MODEL_NOUN}\b", re.I),
        re.compile(rf"\b{_MODEL_NOUN}\b.{{0,60}}\b{_RELEASE_VERB}\b", re.I),
    ],
    "research_paper": [
        re.compile(r"\b(arxiv|preprint|new\s+paper|research\s+paper|published\s+a?\s*paper)\b", re.I),
    ],
    "benchmarks_evals": [
        re.compile(
            r"\b(benchmark|mmlu|swe-bench|humaneval|gpqa|mmmu|arc-agi|"
            r"outperform\w*|state-of-the-art|sota|leaderboard|eval\b|evals\b)\b",
            re.I,
        ),
    ],
    "agents": [
        re.compile(
            r"\b(ai\s+agents?|agentic|autonomous\s+agents?|tool[\s-]use|"
            r"computer\s+use|browser\s+agents?|coding\s+agents?|"
            r"mcp\b|model\s+context\s+protocol)\b",
            re.I,
        ),
    ],
    "open_source": [
        re.compile(r"\bopen[-\s]source\b", re.I),
        re.compile(r"\bopen[-\s]weights?\b", re.I),
        # Nota: nombres de modelos open (llama, mistral, etc.) NO se incluyen
        # porque tambien aparecen en noticias de funding, drama corporativo, etc.
        # Si en el analisis se ve cobertura baja de open_source, agregarlos.
    ],
    "funding_ma": [
        re.compile(r"\braise[ds]?\s+\$[\d.,]+\s*(m|b|million|billion)?\b", re.I),
        re.compile(
            r"\b(funding\s+round|series\s+[a-e]\b|valuation|valued\s+at|"
            r"acquir(es|ed|ing)|acquisition|buyout|merger|to\s+buy|ipo\b|going\s+public)\b",
            re.I,
        ),
    ],
    "regulation": [
        re.compile(
            r"\b(ai\s+act|regulation|regulator|regulates?|regulating|"
            r"ftc\b|sec\b|doj\b|antitrust|"
            r"lawsuit|sue[ds]?|court\s+(rules?|ruling)|judge\s+rul|"
            r"fine[ds]?\b|ban(s|ned|ning)?\b|complian(ce|t))\b",
            re.I,
        ),
    ],
    "geopolitics": [
        re.compile(
            r"\b(export\s+controls?|sanctions?|us-china|china-us|"
            r"sovereign\s+ai|national\s+security|tariffs?|trade\s+war|"
            r"chip\s+(war|controls?|restrictions?|ban)|semiconductor\s+war|"
            r"rare\s+earth|retaliat\w+)\b",
            re.I,
        ),
        # "X bans/restricts/blocks chips/exports" en cualquier orden
        re.compile(r"\b(china|us|eu|biden|trump)\b.{0,40}\b(ban|restrict|block|export)\w*\b.{0,40}\b(chip|semiconductor|tech|export)\w*\b", re.I),
        re.compile(r"\b(ban|restrict|block|export)\w*\b.{0,40}\b(chip|semiconductor)\w*\b.{0,40}\b(china|us|eu)\b", re.I),
    ],
    "infrastructure": [
        re.compile(
            r"\b(data\s+center|datacenter|gpu\s+cluster|training\s+run|"
            r"hyperscaler|cloud\s+ai|inference\s+(cost|infrastructure)|"
            r"compute\s+(cluster|infrastructure|capacity))\b",
            re.I,
        ),
    ],
    "hardware": [
        re.compile(
            r"\b(chip(s|set)?|gpu|tpu|silicon|semiconductor|"
            r"wafer|fab\b|fabrication|asic|"
            r"h100|h200|b100|b200|mi300|mi325)\b",
            re.I,
        ),
    ],
    "security_incident": [
        re.compile(
            r"\b(breach(es|ed)?|vulnerabilit(y|ies)|jailbreak|exploit|"
            r"hack(ed|ing|er|ers)?|malware|phishing|ransomware|"
            r"cve-\d|zero-day|0-day|leaked?\b|data\s+leak)\b",
            re.I,
        ),
    ],
    "product_launch": [
        re.compile(
            r"\b(launch(es|ed)?|roll(s|ed)?\s+out|release[ds]?|introduc(es|ed)?|unveil(s|ed)?)\b"
            r".{0,40}\b(feature|product|app|service|tool|platform|integration|api|sdk)\b",
            re.I,
        ),
    ],
    "enterprise_adoption": [
        re.compile(
            r"\b(enterprise\s+(deploy|adopt|customer|use)|"
            r"fortune\s+500|"
            r"deploys?\s+ai|adopts?\s+ai|rolls?\s+out\s+ai|"
            r"production\s+(use|deployment)\s+of)\b",
            re.I,
        ),
    ],
}


# ---- Entities: diccionario canonico ------------------------------------------

# Cada clave es el nombre canonico (lo que se guarda).
# Cada valor es una lista de patrones literales (case-insensitive, con \b alrededor).
# Usar \b evita matches dentro de palabras (ej: "meta" en "metadata").
ENTITIES: dict[str, list[str]] = {
    # AI labs / model providers
    "Anthropic": ["anthropic"],
    "OpenAI": ["openai"],
    "Google DeepMind": ["deepmind", "google deepmind"],
    "Google": ["google"],
    "Meta": ["meta", "facebook"],
    "Microsoft": ["microsoft"],
    "Apple": ["apple"],
    "Amazon": ["amazon", "aws"],
    "xAI": ["xai"],
    "Mistral": ["mistral"],
    "DeepSeek": ["deepseek"],
    "Cohere": ["cohere"],
    "Stability AI": ["stability ai"],
    "Hugging Face": ["hugging face", "huggingface"],
    "Perplexity": ["perplexity"],
    "Inflection": ["inflection ai"],
    "Character.AI": ["character.ai", "character ai"],
    "Runway": ["runway ml", "runwayml"],

    # Hardware / chips
    "Nvidia": ["nvidia"],
    "AMD": ["amd"],
    "Intel": ["intel"],
    "TSMC": ["tsmc"],
    "Qualcomm": ["qualcomm"],
    "Broadcom": ["broadcom"],
    "ARM": ["arm holdings"],
    "Samsung": ["samsung"],
    "SK Hynix": ["sk hynix"],
    "Micron": ["micron"],

    # China tech
    "Alibaba": ["alibaba"],
    "Baidu": ["baidu"],
    "Tencent": ["tencent"],
    "ByteDance": ["bytedance"],
    "Huawei": ["huawei"],

    # Enterprise / SaaS
    "Salesforce": ["salesforce"],
    "Oracle": ["oracle"],
    "IBM": ["ibm"],
    "Databricks": ["databricks"],
    "Snowflake": ["snowflake"],
    "Palantir": ["palantir"],
    "ServiceNow": ["servicenow"],
    "Adobe": ["adobe"],
    "SAP": ["sap"],

    # Dev infra
    "GitHub": ["github"],
    "GitLab": ["gitlab"],
    "Vercel": ["vercel"],
    "Cloudflare": ["cloudflare"],
    "Replit": ["replit"],
    "Cursor": ["cursor ai"],

    # Other tech
    "Tesla": ["tesla"],
    "SpaceX": ["spacex"],
    "Stripe": ["stripe"],
    "Shopify": ["shopify"],
    "Uber": ["uber"],
    "Airbnb": ["airbnb"],
    "YouTube": ["youtube"],

    # People (founders/CEOs/policymakers que aparecen como sujeto de noticias)
    # Nota: Trump matchea tambien "trump card" — aceptable, el contexto en feeds tech
    # casi siempre es politica/regulacion del expresidente.
    "Elon Musk": ["musk", "elon musk", "elon"],
    "Sam Altman": ["altman", "sam altman"],
    "Donald Trump": ["trump"],

    # AI products de cara al usuario (separados de su lab)
    "ChatGPT": ["chatgpt"],
    "Copilot": [r"copilot\b"],

    # Models (canonical)
    "GPT-4": [r"gpt-?4(?!\.|o|\d)"],
    "GPT-4o": [r"gpt-?4o"],
    "GPT-5": [r"gpt-?5"],
    "o1": [r"\bo1\b(?!\d)"],
    "o3": [r"\bo3\b(?!\d)"],
    "Claude Opus": ["claude opus"],
    "Claude Sonnet": ["claude sonnet"],
    "Claude Haiku": ["claude haiku"],
    "Gemini": ["gemini"],
    "Llama": [r"llama\s*\d"],
    "Sora": ["sora"],
    "DALL-E": ["dall-e", "dalle"],
    "Midjourney": ["midjourney"],
    "Stable Diffusion": ["stable diffusion"],
    "Grok": ["grok"],

    # Regulators / policy
    "FTC": ["ftc"],
    "SEC": ["sec"],
    "DOJ": ["doj"],
    "EU AI Act": ["eu ai act", "ai act"],
    "NIST": ["nist"],
}


def _build_entity_patterns() -> list[tuple[str, re.Pattern]]:
    """Compila patrones de entidades. Patrones que parecen regex (contienen
    metacaracteres) se usan tal cual; literales se envuelven en \\b...\\b."""
    out: list[tuple[str, re.Pattern]] = []
    regex_chars = set(r".\^$*+?()[]{}|")
    for canonical, words in ENTITIES.items():
        for word in words:
            if any(c in word for c in regex_chars):
                pattern = word
            else:
                pattern = rf"\b{re.escape(word)}\b"
            out.append((canonical, re.compile(pattern, re.I)))
    return out


_ENTITY_PATTERNS = _build_entity_patterns()


# ---- Region: heuristica simple -----------------------------------------------

# lab_blog -> "global" (los labs publican para audiencia mundial).
# Si no, buscar keywords de region en el texto. Default: "us".
REGION_PATTERNS: dict[str, list[re.Pattern]] = {
    "eu": [
        re.compile(
            r"\b(eu\s+ai\s+act|brussels|european\s+union|european\s+commission|"
            r"gdpr|germany|france|paris|berlin|uk\b|britain|london|"
            r"spain|madrid|italy|rome|netherlands|amsterdam)\b",
            re.I,
        ),
    ],
    "asia": [
        re.compile(
            r"\b(china|chinese|beijing|shanghai|shenzhen|hong\s+kong|"
            r"taiwan|japan|tokyo|korea|seoul|"
            r"india|mumbai|bangalore|delhi|"
            r"huawei|alibaba|baidu|tencent|bytedance|samsung|tsmc|sk\s+hynix)\b",
            re.I,
        ),
    ],
    "latam": [
        re.compile(
            r"\b(latin\s+america|latam|"
            r"brazil|brasil|mexico|argentina|chile|colombia)\b",
            re.I,
        ),
    ],
}


def _detect_region(text: str, source_type: str) -> str:
    if source_type == "lab_blog":
        return "global"
    for region, patterns in REGION_PATTERNS.items():
        if any(p.search(text) for p in patterns):
            return region
    return "us"


# ---- API publica -------------------------------------------------------------


def classify(title: str, summary: str, source_type: str) -> dict:
    """Devuelve {topics, entities, region} para un item.

    topics: lista de strings (vocab cerrado de TOPIC_PATTERNS), puede estar vacia.
    entities: lista ordenada de nombres canonicos detectados, sin duplicados.
    region: us|eu|asia|latam|global.
    """
    text = f"{title}\n{summary}"

    topics = [t for t, patterns in TOPIC_PATTERNS.items() if any(p.search(text) for p in patterns)]
    entities = sorted({canonical for canonical, p in _ENTITY_PATTERNS if p.search(text)})
    region = _detect_region(text, source_type)

    return {"topics": topics, "entities": entities, "region": region}
