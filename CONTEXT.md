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
to it. (Design reframed 2026-07-08; business case and methodology
documented 2026-07-14 in `BUSINESS_CASE.md` and `METHODOLOGY.md`.)

**App flow — "start with the blender":**

1. **Recipe builder** — search CNF or add a custom food from a nutrition
   facts label; enter grams per ingredient, added water, measured final
   volume.
2. **Delivery input** — how is the feed given? Syringe bolus (mL ×
   times/day), pump (mL/hr × hours/day), or direct mL/day. The tool does
   the multiplication.
3. **Targets (optional)** — RD enters kcal/day, protein g/day, fluid
   mL/day they already know. No assessment page, no energy equations in
   the app (those are documented in `METHODOLOGY.md` §10 as reference).
4. **Results (live)** — densities, daily totals, adequacy vs targets,
   commercial formula comparator, dilution what-if slider.

Three design commitments that follow from "the recipe already works":

1. **Per-mL is the primary lens, not per-recipe.** The outputs that
   matter are densities — kcal/mL, protein/mL, free-water fraction.
   Totals matter only once multiplied by actual daily mL intake.
2. **Final blend volume is a measured input, not computed.** Blending,
   air, and rinse water make volume incalculable from ingredient
   weights — but the user *knows* it (they poured it into a container).
   Ingredients give nutrient totals; measured volume gives the
   denominator.
3. **The core feature is the water trade-off what-if.** "Add 150 mL
   water → kcal/mL drops 1.3 → 1.1 → hitting 1,800 kcal now takes
   1,640 mL/day — within tolerance?" The tool never judges thinness
   (that stays human, hands-on-blender knowledge); it shows what a
   thinning decision *costs*.

It also reports adequacy vs. tube-feeding targets (calories, protein
g/kg, fluid, fibre, sodium, potassium, and the micros that actually go
wrong in BTF: calcium, iron, zinc, vitamin D, B12), plus a
**commercial-formula comparator** (side-by-side: "your BTF at 1,200 mL
vs Peptamen 1.5 at 1,200 mL") — how RDs actually reason about BTF
adequacy.

**Design philosophy — "no black boxes":** Inspired by the EN spreadsheet
by Hui Jun Chew, RD (North York General Hospital, Toronto). Every
calculation visible, every assumption documented, reference data
human-editable, RD clinical judgment always the final authority. See
`BUSINESS_CASE.md` §5 and `METHODOLOGY.md` for the full philosophy.

**Internationalization — "built for Canada, designed for the world":**
The calculator engine is country-agnostic. Each country is a "data pack"
(nutrient database + targets + formula profiles + units config). Canada
first (CNF 2026), then US (USDA), UK (CoFID), Australia (AUSNUT). See
`METHODOLOGY.md` §11 for the data pack specification.

**Out of scope, permanently (fixed caution notes, never computed):**
osmolality (a footnote for this population, not a headline), viscosity /
tube-flow behaviour, nutrient losses from blending and holding, food
safety. **Identity from day one: "for RD use, estimates only"** — not a
family-facing tool.

Built on the **Canadian Nutrient File (CNF) 2026 edition** — a public
Government of Canada dataset of ~5,993 foods × ~173 nutrients, all values
expressed **per 100 g of edible food**. CNF catalogues single/generic
foods, not prepared dishes — a limitation for menu analysis but a
perfect fit for BTF, which is built from single whole foods. CNF's
per-food moisture values make **free water** a first-class computed
output, not an afterthought.

---

## 2. Author & learning context

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
| UI          | Streamlit         | zero-frontend web app; learning bridge to React|
| Persistence | Parquet (pyarrow) | binary, ~20× faster load than CSV              |
| Validation  | pydantic (later)  | typed input models; prep for API stage         |
| Tests       | pytest            | standard, simple                               |
| Formatting  | black + ruff      | auto-style + linter; teaches conventions        |

Deliberately NOT yet included: database, FastAPI, React. Those are the
Phase 6+ graduation path — see §6.

**UI decision recorded 2026-07-08:** the idea-bank doc
(`Projects/CNF_project_ideas.md`) argues for Flask everywhere; per
direct human-mentor advice, *this* project stays **Streamlit**. The
author is not attached either way, so the tiebreak stands. Flask gets
learned later on the lower-stakes Epicure similarity explorer (idea
bank, Project 6b). Don't relitigate without new information.

---

## 4. Folder structure

```
blenderized-tubefeed-calculator/
├── cnf_fcen_all-files-data_2026/   # raw CNF data (DO NOT MODIFY)
├── data/
│   ├── processed/                   # generated parquet (gitignored)
│   └── targets/                     # SME-authored DRI / tube-feed targets
├── src/
│   ├── __init__.py
│   ├── data_loader.py               # CSV → pandas DataFrames (working, verified)
│   ├── build_parquet.py             # one-time: CSV → parquet (working)
│   ├── models.py                    # @dataclass Ingredient, Recipe, Profile (verified)
│   ├── calculator.py               # core math: recipe → nutrient profile (verified)
│   ├── measures.py                  # household-measure → grams (verified)
│   ├── targets.py                   # load DRI / tube-feed targets (verified)
│   └── report.py                    # profile + targets → gap report (verified)
├── reference/                        # bug-free reference solutions (per phase)
│   ├── __init__.py
│   ├── data_loader.py               # Phase 2 reference (verified working)
│   ├── build_parquet.py             # Phase 2 reference (verified working)
│   └── README.md
├── app/
│   └── streamlit_app.py             # the UI
├── scripts/
│   └── verify_backend.py            # full backend integration test (Phases 2–5)
├── tests/
├── notebooks/
│   ├── 00_explore_cnf.ipynb         # data-exploration sandbox
│   └── PHASE2_SPEC.md               # spec, hint list, verification for Phase 2
├── CONTEXT.md                       # this file
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

**Gotcha:** Several CNF CSVs have a UTF-8 BOM (`\ufeff`). Must use
`encoding="utf-8-sig"` in `pd.read_csv()` to strip it, or the first
column name becomes `\ufeffNutrient_Code` and merges silently fail.

---

## 6. Phased build plan

- **Phase 1 — Setup.** venv, requirements.txt, folder skeleton,
  exploration notebook, git init. (No logic; pure plumbing.)
- **Phase 2 — data_loader.py.** Typed, reusable loading functions;
  one-time CSV→parquet build script.
- **Phase 3 — models.py + calculator.py.** @dataclass Ingredient/Recipe;
  Recipe carries ingredients + **added water** + **measured final
  volume**; profile(recipe) → nutrient totals via merge + groupby,
  then **densities** (kcal/mL, protein/mL, free-water fraction) using
  measured volume as denominator.
- **Phase 4 — measures.py.** Household measure → grams via the
  conversion table. Filter to Measure_Type=6 only.
- **Phase 5 — targets.py + report.py.** SME-authored DRI / tube-feed
  target tables; daily adequacy report (needs daily mL intake as input:
  density × mL/day vs targets, % target, status), free-water total,
  commercial-formula benchmark row.
- **Phase 6 — streamlit_app.py.** Editable ingredient table, live
  density panel, adequacy report, **dilution what-if control** (add X mL
  water → new densities → required daily volume vs tolerance),
  export-to-Excel button.
- **Phase 7 — Polish.** Save/load recipes as JSON; pytest suite.
- **Phase 8+ (graduation).** Lift calculator behind FastAPI; build
  React frontend that calls it.

---

## 7. Working method: scaffold-and-fix

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

Bug difficulty ramps: early modules get obvious bugs (typos, wrong
column names); later modules get subtle ones (silent row-drops in
merges, dtype gotchas, off-by-100 unit conversion).

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
- **BOM (Byte Order Mark)** — a `\ufeff` character at the start of some
  UTF-8 files; `encoding="utf-8-sig"` strips it.

---

## 9. Current status

- [x] Phase 1 setup — COMPLETE (venv, requirements.txt, .gitignore, git init, first commit 852cc9e)
- [x] Phase 2 data_loader — SCAFFOLDED (buggy `src/data_loader.py` + `src/build_parquet.py` created; reference solutions in `reference/`; spec in `notebooks/PHASE2_SPEC.md`; exploration notebook in `notebooks/00_explore_cnf.ipynb`; reference verified working 2026-07-01)
- [x] Week 1 planning — COMPLETE (`BUSINESS_CASE.md` and `METHODOLOGY.md` written 2026-07-14; `CONTEXT.md` §1 updated with app flow, design philosophy, and internationalization)
- [x] Phase 3 calculator — COMPLETE & VERIFIED (`src/models.py`, `src/calculator.py`)
- [x] Phase 4 measures — COMPLETE & VERIFIED (`src/measures.py`)
- [x] Phase 5 targets/report — COMPLETE & VERIFIED (`src/targets.py`, `src/report.py`, `data/targets/dri_adult_default.csv`)
- [x] Phase 6 Streamlit UI — SCAFFOLDED (`app/streamlit_app.py` created; recipe builder with CNF search + custom food from label, delivery input, targets, live density panel, adequacy report with color-coded status, dilution what-if with thinning liquid presets, commercial formula comparator, Excel export; import-verified 2026-07-15; commercial formulas + thinning liquids externalized to CSV in `data/`; widget session state warning fixed)
- [ ] Phase 7 polish — NOT STARTED

**Phase 6 pinned issues (to revisit after user testing):**

- **⚠️ emoji on "Measured final volume" label** — the `⚠️` in the
  sidebar label was intended to emphasize that measured volume is the
  critical denominator, but the author found it confusing (looked like
  an error indicator). Remove or replace with a different emphasis
  approach (e.g., `help=` tooltip only, or bold text).
- **App not matching expectations** — author noted "it's not quite what
  I expected." Specific feedback pending after hands-on testing. Week 2
  iteration will address.
- **Reference data now in CSVs** — commercial formulas live in
  `data/formulas/commercial_formulas.csv` and thinning liquids in
  `data/thinning_liquids.csv`. Both load at startup with hardcoded
  fallbacks. RDs can edit these without touching Python.

**Backend verification (2026-07-15): PASSED.** The full backend
integration test lives at `scripts/verify_backend.py` and was run
successfully against real CNF data (all 8 stages: data load, household
measures, profile calculation, delivery, daily totals, adequacy report,
formula comparison, density summary). To re-verify at any time, run:

```
.venv/bin/python scripts/verify_backend.py
```

**Note to AI agents:** do NOT re-verify the backend with long inline
`python -c "..."` commands — use the script above. It exists precisely
so verification is a single short, approvable command. The backend is
done; the next work is Phase 6 (Streamlit UI).

Last updated: 2026-07-15 (Phase 6 Streamlit UI scaffolded in
`app/streamlit_app.py`; recipe builder with CNF search + custom food
from label, delivery input (syringe bolus/pump/direct), targets
(default DRI or custom), live density panel, adequacy report with
color-coded status, dilution what-if with thinning liquid presets
(water/broth/juice/milk/custom), commercial formula comparator, Excel
export. Import-verified. Next: user testing and Phase 7 polish.)

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