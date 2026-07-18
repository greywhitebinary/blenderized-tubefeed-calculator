# Feed-log rework — design & implementation plan

> **Status: designed, NOT yet implemented.** Written 2026-07-17 at the end of
> a hands-on user-testing session with the author (Hui Jun Chew, RD). This is
> the next major piece of work. It is a repo file (not a chat artifact) so any
> tool — Claude Code, Cline, anything — can pick it up cold.
>
> Read `CONTEXT.md` (§9 status, §11 gotchas) and `.clinerules` before
> starting. The nutrient registry / data-pack architecture
> (`data/packs/canada/nutrients.csv`, `src/nutrients.py`,
> `BUSINESS_CASE.md` Appendix C) is untouched by this rework — every
> constraint about it still applies (no hardcoded nutrient lists, etc.).

---

## 1. The bug that triggered this (currently LIVE in the app)

Discovered by the author during real use, 2026-07-17:

The recipe's measured batch volume (e.g. **400 mL**) is used *only* as the
density denominator. Daily totals are computed as `density × schedule volume`
(e.g. **1200 mL/day** from the bolus schedule). The app therefore silently
assumes the client received **three batches' worth** of a recipe that, as
entered, exists once. Nothing reconciles "what the recipe produces" against
"what the schedule claims was delivered."

**Until this rework lands: do not trust the Results tab's daily totals,
adequacy, per-kg, fluid, or chart-note numbers whenever the delivery
schedule's total exceeds the batch volume.** They extrapolate.

The original design docs endorsed the extrapolation ("totals matter once
multiplied by daily mL intake") — defensible only when batches genuinely
scale. As a silent default about actual intake, it is wrong.

**Author's decision: full coherent rework, NO interim patch.** A
cap-at-batch band-aid was explicitly considered and rejected — it would be
throwaway logic that papers over the wrong model.

---

## 2. The model: "the day is a list of feeds"

The author's real-world cases that the current model cannot express:

- Blend in the morning, feed it; blend *different* stuff in the afternoon,
  feed that. (Multiple blends per day, different compositions.)
- Make a batch, keep it in the fridge, draw from it across the day. (A batch
  is a **stock you draw from**, not a unit that maps 1:1 to a schedule.)

### Concepts

- **Blend** — unchanged math: ingredients (CNF + custom label foods) +
  measured batch volume → densities via `calculate_profile()`. NEW: the app
  holds a **list** of blends (open-ended; optimize the UI for 2–4), each with
  a name ("Morning blend", "Fridge batch"), its own ingredient list and
  measured volume.
- **Feed log** — replaces the delivery schedule as the source of truth for
  intake. Rows of: **time · source · volume given (mL)**. A source is one
  of: a blend (by name), a commercial formula (from `formulas.csv`), or a
  water flush. Example day:
  `0800 · Morning blend · 300` / `1200 · Morning blend · 100` /
  `1500 · Fridge batch · 350` / `2000 · Peptamen 1.5 · 250` /
  flush rows interleaved.
- **Daily totals = Σ over log rows**: each blend row contributes
  `its blend's densities × its volume`; formula rows contribute the
  formula's per-mL values × volume (kcal, protein, free water via
  `free_water_per_mL`); flush rows contribute fluid only. Adequacy, per-kg,
  fluid ledger, and chart note all flow from this sum — one definition of
  "what the client received," used everywhere.
- **Batch bookkeeping, not assumption**: per blend, compare
  `Σ volumes logged from this blend` vs `its batch volume`.
  - Logged > batch → **visible error flag** ("logged 500 mL of Morning
    blend but the batch is 400 mL").
  - Logged < batch → fine, that's leftovers. No warning.
- The nutrition math per blend is exactly today's; only the aggregation
  layer is new. `calculate_profile()` is called once per blend.

### What this dissolves (do not rebuild these)

- The **mismatch rule** question (cap? batches-per-day input?) — moot;
  volumes are never inferred, only recorded.
- The separate **"combined regimen" section** built in round 2 (formula +
  mL/day added to BTF) — superseded; a formula is just a feed-log row.
  Remove that section; its free-water-per-mL math moves into log
  aggregation.
- The standalone **flush schedule** in the banner — flushes become log rows.
- The chart note's structure — it becomes the log read aloud, plus totals:
  the note now naturally reports **what was actually received**, per source.

---

## 3. Scope of changes

### Session state (app-level)

- `blends`: dict id → {name, ingredients: [...], measured_volume_mL}
  (ingredient rows keep their existing shape: food_code, description,
  grams/amount, unit, counts_as_fluid). `custom_foods` can stay global
  (negative codes are unique across blends).
- `feed_log`: list of {time_str, source_type: "blend"|"formula"|"flush",
  source_id, volume_mL}.
- Migrate the "Load example recipe" button: one example blend + a small
  example log (e.g. 300+100 mL of it + one flush) — chosen so example
  totals are *internally consistent* (logged ≤ batch).

### Build tab

- Blend selector at top: selectbox of blend names + "➕ New blend" +
  rename/delete. Everything currently in the Build tab (search,
  custom-food NFt form, blend details, ingredient table) operates on the
  **selected** blend. Per-blend density mini-summary (kcal/mL, protein/mL)
  next to the selector helps orient.

### Banner ("Patient, Delivery & Targets")

- Weight + targets: unchanged.
- Delivery section replaced by the **feed log editor**: add/remove rows,
  each row = time text/input, source dropdown (blend names + formula names
  + "Water flush"), volume number input. One-line summary becomes:
  "Received: 750 mL blends + 250 mL formula + 200 mL flushes = 1200 mL".
  (Delivery *method* — syringe/gravity — can become a single free-choice
  field used only for the chart-note wording; it no longer does math.)

### Results tab

- Per-blend density panel (each blend's kcal/mL, protein/mL, free-water
  fraction + coverage) — densities are still the per-blend lens.
- Daily totals/adequacy/micro screen/per-kg/fluid ledger: computed from
  the log aggregation. Fluid provided = Σ(counts-as-fluid contributions
  scaled per blend row) + formula volumes + flushes — same conventions as
  round 2 (full-volume I&O counting), now per-row.
- Batch-bookkeeping flags shown here (and/or next to the log editor).
- Comparator, flow test, Excel export: keep; export gains a Feed Log sheet
  and per-blend sheets. Dilution what-if: keep, operating on the selected
  blend.
- Chart note: log read aloud + totals, e.g.
  `BTF via syringe: 0800 300 mL + 1200 100 mL Morning blend; 1500 350 mL
  Fridge batch; 2000 250 mL Peptamen 1.5; flushes 2×100 mL.
  Provides ~X kcal, X g CHO, X g protein (x.x g/kg), X g fat.
  Fluid provided: ... Free water (CNF-estimated): ...`

### Backend (`src/`)

- `calculate_profile()` and everything below it: unchanged.
- New thin aggregation helper (suggest `src/day.py` or a function in
  `calculator.py`): takes [(profile, volume)] blend rows + formula rows +
  flush total → daily totals dict + fluid numbers + per-blend usage
  bookkeeping. Pure functions, easily verified. Extend
  `scripts/verify_backend.py` with a stage exercising: two blends with
  different densities + a formula row + flushes → hand-checkable totals;
  and the over-draw flag (log 500 from a 400 mL batch).

### Docs (same session as implementation, separate commit)

- CONTEXT.md §1 app-flow + §9; BUSINESS_CASE.md §7 (features) and
  Appendix A5 (daily totals equation becomes the log sum) — the docs
  currently describe the schedule-extrapolation model; they must not
  survive the rework unchanged. README.md Step 6 walkthrough.

---

## 4. Out of scope (v1 of the rework)

- **Batches spanning multiple days** (make Sunday, feed Mon–Wed). The log
  models one day. A batch drawn across days works fine for *charting a
  single day*; multi-day batch accounting (how much is left tomorrow) is a
  future feature. Note it in CONTEXT.md as roadmap.
- Saving/loading blends or days (Phase 7 JSON persistence) — pairs
  naturally with this model but is its own task.
- Prescribed-vs-received comparison (the spreadsheet's "% volume provided"
  concept). The log records received; a prescription field to compare
  against can come later if wanted.
- Any registry/targets/pack changes.

## 5. Verification bar

Usual three scripts green after every commit
(`verify_backend.py` — extended per §3, `trace_calculation.py`,
`check_app_imports.py`), plus AppTest covering at minimum:

1. The original bug case: one blend, batch 400 mL, log 3 rows × 400 mL of
   it → over-draw flag visible, totals computed from the logged 1200 but
   flagged as exceeding stock (i.e., never silently "fine").
2. One blend, batch 400, log 400 → totals = density × 400 exactly (the
   author's stated expectation).
3. Two blends with different densities + formula row + flush rows → totals
   match hand arithmetic; chart note lists every row.
4. Blend add/rename/delete without losing the other blend's ingredients.
5. Example-recipe load produces an internally consistent day.

Commits per the repo's established discipline (green at every commit, no
push, trailer:)

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

## 6. Open questions to confirm with the author before/while implementing

1. Feed-log row times: free text ("0800") is enough for charting, or a
   time picker? (Suggest free text — it's documentation, not computation.)
2. Should the over-draw flag *block* results or just warn loudly?
   (Suggest warn loudly, never block — RD judgment rules.)
3. Naming in the UI: "Blends" and "Feed log" vs other words she'd use at
   work ("Batches"? "Intake record"?).
