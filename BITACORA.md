# Bitácora — Tech AI News

Registro de refreshes del sitio público (https://manzanatraining.com.mx/tech-ai-news/)
y cambios operativos. El más reciente arriba. El procedimiento vive en
`analysis/refresh.sh` (un comando: scp histórico desde EC2 → brief semanal →
rebuild `index.html` → galería → commit/push).

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
