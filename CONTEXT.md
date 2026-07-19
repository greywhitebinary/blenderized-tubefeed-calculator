# Blenderized Tube Feed Calculator — Project Context

> This file is the single source of truth for this project.
> It is written for two audiences: (1) the human author/learner, and
> (2) any AI coding agent picking up the project mid-stream.
> Update it whenever the plan, stack, or status changes.

---

## 1. Project goal

A clinical nutrition tool that **characterizes a real, working
blenderized tube-feed (BTF) recipe** — one already known to flow through
the tube because someone is living on it — and helps navigate changes
to it. The full business case, market analysis, and methodology are in
`BUSINESS_CASE.md` (the Week 1 competition deliverable).

**App flow — "start with the blender":**

1. **Build tab — blends** — a blend selector (new/rename/delete) over
   an open-ended list of recipe formulations; search CNF or USDA
   supplement or add a custom food from a nutrition facts label (g or
   mL basis); enter grams (or mL) per ingredient and measured final
   volume for the selected blend. No separate "added water" field —
   water is an ordinary ingredient, flagged "counts as fluid" like any
   other liquid. A blend is scale-free (a *formulation*) — it doesn't
   know or care how many times it gets made; see the Intake Record
   below for that.
2. **Intake Record (banner)** — replaces the old delivery-schedule
   input. One chronological list of rows — tube feed (blend / commercial
   formula / water flush) and oral food/drink — each with an optional
   time and an amount; displayed grouped under "Tube Feed" and
   "Food & Drink" headers but backed by one list. Daily totals are a
   **direct sum over these rows** — never an extrapolation of a batch
   volume against a schedule (see the ⚠️ KNOWN ISSUE entry in §9, now
   resolved, for the bug this replaced), and there is **no over-draw
   flag** of any kind — a blend's density is scale-free, so logging a
   blend multiple times a day is normal usage, not an anomaly. (Pump
   delivery is not offered in the UI — AHS: almost never used for BTF;
   the delivery method is recorded only as free-text chart-note
   wording.) See `FEED_LOG_REWORK.md` for the full design rationale.
3. **Targets (optional)** — RD enters kcal/day, protein g/day, fluid
   mL/day they already know. Always blank until entered — no
   population defaults. No assessment page, no energy equations in the
   app (those are documented in `BUSINESS_CASE.md` Appendix B as
   reference); an optional patient weight adds a DISPLAY-only per-kg
   row, never a target.
4. **Results (live)** — per-blend densities (+ coverage), daily totals
   from the Intake Record, adequacy vs targets (with a fluids ledger
   driving the fluid row), a per-source (Tube Feed vs. Food & Drink vs.
   Total) breakdown, commercial formula comparator (at an independent
   what-if volume), dilution what-if, flow-test documentation,
   copy-pasteable chart note (the Intake Record read aloud
   chronologically, tube and oral interleaved), live recipe adjustment.

**Design commitments:**

1. **Per-mL is the primary lens, not per-recipe.** The outputs that
   matter are densities — kcal/mL, protein/mL, free-water fraction.
   Totals matter only once multiplied by actual daily mL intake.
2. **Final blend volume is a measured input, not computed.** Blending,
   air, and rinse water make volume incalculable from ingredient
   weights — but the user *knows* it (they poured it into a container).
   Ingredients give nutrient totals; measured volume gives the
   denominator.
3. **Live recipe adjustment — the tool IS the what-if.** Every edit
   (add/remove/swap ingredients, change amounts, swap water for juice
   or broth) updates everything instantly. The RD iterates: tweak →
   check numbers → drip test → tweak again. The tool handles the
   numbers side; the RD handles the physical flow side. **Resolved
   2026-07-17 (round-2 clinical feedback):** this — not the Dilution
   What-If slider — is the core interaction; the Dilution What-If is a
   secondary recipe-development aid ("if we must thin, what does it
   cost in density") that previews a hypothetical without touching the
   real recipe. See the §9 entry below and `BUSINESS_CASE.md` §7 item 6
   / Appendix A8 for the full resolution of the long-pinned
   "dilution-slider vs. live recipe adjustment" question.

**The sweet spot — thin enough to flow, dense enough to nourish:**
Every BTF recipe lives in a tension between two physical realities:
thin enough to flow through the tube (checked by the RD with a drip
test — no app can measure viscosity) and dense enough to nourish
(calculated by the tool as kcal/mL). BTF recipes should be at most as
thick as Resource 2.0. The tool shows the nutritional numbers while
the RD checks the physical flow. See `BUSINESS_CASE.md` §2 for the
full description.

**Thinning liquids aren't just water.** Water (pure dilution), apple
juice (adds calories), broth (adds sodium + protein), milk (adds
calories + protein + calcium), oil (adds fat). The AHS caregiver
handbook confirms: *"If your child needs more calories add: milk,
juice, oil, formula"* vs. *"If your child does not need more calories
add: cooking liquid, water."* The tool shows the nutritional impact
of each thinning choice.

**Design philosophy — "no black boxes":** Inspired by the EN spreadsheet
by Hui Jun Chew, RD (North York General Hospital, Toronto). Every
calculation visible, every assumption documented, reference data
human-editable, RD clinical judgment always the final authority. See
`BUSINESS_CASE.md` §5 and Appendix A for the full philosophy and
equations.

**Internationalization — "built for Canada, designed for the world":**
The calculator engine is country-agnostic. Each country is a "data pack"
(nutrient database + targets + formula profiles + units config). Canada
first (CNF 2026 + USDA SR Legacy supplement), then US, UK, Australia.
See `BUSINESS_CASE.md` Appendix C for the data pack specification.

**Out of scope, permanently (fixed caution notes, never computed):**
osmolality (a footnote for this population, not a headline), viscosity /
tube-flow behaviour, nutrient losses from blending and holding, food
safety. **Identity from day one: "for RD use, estimates only."**

**Data:** Built on the **Canadian Nutrient File (CNF) 2026 edition** —
a public Government of Canada dataset of ~5,993 foods × ~173 nutrients,
all values expressed **per 100 g of edible food** — supplemented by
**USDA SR Legacy** (~7,000 whole foods) for foods CNF doesn't have.
Whole foods are interchangeable across databases; packaged foods are
not (different fortification by country). Custom food entry from
nutrition facts labels covers specific branded products.

---

## 2. Author & learning context

> **Note:** This section describes the original learning project. The
> project has been repurposed for the AI Masters Vibecoding Challenge
> (4-week competition). For the competition, the AI agent writes working
> code directly — no scaffold-and-fix, no deliberate bugs. The learning
> sections below are kept for reference in case the author returns to
> the learning project later.

- The author is a nutrition subject-matter expert (SME) learning Python.
- Goal: deep fluency, not just a working app. "Don't dumb it down" —
  explain all jargon inline.
- Primary language focus: Python (pandas first).
- Existing related projects by the same author (pure Python, no pandas/web):
  `NH_menu_engine`, `menu`, `nharegionalmenu`, `RDO Minced` (a dysphagia
  rotation generator). They follow the standard load → process → render
  separation. This project follows the same general separation of
  concerns — that's a universal good habit, not a copy of the menu
  engine — but uses file names that honestly describe each module's job
  in this project (`data_loader.py`, `calculator.py`, `measures.py`,
  `report.py`, `streamlit_app.py`), since the tools (pandas, Streamlit)
  and the domain objects (Ingredient, Recipe, NutrientProfile) have no
  menu-engine analog. Knowing the author has shipped these projects
  lets a future AI session teach by analogy ("`data_loader.py` is like
  your `load.py`, except it returns DataFrames instead of dicts").

---

## 3. Tech stack (and why)

| Layer       | Choice            | Why                                            |
|-------------|-------------------|------------------------------------------------|
| Language    | Python 3.12+      | matches existing projects; author's focus      |
| Data        | pandas            | standard for tabular data; tames 565k-row CSV  |
| UI          | Streamlit         | fastest path from Python to live web app; free cloud deployment. Chosen for competition speed. Graduation path: FastAPI + React. |
| Persistence | Parquet (pyarrow) | binary, ~20× faster load than CSV              |
| Validation  | pydantic (later)  | typed input models; prep for API stage         |
| Tests       | pytest            | standard, simple                               |
| Formatting  | black + ruff      | auto-style + linter; teaches conventions        |
| Deployment  | Streamlit Community Cloud | free, public URL, auto-deploys from GitHub |

Deliberately NOT yet included: database, FastAPI, React. Those are the
graduation path — see §6.

**UI decision:** Streamlit chosen for the competition because it's the
fastest path from Python to a live web app. The author knows Python, not
JS. The full-page-rerun model is a limitation for editable tables, but
manageable with `@st.cache_data` and `st.session_state`. If editable
tables prove too painful, fallback is FastAPI + HTMX (still Python only).
Graduation path: FastAPI + React.

---

## 4. Folder structure

```
blenderized-tubefeed-calculator/
├── cnf_fcen_all-files-data_2026/   # raw CNF data (DO NOT MODIFY)
├── data/
│   ├── processed/                   # generated parquet (gitignored)
│   └── packs/
│       └── canada/                  # the only pack implemented today
│           ├── nutrients.csv        # the nutrient registry (what to track, why, and target_type)
│           ├── formulas.csv         # commercial formula profiles (CSV)
│           └── thinning_liquids.csv # thinning liquid presets (CSV)
├── src/
│   ├── __init__.py
│   ├── data_loader.py               # CSV → pandas DataFrames (WORKING)
│   ├── build_parquet.py             # one-time: CSV → parquet (WORKING)
│   ├── models.py                    # @dataclass Ingredient, Recipe, Profile
│   ├── nutrients.py                 # per-country nutrient registry (load_registry, NutrientDef)
│   ├── calculator.py               # core math: recipe → nutrient profile
│   ├── measures.py                  # household-measure → grams
│   ├── targets.py                   # load DRI / tube-feed targets
│   └── report.py                    # profile + targets → tier-based adequacy report
├── reference/                        # bug-free reference solutions (per phase; learning project only)
│   ├── __init__.py
│   ├── data_loader.py               # Phase 2 reference (verified working)
│   ├── build_parquet.py             # Phase 2 reference (verified working)
│   └── README.md
├── app/
│   └── streamlit_app.py             # the UI
├── scripts/
│   ├── verify_backend.py            # full backend integration test
│   ├── check_app_imports.py         # app import smoke test
│   └── trace_calculation.py         # hand-checkable calculation + registry trace
├── tests/
├── notebooks/
│   ├── 00_explore_cnf.ipynb         # data-exploration sandbox
│   └── PHASE2_SPEC.md               # spec, hint list, verification for Phase 2
├── BUSINESS_CASE.md                  # Week 1 deliverable + full methodology
├── CONTEXT.md                       # this file (internal project management)
├── README.md                         # newbie-friendly setup + usage guide
├── requirements.txt
└── .gitignore
```

---

## 5. CNF schema (quick reference)

Relational database delivered as CSVs. All nutrient amounts are
**per 100 g edible food**.

| File                          | Rows    | Key columns                              |
|-------------------------------|---------|------------------------------------------|
| Food_Name.csv                 | ~5,993  | Food_Code (PK), descriptions, group code  |
| Nutrient_Name.csv             | ~173    | Nutrient_Code (PK), name, unit, Tagname   |
| Nutrient_Amount.csv           | ~565,409| Food_Code (FK), Nutrient_Code (FK), amount|
| Measure_Name.csv              | ~1,494  | Measure_Code (PK), description ("1 cup")  |
| Measure_Weight_Conversion.csv | ~29,868 | Food_Code + Measure_Code → grams          |
| Measure_Type.csv              | 3       | 3=Refuse, 6=User-defined, 9=Yield         |
| CNF_Food_Group.csv            | 23      | group code → description                 |

Key arithmetic: `nutrient_from_ingredient = grams × (amount / 100)`.

**Gotcha:** Several CNF CSVs have a UTF-8 BOM (`﻿`). Must use
`encoding="utf-8-sig"` in `pd.read_csv()` to strip it, or the first
column name becomes `﻿Nutrient_Code` and merges silently fail.

---

## 6. Build plan

### Competition plan (4 weeks — see `BUSINESS_CASE.md` §12)

| Week | Deliverable | What gets built |
|---|---|---|
| **1 — Plan It** | `BUSINESS_CASE.md` posted publicly | Concept, market, requirements, methodology |
| **2 — Core Feature** | Working Streamlit app | Build calculator, measures, targets/report, Streamlit UI |
| **3 — Build to Last** | Tests, CI, deploy, custom food, USDA | pytest, GitHub Actions, Streamlit Cloud, label-entry, USDA data |
| **4 — Ship + Pitch** | Live app + 2–3 min demo | Polish, export, demo video |

### Learning project phases (original — for reference)

> The phases below describe the original learning project. For the
> competition, we follow the 4-week plan above. The AI agent writes
> working code directly (no scaffold-and-fix). The phases are still
> useful as a module breakdown.

- **Phase 1 — Setup.** venv, requirements.txt, folder skeleton,
  exploration notebook, git init. (COMPLETE)
- **Phase 2 — data_loader.py.** Typed, reusable loading functions;
  one-time CSV→parquet build script. (COMPLETE — working code, parquet
  files built and verified 2026-07-15)
- **Phase 3 — models.py + calculator.py.** @dataclass Ingredient/Recipe;
  Recipe carries ingredients + **added water** + **measured final
  volume**; profile(recipe) → nutrient totals via merge + groupby,
  then **densities** (kcal/mL, protein/mL, free-water fraction) using
  measured volume as denominator.
- **Phase 4 — measures.py.** Household measure → grams via the
  conversion table. Filter to Measure_Type=6 only.
- **Phase 5 — targets.py + report.py.** SME-authored DRI / tube-feed
  target tables; daily adequacy report, free-water total,
  commercial-formula benchmark row.
- **Phase 6 — streamlit_app.py.** Editable ingredient table, live
  density panel, adequacy report, live recipe adjustment, export.
- **Phase 7 — Polish.** Save/load recipes as JSON; pytest suite.
- **Phase 8+ (graduation).** Lift calculator behind FastAPI; build
  React frontend that calls it.

---

## 7. Working method: scaffold-and-fix (learning project only)

> **Note:** This method is for the original learning project only. For
> the competition, the AI agent writes working code directly — no
> deliberate bugs, no scaffold-and-fix.

The author learns by fixing deliberately-buggy code, not by writing from
scratch or studying finished code. Per module the AI agent provides:

1. **Spec** — inputs, outputs, CNF columns to use, edge cases.
2. **Scaffold code** — mostly-correct version with 3–6 deliberate bugs
   spanning: logic, data/pandas, subtle/edge-case.
3. **Hint list** — categories of bugs present (never the answers).
4. **Verification step** — the exact test/print confirming correctness.

Author fixes one bug at a time, re-runs the check after each. When
stuck >20 min, author may ask for a *hint* (not the answer). The
*full fix* is given only if the author explicitly says "just show me."

A `reference/` folder contains bug-free solutions for each phase, so the
author can compare their fixes or unblock themselves if stuck for too long.

---

## 8. Glossary (key terms the author is learning)

- **Relational database / primary key / foreign key** — data split
  across tables linked by shared ID columns.
- **DataFrame (pandas)** — in-memory 2-D table; think "Excel sheet in
  Python."
- **Join / merge** — combine two tables on a shared key (like VLOOKUP).
- **Normalization** — storing each fact once; requires more joins.
- **Virtual environment (venv)** — isolated Python sandbox per project.
- **requirements.txt** — pinned library list for reproducibility.
- **Streamlit** — Python library turning scripts into web apps; re-runs
  the whole script on every interaction.
- **Module / package** — a `.py` file is a module; a folder of modules
  with `__init__.py` is a package.
- **@dataclass** — auto-generates boilerplate for simple record classes.
- **Type hints** — `def f(a: float) -> float:`; documentation + tooling.
- **Per-100g convention** — CNF amounts are per 100 g edible food;
  scale by `grams / 100`.
- **Parquet** — columnar binary format; ~20× faster to load than CSV.
- **Commit / stage / .gitignore** — Git snapshot / pre-commit selection /
  "never track these files."
- **Vectorization** — operating on whole columns at once, not row-by-row
  with `.iterrows()` (which is a code smell).
- **BOM (Byte Order Mark)** — a `﻿` character at the start of some
  UTF-8 files; `encoding="utf-8-sig"` strips it.
- **Sweet spot** — the overlap between "thin enough to flow" (RD's
  drip test) and "dense enough to nourish" (tool's density calc).
- **Drip test** — hands-on check: pull blended food in a 50–60 mL
  syringe without resistance (AHS 2021). The tool can't replace this.
- **Thickness ceiling** — BTF recipes should be at most as thick as
  Resource 2.0; thicker won't flow through a tube.

---

## 9. Current status

**Competition-week framing (see `BUSINESS_CASE.md` §12 for the 4-week plan):**

- [x] Week 1 — Plan It — COMPLETE (`BUSINESS_CASE.md` posted; `CONTEXT.md`
  merged and aligned with it as of this repo audit)
- [x] Week 2 — Core Feature — effectively COMPLETE (calculator, measures,
  targets/report, and the Streamlit UI are all built and backend-verified;
  see the phase-level record below for detail)
- [ ] Week 3 — Build to Last — NOT STARTED (pytest suite, CI, Streamlit
  Cloud deploy, and the USDA SR Legacy supplement are not started; custom
  food entry from a label is already built in Week 2's Streamlit UI)
- [ ] Week 4 — Ship + Pitch — NOT STARTED (polish, export, demo video)

**Phase-level record (module breakdown, kept for detail):**

- [x] Phase 1 setup — COMPLETE (venv, requirements.txt, .gitignore, git init, first commit 852cc9e)
- [x] Phase 2 data_loader — COMPLETE (working `src/data_loader.py` + `src/build_parquet.py`; parquet files built and verified 2026-07-15; reference solutions in `reference/` match src/)
- [x] Week 1 planning — COMPLETE (`BUSINESS_CASE.md` written with full market analysis, competitors, methodology, and 4-week build plan)
- [x] Phase 3 calculator — COMPLETE & VERIFIED (`src/models.py`, `src/calculator.py`)
- [x] Phase 4 measures — COMPLETE & VERIFIED (`src/measures.py`)
- [x] Phase 5 targets/report — COMPLETE & VERIFIED (`src/targets.py`, `src/report.py`, `data/targets/dri_adult_default.csv` as of 2026-07-15 — since moved to `data/packs/canada/targets.csv`, see the nutrient-registry entry below)
- [x] Phase 6 Streamlit UI — SCAFFOLDED, bug-fixed post-audit, restructured 2026-07-17 (`app/streamlit_app.py`; recipe builder with CNF search + food-group filter + custom food from label, delivery input, targets (including fluid mL/day), live density panel, adequacy report with color-coded status (including a Free water row), dilution what-if with thinning liquid presets, commercial formula comparator, Excel export with a sanitized filename; import-verified 2026-07-15; commercial formulas + thinning liquids externalized to CSV in `data/`; widget session state warning fixed; see the "UI restructure" entry below for the Build/Results tabs + persistent banner layout change)
- [ ] Phase 7 polish — NOT STARTED

**Pinned issues (to revisit after user testing):**

- **App not matching expectations** — author noted "it's not quite what
  I expected." Specific feedback pending after hands-on testing. Week 2
  iteration will address.
- **Reference data now in CSVs** — every Canadian reference file
  (nutrient registry, commercial formulas, thinning liquids) lives
  under `data/packs/canada/` (one "data pack" per country — see
  `BUSINESS_CASE.md` Appendix C). Formulas and thinning liquids load
  at startup with hardcoded fallbacks; the nutrient registry
  (`nutrients.csv`) deliberately does NOT fall back — see §11 and
  `src/nutrients.py`'s module docstring for why. RDs can edit any of
  these CSVs without touching Python. (`targets.csv` — see below —
  was deleted in the round-2 clinical feedback pass; no longer part of
  this list.)
- ~~Design gap: dilution-slider vs. live recipe adjustment~~ —
  **RESOLVED 2026-07-17 (round-2 clinical feedback).** The code
  previously implemented the dilution-slider what-if (add X mL of a
  thinning liquid, see new densities) as if it might be the core
  interaction, while `BUSINESS_CASE.md` §7 / Appendix A8 described live
  recipe adjustment as the goal — an unresolved tension between the
  shipped feature and the stated design commitment. The author's
  explicit ruling settles it: **live recipe adjustment (editing the
  actual recipe — the editor itself is the what-if) is the core
  interaction; the Dilution What-If is a demoted, secondary
  recipe-development aid** ("if we must thin, what does it cost in
  density" — a preview, not a substitute for making the real edit). The
  app's caption was changed to match ("If the blend needs thinning, see
  the density impact before you commit" — the self-congratulatory "The
  core feature" framing is gone); `BUSINESS_CASE.md` §7 item 6 and
  Appendix A8 were rewritten to state this explicitly. No longer pinned
  — this was a genuine design-commitment gap, not a layout question (the
  2026-07-17 Build/Results tabs restructuring earlier the same day only
  moved *where* things live on the page and explicitly did NOT resolve
  this; this later same-day round-2 pass is what actually resolves it).
- ~~Fluid target default (2700 mL) needs RD review~~ — **RD-reviewed and
  accepted 2026-07-16, then superseded 2026-07-17.** 2700 mL was
  initially accepted as a *guideline default* (DRI AI for adult women).
  The round-2 clinical feedback pass overturned this: **no default
  targets exist anywhere in the app now** (Part 0 #2 — a default is not
  defensible for tube-fed patients in general, not just for fluid;
  protein practice runs 1.0-1.5 g/kg, not the population RDA). Targets
  always start blank; `data/packs/canada/targets.csv` is deleted. See
  the round-2 entry below.
- **Magnesium and phosphorus are deliberately target-less** — both are
  tracked (`tier=clinical` in `data/packs/canada/nutrients.csv`, since
  the author's EN spreadsheet tracks them and CNF covers them at
  97-98%) and, as of the round-2 clinical feedback pass, carry
  `offer_target=no` in that same registry (no more separate
  `targets.csv` to have a missing row in) — so they always render "No
  target" in the BTF micro screen. This is intentional, not a gap:
  refeeding-risk monitoring happens in hospital on known formulas, not
  via a BTF default target. Do not flip `offer_target` to yes for these
  two without the author's explicit sign-off — see `src/targets.py`'s
  module docstring.
- **Ask practicing RDs which nutrients they'd track in their own area of
  practice.** The current displayed-nutrient set (main table: energy,
  carbohydrate, protein, fat, fluid, fibre, sodium, potassium, calcium,
  iron; micro screen: magnesium, phosphorus, zinc, vitamin D, B12) is
  the author's own clinical judgment as one RD. Any future addition or
  removal goes through the registry's `tier`/`show_in_report`/
  `offer_target` columns (`data/packs/canada/nutrients.csv`), never a
  hardcoded Python list — but which nutrients belong there at all is a
  clinical-practice question this project hasn't surveyed beyond its
  own author.
- **Fluids-ledger convention is flagged overridable after further
  clinical use.** The "Fluid provided" figure uses full-volume I&O
  counting for anything flagged "counts as fluid" (liquids count at
  full volume, not a moisture-adjusted fraction), and the per-ingredient
  toggle IS the clinical policy for judgment calls like soup (no
  validated rule of thumb exists for how much of a soup's volume
  "counts"). The author signed off on this convention for the round-2
  pass but explicitly flagged it as revisitable once used on real
  patients — see the round-2 entry below and Part 0 #8 of the handoff
  plan (`.claude/plans/btf-clinical-feedback-round1.md`, if still
  present) for the full reasoning.
- **US/UK/AU data packs are roadmap, not started** — the registry
  design (`src/nutrients.py`, `data/packs/<pack>/`) is built so that
  adding a country is writing new CSVs under `data/packs/<pack>/` with
  zero Python changes (kJ vs kcal and EU "salt" vs sodium are the one
  documented exception, deferred to a future per-pack `config.yaml` —
  see `BUSINESS_CASE.md` Appendix C). No non-Canadian pack exists yet.

**Repo audit fixes (2026-07-16, this session) — resolved, no longer pinned:**

- ~~⚠️ emoji on "Measured final volume" label~~ — removed; label is now
  bold markdown text, `help=` tooltip kept.
- ~~Food search crashes on regex metacharacters~~ — the search box now
  passes `regex=False` to `str.contains`, matching the `find_food()`
  helper.
- ~~No fluid-adequacy row~~ — the targets CSV (now `data/packs/canada/targets.csv`
  — see the nutrient-registry entry below) gained a `fluid_mL` target;
  `empty_targets()` and the custom-targets sidebar include it;
  `generate_adequacy_report()` appends a "Free water (mL)" row.
- ~~Excel export filename could break on special characters~~ —
  `sanitize_filename()` strips `/\:*?"<>|` before building the download
  filename.
- ~~Custom-food math lived in the UI layer~~ — moved into
  `calculate_profile(recipe, na, custom_foods=...)` in
  `src/calculator.py`; covered by `verify_backend.py` stage 9.
- ~~Parquet layer built but unused~~ — `src/data_loader.py` now reads
  `data/processed/*.parquet` when present, falling back to CNF CSV;
  `verify_backend.py` stage 1 prints the source and load time.
- ~~Stray Cline artifact / duplicate docs in git~~ — see the 2026-07-16
  P0 entry below.

**Nutrient registry & data packs (2026-07-16, this session) — the core
architectural change since the last audit:**

- `src/calculator.py`'s hardcoded 11-nutrient `NUTRIENT_CODES` dict
  (which included vitamin D, B12, and zinc — none of which appear on a
  Canadian label — and omitted magnesium and phosphorus, which the
  author's EN spreadsheet tracks) is replaced by a per-country
  **nutrient registry**: `src/nutrients.py::load_registry()` reads
  `data/packs/<pack>/nutrients.csv`, a 19-row CSV tagging every
  nutrient with `tier` (`label` | `clinical` | `engine` — WHY it's
  tracked) and `on_label` (WHETHER a nutrition-facts label can supply
  it). See `BUSINESS_CASE.md` Appendix C for the full rationale: a
  country's mandatory Nutrition Facts panel IS that country's
  public-health nutrient consensus (Health Canada's and the FDA's own
  stated reasoning, quoted there), so the tracked-nutrient set has to
  be per-country data, not a Python constant.
- All Canadian reference CSVs (`nutrients.csv`, `targets.csv`,
  `formulas.csv`, `thinning_liquids.csv`) now live together under
  `data/packs/canada/` (moved via `git mv` from `data/targets/`,
  `data/formulas/`, and `data/thinning_liquids.csv`). `targets.csv`
  gained a `target_type` column (RDA/AI/UL/estimate).
- `src/report.py` now produces **two** tables instead of one:
  `generate_adequacy_report()` (tier="label" + Free water — the main
  daily-tracked table) and the new `generate_clinical_screen()`
  (tier="clinical" — a one-time ASPEN-style "does this blend need a
  multivitamin?" screen, not a daily panel). Sodium (`target_type=UL`)
  now reports "Above UL"/"Below UL" instead of the misleading "Above
  target"/"Meeting target". Both tables gained a **Source** column
  (label-derivable or CNF-only) and a **Coverage** column (P2 — how
  many of *this recipe's* ingredients actually had CNF data for that
  nutrient, e.g. "1/2 ingredients"; flagged only when incomplete).
- `app/streamlit_app.py`'s custom-food entry form and custom-targets
  sidebar are now generated from the registry instead of hardcoded
  field lists; the custom-food form gained Fat/Saturated
  Fat/Trans Fat/Cholesterol/Carbohydrate/Sugars (real Canadian label
  fields) and lost Vitamin D/B12/Zinc/Water (not on any Canadian
  label) — with a caption warning that moisture is on no label, so
  custom-food recipes will underestimate free water. A new "BTF micro
  screen" expander renders the clinical screen; Excel export gained a
  "Micro Screen" sheet.
- Acceptance criterion — **partially met; do not read the docs as
  saying otherwise.** The goal is that adding a country is writing new
  CSVs under `data/packs/<pack>/` with **zero Python changes**.
  - **Met** for `nutrients.csv` and `targets.csv`: `load_registry()`,
    `load_targets()`, `generate_adequacy_report()` and
    `generate_clinical_screen()` all take a `pack` argument.
    `verify_backend.py` stage 10 checks `load_registry("no_such_pack")`
    raises `FileNotFoundError`, proving the registry is genuinely
    data-driven rather than a Canadian default with a data-shaped facade.
  - **NOT met** for `formulas.csv` and `thinning_liquids.csv`:
    `_load_commercial_formulas()` (`src/calculator.py`) and
    `_load_thinning_liquids()` (`app/streamlit_app.py`) are still
    module-level constants loaded once from a hardcoded `canada` path.
    A US pack would today get US nutrients + US targets but **Canadian
    formulas** — which matters, because commercial formulary is among
    the most country-specific data in the tool. **Outstanding work:**
    parameterize both loaders by `pack`. Note this ripples to
    `COMMERCIAL_FORMULAS`'s importers (`src/report.py`,
    `app/streamlit_app.py`).
  - Deferred by design: kJ/salt-unit handling (future per-pack
    `config.yaml`; see Appendix C).

**UI restructure: Build/Results tabs + persistent banner (2026-07-17) —
a layout/navigation change, not a feature or calculation change:**

- `app/streamlit_app.py`'s single, continuously-scrolling page (sidebar
  doing double duty as both "global recipe identity" and "the one place
  you add every ingredient," density panel through Excel export all
  stacked below the ingredient table) is reorganized into: a
  **decluttered sidebar** (title/branding, recipe name, "Load example
  recipe" only), a **persistent "Patient, Delivery & Targets" banner**
  (collapsible detail — delivery method/params + DRI-default-or-custom
  targets — plus an always-visible one-line summary showing daily
  volume and active kcal/protein/fluid targets) sitting above two
  **`st.tabs`**: **"🔨 Build"** (CNF ingredient search — now full-width
  instead of sidebar-cramped, with a new food-group filter over CNF's
  own 23 native `CNF_Food_Group` categories — custom-food-from-label
  entry, blend details, and the editable ingredient table) and
  **"📊 Results"** (density panel, daily totals & adequacy, BTF micro
  screen, dilution what-if, commercial formula comparator, Excel
  export). Grounded in the author's own hospital EN spreadsheet's
  two-sheet structure (Assessment vs. EN Initiation) and a review of
  the Compleat® recipe builder's persistent target strip.
- **The banner deliberately bundles Delivery together with Targets**,
  not Targets alone — both are patient-side, set-once,
  referenced-everywhere inputs (unlike ingredients, which are
  blender-side and edited constantly), and the banner's one-line daily
  volume comes directly from Delivery. This was flagged as an
  overridable call in the handoff plan; kept as specified — no reason
  surfaced during implementation to move Delivery back to the sidebar.
- **Real behavior fix, not just a code move:** the two former global
  `st.stop()` calls (empty ingredients; `measured_volume <= 0`) — which
  would have halted the *entire* script run and broken Results-tab
  rendering if left in place inside a tab block — are now **tab-local
  guards**. The Build tab always renders its add-ingredient UI even
  with zero ingredients (only the ingredient-table section is skipped,
  with an inline prompt); the Results tab shows an inline "add
  ingredients in the Build tab" guidance message instead of raising or
  halting when ingredients are missing or volume is unset. `recipe` and
  `profile` are now constructed inside the guarded Results-tab branch
  only. Verified explicitly with a Streamlit `AppTest` harness (see
  below) on a fresh, ingredient-free session — both tabs render their
  full shell with no exception.
- No calculation, data-model, or `src/` change. `color_status()`,
  `generate_adequacy_report()`, `generate_clinical_screen()`,
  `generate_formula_comparison()`, `generate_density_summary()`,
  `dilute()`, `required_daily_volume()`, and the Excel sheet structure
  are all relocated verbatim.
- **New:** `get_food_group()` (cached, mirrors `get_food_name()`) wraps
  `src/data_loader.py::load_food_group()`, which already existed but was
  unused. The food-group filter narrows the CNF food-name DataFrame by
  `CNF_Food_Group_Code` *before* the existing substring search — same
  `regex=False` search behavior as before, just pre-narrowed by group
  when one is selected.
- **Explicitly deferred, not built now** (per the handoff plan's
  Decision 4 — a separate design session, not a layout-change bundle):
  purpose-based nutrient category cards (Compleat's "Protein-Rich
  Foods" / "Vitamin C-Rich Fruits & Vegetables" groupings). These would
  need either hand-tagging ~5,993 CNF foods or a nutrient-threshold
  heuristic — real clinical-judgment design work.
- **Does NOT resolve** the pinned "dilution-slider vs. live recipe
  adjustment" item above — that's a feature gap (the tool still adds a
  what-if liquid rather than adjusting the recipe itself live); this
  work only changed where things live on the page, not the dilution
  what-if's behavior.
- Verified with: the three existing regression scripts (still pass
  unchanged, since the backend wasn't touched); a new Streamlit
  `AppTest` harness driving the app programmatically (fresh-load
  rendering of both tab shells and their empty-state guards, example-
  recipe load populating the Build tab and blend details, the Results
  tab rendering density metrics/adequacy table/BTF micro screen/formula
  comparator once ingredients exist, the persistent banner rendering
  once at top level — not duplicated inside either tab, Excel export
  not raising, and the food-group filter both narrowing results to a
  selected group and behaving like today's unfiltered search under
  "All"); and a live `.venv/bin/streamlit run` boot/log check plus an
  `AppTest`-driven interactive-style pass (custom-food-from-label entry,
  food-group filter + search, dilution slider) exercising the real
  script engine end to end, since no browser-automation tool was
  available to click through a live page in this environment.

**Round-2 clinical feedback (2026-07-17, separate session, same day as
the tabs restructuring above) — the author's own hands-on test-drive,
followed by a Q&A that settled every open design question. Unlike the
tabs restructuring, this round deliberately touches `src/`, reference
data, and the app together. Full handoff:
`.claude/plans/btf-clinical-feedback-round1.md` (if still present in
the repo/plans directory).**

- **No default targets anywhere (Part 0 #2).** `data/packs/canada/
  targets.csv` is DELETED outright — see the superseded pinned-issue
  entries above. `src/targets.py` loses `load_targets()`/
  `default_targets()`/`load_target_types()`; `empty_targets()` derives
  its keys from the registry's `offer_target=yes` rows + `fluid_mL`
  instead. `target_type` (RDA/AI/UL/estimate — the UL wording driver)
  moved into `nutrients.csv` itself (a property of the nutrient, not of
  a default value that no longer exists).
- **Registry gains `show_in_report`/`offer_target`/`target_type`
  columns** (`data/packs/canada/nutrients.csv`, `src/nutrients.py`'s
  `NutrientDef`). The main adequacy table now shows 9 nutrients (energy,
  protein, fat, carbohydrate, fibre, sodium, potassium, calcium, iron)
  instead of all 13 label-tier ones — saturated fat, trans fat,
  cholesterol, and sugars are still tracked/exported, just not
  displayed daily ("show what's needed," the author's call). The
  registry CSV's row order was also reordered to CFIA label order
  (Energy, Fat/Sat/Trans, Carbohydrate/Fibre/Sugars, Protein,
  Cholesterol, Sodium, Potassium, Calcium, Iron) so both the
  custom-food form and the targets-entry loop can iterate registry
  order directly with no hardcoded nutrient sequence in Python.
- **Zero-coverage hiding is first-class.** Any adequacy-table or
  micro-screen row with 0/N ingredients supplying a value is hidden
  entirely (never a confident "0"), with a footnote listing what was
  hidden. `generate_adequacy_report()`/`generate_clinical_screen()` now
  return `(DataFrame, hidden_names)`.
- **Fluids ledger replaces the Added-water field (Part 0 #8).** The
  Added-water input is deleted — water is an ordinary ingredient (CNF
  carries it at ~99.9% moisture). Every ingredient gets a
  `counts_as_fluid` checkbox (auto-on for CNF Beverages and a
  description starting with "Water"; always overridable — the toggle
  IS the policy for judgment calls like soup, flagged revisitable
  above). Two fluid numbers now exist: **Fluid provided** (full I&O-
  convention volume of counts-as-fluid ingredients, scaled to daily
  intake, plus water flushes — drives the adequacy row and chart note)
  and **Free water (CNF-estimated)** (the old moisture-based figure,
  demoted to secondary/informational with its own completeness flag).
  The example recipe now includes "Water, municipal" (CNF Food_Code
  2933, 200 g, counts_as_fluid=True) in place of the old
  `added_water_mL=200`.
- **Delivery rework (Part 2.5).** Syringe bolus is now an editable
  (time, volume) schedule (`st.data_editor`, dynamic rows) instead of a
  single bolus-volume × times/day pair; "Direct mL/day" is renamed
  "Total feed volume per day"; Pump is removed from the UI radio (the
  `PUMP` enum stays in `src/models.py`, unused — not removed, to avoid
  backend churn for nothing). New water-flush schedule (same pattern),
  separate from the recipe, feeding the fluids ledger and chart note.
- **Patient weight (display-only), per Part 0 #3.** An optional weight
  (kg) input adds kcal/kg/day, protein g/kg/day, and fluid mL/kg/day
  rows to the density panel. No target, no equation, no IBW — assessment
  stays out of the app, same as always.
- **Custom-food label redesigned as a Canadian Nutrition Facts
  lookalike (Part 0 #7).** A g-or-mL basis selector whose unit flows
  through unchanged to a clearly-separate "Amount used in recipe" field
  outside the label box — no cross-conversion, ever (that would require
  guessing a density). Fields render single-column (a real label IS a
  single column; a two-column zigzag also turned out to scramble the
  intended CFIA order, since Streamlit lays out `st.columns()` content
  column-major, not in loop order). A collapsed "Optional nutrients on
  this label?" expander offers the five clinical-tier fields.
- **Comparator redesigned (Part 0 #11):** `st.multiselect` (max 4
  formulas), transposed — metrics as columns, BTF as the first row.
  `formulas.csv` gained `free_water_per_mL` (source: the author's own EN
  spreadsheet, same sheet as `kcal_per_mL`/`protein_per_mL`) feeding
  this table and the new combined-regimen summary.
- **New features:** flow-test documentation (date/result/notes,
  export-only); combined BTF + commercial-formula regimen summary
  (`src/report.py::generate_regimen_summary()` — BTF/Formula/Flushes/
  TOTAL rows, vs-targets caption); copy-pasteable chart-note text in
  `st.code` (schedule, macros, fluid math, flow-test result — bracketed
  pieces omitted when their inputs are absent).
- **Tab labels enlarged via injected CSS** (Part 0 #10). Verified
  against Streamlit 1.58's actual compiled frontend bundle (grepped the
  installed `streamlit/static/static/js/*.js`) rather than trusting a
  guess: tabs render as `button[data-testid="stTab"]`, not
  `[data-baseweb="tab"]`.
- **Dilution What-If resolved as a secondary aid, not the core
  feature** — see the superseded pinned-issue entry above and
  `BUSINESS_CASE.md` §7 item 6 / Appendix A8.
- **One judgment call made without an explicit spec:** the custom-food
  form was folding EVERY field into `custom_foods` regardless of
  whether the RD touched it (untouched 0.0 defaults included), which
  gave every custom food full "coverage" on every nutrient by
  construction and silently defeated zero-coverage hiding for
  clinical-tier fields through the real UI. Fixed by only folding in
  fields where the RD entered a value greater than 0 — an explicit "0"
  typed for a genuinely-zero label value (e.g., "0 g Trans Fat") now
  reads as "not entered" rather than a supplied zero. This
  under-reports coverage in that one specific case but never fabricates
  it, consistent with the "never a confident 0" principle elsewhere in
  this round. Flagged for the author's awareness, not yet explicitly
  signed off.
- Verified with the three regression scripts (`verify_backend.py`
  extended with new stages for the registry columns and zero-coverage
  hiding; `trace_calculation.py` and `check_app_imports.py` pass
  unchanged in shape) plus several scratch Streamlit `AppTest` scripts
  (not committed, matching this project's established convention of ad
  hoc AppTest verification rather than a committed `tests/` suite) and
  a live `.venv/bin/streamlit run` smoke test.

**✅ RESOLVED (2026-07-18/19) — the Intake Record rework.** The live bug
below (daily totals computed as `density × delivery-schedule volume`) is
fixed; the app now trusts daily totals / adequacy / per-kg / fluid /
chart note unconditionally — see the "Intake Record rework" entry further
down for what shipped. The paragraphs immediately below are kept
verbatim as the historical record of the bug and the design decision
that fixed it; do not re-litigate either.

- **The bug (now fixed):** daily totals were computed as `density ×
  delivery-schedule volume`, silently assuming the client received
  multiple batches of a recipe that exists once (batch 400 mL + schedule
  1200 mL/day → results ×3). Nothing reconciled batch volume against
  delivered volume.
- **Author's design decision (implemented, do not relitigate):** replace
  the single-recipe + schedule model with **"the day is a list of intake
  events"** — multiple named blends per day (morning blend, fridge
  batch, ...), and an **Intake Record** (time · source_type · source ·
  amount) where a source is a blend, a commercial formula, a water
  flush, or an oral food/drink. Daily totals = the direct sum over
  Intake Record rows; there is **no over-draw flag of any kind** — not
  "warn instead of block," genuinely removed as a concept (a blend's
  density is scale-free, so logging it multiple times a day is normal
  usage, not an anomaly). This dissolved the schedule-mismatch problem
  and superseded the separate round-2 "combined regimen" section and the
  standalone flush schedule (both became Intake Record rows).
- **Full coherent rework, no interim patch** — a cap-at-batch band-aid
  was explicitly considered and rejected as throwaway logic.
- **The complete design doc is [`FEED_LOG_REWORK.md`](FEED_LOG_REWORK.md)**
  (repo root) — still the authoritative record of the model and every
  resolved design question (section 6), kept for reference; it is a
  completed plan now, not an in-progress one.
- **Next milestone (author-approved 2026-07-17, unchanged by this
  rework):** the **label-photo → custom food** feature plus **public
  deployment** (Streamlit Community Cloud, API key in app secrets, no
  PHI by design) so practicing RDs can pilot-test the whole tool. The AI
  roadmap and its governing principle ("the agent is in the workflow,
  not in the math"), the cooked-preparations design constraint for
  future recipe matching, and the explicit rejection of AI-written ADIME
  notes are all recorded in `BUSINESS_CASE.md` §7 ("Where AI belongs in
  a clinical calculator").

**Intake Record rework (2026-07-18/19, this session) — implements
`FEED_LOG_REWORK.md` in full, including the scope-expansion to oral
intake the doc's section 6.4 settled. Five commits (plus one bugfix
commit found during verification):**

- `eacc39e` — backend: extracted `calculate_profile()`'s ingredient-
  scaling core (steps 1-6) into `src/calculator.py::_scale_ingredients()`,
  exposed standalone as `compute_nutrient_totals()` /
  `compute_nutrient_totals_and_coverage()` for callers with no
  volume/density concept (an oral row is a single food — no batch to
  divide by). New `src/intake.py::aggregate_intake()` sums Intake Record
  rows into daily totals, fluid provided, and Tube-Feed/Food-&-Drink/
  Total subtotals; `resolve_blend_profile()` raises `InvalidBlendError`
  for a blend with ingredients but no measured volume — the one guard
  that survives the rework. `verify_backend.py` stage 13 covers the
  design doc's full verification bar at the backend level.
- `d9b6f77` — `app/streamlit_app.py` session state reworked to
  `st.session_state.blends` (dict id -> {name, ingredients,
  measured_volume_mL} — an open-ended list of formulations) and
  `st.session_state.intake_log`. The Build tab gained a blend selector
  (new/rename/delete, per-blend density mini-summary). The CNF-search +
  custom-food-from-label UI was refactored into
  `render_add_food_ui()` — one reusable component parameterized by a
  `key_prefix`, with no opinion about its destination (append to a
  blend vs. become an Intake Record oral row).
- `b596bb0` — the banner's old Delivery/bolus-schedule/flush-schedule
  section is replaced by the Intake Record: "Add tube feed" (time +
  blend/formula/flush source + volume) and "Add food/drink" (reuses
  `render_add_food_ui()`), rows grouped by "Tube Feed"/"Food & Drink"
  section header but backed by one list, each removable, an
  always-visible nutrient-total summary line
  (`~kcal | g protein | mL fluid provided`).
  **Deviation from the doc, with reasoning:** the doc's first choice for
  "Add food/drink" was `st.dialog`, with an inline expander sanctioned
  as a fallback "if st.dialog proves awkward in practice." `st.dialog`
  works correctly for real interactive use but is incompatible with this
  project's AppTest-driven verification discipline: any widget rendered
  inside an open `st.dialog` becomes an orphaned node in AppTest's
  tracked element tree once the dialog closes, and the very next
  `.run()` call — regardless of what triggers it — raises a `KeyError`
  reserializing that orphaned widget's state (confirmed with a minimal
  two-widget dialog unrelated to this app's code; `streamlit/testing/v1`
  has zero references to "dialog" anywhere in its source). Since a
  dialog that poisons every subsequent AppTest run can't be verified the
  way this project requires, the sanctioned inline-expander fallback was
  used instead — see `_render_add_oral_ui()`'s docstring in
  `app/streamlit_app.py`.
- `2fb9a0c` — Results tab wired to the Intake Record.
  `src/report.py::generate_adequacy_report()` and
  `generate_clinical_screen()` now take a `daily_totals` dict (+ optional
  `nutrient_coverage`) instead of a single `NutrientProfile` +
  `daily_volume_mL`, since a day's totals can now come from several
  blends/formulas/flushes/oral foods at once. New
  `generate_source_breakdown()` produces the Tube-Feed/Food-&-Drink/
  Total subtotal table; `generate_regimen_summary()` (the old combined
  BTF+formula summary) is **removed** — a formula is just another Intake
  Record row now, so `aggregate_intake()` already produces the combined
  total. The per-blend density panel now shows **every** blend (not just
  the selected one), each with a coverage summary. The chart note is
  rebuilt from Intake Record rows: chronological, tube and oral
  interleaved, same-source tube-feed rows grouped
  (`"0800 300 mL + 1200 100 mL Morning blend"`), matching the design
  doc's own worked example format. Excel export gained an Intake Record
  sheet (all rows, chronological) and one sheet per blend. The
  commercial formula comparator now operates at an explicit "compare at
  this volume" what-if input, independent of the actual Intake Record
  (there is no longer one schedule-derived daily volume to default to).
- `b458431` — bugfix found via AppTest while verifying item 4 of the
  doc's verification bar: the `blend_selector` selectbox widget
  remembers its own prior value across reruns once created (the same
  class of gotcha the round-2 pass hit with the measured-volume input),
  so creating or deleting a blend set `selected_blend_id` correctly but
  the selectbox silently overwrote it back on the next render. Fixed by
  popping the `blend_selector` session_state key wherever
  `selected_blend_id` is changed programmatically.
- **Verification:** all three regression scripts green after every
  commit (`verify_backend.py` extended with stage 13 covering the
  design doc's verification-bar items 1/2/3/5/7 at the backend level;
  `trace_calculation.py` and `check_app_imports.py` unchanged in shape).
  A Streamlit `AppTest` harness drove real UI interactions (not direct
  `session_state` pokes) covering all 8 verification-bar items,
  including item 1 (the original bug case — one blend, 400 mL batch,
  logged 3×400 mL — now computes cleanly with **no** flag or error,
  re-verified through the live UI) and item 6 (the "1 small" banana
  household measure resolves to 101 g, matching the design doc's
  CNF-verified figure exactly, plus the "enter grams directly"
  override). A live `.venv/bin/streamlit run` boot check confirmed HTTP 200.
- **Out of scope for this rework, noted as roadmap per
  `FEED_LOG_REWORK.md` section 4:** batches spanning multiple days
  (a batch drawn across days works fine for charting a single day; how
  much is left tomorrow is a future feature); saving/loading blends or
  days (JSON persistence, Phase 7); a prescribed-vs-received comparison
  field; a "recent/frequent foods" quick-add for oral entries.

**Backend verification (2026-07-16, extended 2026-07-17, extended again
2026-07-18/19 for the Intake Record rework): PASSED.** The full backend
integration test lives at `scripts/verify_backend.py` and now runs 13
stages against real CNF data (data load with Parquet/CSV source timing,
household measures, profile calculation, delivery, daily totals,
adequacy report including the fluid rows, formula comparison,
density summary, custom-food folding, nutrient-registry + tier-based
reporting, per-recipe coverage provenance, zero-coverage hiding, and
Intake Record aggregation — the extraction/calculate_profile()
equivalence, the original over-draw bug re-verified with no flag, a
single-batch exact-scaling case, the two-blend+formula+flush+oral
combined-totals case, the `InvalidBlendError` guard, and chronological
sorting). To re-verify at any time, run:

```
.venv/bin/python scripts/verify_backend.py
```

**Note to AI agents:** do NOT re-verify the backend with long inline
`python -c "..."` commands — use the script above. It exists precisely
so verification is a single short, approvable command.

Last updated: 2026-07-19 (Intake Record rework complete — see the
"✅ RESOLVED" and "Intake Record rework" entries above for the full
detail: five feature commits plus one bugfix commit, all three
regression scripts green, an AppTest harness covering all 8 items of
`FEED_LOG_REWORK.md`'s verification bar, and a live boot check. Next
session's starting point is the milestone noted above: label-photo →
custom food, plus public deployment. History below covers the
2026-07-17 hands-on user-testing day and the 2026-07-16 nutrient-registry
& data-pack refactor
session, following the earlier same-day repo audit & repair session.
Repo-audit commits: (1) P0 repo hygiene — merged CONTEXT.md so it
matches `BUSINESS_CASE.md`'s design framing (competition framing, CNF
+ USDA SR Legacy, sweet-spot/drip-test/thickness-ceiling concepts,
live recipe adjustment as the stated goal), retired scaffold-and-fix
to "learning project only", removed references to a non-existent
methodology file in favor of `BUSINESS_CASE.md` Appendices A/B/C, and
removed duplicate/generated documents (`CONTEXT.md</path`, `BUS`,
`.docx`, `.epub`) from git; (2) P1 bug fixes — search-crash regex,
fluid-adequacy row, emoji removal, Excel filename sanitization; (3)
P2-1 — moved custom-food math from the UI into `calculate_profile()`;
(4) P2-2 — `data_loader.py` now prefers Parquet over CSV.
Nutrient-registry-refactor commits (same day, separate session): (5)
committed the pending `scripts/trace_calculation.py`; (6) P1a — built
`src/nutrients.py` + `data/packs/canada/nutrients.csv` + moved all
Canadian reference CSVs into `data/packs/canada/`; (7) P1b —
`src/report.py` tier-based reporting (main table + BTF micro screen)
and UL status semantics; (8) P1c — wired `app/streamlit_app.py` and
extended both verification scripts; (9) P2 — per-recipe coverage
provenance (strictly additive); (10) P3 — this documentation pass
(`BUSINESS_CASE.md` Appendix C rewrite, §7/A6, this section, §10, §11,
README). See the "Nutrient registry & data packs" entry above for what
changed and why. Next: Week 3 scope (pytest suite, CI, Streamlit Cloud
deploy, USDA SR Legacy supplement), the US/UK/AU data packs (roadmap,
pure data per Appendix C), and the remaining pinned issues above.

2026-07-17 update (separate session): UI restructuring only — Build/
Results `st.tabs` + persistent "Patient, Delivery & Targets" banner +
CNF food-group filter, per an approved handoff plan. See the "UI
restructure" entry above for full detail. No backend/`src/` change; the
pinned "dilution-slider vs. live recipe adjustment" item is explicitly
NOT resolved by this work — it's a layout change, that's a feature gap.

2026-07-17 update (round-2 clinical feedback, separate later session
same day): the author's own hands-on test-drive plus a settled Q&A,
DELIBERATELY touching `src/`, reference data, and the app together (six
commits: registry+report+targets backend, formulas free-water column,
banner, Build tab, Results tab, docs). Deletes `data/packs/canada/
targets.csv` and all default-target machinery; adds `show_in_report`/
`offer_target`/`target_type` to the nutrient registry and zero-coverage
hiding to both report tables; replaces Added-water with a per-ingredient
fluids ledger (Fluid provided + demoted Free water); reworks delivery
into bolus/flush schedules with Pump removed from the UI; adds a
display-only patient-weight per-kg row; redesigns the custom-food form
as a Nutrition-Facts lookalike with a g/mL basis unit; redesigns the
comparator as a multi-formula transposed table; adds flow-test
documentation, a combined BTF+formula regimen summary, and a
copy-pasteable chart note; enlarges tab labels via CSS verified against
the real Streamlit 1.58 bundle. **This is the session that resolves the
long-pinned "dilution-slider vs. live recipe adjustment" item** — see
the superseded pinned-issue entry above and the "Round-2 clinical
feedback" entry above for full detail. `BUSINESS_CASE.md` (§7, Appendix
A6/A7/A8/A9, Appendix C's registry schema) and `README.md` (reference-
data table, Added-water/DRI-default mentions) were updated in the same
pass. Two new pins added: ask practicing RDs which nutrients they'd
track in their own practice area; the fluids-ledger convention
(full-volume I&O counting, per-ingredient toggle as policy) is
author-approved but flagged revisitable after further clinical use.

---

## 10. Quick-start guide (how to run the app)

After restarting your computer:

1. **Open VS Code** and open the project folder
   (`blenderized-tubefeed-calculator`).

2. **Open a terminal** in VS Code (`` Ctrl+` `` or Terminal → New Terminal).

3. **Start the app:**

   ```
   .venv/bin/streamlit run app/streamlit_app.py
   ```

4. **Open your browser** to `http://localhost:8501` (Streamlit prints
   the URL; if port 8501 is taken, it uses 8502, etc.).

5. **To stop the app:** go back to the terminal and press `Ctrl+C`.

**To verify the backend still works (optional, after code changes):**

```
.venv/bin/python scripts/verify_backend.py
```

**To verify the app imports without errors (optional):**

```
.venv/bin/python scripts/check_app_imports.py
```

**To edit reference data (no Python needed):**

All Canadian reference data lives under `data/packs/canada/` — one
"data pack" per country (see `BUSINESS_CASE.md` Appendix C).

| Data | File |
|---|---|
| Nutrient registry (what to track, why, and its target_type) | `data/packs/canada/nutrients.csv` |
| Commercial formulas (incl. free_water_per_mL) | `data/packs/canada/formulas.csv` |
| Thinning liquid presets | `data/packs/canada/thinning_liquids.csv` |

There is no `targets.csv` — deleted in the round-2 clinical feedback
pass (see §9). There are no default targets anywhere in the app; the
RD always enters patient-specific numbers at runtime, or leaves them
blank.

Edit the CSV, save, and rerun the app. Changes take effect on next load.
Adding a nutrient to track is a `nutrients.csv` row (see its `tier` /
`on_label` / `show_in_report` / `offer_target` / `target_type` columns,
documented in `src/nutrients.py`'s module
docstring) — no Python change needed. Unlike the other two files,
`nutrients.csv` has **no hardcoded fallback**: if it's missing, the app
fails loudly with `FileNotFoundError` instead of silently guessing —
this is deliberate, see §11 and `src/nutrients.py`.

---

## 11. Conventions & gotchas

- The author's existing projects use `SEED = 42` and a single `run.py`
  entry point — this project uses `app/streamlit_app.py` as entry instead.
- macOS `.DS_Store` must be gitignored globally.
- CNF `STD_Error=0` and `Observations=0` often means "derived, not
  measured" — see the CNF user guide PDF for nuances.
- Streamlit re-runs the whole script on every widget interaction; state
  must be preserved via `st.session_state` (a Phase 6 lesson).
- **A widget's `index=`/`value=` argument only takes effect the FIRST
  time its `key=` is created — every rerun after that, Streamlit uses
  whatever the widget's own `session_state[key]` already holds, and
  silently ignores `index=`/`value=` even if your code just changed the
  underlying data it was computed from.** Hit twice: the measured-volume
  `number_input` after "Load example" (worked around by popping its key
  before the value should change), and the Intake Record rework's
  `blend_selector` selectbox after creating/deleting a blend (the code
  set `st.session_state.selected_blend_id` correctly, but the selectbox
  silently overwrote it back to its last-shown index on the very next
  render — see `_new_blend()` and the delete-blend handler in
  `app/streamlit_app.py`, both of which now `st.session_state.pop(
  "blend_selector", None)` after changing selection programmatically).
  If a widget's displayed value needs to change because of a
  programmatic state change rather than the user's own interaction with
  that widget, pop its session_state key so it re-seeds from `index=`/
  `value=` on the next render.
- The AI agent's configured working directory may be wider than the VS
  Code workspace; agent self-imposes project-folder-only access.
- `reference/` files use the same path resolution as `src/` (both at
  project root); code can be copied between them without path changes.
- **CNF's sodium row is the literal string `"NA"`, and pandas will eat
  it.** In `Nutrient_Name.csv`, sodium's `Tagname` and `Nutrient_Symbol`
  columns both contain the literal text `NA` — and `pd.read_csv()`'s
  default `na_values` handling parses the string `"NA"` as a missing
  value (`NaN`), not as the two-letter sodium symbol. Any lookup that
  joins or filters on `Tagname`/`Nutrient_Symbol` will silently lose
  sodium — the row doesn't error, it just vanishes. `src/nutrients.py`'s
  registry sidesteps this entirely by keying on the **numeric**
  `Nutrient_Code` (307 for sodium) instead, which is safe. If you ever
  need to look nutrients up by Tagname/Symbol, either avoid sodium that
  way or pass `pd.read_csv(..., keep_default_na=False)`. Documented
  here, next to the BOM gotcha in §5, so nobody "fixes" the registry's
  numeric-code lookup into a Tagname lookup and reintroduces this bug.
- **`src/nutrients.py::load_registry()` raises `FileNotFoundError` if
  `nutrients.csv` is missing — deliberately, with no hardcoded
  fallback**, unlike `_load_commercial_formulas()` /
  `_load_thinning_liquids()` (which fall back to a small hardcoded
  dict). Formulas and thinning liquids are reference data — nice to
  have, safely defaulted. The nutrient registry is structural: it
  defines which nutrients the whole app tracks and why (`tier` /
  `on_label`). A silent fallback to a hardcoded Canadian list would
  defeat the entire data-pack design (a US pack that forgot its
  `nutrients.csv` would silently render the Canadian panel instead of
  failing loudly). Do not "fix" this by adding a fallback — see the
  comment at the top of `_load_registry_cached()` in `src/nutrients.py`.
