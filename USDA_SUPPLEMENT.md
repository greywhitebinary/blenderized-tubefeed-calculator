# USDA SR Legacy Supplement — Design Proposal

**Status: awaiting the author's sign-off. No code has been written for this
feature. Everything below is a proposal to approve, amend, or reject —
per `HANDOFF.md`'s standing instruction that this is designed before it's
built.**

This document covers the three decisions HANDOFF.md flagged as expensive
to reverse, plus search behaviour, the `thinning_liquids.csv` ride-along,
the SR Legacy-vs-Foundation choice, effort, risk, and a small first slice
to test the design before committing to all of it. All numbers below were
measured directly against the files on disk during this review — none are
remembered or assumed. Where a decision needs clinical judgment, I've
flagged it as a question for you rather than making the call.

**tl;dr of the three decisions:**

| # | Decision | Recommendation |
|---|---|---|
| 1 | Where the derived table lives / its shape | A new **shared** source, `data/shared/usda_supplement/`, sibling to `data/packs/` — not nested inside `data/packs/canada/`. Plain CSV, ~1,600 rows or fewer, opt-in per pack. |
| 2 | Nutrient-code mapping | A small dedicated mapping CSV, keyed on the numeric codes both databases already share (see below — this is the pleasant surprise of this review). Verified by a hard assertion in `verify_backend.py`, not just a build script. |
| 3 | Provenance in the UI/report | Surface it in the food-search results, the ingredient table, the chart note, and Excel export. Do **not** touch the Results-tab comparator (out of scope, per your standing note). |

---

## 0. What I actually looked at

- `data/raw/usda/` is **69 MB** total, gitignored, confirmed via
  `git check-ignore -v` (matches the `.gitignore` line `data/raw/`).
  Streamlit Cloud only has what's committed — this can never be read at
  runtime, matching what HANDOFF.md already assumed.
  - SR Legacy (`FoodData_Central_sr_legacy_food_csv_2018-04/`): **38 MB**.
  - Foundation Foods (`FoodData_Central_foundation_food_csv_2026-04-30/`):
    **31 MB**.
- SR Legacy: `food.csv` has **7,793 foods** (one `data_type`:
  `sr_legacy_food` — this is a single flat list, not several data types
  mixed together). `food_nutrient.csv` has **644,126 rows**. `nutrient.csv`
  has 475 nutrient definitions (most irrelevant — amino acid breakdowns,
  isoflavones, etc. that neither pack tracks). `food_portion.csv` has
  14,450 household-measure rows.
- Foundation Foods: `food.csv` has **87,992 rows total**, but only **469**
  of them are `data_type == "foundation_food"` — the actual named,
  consumable foods. The other 87,523 rows are lab/QC bookkeeping
  (`sub_sample_food` 75,055, `market_acquisition` 7,577, `sample_food`
  4,079, `agricultural_acquisition` 810) — individual lab specimens and
  acquisition records behind each of the 469 real foods, not additional
  foods you could search for. This matters for decision 6 below.

---

## 1. Decision 1 — where the derived table lives, and its shape

### What "whole food" has to mean operationally

Appendix C's governing principle — whole foods are interchangeable across
databases, packaged foods are not — needs a mechanical filter, because
nobody is going to hand-classify 7,793 rows. I built one to see what it
actually produces, using three passes:

1. **Category filter.** SR Legacy's `food_category.csv` groups foods into
   28 categories (near-identical to CNF's own 23 `CNF_Food_Group`
   categories — same lineage, see decision 2). I kept the 13 that read as
   "whole or minimally-prepared food": Fruits and Fruit Juices,
   Vegetables, Legumes, Nuts and Seeds, Poultry, Beef, Pork, Lamb/Veal/
   Game, Finfish/Shellfish, Cereal Grains and Pasta, Dairy and Eggs,
   Spices and Herbs, Fats and Oils. That's **4,748 of 7,793 rows**.
   Excluded outright: Baked Products, Sweets, Fast Foods, Restaurant
   Foods, Soups/Sauces/Gravies, Snacks, Sausages and Luncheon Meats, Baby
   Foods, Breakfast Cereals, Meals/Entrees/Side Dishes, Beverages,
   American Indian/Alaska Native Foods (this last one is a real loss —
   see below).
2. **Keyword exclusion.** Even inside "whole food" categories, USDA
   carries plenty of processed variants: `canned`, `cured`, `smoked`,
   `breaded`, `imitation`, `fast food`, `luncheon`, `sausage`, `hot dog`,
   `bologna`. Excluding rows matching those cut it to **4,180 rows**.
3. **De-duplication against CNF, via a real cross-reference I didn't
   expect to find.** CNF's own `Food_Name.csv` has a `USDA_NDB_Code`
   column — **4,798 of CNF's 5,993 foods (80%)** carry one. This is
   Health Canada's own paper trail: CNF was historically built by
   adapting USDA's nutrient database, and this column records which
   USDA food each CNF row was adapted from. Cross-referencing those
   codes against SR Legacy's own `NDB_number` (in `sr_legacy_food.csv`)
   gets a clean match for **4,448 of CNF's 4,619 distinct USDA-derived
   codes (96%)** — a real join, not fuzzy matching. Removing SR Legacy
   rows that CNF already has via this link drops the candidate list to
   **1,628 rows.**

### The uncomfortable finding: what's left skews toward noise, not the stated goal

Of those 1,628 "genuinely new" rows, **1,074 (66%) are Beef, Lamb, Veal,
or Pork** — and almost all of that is USDA's extremely fine-grained
butchery nomenclature: "Beef, chuck, shoulder clod, shoulder top and
center steaks, separable lean and fat, trimmed to 0" diced fat, select,
raw" as a *distinct row* from a dozen sibling cuts. For a BTF recipe, an
RD blending ground beef doesn't need to distinguish a top round steak
from a bottom round steak — both are "beef, cooked" for this purpose.
This isn't a defect in the filter so much as a mismatch between USDA's
retail-cut taxonomy and what this tool actually needs.

More importantly: **BUSINESS_CASE.md §8's own motivating examples
(plantain, cassava, specific ethnic foods) are mostly already in CNF
2026.** I checked directly:

| Search term | Hits in USDA SR Legacy | Hits in CNF 2026 |
|---|---|---|
| plantain | 7 | 6 |
| cassava | 2 | 2 |
| okra | 6 | 6 |
| lentil | 9 | 12 |
| yam | 6 | 4 |
| taro | 13 | 13 |
| breadfruit | 4 | 4 |
| tamarind | 3 | 1 |
| jackfruit | 2 | 2 |
| bok choy | **0** | 2 |
| egusi | 0 | 0 |
| dal | 0 | 0 |

CNF already matches or beats USDA on almost every named example from the
business case. Bok choy is USDA-*absent*, not USDA-supplied. Egusi and
"dal" (as a named dish/ingredient, distinct from generic lentils) are in
**neither** database — the USDA supplement would not fix those; only
custom food entry does. I'd rather tell you this now than have the
supplement ship and under-deliver against the exact claim used to justify
it. The supplement still has real value (see below), just a narrower and
more specific one than "fixes the ethnic-food gap" — it's closer to "adds
redundancy and a long tail of USDA-specific whole foods CNF happens not
to carry," which is real but more modest.

Also worth flagging: even after the keyword filter, at least one clearly
branded product slipped through — "Yogurt, Greek, Blueberry, CHOBANI" is
in the 1,628-row candidate list. Any mechanical filter on free-text
descriptions will have this kind of leak, which is exactly Appendix C's
"packaged foods are different" line becoming a maintenance burden rather
than a one-time decision. I don't think this is fixable to zero with more
regex; it needs a human pass either at build time or as an easy
after-the-fact "remove this row" edit (see below — this is why plain CSV
matters).

### Recommendation for the filter and the resulting size

**Two honest options, your call:**

- **(a) Ship the ~1,628-row automated-filter list as-is, then let you
  delete rows you don't want** (it's a CSV — deleting a row is a text
  edit, same philosophy as every other reference file in this project).
  Fast to build, noisy, but nothing is lost by shipping it and pruning
  later.
- **(b) Hand-curate a much smaller list** (my guess: 100-300 rows) aimed
  specifically at real gaps — foods you or a pilot RD have actually
  looked for and not found in CNF — rather than every USDA row that
  survives a category filter. Slower to build (needs a real "what's
  actually missing" pass, which the smallest-slice section below
  proposes testing cheaply first), but matches the tool's actual stated
  purpose ("your kitchen, your food, your culture") much more precisely,
  and avoids drowning a search box in a dozen near-identical beef cuts.

My recommendation is **(b)**, informed by the numbers above: the
automated filter's marginal rows are dominated by content this tool has
no real use for, and the real gaps (per my spot-check) are narrower and
different in character than "any whole food in a plausible category."
But this is a product-scope call as much as a technical one, so it's
listed as an open question at the end rather than something I've decided
for you.

### Where it lives: shared source, not nested in the Canada pack

Appendix C's acceptance criterion for a country pack is "new CSVs under
`data/packs/<pack>/`, zero Python changes" — and a pack's files
(`nutrients.csv`, `formulas.csv`, `thinning_liquids.csv`) are all
inherently country-specific (what's on *this* country's label, *this*
country's formulas). The USDA whole-food supplement is the opposite by
construction — its entire justification is that it's **not**
country-specific. Nesting it inside `data/packs/canada/` would say the
opposite of what the feature means, and would leave a future US or UK
pack either duplicating the file or reaching across another pack's
directory (which the pack design deliberately avoids elsewhere).

**Recommendation:** a new top-level directory, sibling to `data/packs/`:

```
data/shared/
  usda_supplement/
    foods.csv          # the filtered/curated whole-food table
    nutrient_map.csv   # decision 2's mapping table
    source_notes.md     # what was filtered, when, against which USDA release (plain text, not code)
```

Each pack **opts in** via a small addition to Appendix C's already-planned
per-pack `config.yaml` (documented there as a future deferral for kJ/salt
units — this just adds one more key to that same planned file, not a new
mechanism):

```yaml
# data/packs/canada/config.yaml
usda_supplement: true
```

This keeps the acceptance criterion intact — a future pack that doesn't
set this flag gets CNF-only-equivalent search behavior with zero code
branching, and the flag is a one-line, reviewable statement of intent
rather than an implicit "every pack automatically gets this."

### Format: CSV, not parquet

At either size (1,628 rows or a curated few hundred), this table is
roughly **150-350 KB as CSV** — small enough that parquet's ~20× load
speedup (real for CNF's 565k-row table) doesn't matter here; the whole
file loads and filters in well under the time a human notices. CSV also:

- Needs no `.gitignore` change (`*.parquet` is currently gitignored
  project-wide — a parquet artifact here would need an explicit
  exception carved into that pattern, e.g. `!data/shared/**/*.parquet`,
  which is one more thing to get right and one more thing to explain to
  a future contributor).
- Matches every other reference file's "diff it in a PR, edit it by
  hand" convention (`nutrients.csv`, `formulas.csv`,
  `thinning_liquids.csv`) — this project's whole design philosophy is
  human-editable reference data, and a compiled binary format works
  against a human wanting to delete the CHOBANI row.

If the row count later grows by an order of magnitude (e.g. Foundation
Foods gets added, or a future pack wants a much bigger supplement),
parquet becomes worth revisiting — not now.

---

## 2. Decision 2 — nutrient-code mapping

### The good news, verified directly

CNF keys nutrients by a numeric `Nutrient_Code` (307 = sodium) —
deliberately, because CNF's own `Nutrient_Name.csv` has the literal
string `"NA"` in sodium's `Tagname`/`Nutrient_Symbol` columns, which
pandas reads as missing (see `CONTEXT.md` §11). USDA has a different,
larger numeric ID (`nutrient_id`, e.g. 1093 for sodium, the join key into
`food_nutrient.csv`) — **but it also carries a `nutrient_nbr` column,
and for every one of the 19 nutrients tracked in
`data/packs/canada/nutrients.csv`, that number matches CNF's
`Nutrient_Code` exactly:**

| Canada pack nutrient | CNF `code` | USDA `nutrient_id` | USDA `nutrient_nbr` | Units match? |
|---|---|---|---|---|
| energy_kcal | 208 | 1008 | 208 | kcal = KCAL ✓ |
| protein_g | 203 | 1003 | 203 | g = G ✓ |
| fat_g | 204 | 1004 | 204 | g = G ✓ |
| carbohydrate_g | 205 | 1005 | 205 | g = G ✓ |
| fibre_g | 291 | 1079 | 291 | g = G ✓ |
| sugars_g | 269 | 2000 | 269 | g = G ✓ |
| saturated_fat_g | 606 | 1258 | 606 | g = G ✓ |
| trans_fat_g | 605 | 1257 | 605 | g = G ✓ |
| cholesterol_mg | 601 | 1253 | 601 | mg = MG ✓ |
| sodium_mg | 307 | 1093 | 307 | mg = MG ✓ |
| potassium_mg | 306 | 1092 | 306 | mg = MG ✓ |
| calcium_mg | 301 | 1087 | 301 | mg = MG ✓ |
| iron_mg | 303 | 1089 | 303 | mg = MG ✓ |
| magnesium_mg | 304 | 1090 | 304 | mg = MG ✓ |
| phosphorus_mg | 305 | 1091 | 305 | mg = MG ✓ |
| zinc_mg | 309 | 1095 | 309 | mg = MG ✓ |
| vitamin_d_ug | 328 | 1114 | 328 | µg = UG ✓ |
| vitamin_b12_ug | 418 | 1178 | 418 | µg = UG ✓ |
| water_g | 255 | 1051 | 255 | g = G ✓ |

Zero divergences across all 19 tracked nutrients, both in code and in
unit. This isn't a coincidence — CNF was built by adapting USDA's
numbering scheme (the same `USDA_NDB_Code` lineage from decision 1), so
the two systems share a common ancestor for the core nutrient IDs.

**This is good news, but it is exactly the kind of "looks safe, so
nobody double-checks it" situation the task brief warns about.** The
match is real for these 19 nutrients today. It is not a proof that it
holds for any future addition to the registry, and I'd actively avoid
writing code that *assumes* `usda_nutrient_nbr == canada_code` by
construction — that's the shortcut that turns into next year's silent
sodium bug. The mapping should be an **explicit, committed table**, not
an inferred rule, even though right now every row of that table would
read "yes, they match."

**One unit trap that doesn't bite today but will if the registry grows:**
USDA carries vitamin A and vitamin D in *two* forms each — an old
International Units (IU) column and a modern mass-based column (vitamin
A as µg RAE, nutrient_nbr 320; vitamin D as µg, nutrient_nbr 328 — the
one already in the table above). Canada's registry doesn't track vitamin
A at all (Health Canada dropped it from the label in 2022 — Appendix C),
so this doesn't affect the current 19 nutrients. But if a future pack
(e.g. a US pack, which *would* want vitamin A) is built against this
same supplement, whoever writes that mapping row has two vitamin-A rows
to choose from and picking the IU one would silently produce numbers
off by roughly an order of magnitude. Documenting this now, next to the
sodium-`"NA"` gotcha in `CONTEXT.md` §11, is cheap insurance.

### Mapping file: format and location

`data/shared/usda_supplement/nutrient_map.csv`:

```csv
nutrient_name,usda_nutrient_id,usda_nutrient_nbr,usda_unit,canada_code,canada_unit,verified,notes
energy_kcal,1008,208,KCAL,208,kcal,2026-07-30,exact match
sodium_mg,1093,307,MG,307,mg,2026-07-30,exact match; CNF's own Tagname for this row is the literal string "NA" -- always join by numeric code, never Tagname
vitamin_d_ug,1114,328,UG,328,µg,2026-07-30,USDA also has an IU form (nutrient_id 1110, nutrient_nbr 324) -- do not use it
...
```

Keyed on `nutrient_name` (matching the internal name already used
throughout `src/nutrients.py`, `src/calculator.py`, etc.), not on the
country pack's registry file itself — this keeps the mapping a property
of "how USDA data gets translated into this project's internal nutrient
vocabulary," independent of which pack is asking, matching how the
supplement itself is a shared, not per-pack, resource.

### Verification — the part that actually matters

A build script alone isn't enough; the brief specifically asks how a
wrong mapping gets *caught*, not just produced. Two concrete mechanisms:

1. **A hard assertion, added as a new stage in `scripts/verify_backend.py`**
   (following that script's existing pattern of numbered stages), not a
   one-off check that only runs when someone remembers to run it:
   for every row in `nutrient_map.csv`, assert
   `usda_nutrient_nbr == canada_code` (or, if a future pack's registry
   legitimately needs the mapping to diverge, assert that the *divergence
   itself* is documented in the `notes` column — i.e., fail loudly on an
   *silent* mismatch, not on a documented one). This makes "someone added
   a 20th nutrient to the registry and didn't check USDA's number" a red
   CI run, not a quiet wrong value in a clinical table.
2. **A spot-check against known foods, using real values, not
   invented ones.** During this review I already confirmed nutrient
   *coverage* (not correctness, that needs a second pass) for these 19
   codes across all 7,793 SR Legacy rows:

   | Nutrient | % of SR Legacy rows with a value |
   |---|---|
   | energy, protein, fat, carb, water | 100% |
   | sodium | 98.9% |
   | iron | 99.0% |
   | calcium | 98.9% |
   | saturated fat | 95.6% |
   | potassium | 96.4% |
   | phosphorus | 95.8% |
   | magnesium | 95.2% |
   | zinc | 95.0% |
   | cholesterol | 94.9% |
   | vitamin B12 | 91.3% |
   | fibre | 92.8% |
   | sugars | 77.1% |
   | vitamin D | 66.5% |
   | trans fat | 53.6% |

   These gaps are the same shape as CNF's own known gaps (the project
   already notes CNF's vitamin D coverage is ~88%), and the existing
   zero-coverage-hiding machinery in `report.py` already handles "0/N
   ingredients supplied a value" correctly with no code change needed —
   this is a reassuring finding, not a new problem. The spot-check I'd
   propose *before* trusting the mapping for real: pick 3-5 foods with an
   obvious CNF near-equivalent (e.g., "Chicken, broilers or fryers,
   breast, meat only, raw" in USDA vs. CNF's own raw chicken breast
   entry) and confirm sodium/potassium/energy land in the same
   ballpark — not identical (different sourcing, different year), but
   not off by a factor of 10 or 1000, which is what a unit or
   code-mapping error looks like. This is a data-QA sanity check, not a
   clinical judgment call, so it's a reasonable thing to script and run
   once as part of the build step, then keep as a documented worked
   example (in the style of `scripts/trace_calculation.py`) rather than
   asserting a clinical target.

---

## 3. Decision 3 — provenance in the UI and report

An RD needs to know when a number came from USDA rather than CNF — the
project's own "no black boxes" identity (`BUSINESS_CASE.md` §5) and
Appendix A11's key assumption ("CNF/USDA values are accurate for the
foods used") both depend on that visibility existing somewhere, not just
being true in the abstract.

**One note on an apparent conflict:** `BUSINESS_CASE.md` §8 currently
says *"The user sees one unified search — they don't need to know which
database it came from."* I'm treating that as describing the *search
box* (one text field, one flow — not two separate search UIs to learn),
not as a instruction to hide provenance from the resulting ingredient.
Those aren't the same claim, and I think the clinical requirement (this
review's brief, and the project's own "no black boxes" framing) should
win where they'd otherwise conflict — but flagging this explicitly since
it's a reinterpretation of existing wording, not a clean continuation of
it, and you may want `BUSINESS_CASE.md` §8 reworded once you've ruled on
it.

**Where provenance surfaces (all additive — no layout change):**

- **Food search results** (`render_add_food_ui()` in
  `app/streamlit_app.py`, the `st.selectbox(f"Found {len(matches)}
  foods", food_options)` list). CNF options already render as
  `"{description}  [{food_code}]"`. USDA fallback options get the same
  treatment with a visible tag: `"{description}  [USDA SR Legacy — {fdc_id}]"`
  — one string-formatting change, no new widget.
- **The ingredient table.** Each blend's ingredient editor already shows
  description/grams/counts-as-fluid per row; add one more column,
  `Source` (CNF / USDA SR Legacy / Custom), populated from the new
  `Ingredient.source` field (see decision 4). A column addition to an
  existing `st.data_editor`/table, not a new section.
- **The adequacy table area.** Not a new report *column* (per-nutrient
  coverage is source-agnostic — it already just counts "did an ingredient
  supply a value," regardless of which database), but a one-line caption
  under the table, in the same place the existing "N/M ingredients"
  footnote already lives: *"This recipe includes 2 ingredient(s) from the
  USDA SR Legacy (2018) supplement — see the ingredient table for
  which."* Shown only when count > 0, same convention as the existing
  zero-coverage footnote.
- **The chart note.** One trailing clause, matching its existing
  bracketed-piece-omitted-when-absent convention: *"(2 ingredients
  sourced from USDA SR Legacy, not CNF)"* — omitted entirely on an
  all-CNF day.
- **Excel export.** Add `Source` to each blend's ingredient sheet — same
  column as the ingredient table above, free once that field exists.
- **Explicitly not touched: the Results-tab comparator.** You've flagged
  that table as a design you're unhappy with but haven't specified a fix
  for (`HANDOFF.md`). I'm not proposing anything there, and provenance
  doesn't need to live there anyway — the comparator is about commercial
  formulas, not recipe ingredients.

---

## 4. Search behaviour

**Trigger: USDA appears only when CNF's search for that exact term
returns zero matches** — the simplest reading of `BUSINESS_CASE.md` §8's
"checks CNF first, then USDA for foods not found," and the safest given
what decision 1 found: a supplement with heavy overlap against CNF (96%
of CNF's own USDA-derived foods have a direct match) would, if shown
unconditionally or "always, ranked below," mostly clutter the picker
with near-duplicates of what CNF already offers. The narrower trigger
also matches "additive, minimal" — it's a single added `if len(matches)
== 0:` branch in the existing search block of `render_add_food_ui()`,
not a merged/re-ranked result set.

**A real technical wrinkle that needs a `src/` change, flagged
explicitly:** `Ingredient` (`src/models.py`) currently has one field,
`food_code: int`, that both identifies the food *and* implicitly says
"look this up in CNF's `Nutrient_Amount` table." Two databases means two
lookup tables, and CNF's Food_Codes (roughly 1-10,000) are not guaranteed
to avoid colliding with USDA's `fdc_id`s if both are used as a bare int
in the same field. The clean fix is a new field, `source: str = "cnf"`
(values `"cnf"` / `"usda"` / already-existing negative codes for
`"custom"`), and `_scale_ingredients()` in `src/calculator.py` — the one
function every nutrient total flows through — needs to branch on it:
CNF-sourced ingredients merge against `Nutrient_Amount` as today,
USDA-sourced ingredients merge against the new supplement table via
`nutrient_map.csv`, then both totals combine exactly as custom-food
totals already do today. **This is a real, necessary edit to the
"complete and verified" backend** (`.clinerules` §2), not something that
can be bolted on purely in `app/streamlit_app.py` — flagging it now so
it isn't a surprise mid-implementation, and so you can decide whether
you want to review that specific diff closely given the backend's
otherwise-hands-off status.

**Household measures (recommend cutting for v1, note the trade-off):**
CNF foods get a "1 small banana → 101 g" household-measure dropdown via
`Measure_Weight_Conversion.csv`. USDA's `food_portion.csv` (14,450 rows,
same shape: `fdc_id`, `portion_description`, `gram_weight`) could support
the same experience for the supplement, but building and wiring a
second, parallel measure-lookup table is extra work for a feature that
only serves the fallback path (searches with zero CNF results are
already the minority case). Recommend v1 ships USDA-sourced foods as
grams-only entry (same "Enter grams directly" checkbox already in the
UI, just without the shortcut above it), and revisit household measures
for the supplement only if pilot feedback says it's missed.

---

## 5. `thinning_liquids.csv` pack-awareness — the ride-along

`_load_thinning_liquids()` (`app/streamlit_app.py:106-127`) is the last
loader still reading a hardcoded `canada` path — `_load_commercial_formulas()`
in `src/calculator.py` already takes `pack: str = DEFAULT_PACK`, matching
`load_registry()`'s idiom. This is unrelated to where USDA data lives —
it's a pre-existing gap in the *Canada* pack's own plumbing — but it's
genuinely free to fix in the same PR: add a `pack: str = DEFAULT_PACK`
parameter to `_load_thinning_liquids()`, mirroring the formulas loader's
already-established pattern almost line for line. No design decision
needed here; it's a ~10-line diff, inert until a second pack exists
either way, and bundling it avoids a second small PR later for a change
this trivial.

---

## 6. SR Legacy (2018) vs. Foundation Foods (2026)

**Recommendation: SR Legacy only, for v1.**

- **SR Legacy**: 7,793 named foods, one flat consumable list, complete
  macro coverage, broad category spread (Beef 954, Vegetables 814, Baked
  517, Fruits 355, etc. — see decision 1's table). This is the dataset
  the entire filter/mapping analysis above was built against.
- **Foundation Foods**: only **469** of its 87,992 rows are actual named,
  searchable foods (`data_type == "foundation_food"`) — the rest is lab
  methodology bookkeeping (which specific physical sample was tested,
  by which lab, on which date) that sits *behind* those 469 foods, not
  additional foods. 469 rows is too narrow to move the needle on
  anything this supplement is trying to do — you'd get very precise,
  very recent data for a small, essentially arbitrary handful of foods.

**The clinical trade-off, for your judgment:** SR Legacy is frozen at
2018 — an ingredient whose real-world nutrient profile shifted since
then (reformulation, breeding changes, updated lab methods) won't be
reflected. This matters far less here than it would for a packaged food,
*because* the filter in decision 1 is specifically steering away from
packaged/fortified foods and toward things like raw or simply-prepared
whole foods, whose nutrient profile is comparatively stable over
time — a raw banana's potassium content in 2018 is a reasonable proxy for
2026's. But "comparatively stable" isn't "provably unchanged," and if any
residual packaged-adjacent rows survive the filter (the CHOBANI yogurt
example from decision 1 is exactly this case), the 2018 freeze applies to
them at full force — one more reason to lean toward the narrower,
curated option in decision 1 rather than the broad automated list.

**A future option, not now:** once real gaps surface from pilot use (a
specific food missing from both CNF and SR Legacy), it's worth checking
whether that one food happens to be in Foundation's 469 — but building
general infrastructure around a 469-row dataset isn't worth it today.

---

## 7. Scope and effort

Three buckets, roughly in the order the work has to happen:

1. **Build the data artifact** (`data/shared/usda_supplement/foods.csv` +
   `nutrient_map.csv`): filtering (category + keyword + NDB dedup, all
   scripted, all reproducible), the verification stage in
   `verify_backend.py`, and — if you choose option (b) from decision 1 —
   a hand-curation pass. **~1 day** for option (a) (ship the automated
   1,628-row filter and prune later); **~2-3 days** for option (b)
   (curate down to a smaller, higher-precision list), most of that being
   your own review time, not build time.
2. **Wire it into search**: the `Ingredient.source` field, the
   `_scale_ingredients()` branch to merge against two lookup tables, the
   CNF-first/USDA-fallback trigger in `render_add_food_ui()`, negative/
   distinct code-space handling. This is the one piece that touches the
   "complete and verified" backend genuinely, not cosmetically.
   **~1-2 days**, plus `verify_backend.py` extension and an `AppTest`
   script per this project's existing UI-verification convention.
3. **Surface provenance**: the five additive surface points in decision
   3 (search label, ingredient-table column, adequacy footnote, chart
   note clause, Excel column). **~0.5 day** — all small, independent,
   easy to verify one at a time.

**Total: roughly 3-5 focused days**, most of the range driven by how much
hand-curation decision 1 gets.

**What to cut first if time is short, in order:**

1. Household measures for USDA foods (decision 4) — grams-only entry is
   a real but minor UX asymmetry, not a correctness issue.
2. The NDB-dedup refinement in decision 1 — a coarser category+keyword
   filter alone still works, just leaves more CNF-redundant rows in the
   picker (which the zero-CNF-match trigger already limits exposure to).
3. Foundation Foods entirely — already recommended to skip for v1
   regardless of time pressure (decision 6), not really a "cut," a "no."
4. **Do not cut**: the `verify_backend.py` mapping assertion. It's the
   cheapest item in the whole plan and it's the one thing standing
   between a code-review pass and a silently wrong sodium value.

---

## 8. What could go wrong

- **A nutrient mapping error that doesn't error.** This is the scenario
  the brief specifically warns about, and it's real: nothing in pandas
  or Streamlit will complain if `nutrient_map.csv` points sodium at the
  wrong `nutrient_id` — an RD just sees a plausible-looking wrong number
  in a clinical table. Mitigated by the hard assertion + spot-check in
  decision 2, but only if that verification step is actually built
  alongside the data, not deferred.
- **Food-code collisions** between CNF's `Food_Code` and USDA's `fdc_id`
  if the `Ingredient.source` field isn't added and code just reuses the
  bare-int `food_code` field to mean two different things depending on
  context. Flagged explicitly in decision 4 as a required backend change.
- **Search-result clutter from redundancy.** My own numbers show 96% of
  CNF's USDA-derived foods have a direct SR Legacy match — an
  unconditional or "always ranked below" fallback would mostly show
  RDs foods they already have under a slightly different name. Mitigated
  by the strict zero-CNF-match trigger.
- **Overpromising the cultural-food story.** The original motivating
  examples (plantain, cassava, etc.) are mostly already in CNF — see
  decision 1. If this supplement gets pitched publicly as "now your
  family's cultural foods are covered," that's not quite what the
  numbers support; the honest framing is narrower (a long tail of
  USDA-specific whole foods, plus redundancy/resilience), and I'd rather
  flag that now than have it surface during a pilot RD's first real use.
- **Coverage gaps** (vitamin D 66.5%, trans fat 53.6% of SR Legacy rows)
  causing more zero-coverage-hidden rows on a recipe that leans on
  USDA ingredients. Not a bug — the existing `report.py` machinery
  already handles this — but worth flagging so it isn't mistaken for one
  during testing.

---

## 9. The smallest slice to prove the design first

Before building the full filter pipeline or touching `_scale_ingredients()`,
the cheapest way to test the two riskiest assumptions (the mapping is
actually correct, and the supplement actually fills real gaps) is:

1. Pick 15-20 real foods — ideally ones you or a pilot RD have actually
   gone looking for, not ones I pick. Use the business-case examples as
   a starting point, since I've already shown several of them aren't
   real gaps (plantain, cassava, okra, yam, taro are already in CNF) —
   this step would tell you *which* of your actual candidates are
   genuine gaps before any filter-building happens.
2. For each one that's genuinely missing from CNF, pull it from SR
   Legacy by hand, map its 19 tracked-nutrient values through the
   mapping table above, and compare 2-3 values (sodium, potassium,
   energy are good choices — high clinical relevance, easy to sanity-
   check against a public reference) against what you'd expect from
   clinical experience or a quick cross-check with a similar CNF food.
3. If that holds up, the filter-and-build work in bucket 1 above is
   worth doing at full scale. If it doesn't, you've caught it having
   spent a few hours, not several days.

This also directly answers decision 1's open question — after step 1,
you'll know from real candidates whether the automated ~1,600-row filter
is worth building at all, or whether a much smaller hand-picked list
serves the actual need better.

---

## 10. Questions that need your ruling (not mine to answer)

1. **Filter scope for decision 1**: automated ~1,628-row filtered list
   (option a) vs. a smaller hand-curated list targeting real gaps
   (option b, my recommendation)? The smallest-slice exercise in §9
   should inform this directly.
2. **Do you accept the reframed cultural-food value proposition** — a
   long tail of USDA-specific whole foods and redundancy, rather than
   "fixes the ethnic-food gap" as originally framed in `BUSINESS_CASE.md`
   §8 — or would you rather that section's language change to match?
3. **The §8 "one unified search... they don't need to know which
   database" line** — do you agree with my reading that provenance
   should still surface per-ingredient even though that sentence reads
   as "don't show it," or would you rather keep search results
   database-blind and only reveal source somewhere else (e.g. only in
   the Excel export, never in the live UI)?
4. **Is the `data/shared/` top-level directory (sibling to
   `data/packs/`) the right home**, or would you rather it lived
   somewhere else entirely (e.g. under `data/` directly, or genuinely
   nested inside `canada/` despite the cross-country argument above, if
   you don't expect a second pack soon enough for the distinction to
   matter in practice)?
5. **Whether the American Indian/Alaska Native Foods category** (165 SR
   Legacy rows, excluded from the whole-food-category filter in decision
   1 because it doesn't map cleanly to a "prep style" the way the other
   12 do) should be reconsidered — I excluded it for lack of a clean
   rule, not because I looked closely at what's in it, and it may
   contain exactly the kind of foods this supplement is meant to add.
