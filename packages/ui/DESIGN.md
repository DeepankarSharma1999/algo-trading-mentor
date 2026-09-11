# DESIGN.md — the ledger-terminal

Algo Trading Mentor is a working instrument, not a marketing site. Two ancestors: the density and
honesty of a trading terminal, and the composure of a printed ledger. Everything on screen is a row
in a book of record: a label on the left in small uppercase mono, a value on the right in tabular
figures, a hairline rule beneath. Nothing floats. Nothing is boxed for decoration.

## Why this does not look generic

Generic SaaS builds pages out of cards: rounded, shadowed, padded, arranged in a grid, topped with
four KPI tiles and a hero sentence. We build pages out of **rows**. A page is one column, at most
1080px wide, left-aligned in a fixed 200px rail layout. Separation is by 1px rules and by vertical
space, never by containers. There is exactly one elevated surface in the entire product: the active
rule-trace panel on the Desk, which sits on `--paper` with a 2px `--accent` top border. Everything
else sits directly on `--ground`.

Type does the work colour usually does. Headings are Instrument Serif at real sizes (24/34) and are
rare: one per page, sometimes one per major section. Never for numbers. Body is Familjen Grotesk.
Every number, ticker, timestamp, rule expression, and state name is JetBrains Mono with tabular
figures, so columns of figures line up like a ledger. Labels are 11.5px uppercase with 0.12em
tracking.

Colour is almost absent. Bone ground, near-black ink, one indigo accent used only for things you can
click and for the marker of the current state. Semantic colours (eligible green, watch amber,
blocked red) are separate from the accent and only ever encode meaning, with soft tints for row
backgrounds. No gradients anywhere. Charts are a single-hue line on a faint grid with an emphasised
endpoint; the only area fill in the app is the drawdown chart, which fills downward in blocked-tint.

State is encoded in **shape**, not just colour, so it survives colour-blindness and monochrome
print: CALM is a plain outline chip, ELEVATED is a diagonal-hatch fill, COOLDOWN is solid
blocked-tint with a strike-through bar, RESEARCH is a dashed outline. Gates in a rule trace are
square checkboxes, never pills.

Motion: none decorative. The validation checklist fills stage by stage with a 120ms fade.
`prefers-reduced-motion` collapses it to 0.

## Tokens

All tokens live in `tokens.css`. Three theme states are implemented: bare `:root` (light),
`prefers-color-scheme: dark` guarded by `:root:not([data-theme="light"])`, and `:root[data-theme="dark"]`.

| Token | Light | Dark |
|---|---|---|
| `--ground` | `#F2F1EC` bone | `#121417` |
| `--paper` | `#FBFAF7` | `#181B1F` |
| `--ink` / `--ink-2` | `#1B1F23` / `#5B6470` | `#E8E6E0` / `#A3A9B2` |
| `--rule` | `#D6D3CB` | `#2A2E34` |
| `--accent` | `#2F4A8A` ledger indigo | `#8FA5E0` |
| `--eligible` | `#1F7A3F` | `#5FBF80` |
| `--watch` | `#9A5B00` | `#E0A64A` |
| `--blocked` | `#A82A2A` | `#E06A6A` |

Type scale: 13 / 15 / 16 / 19 / 26 / 36 (raised one notch from the brief's 12 / 13.5 / 15 / 18 / 24 / 34
after usability review: 13.5px body and 10px strip labels were below comfortable reading size). Faces:
Instrument Serif (display), Familjen Grotesk (UI), JetBrains Mono (figures, `font-variant-numeric: tabular-nums`).

Usability rules that sit on top of the identity: every clickable thing is at least 40px tall
(`--target`); `:focus-visible` draws a 2px accent ring; every page opens with one `.page-intro`
paragraph saying what the page is for; helper text (`.help`) sits under any input whose meaning is
not obvious; empty states (`.empty`) say what to do next and offer one button; long content folds
behind `details.fold` with a visible Show/Hide; the rail lists each section with a one-line
description; under 900px the rail becomes a horizontal `.topnav` and ledger rows stack.

Layout: `--rail-w: 200px` fixed left rail with section list in mono; `--strip-h: 44px` persistent top
strip carrying risk budget and behavioural state; content is a single column of ledger rows,
`--label-col: 200px` label column.

## Banned (lint failures)

Inter, Space Grotesk, Roboto, or `system-ui` as the primary face; purple/blue gradients; hero
sections; glassmorphism; rounded cards with drop shadows as the default container; an accent bar on
the left of every card; emoji anywhere in UI; centred layouts for data; skeleton shimmer; the cream
`#F4F1EA` + terracotta look; near-black with a single acid-green pop; big-number KPI tiles at the top
of every page; 01/02/03 numbered section markers unless order matters (the validation pipeline is the
one place order matters, so stages are numbered there).

`packages/ui/lint-design.mjs` greps the web app for the banned faces, gradients, emoji, `shadow-`
utilities and `rounded-xl` and fails `make check` on any hit.

## Primitives (packages/ui/primitives.css)

- `.ledger` — a table-like block: rows are `.row` grids `[label-col] 1fr [auto]`, 1px `--rule` between.
- `.label` — uppercase mono label.
- `.fig` — mono tabular figure.
- `.chip` — behavioural state chip with the four shape variants: `.chip--calm .chip--elevated .chip--cooldown .chip--research`.
- `.gate` — square checkbox glyph for rule-trace gates: `.gate--pass .gate--fail .gate--pending`.
- `.btn` — flat, 1px rule border, accent ink on hover. Primary variant fills accent. No radius above 2px.
- `.trace` — the one elevated panel (paper surface, 2px accent top border).
- `.h-display` — Instrument Serif heading.
- `.footer-note` — the legal footer line.

## Per-page notes (what makes each page not generic)

- **Onboarding**: no illustration, no progress dots. A ledger of three rupee rows and a profile
  row; the live sentence "For you, 1R = ₹X" is set in serif as the page's only large type. It is the
  contract you sign before you may see a chart.
- **Desk**: the top strip is the instrument panel. Watchers are rows, not cards; the latest signal
  is a rule trace: a checklist of conditions, a gate list of square boxes, figures in mono. Only the
  active trace is elevated.
- **Library**: a filtered list grouped by regime, each entry a plain-language rule paragraph with
  its ambiguity notes underneath. No thumbnails, no stars, no numbers.
- **Builder**: a two-column ledger, schema on the left as editable rows, the live "testable" verdict
  on the right listing the exact missing pieces in mono.
- **Validation**: a vertical, numbered (order matters) checklist that fills in with a 120ms fade;
  the weakest-stage sentence is the page's only serif line.
- **Journal**: a ledger of closed trades with planned vs actual columns; aggregates are small
  mono tables, not tiles.
- **Research / Settings**: ledgers with a diff view in mono; nothing else.
