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

1. **Recipe builder** — search CNF or USDA supplement or add a custom
   food from a nutrition facts label; enter grams per ingredient, added
   water, measured final volume.
2. **Delivery input** — how is the feed given? Syringe bolus (mL ×
   times/day), pump (mL/hr × hours/day), or direct mL/day. The tool does
   the multiplication.
3. **Targets (optional)** — RD enters kcal/day, protein g/day, fluid
   mL/day they already know. No assessment page, no energy equations in
   the app (those are documented in `BUSINESS_CASE.md` Appendix B as
   reference).
4. **Results (live)** — densities, daily totals, adequacy vs targets,
   commercial formula comparator, live recipe adjustment.

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
   numbers side; the RD handles the physical flow side.

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
│   ├── targets/                     # SME-authored DRI / tube-feed targets
│   ├── formulas/                    # commercial formula profiles (CSV)
│   └── thinning_liquids.csv         # thinning liquid presets (CSV)
├── src/
│   ├── __init__.py
│   ├── data_loader.py               # CSV → pandas DataFrames (WORKING)
│   ├── build_parquet.py             # one-time: CSV → parquet (WORKING)
│   ├── models.py                    # @dataclass Ingredient, Recipe, Profile
│   ├── calculator.py               # core math: recipe → nutrient profile
│   ├── measures.py                  # household-measure → grams
│   ├── targets.py                   # load DRI / tube-feed targets
│   └── report.py                    # profile + targets → gap report
├── reference/                        # bug-free reference solutions (per phase; learning project only)
│   ├── __init__.py
│   ├── data_loader.py               # Phase 2 reference (verified working)
│   ├── build_parquet.py             # Phase 2 reference (verified working)
│   └── README.md
├── app/
│   └── streamlit_app.py             # the UI
├── scripts/
│   ├── verify_backend.py            # full backend integration test
│   └── check_app_imports.py         # app import smoke test
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
- [x] Phase 5 targets/report — COMPLETE & VERIFIED (`src/targets.py`, `src/report.py`, `data/targets/dri_adult_default.csv`)
- [x] Phase 6 Streamlit UI — SCAFFOLDED, bug-fixed post-audit (`app/streamlit_app.py`; recipe builder with CNF search + custom food from label, delivery input, targets (including fluid mL/day), live density panel, adequacy report with color-coded status (including a Free water row), dilution what-if with thinning liquid presets, commercial formula comparator, Excel export with a sanitized filename; import-verified 2026-07-15; commercial formulas + thinning liquids externalized to CSV in `data/`; widget session state warning fixed)
- [ ] Phase 7 polish — NOT STARTED

**Pinned issues (to revisit after user testing):**

- **App not matching expectations** — author noted "it's not quite what
  I expected." Specific feedback pending after hands-on testing. Week 2
  iteration will address.
- **Reference data now in CSVs** — commercial formulas live in
  `data/formulas/commercial_formulas.csv` and thinning liquids in
  `data/thinning_liquids.csv`. Both load at startup with hardcoded
  fallbacks. RDs can edit these without touching Python.
- **Design gap: dilution-slider vs. live recipe adjustment** — the code
  currently implements the dilution-slider what-if (add X mL of a
  thinning liquid, see new densities), but `BUSINESS_CASE.md` §7 /
  Appendix A8 describes live recipe adjustment as the goal (no separate
  what-if mode — every edit to the recipe itself updates everything
  instantly). UI iteration pending after user testing. (Deferred by
  design — this is a UI rework, not a bug; roadmap item for Week 3/4.)
- **Fluid target default (2700 mL) needs RD review** — added as part of
  the 2026-07-16 audit's fluid-adequacy fix (see below). This is the
  DRI AI for adult women (2.7 L/day); adult men's AI is higher
  (~3.7 L/day). Edit `data/targets/dri_adult_default.csv` or use the
  custom-targets sidebar input to correct per patient.

**Repo audit fixes (2026-07-16, this session) — resolved, no longer pinned:**

- ~~⚠️ emoji on "Measured final volume" label~~ — removed; label is now
  bold markdown text, `help=` tooltip kept.
- ~~Food search crashes on regex metacharacters~~ — the search box now
  passes `regex=False` to `str.contains`, matching the `find_food()`
  helper.
- ~~No fluid-adequacy row~~ — `data/targets/dri_adult_default.csv` now
  has a `fluid_mL` target; `empty_targets()` and the custom-targets
  sidebar include it; `generate_adequacy_report()` appends a "Free
  water (mL)" row.
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

**Backend verification (2026-07-16): PASSED.** The full backend
integration test lives at `scripts/verify_backend.py` and now runs 9
stages against real CNF data (data load with Parquet/CSV source timing,
household measures, profile calculation, delivery, daily totals,
adequacy report including the Free water row, formula comparison,
density summary, custom-food folding). To re-verify at any time, run:

```
.venv/bin/python scripts/verify_backend.py
```

**Note to AI agents:** do NOT re-verify the backend with long inline
`python -c "..."` commands — use the script above. It exists precisely
so verification is a single short, approvable command.

Last updated: 2026-07-16 (repo audit & repair session, four commits:
(1) P0 repo hygiene — merged CONTEXT.md so it matches
`BUSINESS_CASE.md`'s design framing (competition framing, CNF + USDA SR
Legacy, sweet-spot/drip-test/thickness-ceiling concepts, live recipe
adjustment as the stated goal), retired scaffold-and-fix to "learning
project only", removed references to a non-existent methodology file in
favor of `BUSINESS_CASE.md` Appendices A/B/C, and removed
duplicate/generated documents (`CONTEXT.md</path`, `BUS`, `.docx`,
`.epub`) from git; (2) P1 bug fixes — search-crash regex, fluid-adequacy
row, emoji removal, Excel filename sanitization; (3) P2-1 — moved
custom-food math from the UI into `calculate_profile()`; (4) P2-2 —
`data_loader.py` now prefers Parquet over CSV. Next: Week 3 scope
(pytest suite, CI, Streamlit Cloud deploy, USDA SR Legacy supplement)
and the remaining pinned issues above.)

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

| Data | File |
|---|---|
| DRI targets | `data/targets/dri_adult_default.csv` |
| Commercial formulas | `data/formulas/commercial_formulas.csv` |
| Thinning liquid presets | `data/thinning_liquids.csv` |

Edit the CSV, save, and rerun the app. Changes take effect on next load.

---

## 11. Conventions & gotchas

- The author's existing projects use `SEED = 42` and a single `run.py`
  entry point — this project uses `app/streamlit_app.py` as entry instead.
- macOS `.DS_Store` must be gitignored globally.
- CNF `STD_Error=0` and `Observations=0` often means "derived, not
  measured" — see the CNF user guide PDF for nuances.
- Streamlit re-runs the whole script on every widget interaction; state
  must be preserved via `st.session_state` (a Phase 6 lesson).
- The AI agent's configured working directory may be wider than the VS
  Code workspace; agent self-imposes project-folder-only access.
- `reference/` files use the same path resolution as `src/` (both at
  project root); code can be copied between them without path changes.
