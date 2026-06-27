# Blenderized Tube Feed Calculator — Project Context

> This file is the single source of truth for this project.
> It is written for two audiences: (1) the human author/learner, and
> (2) any AI coding agent picking up the project mid-stream.
> Update it whenever the plan, stack, or status changes.

---

## 1. Project goal

A clinical nutrition tool that lets a dietitian enter a recipe of real
foods (by household measure or grams) and returns the full nutrient
profile of the blend, plus a check against tube-feeding nutrient targets
(calories, protein g/kg, fluid, fibre, sodium, potassium, key
micronutrients), flagging shortfalls.

Built on the **Canadian Nutrient File (CNF) 2026 edition** — a public
Government of Canada dataset of ~5,993 foods × ~173 nutrients, all values
expressed **per 100 g of edible food**.

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
│   ├── data_loader.py               # CSV → pandas DataFrames
│   ├── build_parquet.py             # one-time: CSV → parquet
│   ├── models.py                    # @dataclass Ingredient, Recipe, Profile
│   ├── calculator.py               # core math: recipe → nutrient profile
│   ├── measures.py                  # household-measure → grams
│   ├── targets.py                   # load DRI / tube-feed targets
│   └── report.py                    # profile + targets → gap report
├── app/
│   └── streamlit_app.py             # the UI
├── tests/
├── notebooks/
│   └── 00_explore_cnf.ipynb         # data-exploration sandbox
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
| Measure_Name.csv              | ~1,496  | Measure_Code (PK), description ("1 cup")  |
| Measure_Weight_Conversion.csv | ~29,868 | Food_Code + Measure_Code → grams          |
| Measure_Type.csv              | 3       | 3=Refuse, 6=User-defined, 9=Yield         |
| CNF_Food_Group.csv            | 23      | group code → description                 |

Key arithmetic: `nutrient_from_ingredient = grams × (amount / 100)`.

---

## 6. Phased build plan

- **Phase 1 — Setup.** venv, requirements.txt, folder skeleton,
  exploration notebook, git init. (No logic; pure plumbing.)
- **Phase 2 — data_loader.py.** Typed, reusable loading functions;
  one-time CSV→parquet build script.
- **Phase 3 — models.py + calculator.py.** @dataclass Ingredient/Recipe;
  profile(recipe) → {nutrient_code: amount} via merge + groupby.
- **Phase 4 — measures.py.** Household measure → grams via the
  conversion table. Filter to Measure_Type=6 only.
- **Phase 5 — targets.py + report.py.** SME-authored target tables;
  gap report (amount vs target, % target, status).
- **Phase 6 — streamlit_app.py.** Editable ingredient table, live
  nutrient panel, gap report, export-to-Excel button.
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

---

## 9. Current status

- [x] Phase 1 setup — COMPLETE (venv, requirements.txt, .gitignore, git init, first commit 852cc9e)
- [ ] Phase 2 data_loader — NOT STARTED
- [ ] Phase 3 calculator — NOT STARTED
- [ ] Phase 4 measures — NOT STARTED
- [ ] Phase 5 targets/report — NOT STARTED
- [ ] Phase 6 Streamlit UI — NOT STARTED
- [ ] Phase 7 polish — NOT STARTED

Last updated: 2026-06-26

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

