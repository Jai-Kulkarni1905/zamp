# Design system

Calm, dense, finance-tool UI: white cards on a cool gray canvas, thin borders instead of heavy
shadows, monospace for every number and identifier, and one status color map used everywhere.
The tokens live in `frontend/src/styles/theme.css` (Tailwind v4 `@theme`); this page explains how
to use them. Extracted from the reference screenshots shared for Layer 4.

## Status colors (the one map)

| Status | Meaning | Token family | Solid (buttons) | Pill (bg / text / border) |
|---|---|---|---|---|
| APPROVED, PASS | good to pay, check passed | `approve` | `approve-700` | `approve-50` / `approve-800` / `approve-300` |
| NEEDS_REVIEW, WARN | a person must look | `review` | `review-600` | `review-50` / `review-800` / `review-300` |
| REJECTED, FAIL | do not pay, check failed | `reject` | `reject-600` | `reject-50` / `reject-700` / `reject-300` |
| RUNNING | in progress | `accent` | `accent-600` | `accent-50` / `accent-700` / `accent-200` |
| PENDING, SKIPPED, QUEUED | not run | neutrals | n/a | `sunken` / `ink-3` / `line` |

In code this is `frontend/src/lib/status.ts`: one function maps any decision, stage status or rule
outcome to its classes and icon. Components never pick status colors themselves.

Highlighted rows (a line or stage that triggered a warning) use the `*-50` background for the whole
row plus the pill on the right, like the amber "Freight" row in the reference.

## Color

- Canvas `#f4f6fa`, surfaces white, field boxes inside cards `sunken #f5f7fc`.
- Borders `line #e3e7ef` (1px everywhere), `line-strong` on hover.
- Text: `ink` primary, `ink-2` secondary, `ink-3` labels and meta, `ink-4` placeholders.
- Accent indigo is for navigation (active tab), links, focus rings, running state and progress
  bars. It is never used to mean approve or reject.

## Typography

- **Inter** for UI text, **JetBrains Mono** for amounts, invoice and PO numbers, GSTINs, hashes,
  timestamps, percentages and counts. Load both from Google Fonts with system fallbacks.
- Money is always `font-mono tabular-nums`, right-aligned in tables, formatted `₹1,77,000.00`.

| Token | Size | Use |
|---|---|---|
| `text-label` | 11px, 600, +0.04em, uppercase | field labels: `INVOICE EXTRACTED`, `PO REMAINING` |
| `text-xs` | 12px | meta, captions, table secondary lines |
| `text-sm` | 13px | body default |
| `text-base` | 14px, 600 | section and card titles |
| `text-lg` | 16px, 600 | page title, vendor names |
| `text-xl` | 20px, mono 600 | KPI values, totals |
| `text-2xl` | 26px, 700 | decision headline |

## Spacing, radius, shadow

- 4px grid. Card padding 16px (`p-4`), field boxes 12px (`p-3`), gaps 8 / 12 / 16px.
- Page gutter 24px desktop, 16px mobile.
- Radius: `rounded-chip` 4px chips, `rounded-control` 6px buttons and inputs, `rounded-card` 8px
  cards, `rounded-panel` 12px page sections. Pills are `rounded-full`.
- Shadows: `shadow-card` on cards (barely visible), `shadow-raised` only on popovers and the sticky
  action bar. Focus: `shadow-focus` ring in accent.

## Components

| Component | Look |
|---|---|
| `TopBar` | white bar, logo square + product name, nav tabs (active tab = `accent-50` pill with `accent-800` text), user on right |
| `Button` | `primary` approve-700 solid white text, optional mono amount chip inside; `danger` reject-50 bg, reject-600 text and border; `neutral` white, `line` border, ink text; `ghost` text only. Height 32px, `rounded-control`, 13px 600 |
| `StatusPill` | `rounded-full`, 1px border, 12px 600, leading icon (check, alert, x, spinner) |
| `Chip` | mono 11px, `rounded-chip`, tinted bg, e.g. `99.8%`, `+₹3,010.00` |
| `Card` | white, `line` border, `rounded-card`, `shadow-card`, header row: icon in 28px rounded square + title + right slot |
| `KpiTile` | white box with `line` border, `text-label` title, mono `text-base` value, small colored sub text |
| `Banner` | full-width tinted strip (status `*-50` bg) with icon, title, one-line detail and KPI tiles on the right |
| `FieldBox` | `sunken` bg, `rounded-card`, 3-column grid of `text-label` + mono value |
| `KeyValueRows` | label left `ink-3`, value right mono `ink`, 8px row gap |
| `StageCard` | numbered mono badge `01`, title, status pill right; expands to show payload; row tinted when WARN/FAIL |
| `ConfidenceBar` | 4px bar, approve-600 when at or above 0.70, review-600 below |
| `ProgressBar` | 6px accent bar on `accent-100` track (tolerance budget, PO consumption) |
| `Timeline` | 8px dots on a 1px `line` rail, mono time + label (event log) |
| `Tabs` | underlined tab bar, accent-600 underline on the active tab, count badge per tab (accent-600 filled when it needs attention, like the review queue) |
| `SearchInput` | 32px, `sunken` bg, search icon left, `/` shortcut hint right; lives in the top bar and drives the dashboard's `?q=` |
| `Dropzone` | dashed 2px `line` border on `sunken`, accent when dragging; `compact` variant is one row for the dashboard header |
| `RunsTable` | `sunken` header row with `text-label` headings, 1px row dividers, whole row clickable; collapses to stacked cards below `md` |
| `POTable` | per-PO row with a consumption `ProgressBar` (accent within PO, review amber when over within tolerance), expands to its invoices with "counts" / "not counted" chips |
| `QueueNav` | "Queue: 2 of 3" with prev / next arrows, shown on the run page when opened from the review queue |
| `KpiTile size="lg"` | dashboard variant: 20px mono value, sub text on its own line |

## Rules

- No em dashes in UI text.
- Every number from the API is a string Decimal; format with the shared `formatINR`, never `parseFloat` for display math.
- Icons: 16px line icons, `ink-3` by default, status color inside pills.
- Keep it calm: no gradients, no saturated large fills except the primary action button and the decision headline badge.
