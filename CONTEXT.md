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
to it. (Design reframed 2026-07-08; full rationale in
`~/Documents/Projects/CNF_project_ideas.md`, Project 1.)

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
**commercial-formula benchmark row** (e.g. "vs 1.5 kcal/mL standard
formula per 1000 mL") — how RDs actually reason about BTF adequacy.

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
│   ├── data_loader.py               # CSV → pandas DataFrames (scaffolded, buggy)
│   ├── build_parquet.py             # one-time: CSV → parquet (scaffolded, buggy)
│   ├── models.py                    # @dataclass Ingredient, Recipe, Profile
│   ├── calculator.py               # core math: recipe → nutrient profile
│   ├── measures.py                  # household-measure → grams
│   ├── targets.py                   # load DRI / tube-feed targets
│   └── report.py                    # profile + targets → gap report
├── reference/                        # bug-free reference solutions (per phase)
│   ├── __init__.py
│   ├── data_loader.py               # Phase 2 reference (verified working)
│   ├── build_parquet.py             # Phase 2 reference (verified working)
│   └── README.md
├── app/
│   └── streamlit_app.py             # the UI
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
- [ ] Phase 3 calculator — NOT STARTED
- [ ] Phase 4 measures — NOT STARTED
- [ ] Phase 5 targets/report — NOT STARTED
- [ ] Phase 6 Streamlit UI — NOT STARTED
- [ ] Phase 7 polish — NOT STARTED

Last updated: 2026-07-08 (design reframe adopted into §1, §3, §6 from
`Projects/CNF_project_ideas.md`; Phases 1–2 unaffected — the reframe
changes the calculator's *outputs*, not the data plumbing)

---

## 10. Conventions & gotchas

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