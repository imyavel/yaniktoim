# divergence_001 — Gate report (Phase 3 «ворота»)

> **Goal of the gate:** prove reversibility — that ONE semantic source (`article.zml2`)
> renders through ONE theme-agnostic HTML skeleton (`render.mjs` + class contract) into
> all 5 reference designs via CSS-only skins. This report records, per theme, what was
> reproduced, what diverged, and — most importantly — what is **NOT expressible** from the
> current source/spec (format gaps that must go back to Phase 2).

---

## 0. Reversibility verdict — PASS

- `node render.mjs` regenerates all 5 outputs with exit 0:
  `manuscript-narrow`, `manuscript-wide`, `classic-narrow`, `editorial`, `modern`.
- **Single skeleton proven byte-for-byte.** After normalizing the theme name, the rendered
  HTML bodies are **identical** across themes (`diff` of `manuscript-narrow.html` vs
  `editorial.html` with theme token substituted → no differences). The only per-theme
  variation in the document is `<html data-theme="…">` and the `<link>` to `themes/<theme>.css`.
  Everything visual lives in CSS. This is the core claim of the gate, and it holds.
- The shared class dictionary (the “contract”) is documented at the top of `render.mjs`.
  All 5 skins target only those classes + the structural `data-*` attributes
  (`data-role`, `data-ord-word`, `data-chapter-index/total`, `data-kind`, `data-stanzas`, `data-art`).

### Mandatory baseline behaviors — all met
- **#1 Type-scale guards.** `base.css` sets a footnote floor (`.fnlist` =
  `max(--fs-note-floor, 0.875rem)` ≈ 14px) and a caps-label floor hook (`--fs-label-floor`).
  Every theme uses `clamp()` with an explicit ceiling on titles and applies the label floor
  to tracked-caps kickers. Max/min running-text ratios stay within each spec’s target
  (≤4× classic, ≈5× manuscript, ≤7.6× editorial, ≤8× modern).
- **#2 Reading-order connectors.** Present ONLY in the multi-column verse themes
  (`manuscript-wide`, `editorial`); **absent** in single-column themes
  (`manuscript-narrow`, `classic-narrow`) and in `modern` (single-column by spec). Hidden on
  mobile where columns collapse to 1. See §“Known cosmetic limitation” for the CSS caveat.
- **#3 `:target` footnote highlight.** Implemented in all 5 themes with a palette-matched
  treatment (gold inset for manuscript-narrow; rubric left-rule for manuscript-wide;
  cream-rose halo `#fbeede` for classic-narrow; accent line + flash for editorial;
  garnet tint + left tick for modern). Neutral fallback also lives in `base.css`.

---

## 1. Per-theme reproduction

### manuscript-narrow (single-column parchment scroll) — reproduced
- Parchment gradient body, double gold inner frame (`::before/::after`), rubric title with
  gold author-glyph, fleuron `❖` section dividers, three distinct epigraph treatments,
  `Стих <слово>` kicker via `attr(data-ord-word)`, dropcaps on lead prose + lead stanza,
  CAPS-crescendo warmed ink, footnote apparatus with absolute `.fn-num`, src/author/ext/artlink.
- **Diverged:** none material. Single-column → no connectors (correct).

### manuscript-wide (wide codex spread) — reproduced
- 1280px gold-framed page (sharp corners, radius 0), Playfair 900 rubric title, `\2042`
  fleurons + corner `✾`, 2-column verse and prayer, 2-column footnote apparatus with
  `.note.wide` spanning all columns, `.exalted`-style gold left-rule on CAPS stanzas.
- **Diverged (cosmetic):** the in-chapter “dialogue” panel (`.dialogue`) the spec describes
  has no corresponding body block in this source — the Avatar quote lives in footnote `[^7]`,
  not as an inline block. So that treatment is unexercised, not broken (see GAP-6).

### classic-narrow (old printed liturgical book) — reproduced
- `.sheet` (50rem) on warm paper, 42rem inner measure, EB Garamond body + Playfair display,
  Roman chapter ornament via CSS counter (`counter(…, upper-roman)`), `Стих <слово>` kicker,
  fleuron dividers, hanging-indent verse lines, framed `.majuscule` CAPS block, `#fbeede`
  `:target` halo, footnote `↩` only where a back-reference exists.
- **Diverged:** none material. Single-column → no connectors (correct).

### editorial (wide magazine longread) — reproduced
- 1480px wrap, hero masthead with bordeaux uppercase title + gold glyph, dark feature-banner
  prose epigraph with 13rem watermark quote, `.term` badge (КАТНУТ/ГАДЛУТ), auto-fit verse
  grid, `columns:2` prayer + finale, apparatus as a 1px-gap card grid (`.note.wide` spans),
  `:target` accent line + flash keyframe.
- **Diverged (cosmetic):** the spec’s `.fn-legend` (glyph-legend grid for `;;;;`, fn-28/29)
  and stepped `.deflist` cannot be built — the source footnotes carry no nested structure
  (see GAP-5). They render as ordinary wide notes. Acceptable but not pixel-identical.

### modern (sacred-modern editorial) — reproduced
- 1280px, rail/main 1:2 grid with **sticky rail** (built by placing `.section-head` in column 1,
  `grid-row: 1 / span 99`, `position:sticky`), big garnet Roman ordinal in the rail via counter,
  hero glyph as a pill capsule (`border-radius:999px`), Playfair/Spectral/Manrope pairing,
  centered katrens + left epic, literal-register CAPS (`text-transform:none`), garnet
  `:target` tint. Single-column → no connectors (correct, per spec §5).
- **Diverged (cosmetic):** rail/main split is reconstructed from the flat skeleton via grid
  placement rather than a dedicated `rail`/`main` wrapper. Visually faithful; structurally it
  leans on `> *:not(.section-head)` flowing into column 2. Robust for this document; a future
  skeleton could expose an explicit rail slot if desired (cosmetic, not a gate blocker).

---

## 2. Format gaps — NOT expressible from current source/spec → return to Phase 2

These are **source/render/spec defects**, not theme cosmetics. The skins work around them with
heuristics; the proper fix is richer semantics in ZML 2.

- **GAP-1 — Chapter ordinal fused into the heading.** Source encodes `## СТИХ ПЕРВЫЙ. ЭКРАН.`
  as one string. There is no separate `section.ordinal` / `section.title` / numeric index.
  `render.mjs` derives `data-ord-word/-index/-total` from position and renders the whole
  string in `.section-title`; themes that want a “Стих первый” kicker + “ЭКРАН.” title
  separately, or a Roman numeral from the number, must reconstruct it. **Fix:** carry
  `section.ordinal` (number) + `section.title` (clean) as distinct fields.

- **GAP-2 — CAPS-crescendo register has no semantic flag.** The literal uppercase is in the
  data (correct, never transformed), but “this stanza is the exalted/invocation voice” is
  **not** marked. `render.mjs` derives `.stanza.caps` with a heuristic (`stanzaIsCaps`: all
  cased lines uppercase, ≥2 cased lines). Every theme spec explicitly forbids the theme from
  *guessing* the register. **Fix:** add `stanza.role = normal | caps-crescendo | invocation`.

- **GAP-3 — Footnote fields are unstructured.** Source footnotes are free text; `render.mjs`
  splits `{source-type, author, url}` with regexes (`^(См. также|Музыка|Цитата…):`,
  trailing ` — Author`). This **mis-tags** real cases: `[^7]` “Цитата из Х/Ф Аватар — Джейк и
  Банши выбирают друг друга” tags the *description* as `.author`. **Fix:** carry structured
  `{kind, source, author, url}` per footnote.

- **GAP-4 — Footnote weight (`wide`) is heuristic.** `.note.wide` is chosen by body length
  (>260 chars). Editorial/modern want `note.kind` (extended / legend / prayer / term) from
  data to decide full-width and special layout. **Fix:** `footnote.kind`.

- **GAP-5 — No nested structure inside footnotes.** The reference designs build a glyph-legend
  grid (`;;;;`, fn-28/29) and stepped definition lists. The source has no sub-item model in
  footnotes, so these render as flat wide notes. **Fix:** `footnote.subitems[]`.

- **GAP-6 — In-chapter epigraph/dialogue not a distinct block.** Specs describe an in-chapter
  dialogue panel (`.inline-epi` / `.inner-epi` / `.dialogue`). In this source the only such
  material (the Avatar quote) is a footnote, so the block type is unexercised. If future
  articles need an in-body dialogue distinct from top epigraphs, ZML 2 needs an
  `inline-epigraph` / `dialogue` block type. (Currently a latent gap, not triggered here.)

- **GAP-7 — Empty-body footnotes `[^22]`, `[^26]`.** Both referenced in text but carry no
  body; render emits `.note.empty` with a dash. Confirm with Phase 2 whether the text is
  genuinely missing (content defect) or intentionally a placeholder.

---

## 3. Known cosmetic limitation (theme CSS, not a source gap)

- **Reading-order connectors are a CSS approximation.** Pure CSS cannot detect *which* stanza
  ends a given column under `columns:2` / `auto-fit`. So instead of per-boundary `↳`/`↱`
  arrows, `manuscript-wide` and `editorial` render a single light golden reading-order hint
  spanning the top of the multi-column verse (`column-span:all`, `opacity:.55`), hidden when
  columns collapse to 1. This satisfies BASELINE #2 (connector present in multi-column themes,
  absent in single-column) but is not the exact per-column-boundary arrow the specs sketch.
  True boundary arrows would need a data flag for “stanzas form one continuous flow” + JS or
  container queries to locate the column break. Recorded as cosmetic, not a gate blocker.

---

## 4. Deliverables (all under `proof1\`)

- `render.mjs` — theme-agnostic zml2→HTML renderer; class contract in header comment.
- `themes/base.css` — invisible skeleton (reset, variable hooks, baseline scaffolding).
- `themes/{manuscript-narrow,manuscript-wide,classic-narrow,editorial,modern}.css` — 5 skins.
- `out/{…5…}.html` — source rendered through each theme (regenerated, exit 0).
- `divergence_001.md` — this report.
