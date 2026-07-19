# Intake record rework — design & implementation plan (v2)

> **Status: fully designed, NOT yet implemented.** v1 of this doc (2026-07-17,
> tube-feed-only) was superseded the same day after further design
> conversation with the author (Hui Jun Chew, RD) settled every open
> question, including expanding scope to a **combined tube-feed + oral
> intake record**. This is the next major piece of work. It is a repo file
> (not a chat artifact) so any tool — Claude Code, Cline, anything — can
> pick it up cold.
>
> Read `CONTEXT.md` (§9 status, §11 gotchas) and `.clinerules` before
> starting. The nutrient registry / data-pack architecture
> (`data/packs/canada/nutrients.csv`, `src/nutrients.py`,
> `BUSINESS_CASE.md` Appendix C) is untouched by this rework — every
> constraint about it still applies (no hardcoded nutrient lists, etc.).
>
> **All open questions from v1 are resolved — do not re-ask, do not
> reintroduce the over-draw flag, do not split this into two logs. See §6.**

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

## 2. The model: "the day is a list of intake events"

The author's real-world cases the old model couldn't express, plus the
scope expansion agreed in the follow-up conversation:

- Blend in the morning, feed it; blend *different* stuff in the afternoon,
  feed that. (Multiple blends per day, different compositions.)
- Make a batch, keep it in the fridge, draw from it across the day. (A batch
  is a **stock you draw from**, not a unit that maps 1:1 to a schedule.)
- **The client may also eat and drink by mouth.** A BTF patient is not
  necessarily NPO-except-tube; oral intake for pleasure or supplementation
  is real and clinically relevant. The author wants **one combined record**
  — tube feed and oral intake together — producing **one set of daily
  totals**, not two logs that need manual reconciling.

### Concepts

- **Blend** — unchanged math: ingredients (CNF + custom label foods) +
  measured batch volume → densities via `calculate_profile()`. The app
  holds a **list** of blends (open-ended; optimize the UI for 2–4), each
  with a name ("Morning blend", "Fridge batch"), its own ingredient list
  and measured volume. **Blends are formulations, not batches** — see the
  "blend vs. batch" distinction in §6.2.
- **Intake Record** — replaces the old delivery schedule / v1 "feed log" as
  the single source of truth for everything the client received. **One
  list**, not two. Each row has a `source_type`:
  - `blend` — references a blend by id; `amount` is mL given from it.
  - `formula` — references a name in `formulas.csv`; `amount` is mL given.
  - `flush` — no source reference; `amount` is mL of water.
  - `oral` — a single food (CNF food_code or a custom label food, same
    mechanism as blend ingredients); `amount` + `unit` (g or mL, matching
    whatever basis the food was entered in — see §3.2); has its own
    `counts_as_fluid` flag (soup, yogurt, juice — same open judgment call
    already documented for blend ingredients, not a new problem).

  Every row also carries an **optional** `time` (a real time value, not a
  string — see §6.1) so the record can be sorted chronologically across
  *all* source types together: a tube feed at 0800 and breakfast at 0830
  belong in one sorted timeline, not two disconnected sections that happen
  to both mention "morning."

  UI presentation: **grouped by section header** ("Tube Feed" / "Food &
  Drink") for scannability, but backed by **one list and one aggregation**.
  Rationale (important — do not relitigate): a second, independently
  maintained list that gets "combined" into a third view is exactly the
  dual-source-of-truth pattern that caused the bug in §1 (batch volume and
  schedule volume, two numbers nobody reconciled). One list, always summed
  the same way, is the whole point of this rework.

- **Daily totals = Σ over intake-record rows.** Each row contributes its
  nutrients: blend rows via that blend's per-mL densities × amount;
  formula rows via `formulas.csv` per-mL values × amount (kcal, protein,
  free water via `free_water_per_mL`); flush rows contribute fluid only;
  oral rows via direct ingredient scaling (§3.1 — no density/volume
  concept needed, a single food scales the same way a blend ingredient
  does). Adequacy, per-kg, fluid ledger, and chart note all flow from this
  one sum.
- **No batch bookkeeping, no over-draw flag.** Dropped entirely per §6.2 —
  not "warn instead of block," genuinely removed as a concept. The only
  guard that remains is a real error: a blend with ingredients but no
  measured volume (÷0) is invalid and must say so.
- The nutrition math per blend/oral-food is exactly today's; only the
  aggregation layer is new. `calculate_profile()` (or its extracted core,
  §3.1) is the single place scaling happens — never duplicated inline.

### What this dissolves (do not rebuild these)

- The **mismatch rule / over-draw flag** question — moot, resolved in §6.2.
- The separate **"combined regimen" section** built in round 2 (formula +
  mL/day added to BTF) — superseded; a formula is just an intake-record row.
  Remove that section; its free-water-per-mL math moves into row
  aggregation.
- The standalone **flush schedule** in the banner — flushes become rows.
- The chart note's structure — it becomes the record read aloud
  chronologically, plus totals: the note now naturally reports **what was
  actually received**, per source, oral included.

---

## 3. Scope of changes

### 3.1 Backend (`src/`) — do this first, it's the foundation

- **Extract the ingredient-scaling core out of `calculate_profile()`.**
  Today, `calculate_profile()` does: (1) build ingredient table, (2) filter
  Nutrient_Amount to tracked codes, (3) merge, (4) scale by grams/100,
  (5) groupby+sum, (6) fold in custom foods, THEN wraps the result in a
  `NutrientProfile` whose density *properties* need `measured_volume_mL > 0`
  — and the function **early-returns an empty profile if volume is 0**,
  discarding steps 1–6 even though they don't actually need volume.

  Oral intake-record rows are single foods with **no batch/density
  concept** — there is no "volume" to measure for one banana. They still
  need steps 1–6 (grams × per-100g, correctly handling both CNF and custom
  foods). **Do not** work around the volume guard with a fake `1.0 mL`
  placeholder, and **do not** duplicate the merge/scale logic inline for
  oral rows — that recreates exactly the kind of divergent-second-copy bug
  this project has already hit once (see the historical `NUTRIENT_CODES`
  hardcoding note in `CONTEXT.md` if present, or the custom-food coverage
  fix from the previous round).

  Instead: factor steps 1–6 into a standalone function — e.g.
  `compute_nutrient_totals(ingredients, nutrient_amount_df, custom_foods=None) -> dict[str, float]`
  in `src/calculator.py` — that `calculate_profile()` calls internally
  (its public signature and behavior must not change), and that oral-row
  scaling calls **directly**, with no volume/density wrapper at all.

- **New aggregation function** (suggest `src/intake.py` or a function in
  `calculator.py`): takes the full list of intake-record rows (each
  resolved to its nutrient contribution — blend rows via
  `NutrientProfile` densities × amount, formula rows via `formulas.csv`,
  flush rows fluid-only, oral rows via `compute_nutrient_totals()`) →
  daily totals dict + fluid numbers (fluid-provided vs. free-water,
  per-source subtotals for the Results-tab breakdown in §3.4). Pure
  function, easily verified.
- Extend `scripts/verify_backend.py`: a stage with two blends of different
  densities + a formula row + flush rows + two oral rows (one CNF food by
  grams, one custom food by mL) → hand-checkable combined totals. Also
  assert `compute_nutrient_totals()` matches `calculate_profile()`'s
  `nutrient_totals` exactly for an equivalent single-ingredient case
  (proves the extraction didn't diverge).

### 3.2 Session state (app-level)

- `blends`: dict id → {name, ingredients: [...], measured_volume_mL}
  (ingredient rows keep their existing shape: food_code, description,
  grams/amount, unit, counts_as_fluid). `custom_foods` can stay global
  (negative codes are unique across blends and oral entries).
- `intake_log`: list of row dicts:
  `{time: time|None, source_type: "blend"|"formula"|"flush"|"oral",
    source_id, amount, unit, counts_as_fluid}`.
  (`unit` is `"mL"` for blend/formula/flush rows always; for `oral` rows it
  matches whatever basis the food was entered in — reuse the g/mL basis
  convention already established for custom foods, §3.3.)
- Migrate the "Load example recipe" button: one example blend + a small
  example intake log mixing tube and oral (e.g. 300+100 mL of the blend,
  one flush, one oral CNF food like "1 small banana" using the real
  household-measure entry, verified to exist in CNF — see §6.3) — chosen
  so totals are internally consistent and demonstrate both source families.

### 3.3 Build tab

- Blend selector at top: selectbox of blend names + "➕ New blend" +
  rename/delete. Everything currently in the Build tab (search,
  custom-food NFt-lookalike form, blend details, ingredient table) operates
  on the **selected** blend. Per-blend density mini-summary (kcal/mL,
  protein/mL) next to the selector helps orient. (Unchanged from v1 of this
  doc — blends are still recipe formulations, built here.)
- **The existing "Add ingredient" component (CNF search with food-group
  filter + household-measure-or-grams entry, and the custom-food
  NFt-lookalike form) must become reusable independent of "adding to the
  selected blend."** It needs a second call site: adding a single oral food
  to the intake record (§3.4). Refactor into a function/component
  parameterized by its destination (append to a blend's ingredient list vs.
  append one row to `intake_log`) rather than duplicating the search/entry
  UI. This is the same "one source of truth for scaling logic" discipline
  as §3.1, applied to the UI layer.
- **Both entry granularities must be offered for oral food, not just one**:
  the existing household-measure dropdown (which already includes
  size-qualified options like "1 small (15cm to 17.5cm long)" for
  banana — verified in CNF, see §6.3) AND the "Enter grams directly"
  checkbox override, exactly as already built for blend ingredients. No new
  precision-vs-convenience mechanism needed — the existing one already
  does this; just reuse it for oral entries too.

### 3.4 Banner ("Patient, Delivery & Targets" → rename its intake section)

- Weight + targets: unchanged.
- The old "Delivery" schedule input and v1 "feed log editor" are replaced
  by the **Intake Record**: a single editable list, grouped in display by
  section header ("Tube Feed" / "Food & Drink") but one underlying list
  (§2). Add-row UI:
  - "➕ Add tube feed" — time (optional picker, §6.1) + source dropdown
    (blend names + formula names + "Water flush") + volume mL.
  - "➕ Add food/drink" — opens an **`st.dialog`** (confirmed available in
    the installed Streamlit version) containing the reused
    search-or-custom-food component from §3.3, plus the `counts_as_fluid`
    toggle (pre-checked when the food is a CNF Beverages-group item or
    named "water"; otherwise unchecked, always overridable — same
    auto-default logic already used for blend ingredients). Submitting
    the dialog appends one `oral` row and closes it. (An inline expander
    is an acceptable fallback if `st.dialog` proves awkward in practice,
    but try the dialog first — it keeps the already-busy banner from
    growing another full search UI inline.)
  - Rows display chronologically (time-sorted; rows with no time sort
    last), each removable.
  - **Delivery method** (syringe/gravity/etc.) becomes a single free-choice
    field used only for chart-note wording — it no longer drives any math.
- **Always-visible summary line — nutrient totals, not a raw volume/mass
  roll-up.** Do NOT try to sum heterogeneous units (750 mL of blend + 45 g
  of banana is not a meaningful single number). Show e.g.:
  `"Today: ~1850 kcal | 92 g protein | 1400 mL fluid provided"` — the
  aggregated nutrient totals from §3.1, always unit-consistent.

### 3.5 Results tab

- Per-blend density panel (each blend's kcal/mL, protein/mL, free-water
  fraction + coverage) — densities are still the per-blend lens.
- Daily totals/adequacy/micro screen/per-kg/fluid ledger: computed from the
  intake-record aggregation (§3.1), oral rows included. Fluid provided =
  Σ(counts-as-fluid contributions, tube and oral alike, full-volume I&O
  convention, same as round 2) + flushes.
- **New: a per-source subtotal breakdown** (Tube Feed vs. Food & Drink vs.
  Total) — directly addresses the author's "I want combined numbers, but I
  still want to see the split" request from the design conversation. A
  small table: rows = {Tube Feed, Food & Drink, Total}, columns = the
  displayed macro/fluid nutrients.
- Comparator, flow test, Excel export: keep; export gains an Intake Record
  sheet (all rows, chronological) and per-blend sheets. Dilution what-if:
  keep, operating on the selected blend.
- Chart note: the record read aloud chronologically (tube and oral
  interleaved by time) + totals, e.g.:
  ```
  BTF via syringe: 0800 300 mL + 1200 100 mL Morning blend; 1500 350 mL
  Fridge batch; 2000 250 mL Peptamen 1.5; flushes 2×100 mL.
  Oral: 0830 1 small banana; 1030 125 mL apple juice.
  Provides ~X kcal, X g CHO, X g protein (x.x g/kg), X g fat.
  Fluid provided: ... Free water (CNF-estimated): ...
  ```

### 3.6 Docs (same session as implementation, separate commit)

- CONTEXT.md §1 app-flow + §9; BUSINESS_CASE.md §7 (features) and
  Appendix A5 (daily totals equation becomes the intake-record sum) — the
  docs currently describe the schedule-extrapolation model; they must not
  survive the rework unchanged. README.md Step 6 walkthrough.
- **BUSINESS_CASE.md's competitive-landscape scope note: explicitly NOT
  needed** — the author judged the oral-intake addition trivial enough not
  to warrant a scope-statement update. Do not add one unprompted.

---

## 4. Out of scope (v1 of the rework)

- **Batches spanning multiple days** (make Sunday, feed Mon–Wed). The
  record models one day. A batch drawn across days works fine for
  *charting a single day*; multi-day batch accounting (how much is left
  tomorrow) is a future feature. Note it in CONTEXT.md as roadmap.
- Saving/loading blends or days (Phase 7 JSON persistence) — pairs
  naturally with this model but is its own task.
- Prescribed-vs-received comparison (the spreadsheet's "% volume provided"
  concept). The record records received; a prescription field to compare
  against can come later if wanted.
- **"Recent/frequent foods" quick-add for oral entries** — a real usability
  win for repeat logging (e.g., the same breakfast most days), but it's an
  enhancement on top of a working search, not required for v1. Note as
  roadmap.
- Any registry/targets/pack changes.

## 5. Verification bar

Usual three scripts green after every commit
(`verify_backend.py` — extended per §3.1, `trace_calculation.py`,
`check_app_imports.py`), plus AppTest covering at minimum:

1. **The original bug case, re-verified with the flag removed**: one
   blend, batch 400 mL, log 3 rows × 400 mL of it → totals = density ×
   1200 mL, computed cleanly, **no error, no flag** (this is now normal
   usage — making a blend multiple times a day — not an anomaly).
2. One blend, batch 400, log 400 → totals = density × 400 exactly.
3. Two blends with different densities + formula row + flush rows + two
   oral rows (one CNF-by-grams, one custom-by-mL) → totals match hand
   arithmetic; chart note lists every row chronologically, tube and oral
   interleaved.
4. Blend add/rename/delete without losing other blends' ingredients or any
   intake-record rows referencing them.
5. `compute_nutrient_totals()` exactly matches an equivalent
   `calculate_profile()` call's `nutrient_totals` (the extraction in §3.1
   didn't diverge).
6. The household-measure size-qualified entry (e.g. "1 small banana")
   correctly resolves to its CNF gram weight in an oral row, and the
   "enter grams directly" override still works as an alternative for the
   same food.
7. A blend with ingredients but `measured_volume_mL == 0` produces a clear
   error/guard — the one case that's still genuinely invalid.
8. Example-recipe load produces an internally consistent day spanning both
   source families.

Commits per the repo's established discipline (green at every commit, no
push, trailer:)

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

Suggested split: (1) backend extraction + aggregation (§3.1) with extended
verify_backend; (2) session-state model + Build-tab reusable add-food
component (§3.2–3.3); (3) banner Intake Record editor incl. the oral
`st.dialog` (§3.4); (4) Results tab wiring incl. subtotal breakdown and
chart note (§3.5); (5) docs (§3.6). Each commit green per the bar above
before moving to the next.

---

## 6. Decisions (resolved 2026-07-17 — do not re-ask)

### 6.1 Row times: optional time picker, not free text

A picker (not free text) because it enables real chronological sorting
across tube and oral rows — the actual near-term need, not a hypothetical.
**Make it optional**: real logs have PRN doses, "overnight," or genuinely
unremembered times; a required field would invent false precision.
Unset-time rows sort last. Direction of migration risk was also a factor:
picker→display-as-text later is trivial; text→picker later means writing a
parser for whatever people actually typed. Starting with the picker is the
reversible choice.

### 6.2 Over-draw flag: removed entirely, not softened to a warning

Not "warn instead of block" — the concept is dropped. Reasoning: the flag
re-introduces the exact category of error this rework exists to fix. The
original bug treated the batch-volume number as something to *extrapolate
from*; the flag treated the same number as a stock ledger to *police*.
Both give measured volume a second job beyond its one designed purpose —
the density denominator (`CONTEXT.md` design commitment #2). Composition is
scale-free: a blend at 1.2 kcal/mL is 1.2 kcal/mL whether made once or
three times today. Logging 600 mL against a "400 mL blend" just means it
was made more than once — the ordinary case, not an anomaly — so a flag
here would fire hardest on completely normal use.

Vocabulary that falls out of this and should be used consistently in code/
comments/UI copy: **blend = formulation** (scale-free, what densities
belong to); **batch = one physical making of it**; **intake-record row =
what was actually given**, referencing a blend by name without needing to
know how many times it was made. The v1 flag conflated blend with batch.

The one guard that remains is a real invalidity, not a judgment call: a
blend with ingredients but no measured volume can't produce densities
(÷0) — that must still surface clearly.

### 6.3 Naming: "Intake Record," grouped into "Tube Feed" and "Food & Drink"

Clinical terminology check: in standard I&O (intake and output)
documentation, "intake" already formally includes tube feedings alongside
oral and IV fluids — it is not colloquially oral-only, that reading is
informal. "Tube Feed" is unambiguous for the EN-specific rows. So:

- **Overall section/data model name: "Intake Record."**
- **Display grouping (not separate data, not separate logs): "Tube Feed"**
  (blend/formula/flush rows) **and "Food & Drink"** (oral rows) as section
  headers within the one chronological list.
- Reject the two-separate-logs-plus-a-combined-view structure explicitly
  considered and rejected in favor of the single-list model — see §2's
  "Intake Record" bullet for the full reasoning (avoids recreating a
  dual-source-of-truth bug).
- "Blends" stays the term for the list of recipe formulations managed in
  the Build tab (unchanged from v1 of this doc).

### 6.4 Oral intake: full scope for v1, not deferred

Originally proposed as a future add-on; the author pushed for full scope
now after confirming there's no hard technical blocker. Verified before
finalizing this decision:
- CNF genuinely has size-qualified household measures (checked directly:
  "Banana, raw," Food_Code 1704, includes "1 small (15cm to 17.5cm long)"
  = 101 g, "1 medium" = 118 g, "1 large" = 136 g, etc.) — the
  precision-vs-convenience UI the author wanted already exists in the
  Build tab's ingredient-add flow and just needs reuse (§3.3), not new
  data or a new mechanism.
- Oral rows are architecturally *simpler* than blend rows — a single food
  needs no batch/density/volume abstraction, just direct ingredient
  scaling (§3.1), which the extraction step makes available cleanly.
- `st.dialog` is available in the installed Streamlit version, giving a
  clean UI slot for "add food/drink" without further crowding the banner.
- The `counts_as_fluid` ambiguity for foods like soup (already flagged as
  unsolved for blend ingredients — "even soup is dicey... no validated
  rule of thumb") extends to oral rows too. This is **not new scope**, just
  more instances of an already-accepted open judgment call, resolved the
  same way: a manual toggle, auto-defaulted where confident (CNF Beverages
  group, "water" in the name), always overridable.
- **Explicitly declined**: updating BUSINESS_CASE.md's competitive-scope
  language to reflect the addition of oral tracking — the author judged
  this not worth doing (see §3.6). Do not add it unprompted.
