# TaskDash / TrueDuty — Design System

Design documentation for `taskdash-landing.html` (standalone single-file landing page).
This document explains **how the UI was built**, every design decision behind it, and
the complete **WHITE mode** (light theme) specification.

---

## 1. How this UI was made (the method)

The page looks the way it does because of five deliberate moves, applied in this order:

1. **A tiny token system was locked before any layout was written.** One background
   family, one accent, three radii, one easing curve, two fonts. Every visual decision
   on the page resolves back to these variables. Nothing is styled ad hoc.
2. **The theme is data, not markup.** Dark is the default; WHITE mode is a single
   `@media (prefers-color-scheme: light)` block that swaps ~20 CSS variables. No
   component knows which theme it is in — that is why light mode exists at all, and
   why it is consistent (see §4 and §6).
3. **Contrast was engineered, not assumed.** The brand green works on dark but fails
   on white. It was darkened in three steps until it passed WCAG AA for small text
   (see §6.3). This is the single most common thing landing pages get wrong in light
   mode.
4. **The product is shown working, not screenshotted.** The TrueDuty tracker, the
   chat, the kanban board, the doc checklist and the pricing toggle are real DOM with
   real state — visitors can start a timer or drag a card. Fake screenshots of a fake
   product read as fake; a working widget reads as product truth.
5. **Restraint rules (the anti-slop discipline).** One accent color for the whole
   page, one shadow scale, one icon weight, rationed eyebrows, zero em-dashes, no
   gradient-purple anything. Uniform constraints are what make a page feel designed
   rather than assembled.

Stack: **no framework, no animation library**. Vanilla CSS (~570 lines) + vanilla JS
(~250 lines). Three AI-generated brand renders are inlined as base64 JPEG (~151 KB),
which is why the whole page is one 276 KB file that opens from anywhere.

---

## 2. Architecture

| Layer | Choice | Why |
|---|---|---|
| Markup | Single HTML file, semantic landmarks (`header` / `main` / `footer`, one `<main>`) | Portable, greppable, no build step |
| CSS | Hand-written, organized in one `<style>` block: tokens → base → buttons → per-section → responsive → reduced-motion | Token-first order means everything downstream consumes variables |
| JS | One IIFE, `'use strict'`, ES5-style | No bundler; degrades cleanly |
| Fonts | Satoshi via Fontshare CDN, JetBrains Mono via Google Fonts, system fallbacks | Distinctive without license cost |
| Icons | Phosphor Icons web (regular weight) via unpkg | One icon weight keeps the page visually quiet |
| Images | 3 AI-generated renders, inlined base64 | Zero external requests, no "fake screenshot" smell |

**Progressive enhancement contract:** JS adds an `html.js` class immediately. Every
scroll-reveal style is gated behind `html.js .reveal`, so a no-JS visitor sees the
full page, fully visible, statically. Nothing is hidden by default in CSS.

---

## 3. Color system — DARK (default)

Dark is the base theme (`:root`). All surfaces carry a faint green undertone so the
emerald accent feels native rather than pasted on.

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0a0c0b` | Page background (near-black, green-tinted) |
| `--bg-2` | `#0d100f` | Alternating band background (TrueDuty section, metrics band) |
| `--panel` | `#101413` | Cards, cells, plans |
| `--panel-2` | `#151a18` | Nested/inset surfaces (chat bubbles, kanban wells) |
| `--line` | `rgba(255,255,255,.08)` | Hairline borders (the main separator — not shadows) |
| `--line-2` | `rgba(255,255,255,.16)` | Emphasized borders (inputs, ghost buttons) |
| `--text` | `#edf2ef` | Primary text |
| `--muted` | `#a7b2ad` | Secondary text |
| `--faint` | `#87928d` | Tertiary/meta text (lifted from `#7d8883` in QA to keep AA) |
| `--accent` | `#21eb98` | Brand emerald — taken from the uploaded dark-surface logo |
| `--accent-soft` | `rgba(33,235,152,.13)` | Accent tint fills (badges, glow washes, hover wells) |
| `--accent-line` | `rgba(33,235,152,.38)` | Accent-tinted borders (focus, popular plan, your-avatar) |
| `--accent-ink` | `#052b1c` | Text/icons placed **on** accent (dark green on emerald) |
| `--logo-d` | `#ffffff` | Fill of the logo's "D" mark |
| `--overlay` | `rgba(6,10,8,.74)` | Scrim over the CTA photo |
| `--shadow-card` | `0 24px 70px rgba(0,0,0,.5)` | Floating media (hero art, trackers) |
| `--shadow-pop` | `0 10px 34px rgba(0,0,0,.38)` | Raised cards (day card) |

**Accent discipline:** the emerald appears only as ink/fill for actionable or "live"
things — primary buttons, running timers, checked boxes, the shipped timeline block,
drawn lines, count-up numbers. It is never used for passive decoration, which is what
keeps it loud after nine sections.

**Surface depth model:** four steps, always used in order — page (`--bg`) → band
(`--bg-2`) → card (`--panel`) → inset (`--panel-2`). A chat bubble sits on a kanban
well sits on a card sits on the page; no surface ever skips more than one step.

---

## 4. How the theme switch works (token-level swap)

```css
:root { /* dark tokens (§3) */ }

@media (prefers-color-scheme: light) {
  :root { /* white tokens (§6.1) */ }
}
```

Rules that make this architecture work:

1. **Swap happens only at token level.** The entire light theme is ~20 variable
   reassignments in one media query. No component restyles itself per theme.
2. **Components may consume variables but never hardcode theme colors.** A card that
   says `background: var(--panel)` is theme-agnostic by construction.
3. **Exactly three component-level exceptions exist**, each with a reason (§6.4).
   If a fourth is ever needed, it must justify itself the same way.
4. **Some things intentionally never flip.** The CTA band is a photo with a dark
   scrim and white text in both themes (`--overlay` is unchanged); `.btn-ghost-light`
   exists only on top of that photo. A photo has no theme; scrimming it keeps one
   design for both.
5. **The logo participates via `--logo-d`** (`#ffffff` in dark, `#0c100e` in white),
   so the brand mark re-inks itself without an image swap.

There is no manual toggle in this build; the page follows the OS setting. Because the
switch is token-level, adding a `.light` / `.dark` class override later is a
mechanical change (mirror the media query into two class selectors).

---

## 5. Typography, shape, elevation, spacing

### 5.1 Typography

Two fonts, strict roles:

| Role | Font | Spec |
|---|---|---|
| Display / H1 | Satoshi 700 | `clamp(2.5rem, 5vw, 3.7rem)`, letter-spacing `-.035em`, line-height `1.06`, max-width `19ch`, `text-wrap: balance` |
| H2 | Satoshi 700 | `clamp(1.9rem, 3.6vw, 2.85rem)`, `-.03em` |
| H3 / card titles | Satoshi 700 | `1.05–1.14rem`, `-.015em` |
| Eyebrow | JetBrains Mono 500 | `.72rem`, uppercase, `+.18em` tracking, accent color |
| Body | Satoshi 400 | `16px / 1.55`; lede `.sub` `clamp(1rem, 1.3vw, 1.1rem)`, max `56ch` |
| Data | JetBrains Mono 700 | Timers, metric values, plan prices, stat chips — always with `font-variant-numeric: tabular-nums` so digits never jitter while animating |

The pairing is the personality: Satoshi (geometric-humanist, warmer than Inter) for
voice, JetBrains Mono for **instruments**. Anything that "measures" — a timer, a
percent, a price — is mono. That split is what makes the page read as "work software"
instead of "marketing template".

### 5.2 Shape system (three radii, no exceptions)

| Token | Value | Applies to |
|---|---|---|
| `--r-card` | `16px` | Cards, media frames, tracker widget |
| `--r-chip` | `10px` | Chips, kanban cards, integration tiles, inputs |
| `--r-pill` | `999px` | All buttons, segmented control, avatars, status dot |

One sanctioned outlier: the CTA band at `24px` (a hero-scale object). Nested elements
always step down (card 16 → inner tile 10), never mix scales randomly.

### 5.3 Elevation

Two shadow tokens only (§3). Separation is carried by **1px hairline borders**
(`--line`) in ~95% of cases; shadows are reserved for things that genuinely float
above the page (hero render, tracker overlay). In WHITE mode the same shadows are
re-tinted and lightened ~4× so cards sit "on paper" instead of "in a void".

### 5.4 Spacing & layout

- Container: `.wrap` max-width `1240px`, side padding `clamp(20px, 4vw, 32px)`.
- Section rhythm: `padding-block: clamp(84px, 9vw, 132px)` — one rule for every
  section, which is why vertical pacing feels even.
- Grids are **deliberately unequal**: hero splits `1.05fr / .95fr`, TrueDuty
  `.98fr / 1.02fr`, bento rows `7/5` then `4/4/4`. Equal column splits are the
  template smell this page avoids; asymmetry + varied cell backgrounds (flat, tinted,
  radial-glow, dot-grid) keep the bento from reading as a card farm.
- All type scales via `clamp()`; no fixed px typography anywhere.

---

## 6. WHITE mode (light theme) — full specification

### 6.1 Token table

| Token | Dark | White | Note |
|---|---|---|---|
| `--bg` | `#0a0c0b` | `#f4f6f5` | Green-grey **paper**, not `#fff` — pure white backgrounds feel clinical next to the emerald |
| `--bg-2` | `#0d100f` | `#ecf0ee` | Band alternation survives |
| `--panel` | `#101413` | `#ffffff` | Cards pop against the paper |
| `--panel-2` | `#151a18` | `#f4f7f5` | Inset wells |
| `--line` | `rgba(255,255,255,.08)` | `rgba(12,22,17,.1)` | Borders flip from "light on dark" to dark-on-light, same 8–10% strength |
| `--line-2` | `rgba(255,255,255,.16)` | `rgba(12,22,17,.2)` | |
| `--text` | `#edf2ef` | `#111614` | Near-black with the same green undertone |
| `--muted` | `#a7b2ad` | `#49544f` | |
| `--faint` | `#87928d` | `#67736d` | |
| `--accent` | `#21eb98` | `#0d7c47` | **Darkened** — see §6.3 |
| `--accent-soft` | `rgba(33,235,152,.13)` | `rgba(13,124,71,.11)` | |
| `--accent-line` | `rgba(33,235,152,.38)` | `rgba(13,124,71,.42)` | |
| `--accent-ink` | `#052b1c` | `#ffffff` | **Direction flips**: on bright emerald you write dark green; on deep green you write white |
| `--logo-d` | `#ffffff` | `#0c100e` | Logo "D" re-inks automatically |
| `--overlay` | `rgba(6,10,8,.74)` | *(unchanged)* | CTA photo stays dark in both themes |
| `--shadow-card` | `0 24px 70px rgba(0,0,0,.5)` | `0 24px 70px rgba(20,32,26,.14)` | Green-tinted, ~4× lighter |
| `--shadow-pop` | `0 10px 34px rgba(0,0,0,.38)` | `0 10px 34px rgba(20,32,26,.12)` | |

### 6.2 What changes vs. what must not change

**Changes:** every surface color, every text tier, hairline polarity, shadow color
and alpha, accent value, `accent-ink` direction, logo fill.

**Must not change:** layout, spacing, radii, type scale, motion, the one-accent rule,
accent *usage* semantics. A theme swap that moves anything structural is a redesign,
not a theme.

### 6.3 Contrast engineering (the important part)

The brand's light-surface green (`#22b573`, from the uploaded light-theme logo) fails
on white: roughly 2.6:1 against `#ffffff` — below AA for normal text, and even UI
elements look washed out. The value was stepped down twice during QA:

```
#22b573  (brand, light-surface)   ~2.6:1  ✗ fails
#16a163  (first candidate)        ~3.3:1  ✗ still fails small text
#0d7c47  (final --accent, white)  ≈4.6:1  ✓ AA for small text
```

On dark, the same family gets **brighter** instead (`#21eb98` ≈ 12:1 on `#0a0c0b`).
So the rule is: **the accent hue never changes, its lightness does** — brighten toward
neon on dark, darken toward forest on white. `--accent-ink` flips direction with it.

Also fixed in QA for dark mode: `--faint` lifted `#7d8883 → #87928d` so tertiary text
clears AA on panels. Both modes were then screenshot-verified at 1440×900.

### 6.4 The three sanctioned component exceptions

Each is a material interaction with the theme that tokens alone can't express:

1. **`.nav.scrolled`** → `rgba(244,246,245,.82)` in white / `rgba(10,12,11,.8)` in
   dark. The frosted nav bar tints toward its own background family; a theme-agnostic
   glass would look grey in one mode or the other.
2. **`.tracker`** → `rgba(255,255,255,.88)` vs `rgba(16,20,19,.82)`. The signature
   widget is *frosted glass*, and glass must pick up the light around it — white
   frost on paper, dark smoke on charcoal.
3. **`.cell-e` dot-grid** → dot color flips polarity (`rgba(255,255,255,.05)` →
   `rgba(12,22,17,.07)`). A texture, not a color, so it lives outside tokens.

Anything else that needed light-mode love (timeline hatch swatches, shadow tokens,
cell glows) was solved **inside** the token system.

### 6.5 White-mode QA notes

- Verified at 1440×900 and 390×844, including the tracker frost, nav frost, plan
  gradient (`.plan.pop` uses `--accent-soft` over `--panel`, so it survives the swap
  untouched) and the CTA photo band.
- Common white-mode failures checked and absent: accent-on-white buttons, washed-out
  hairlines, logo illegibility, shadow "dirt", hero glow turning milky
  (`--accent-soft` at 11% alpha stays a whisper on paper).

---

## 7. Component inventory

| Component | Behavior |
|---|---|
| Fixed nav | Transparent → frosted + hairline on scroll; state via **IntersectionObserver sentinel**, zero scroll listeners |
| Mobile menu | Burger at ≤920px; Escape closes, body scroll locks, `max-height` cap, `aria-expanded` synced |
| Buttons | `btn-primary` (accent pill, lift + glow on hover), `btn-ghost` (hairline), `btn-ghost-light` (photo-only) |
| TrueDuty tracker ×2 | Live start/stop/reset timers, mono tabular digits, pulsing status dot, activity segment meter, per-app time bars. Hero instance sits half off the render's edge — composed, not docked |
| Logo marquee | Fictional monogram marks, CSS `translateX(-50%)` loop, edge mask-fade, pauses on hover |
| Day timeline | Storytelling prop: fragmented day rendered as hatched gap segments, shipped work as a solid accent block |
| Bento (12-col) | 5 cells: **chat** (send + auto-reply), **kanban** (HTML5 drag-and-drop + tap fallback + drop-hover wells), **docs** (custom checkboxes with focus rings), **integrations** (real brand SVG paths from simple-icons), **activity** (sparkline draws itself via `stroke-dashoffset`) |
| Workflow rail | 3 steps; connecting line `scaleX` draws on first intersection |
| Metrics band | 4 mono count-up values (rAF + ease-out), divider grid |
| Pull quote | Inline `<em>` tinted accent, no blockquote cliché |
| Pricing | Working monthly/annual segmented toggle, price pulse animation, popular plan = accent border + soft gradient fill + floating tag |
| CTA band | AI render + dark scrim + white text, theme-invariant |
| Footer | `2fr + 4×1fr`, hairline top/bottom rules |

---

## 8. Motion system

**One easing curve for the entire page:** `cubic-bezier(.16,1,.3,1)` (ease-out-expo
family) — exposed as `--ease` and reused everywhere, including shadows and color
transitions. One curve is half of why the page feels coherent.

| Motion | Implementation |
|---|---|
| Scroll reveals | `.reveal` → `.in` via IO; `opacity` + `translateY(20px)`, `.75s`; stagger via a `--rd` custom property |
| Hero entrance | Staggered `rise` keyframes on the stack (delays `.05/.16/.27/.38s`), media follows |
| Sparkline draw | `stroke-dasharray/offset` transition, `1.6s` |
| Workflow line | `transform: scaleX(0 → 1)`, `1.5s`, origin left |
| Count-ups | rAF, ease-out, IO-triggered once |
| Marquee | CSS keyframes, `38s` linear, hover-pause |
| Micro-interactions | Buttons/cards `translateY(-1px)` + shadow on hover, `scale(.97)` on active |
| Price toggle | `pricepulse` keyframe on swap |

**Two hard gates:**

1. `html.js` gate — no JS, no hidden content.
2. `prefers-reduced-motion: reduce` — animations and transitions are nulled globally,
   the marquee freezes, the workflow line renders pre-drawn, smooth scroll off. The
   page is fully usable as a static document.

---

## 9. Imagery & iconography

- **Renders, not screenshots.** Three AI-generated brand images (hero glass panels,
  TrueDuty emerald ring, CTA wave) were generated *to the palette* and inlined as
  base64 JPEG. Abstract brand renders age better than fake product screenshots and
  can't contradict a product that doesn't exist yet.
- **Scrims** are `::after` gradients, so text contrast is guaranteed over any image.
- **Icons:** Phosphor regular weight only — one weight, one stroke world.
- **Integration logos:** genuine SVG paths extracted from the `simple-icons` package
  (GitHub, Figma, Notion, Google Drive, Zoom, Stripe), monochrome `fill:
  var(--muted)` so third-party brands can't fight the palette.
- **Fictional customer marks:** monogram letters in 1.5px-bordered squares/circles,
  mono font — unmistakably illustrative, visually consistent, legally safe.

---

## 10. Accessibility

- Contrast: AA-checked in **both** themes (see §6.3); `--faint` tier exists so meta
  text never dips below AA on panels.
- `:focus-visible` — 2px accent outline, 3px offset, radius 4.
- Custom doc checkboxes keep the real `<input>` (visually hidden) and mirror
  `:focus-visible` onto the drawn box; keyboard flow intact.
- Kanban has a **tap-to-move fallback** for touch and keyboard users, not only
  pointer drag.
- Landmarks: one `<main>`, labeled `<nav>`, `aria-label`s on icon-only buttons
  (burger, reset), `aria-expanded` on the burger, `role="timer"` on the readout,
  decorative SVGs `aria-hidden`.
- Anchor offsets: `[id] { scroll-margin-top: 84px }` under the fixed nav.
- Escape closes the mobile menu; body scroll is locked while open.
- All 3 content images carry `alt` text.

---

## 11. Copy rules (part of the design)

The copy is treated as a visual material and follows hard rules:

- **Zero em-dashes and en-dashes** (grep-verified).
- **No slop verbs** — unleash, empower, supercharge, elevate, streamline, revolutionize.
- **Organic numbers** — `57%`, `3.2h`, `12,400`, `19 min`, not `99.9%` and `10x`.
- **Realistic names** for people, teams, channels and customers.
- **One register** everywhere: dry, concrete, product-literate. Marketing adjectives
  rationed like the accent color.
- All product data, metrics, customer names and quotes are flagged as illustrative
  mock content in a header comment.

---

## 12. Responsive behavior

| Breakpoint | Changes |
|---|---|
| ≤1024px | Hero and TrueDuty collapse to single column; bento A/B span full width |
| ≤920px | Burger nav replaces links; metrics 2×2; pricing stacks (popular plan ordered **first**) |
| ≤820px | Workflow line hidden, steps stack; bento C/D/E full width |
| ≤560px | Tracker repositions from overlay into flow; metrics single column; CTA buttons full-width; activity meter hidden |

The tracker's journey is the detail worth copying: it starts as a composed overlay
(half off the hero render's edge), then gracefully becomes an in-flow card on small
screens instead of shrinking into illegibility.

---

## 13. QA performed before delivery

- Desktop 1440×900 in **both** themes; mobile 390×844; burger menu; full-page shots.
- Interaction smoke tests: both timers, chat send, board drag + tap, doc checklist,
  pricing toggle, scroll reveals, count-ups, line draw.
- Fixes found by QA: activity-bar overflow in the tracker, mobile-menu
  Escape/scroll-lock/max-height, anchor offset under fixed nav, pricing button
  alignment, timeline segment backgrounds, and the two contrast corrections in §6.3.
- Anti-slop pre-flight: one accent, one radius system, one icon weight, one easing
  curve, rationed eyebrows (a single one on the whole page), no duplicate CTA intent
  per viewport, no em-dashes, reduced-motion collapse verified.
