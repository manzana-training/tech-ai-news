# Bitácora — Tech AI News

Registro de refreshes del sitio público (https://manzanatraining.com.mx/tech-ai-news/)
y cambios operativos. El más reciente arriba. El procedimiento vive en
`analysis/refresh.sh` (un comando: scp histórico desde EC2 → brief semanal →
rebuild `index.html` → galería → commit/push).

---

## 2026-08-09 — Refresh W32

**Refresh end-to-end** vía `bash analysis/refresh.sh` (scp NO bloqueado).

- **8 días nuevos:** 02–09 ago.
- **Cobertura:** 2026-01-01 → 2026-08-09. **6964 items (907 curados).**
- **Brief nuevo W32:** *"AI Agents Keep Escaping Their Sandboxes as Capital Keeps Flowing In"*.
- Refresh previo fue W31 (hasta 01-ago, commit `8baa26d`). Pusheado `c8249fd`.

---

## 2026-08-02 — Refresh W31 + piso de datos para el share mensual

**Refresh end-to-end** vía `bash analysis/refresh.sh` (scp NO bloqueado).

- **7 días nuevos:** 26 jul – 01 ago (el 02 aún no existe; el cron corre 12pm CDMX).
- **Cobertura:** 2026-01-01 → 2026-08-01. **6664 items (837 curados).**
- **Brief nuevo W31:** *"OpenAI and Anthropic Confirm Autonomous Agents Hacked Real Companies"*
  (kicker: "AI agents go rogue, industry scrambles for guardrails"). Imagen Flux 110 KB.
- Refresh previo fue W30 (hasta 25-jul, commit `f1fe934`).

**Fix — el mes en curso contaminaba la rotación mensual (`build_editorial.py`):**
al refrescar el día 1-2 del mes, el bucket del mes nuevo tenía 6 tags (un día) y
el share salía 33.3% funding / 16.7% regulation. El primer brief generado lo leyó
como tendencia ("funding subió a 33.3% en agosto, desde 21.7% en julio") — cifra
verbatim de la señal, pero la señal era ruido con n=1 día. Ahora `compute_signals`
excluye los meses con menos de **60 tags** (`MIN_MONTH_TAGS`); si ninguno califica,
usa los últimos tal cual. Con el piso: julio 469 tags ✅, agosto 6 ❌.

**Fix — prosa cortada a media frase (`build_editorial.py`):** la 2ª generación
devolvió el párrafo terminando en *"...Sam Altman signals he's ready to "*, con
JSON válido y `stop_reason=end_turn` — ningún check lo cazaba. `generate_brief`
ahora valida que párrafo y bullets terminen en `.`/`!`/`?` y reintenta hasta 3 veces
(el modelo real va en `_call_model`).

**Verificación del editorial (regla dura: números verbatim de las señales):**
- Momentum exacto vs señales: security_incident +54% (3.14 vs 2.04/día),
  Hugging Face +1670% (1.71 vs 0.04/día).
- $ notables verbatim: OpenAI $750B, AMD $5B a Anthropic, Cyera/Oasis $1B, Okta/Permiso ~$200M.
- Afirmaciones ancladas a titulares curados reales: "Claude published malicious code
  and attacked 3 real companies" (01-ago), "Nvidia, Microsoft launch open AI security
  alliance — without OpenAI, Google, or Anthropic" (27-jul), "Sam Altman is ready to
  decelerate" (29-jul).
- Veredicto: **editorial fiel, 0 cifras alucinadas.** Embebido en `index.html` (tab default).

---

## 2026-07-26 — Refresh W30 + galería de briefs

**Refresh end-to-end** vía `bash analysis/refresh.sh` (scp NO bloqueado). Commit `f1fe934`, pusheado a `main`.

- **6 días nuevos:** 20–25 jul (el 26 aún no existe; el cron corre 12pm CDMX).
- **Cobertura:** 2026-01-01 → 2026-07-25. **6361 items (773 curados).**
- **Brief nuevo W30:** *"Kimi K3 Rattles Washington as OpenAI Commits $750B"*
  (kicker: "China's open-weight surge meets record US capex"). Imagen Flux 355 KB.
- Refresh previo fue W29 (hasta 19-jul, commit `588c1e6`).

**Verificación del editorial (regla dura: números verbatim de las señales, cero inventados):**
- Momentum/share exactos vs señales: open_source +103%, security +44%, regulation +35%,
  Gemini +93%, Microsoft −56%.
- $ notables verbatim: OpenAI $750B, AMD $5B, Etched $10.3B, Anduril $100B.
- Afirmaciones de historia ancladas a titulares curados reales (Kimi K3 subs
  suspendidas, Suno 55M, EU fine Google $1B, HF breach por modelos OpenAI, kill-switch bill).
- Veredicto: **editorial fiel, 0 cifras alucinadas.** Embebido correctamente en `index.html` (tab default).

**Nuevo mecanismo — galería de imágenes del brief (`brief-gallery/`):**
- Script `analysis/sync_gallery.py`: copia cada `assets/editorial/<week>.webp` a
  `brief-gallery/<week> - <headline>.webp` (idempotente, limpia versiones viejas si
  cambia el headline). Enchufado como paso 4/5 de `refresh.sh` → cada semana futura
  se agrega sola.
- Backfill inicial: 4 imágenes (W27–W30).

**Legibilidad del conteo (commit `6b078a8`):** el número de items del header ahora
lleva separador de miles (`6,361` en vez de `6361`) para leerse mejor conforme crece.
Helper `fmtInt` (`toLocaleString`) aplicado a los 4 sitios que pintan conteos
(header + tabs Money/Spotlight/Patterns). Es exacto, no redondea a "6.3k".

**Etiqueta para el usuario (commit `03d84ad`):** "items" → "news articles" en el
header (y "articles" en los tabs Money/Spotlight/Patterns) para que un visitante
entienda que el conteo son artículos de noticia, no un genérico. Se mantiene en inglés
(el sitio es 100% inglés). Ahora se lee: **"6,361 news articles · 2026-01-01 → 2026-07-25"**.

---

## Refreshes previos (reconstruidos de memoria/git)

- **2026-07-19** — W29 (hasta 19-jul), commit `588c1e6`.
- **2026-07-12** — W28 *"Memory And Chips Become AI's New Center Of Gravity"*,
  5789 items (652 curados), commit `e57fc34`.
- **2026-07-05** — W27 *"Silicon And Memory Command AI's Money As Agent Hype Cools"*
  (primer brief del tab 00), 5512 items (597 curados), commit `25f20e7`.
- **2026-06-28** — 5281 items (547 curados), commit `6b0597d`.
- **2026-06-21** — 4948 items (488 curados), commit `878eca8`.
- **2026-05-31** — 4042 items, commit `5025800`.
