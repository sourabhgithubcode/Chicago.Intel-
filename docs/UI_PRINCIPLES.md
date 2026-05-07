# UI Principles — Chicago.Intel

This is the **rendering contract** for the front-end. Same role as
`DATA_DICTIONARY.md`, but for what the user sees instead of what's stored.
If a section component or panel violates a rule here, fix the component —
not this doc.

Pinned to the same philosophy as `CLAUDE.md`:

> Show what data says. Show the source. Show confidence. Let the user
> decide. Never tell someone where to live.

---

## Section 1 — Who this is for

The user is a **renter who is not a data analyst**. They've entered an
address and a salary. They don't speak in:

- confidence intervals, MOE, p-values
- census tracts, CCA numbers, IUCR codes
- median vs. mean, distribution spread
- "ACS B25064" or any other source code

They DO speak in:

- "Can I afford this?"
- "Is this block safe at night?"
- "How long is my commute?"
- "Is this landlord legit?"
- "What does this neighborhood feel like?"

**Design for that vocabulary.** Technical names live in tooltips and
expanders, not in the visible label.

This is **not a dashboard.** A dashboard is many panels for someone who
monitors a system over time. Chicago.Intel is one address → one answer
page, with the receipts underneath. Treat each address view as a long,
scannable answer — not a Bloomberg terminal.

---

## Section 2 — The 5 principles

### 2.1 One number on top, then proof underneath
The hero is **the surplus dollar amount + one sentence**. If a user reads
only the top 200px, they got the answer. Everything below is the receipt.

### 2.2 Plain-English first, jargon on hover
Visible label is a sentence a renter would say. Source citation expands
on click/hover.

| ❌ Don't render | ✅ Do render |
|----------------|--------------|
| `ACS B25064 median rent · MOE ±$120` | `Typical rent on this block: $1,387` · *why we trust this* |
| `IUCR violent crime, 0.25mi, 5yr` | `12 violent incidents within a 5-min walk · last 5 years` |
| `Tract-level rent · 6/10` | `Block-level rent estimate · directional only` |
| `9/10 confidence` | 🟢 *Verified* |

### 2.3 Confidence as color + word, never a number
The 1–10 scale lives in the tooltip for people who want it. Visible UI
uses dot + word.

| Backend rating | Visible chip |
|----------------|--------------|
| 9–10/10 | 🟢 **Verified** |
| 7–8/10 | 🔵 **Strong signal** |
| 6/10 | 🟡 **Directional only** |
| Signal-only (price tier) | ⚪ **Signal — not a measurement** |

`ConfidenceTag.jsx` is the single source of truth for this rendering.
Components must pass the backend rating; the chip handles the mapping.

### 2.4 Progressive disclosure, not navigation
No tabs. No side menu. No "click here for more." One scrollable page per
address; sections collapse/expand inline. The **only navigation surface**
is the breadcrumb (`Chicago › CCA › Street › Building`). Zooming out is a
breadcrumb click, not a separate page.

### 2.5 Anti-median rule = anti-confusion rule
Per `DATA_DICTIONARY.md` §8.0, never render a median, average, or modal
value alone. Required render shape:

```
$1,387 typical rent
$825 – $2,940 across 412 buildings · this place: $1,500
```

A range plus the user's position in it is what a non-analyst can use to
decide. A bare median is just a number.

---

## Section 3 — Logical order on the Building view

This order is the contract. Sections may be hidden behind a collapse, but
their position is fixed.

| # | Section | Component | Why it's here |
|---|---------|-----------|---------------|
| 1 | Address + photo + breadcrumb | (header) | Identity |
| 2 | **Surplus hero** + salary slider + rent override | `SurplusHero.jsx` | The answer |
| 3 | Surplus formula breakdown | `CostSliders.jsx` | The receipt for #2 |
| 4 | Safety | `SafetySection.jsx` | "Will I be safe?" |
| 5 | Cost reality (grocery / dining / parking deltas) | `AmenityLayer.jsx` (cost subset) | "Can I afford the lifestyle?" |
| 6 | Getting around (nearest CTA, walkability, commute) | `NearestCTAStop.jsx` + commute panel | "Can I get to work?" |
| 7 | Building quality (311, owner, tax status) | `BuildingIntel.jsx` | "Is the unit OK?" |
| 8 | Wider context (displacement, vibe, schools) | `DisplacementRisk.jsx`, `LocationData.jsx` | Background |
| 9 | Composite + per-pillar scores | `CompositeScore.jsx` | Summary, last on purpose |
| 10 | "What this page does not tell you" | (footer) | Explicit limits |

**Why money → safety → cost → access → unit → context:** it mirrors how a
renter actually decides. Not what's easiest to query, not what the API
returns first.

The composite score is **last**, not first, because the components are
the truth and the composite is a derivative. Putting the composite at the
top would invert the trust hierarchy this product is built on.

---

## Section 4 — Section component contract

Every section component (`src/components/sections/*.jsx`) must:

1. **Show source + confidence on every value.** Use `ConfidenceTag.jsx`.
   No raw numbers without provenance.
2. **Show a "what this does not tell you" line for any value < 8/10.**
   Plain English. One sentence.
3. **Render a loading skeleton, not a spinner.** Spinners hide the page
   shape; skeletons preserve scroll position.
4. **Fail visibly, not silently.** If the backend call errors, render
   "Couldn't load — try again" with the section title still visible.
   Never disappear silently.
5. **Never delay first paint on optional data.** Section 2 (surplus)
   blocks first paint; sections 4–9 don't. They render their skeleton and
   fill in.
6. **Hardcoded values are forbidden in committed code.** If a section
   doesn't have a wired data source yet, render a clearly-labeled
   "Not yet wired — coming soon" placeholder. No fake numbers.

---

## Section 5 — Map behavior

Pinned in `CLAUDE.md`; restated for completeness:

| Zoom | Polygon shown |
|------|---------------|
| 10–12 | CCA polygons (77) |
| 12–14 | Census tract polygons (~800) |
| 14–16 | Street segments + building footprints |
| 16+ | Single building highlight + neighbors |

**Color-by dropdown** options: Surplus / Safety / Walkability /
Displacement / Landlord. Salary slider recolors live — no submit button.

The map is **a context layer**, not the main UI. It's beside the answer
page, not above it.

---

## Section 6 — What we explicitly do NOT do

- **No dropdown filters at the top of the page.** The filter is the
  address.
- **No tabs.** Tabs hide things; renters don't know what they don't know.
- **No score out of 100 without all component weights visible.** Per
  `CLAUDE.md`.
- **No icons without text labels.** A house glyph next to "$1,387" means
  nothing.
- **No "AI summary" paragraph.** Trust mechanism is data + source +
  confidence; prose replaces that with vibes.
- **No animation that delays content.** Skeletons, not spinners.
  No fade-ins on the hero number.
- **No "we recommend X."** Per `CLAUDE.md` — never tell someone where to
  live.
- **No precise dollar amounts from price-tier signals** (Google Places
  $/$$/$$$). Always labeled as estimate + signal.
- **No modal dialogs for errors or "no results."** Inline rows only.

---

## Section 7 — Open questions

Not decided yet — flag if a PR forces a decision:

- Mobile layout: same vertical order on phones, or does the map drop
  below the answer? (Tentative: drop below.)
- Print / share view: PDF export is out of MVP, but should the page work
  on `Cmd-P` today? (Tentative: yes — basic readable print CSS.)
- Recent searches list: in V2 per `DATA_DICTIONARY.md` §7.1.
- Comparison surface (§9.7): single-page or side-drawer? (Tentative:
  side-drawer that doesn't lose the current address.)

---

## Section 8 — How this doc gets enforced

- New section component → must conform to §4 before merge.
- Existing components currently violating §3 order or §4 contract are
  in-flight — see issue tracker.
- `ConfidenceTag.jsx` is the only place the rating-to-chip mapping lives.
  If you find a component reimplementing it, that's a bug.

If a rule here is wrong, change the rule with a commit that explains
why. Don't ship a component that quietly violates it.
