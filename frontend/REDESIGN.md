# CareerOS frontend redesign — implementation plan

**Direction: editorial / paper.**
**Scope:** token system + primitives + shell + dashboard, ATS, resume, tailor. Remaining pages inherit via primitives, cleaned up in the final sweep.

---

## What we're removing (measured, in `frontend/app`)

| Pattern | Hits |
|---|---|
| `shadow-[0_0…` / `drop-shadow-[0_0…` glows | 65 |
| `bg-gradient-to-*` | 47 |
| `glass-card-premium` / `glass-panel` | 39 |
| `blur-[…]` / `backdrop-blur` | 26 |
| `font-extrabold` / `font-black` | 24 |
| `rounded-2xl` / `rounded-3xl` / `rounded-[2.5rem]` | 24 |
| `gradient-text` | 17 |
| `hover-glow`, `animate-border-glow`, `pulse-glow`, `magnetic-hover`, `ring-glow` | 12 |
| `AnimatedCounter`, `animate-ping` | 9 |
| `motion.*` | 160 → keep maybe 15 |

That's the grep hitlist for the sweep. Also going: `GlowBackground.tsx` (4 drifting orbs), the orb keyframes, the counter-rotating loading rings, and copy like "Launch Control", "Platform Online", "Your AI-powered career command center".

---

## Design principles

1. **Paper canvas, ink text.** No navy, no glass, no glow. The product's artifact is a typeset page — the app should agree with it.
2. **Hierarchy comes from type and space**, not from color, gradient, or blur. One accent, used only for links / active nav / primary action.
3. **Hairline rules over boxes.** Most current `Card`s should be a heading + a rule, not a bordered container. Boxes are for genuinely separable objects only.
4. **Data reads as data.** Tables, tabular numerals, aligned columns — not four identical glowing stat tiles with rotating icons.
5. **Motion for state change only.** 120–150 ms, opacity and position. Nothing loops, nothing breathes, nothing pulses.
6. **Plain nouns in copy.** "Overview", "Resumes", "Issues", "Apply".

---

## Token system

**Color**

- Paper `#FCFCFA` · raised `#FFFFFF` · sunken `#F4F3F0`
- Ink `#101010` · secondary `#52504B` · tertiary `#8A867E`
- Rule `#E6E3DD` · rule-strong `#D4D0C8`
- Accent: single ink blue `#1B4D9B` — links, active nav, primary button, focus ring. Nothing else.
- Semantic, print-ink desaturated, used at **text weight** not as glow: good `#1E6F4B`, warn `#8A5A00`, bad `#A32222`

**Type** — replace Outfit + Plus Jakarta (both read as generic AI-SaaS).

- Display/headings: **Newsreader** or **Instrument Serif** — gives the editorial voice
- UI/body: **Inter**, with `font-variant-numeric: tabular-nums` globally
- Scale: 12 / 13 / 14 / 16 / 20 / 28 / 40. Line-height 1.5 body, 1.15 display
- Weights: 400 / 500 / 600 only. `extrabold` is banned.

**Geometry** — radius 4px (controls) / 8px (panels), max. Shadow: none, except one `0 1px 3px rgba(0,0,0,.08)` for modals and popovers.

Dark mode is a second `:root` block once tokens exist — not in this scope.

---

## Phases

### Phase 0 — Strip *(½ day)*

Delete `GlowBackground.tsx` and every decorative class from `globals.css`. File goes 279 → ~90 lines. The app will look plain and slightly broken; that's the correct intermediate state.

### Phase 1 — Tokens *(½ day)*

Rewrite `globals.css` `:root` and `tailwind.config.ts` with the palette above. Name tokens by intent (`paper`, `surface`, `sunken`, `ink`, `rule`) so misuse is visible in a diff.

### Phase 2 — Primitives *(1 day)* — rewrite `app/components/ui.tsx`

- `Card` → **`Panel`** (hairline border, flat) + **`Section`** (heading + rule, no box). Most current Cards become Sections.
- `Button` — solid ink primary / bordered secondary / plain ghost. 36px default, not 44. No gradient, no glow.
- `Input` / `Textarea` — white field, 1px rule, 2px accent focus ring.
- `Badge` → **`Tag`**, text-weight.
- `ScoreRing` → **`Score`**: large tabular numeral + thin single-color arc keyed to band. Plus **`ScoreBar`** for inline use. Drop the cyan→purple gradient stroke.
- New: **`Table`/`Row`**, **`Stat`** (label, number, delta), **`EmptyState`**, **`Toolbar`**.
- Delete **`AnimatedCounter`** — count-up numbers are the single loudest tell.

### Phase 3 — Shell *(1 day)* — `LayoutClient.tsx`, `Sidebar.tsx`

- Replace the 260px glass sidebar with a flat **top bar**: wordmark + Overview / Resumes / ATS / Tailor, with Builder / Skills / Chat / GitHub under an overflow menu, account menu right. Reclaims 260px — which matters for the tailor and builder split panes.
- Content column 1100px, generous vertical rhythm.
- Kill the per-route `AnimatePresence` y-20 spring — it adds perceived latency on every navigation. 120 ms opacity or nothing.
- Loading screen: wordmark + 2px determinate bar, not dual counter-rotating glowing rings.

### Phase 4 — Pages *(2–3 days)*, in this order

1. **Dashboard** (`app/page.tsx`, 491 ln) — delete the hero banner outright (grid pattern + 3 blur orbs + ping dot + gradient text). Becomes `Overview` + last-activity line. Stat tiles → one rule-separated stat row. "Launch Control" section dissolves into a toolbar. Recent resumes + tailored sessions merge into a single table.
2. **ATS** (`app/ats/page.tsx`, 1616 ln) — biggest win. Score header = numeral + band word + one-line verdict. Severity as a left rule + word ("High"), not three neon background tints. Suggestions become table rows with inline accept/reject. Improver chat becomes a plain panel.
3. **Resume** (`app/resume/page.tsx`, 624 ln) — dashed-rule upload zone; versions as a table with score / date / actions.
4. **Tailor** (`app/tailor/page.tsx`, 1302 ln) — split pane; diff in print colors (6% wash + underline / strikethrough), never neon.

### Phase 5 — Sweep *(½ day)*

Run the grep hitlist over builder, skills, chat, github, login, register, forgot-password; swap to primitives. Then contrast check, visible focus rings, `prefers-reduced-motion`.

---

## Notes

- **No logic changes.** Every phase is presentational — API calls, state, and handlers in each page stay exactly as they are.
- **Dependencies:** `gsap` and `lottie-react` are installed; after this they're almost certainly dead — drop them. `framer-motion` survives but shrinks a lot.
- **The builder and resume preview** render actual resume documents on white paper. Editorial direction makes app and artifact finally agree, instead of neon chrome framing a white page.
- **Total: ~6 days.** Phase 0–2 is the load-bearing part; if you stop after Phase 3 the app already stops looking generated.
