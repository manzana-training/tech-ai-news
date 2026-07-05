# Tab 00 "Brief" — editorial ejecutivo semanal auto-generado

**Fecha:** 2026-07-05 · **Estado:** aprobado por Gerardo (sesión 2026-07-05)

## Qué

Un tab nuevo (`00 Brief`, activo por default) en el dashboard público de Tech AI News
(https://manzanatraining.com.mx/tech-ai-news/) con un editorial ejecutivo semanal
auto-generado: imagen hero 16:9, kicker, headline, párrafo de 3-4 oraciones y 4-5
bullets. **Idioma: inglés. Registro: C-level, conciso.** Se regenera como parte del
refresh manual (`analysis/refresh.sh`), clave por semana ISO.

## Decisiones cerradas

| Decisión | Valor |
|---|---|
| Idioma del brief | Inglés |
| Estética de imagen | Propia del dashboard (Axioma: papel `#F4F2ED`, tinta, acento ocre `#9C6B2B`) |
| Archivo de briefs pasados | Solo se muestra el actual; JSON/webp semanales quedan versionados |
| Modelo de texto | Claude Sonnet 5 (`claude-sonnet-5`), structured outputs |
| Modelo de imagen | Replicate `black-forest-labs/flux-1.1-pro` (mismo flujo que blog manzana) |
| Dónde corre | Local, en el refresh manual. No toca EC2 ni su crontab |

## Componentes

### 1. `analysis/build_editorial.py` (nuevo)

- **Señales en Python puro** (sin LLM): share mensual de topics; ritmo diario de
  entidades y topics últimos 14d vs 45d previos; items curados de los últimos 7 días
  (título + digest_summary); top montos $ de la semana. Fuente: `history/*.jsonl`
  (dedup por `id`, última versión gana — misma regla que `build_dashboard.py`).
- **Llamada 1 — Anthropic** (`ANTHROPIC_API_KEY` de `C:\Users\supip\.secrets\credentials.env`):
  Sonnet 5, `output_config.format` con json_schema →
  `{kicker, headline, paragraph, bullets[4-5], image_prompt}`. Prompt de sistema con
  registro C-level en inglés; los números vienen precalculados (el LLM editorializa,
  no aritmetiza).
- **Llamada 2 — Replicate** (`REPLICATE_API_TOKEN`; fallback de lectura:
  `manzana/sitio-web/.env.local`): Flux 1.1 Pro, prompt base propio del dashboard:
  *"Minimalist editorial illustration on warm ivory paper. [escena]. Near-black ink
  with a single ochre accent. Abstract, restrained, print-quality. No text."*,
  `aspect_ratio 16:9`, webp q90, polling asíncrono → `assets/editorial/<YYYY-Www>.webp`.
- **Idempotencia:** clave = semana ISO de hoy (`2026-W27`). Si
  `analysis/editorial/<week>.json` existe, no llama a ninguna API. Flag `--force`
  regenera. Si falta el token de Replicate o falla la imagen → brief sin imagen
  (campo `image` null), warning, exit 0.
- **Validación:** el JSON se valida contra el schema antes de persistir.

### 2. `analysis/build_dashboard.py` (modificado)

- Lee el JSON editorial más reciente de `analysis/editorial/` y lo inyecta como
  `DATA.editorial` (incluye `week_label`, `generated_at`, ruta de imagen relativa).
- Si no hay ninguno → `editorial: null`. El build nunca falla por el editorial.

### 3. `analysis/dashboard_template.html` (modificado)

- Botón `<button data-tab="brief"><span class="n">00</span>Brief</button>` antes de
  Search; **activo por default** cuando `DATA.editorial` existe; si es `null`, el
  botón no se pinta y Search queda como default (lógica en JS, sin duplicar template).
- Sección: imagen hero 16:9 (si hay), kicker en mono, headline en Fraunces, párrafo,
  bullets con regla fina, línea de fecha "Week of Jun 29 – Jul 4 · generated Jul 5".
- Estilo consistente con Axioma relax del template (un solo acento, sin chrome nuevo).

### 4. `analysis/refresh.sh` (modificado)

Paso 2.5 entre scp y rebuild: `python analysis/build_editorial.py` — **no fatal**
(`|| echo warning`); el refresh completa aunque el editorial falle.

## Datos y layout de archivos

```
analysis/editorial/2026-W27.json    # texto del brief (versionado)
assets/editorial/2026-W27.webp      # imagen hero (versionada; ~100-300KB/semana)
```

Schema del JSON: `{week, week_label, date_range, generated_at, kicker, headline,
paragraph, bullets[], image (ruta relativa | null), image_prompt}`.

## Errores

| Falla | Comportamiento |
|---|---|
| Sin ANTHROPIC_API_KEY / sin red | build_editorial sale con warning; dashboard usa el editorial previo o null |
| Sin REPLICATE_API_TOKEN / Flux falla | Brief sin imagen (layout lo tolera) |
| JSON del LLM no valida | No se persiste; warning; se conserva el previo |
| editorial null en build | Tab no se pinta; Search default |

## Verificación

1. `python analysis/build_editorial.py` genera JSON + webp de la semana actual.
2. Rebuild + screenshot Playwright del tab Brief en server local.
3. Re-correr refresh el mismo día → 0 llamadas API (idempotencia).
4. Commit + push → verificar en Pages.

## Costo

~$0.05/semana (centavos de Sonnet + ~$0.04 Flux). Solo corre cuando Gerardo corre el
refresh y como máximo 1× por semana ISO.
