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

1. **Feed Recipes tab — blends** — a blend selector (new/rename/delete) over
   an open-ended list of recipe formulations; search CNF (three-layer
   search: all-words, typo-tolerant, synonyms) or add a custom food
   from a nutrition facts label (g or mL basis); enter grams (or mL) per ingredient and measured final
   volume for the selected blend. No separate "added water" field —
   water is an ordinary ingredient, flagged "counts as fluid" like any
   other liquid. A blend is scale-free (a *formulation*) — it doesn't
   know or care how many times it gets made; see the Intake Record
   below for that.
2. **Daily Intake Record tab — the Intake Record (formerly the Intake
   tab; see the 2026-07-20 three-tab restructure entry in §9)** — replaces the old
   delivery-schedule input. One chronological list of rows — tube feed
   (blend / commercial formula / water flush) and oral food/drink — each
   with an optional
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
3. **Nutrition Targets tab — targets (optional)** — RD enters kcal/day, protein g/day, fluid
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

**Two constraints at once — thin enough to flow, dense enough to nourish:**
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
first (CNF 2026), then US, UK, Australia. Packs are selected whole,
never blended together — see §9's USDA entry for why.
See `BUSINESS_CASE.md` Appendix C for the data pack specification.

**Out of scope, permanently (fixed caution notes, never computed):**
osmolality (a footnote for this population, not a headline), viscosity /
tube-flow behaviour, nutrient losses from blending and holding, food
safety. **Identity from day one: "for RD use, estimates only."**

**Data:** Built on the **Canadian Nutrient File (CNF) 2026 edition** —
a public Government of Canada dataset of ~5,993 foods × ~173 nutrients,
all values expressed **per 100 g of edible food**. CNF is itself a
merged database — 55.4% of its values come verbatim from USDA, already
vetted and localised by Health Canada (see §9, 2026-07-30). A separate
USDA supplement was investigated and rejected. Custom food entry from
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
| Deployment  | Streamlit Community Cloud | free, public URL, auto-deploys from GitHub. **LIVE since 2026-07-23 at <https://btfcalc.streamlit.app>** (repo `greywhitebinary/blenderized-tubefeed-calculator`, branch `main`, main file `app/streamlit_app.py`). See §11 for version-skew gotchas. |

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
├── src/                              # NEVER imports streamlit — that is what
│   │                                 # makes everything here unit-testable
│   ├── __init__.py
│   ├── data_loader.py               # CSV → pandas DataFrames
│   ├── build_parquet.py             # one-time: CSV → parquet
│   ├── models.py                    # @dataclass Ingredient, Recipe, NutrientProfile
│   ├── nutrients.py                 # nutrient registry + thinning-liquid presets
│   ├── calculator.py                # core math: recipe → nutrient profile
│   ├── intake.py                    # Intake Record aggregation; blend naming; fluids rule
│   ├── measures.py                  # household-measure → grams; recipe-card grouping
│   ├── food_search.py               # the three-layer CNF search, and find_food()
│   ├── label_extract.py             # nutrition-label photo → per-100 g values
│   ├── recipe_io.py                 # recipe ↔ .xlsx
│   ├── day_io.py                    # a whole record ↔ .xlsx
│   ├── targets.py                   # the blank targets scaffold (no defaults, ever)
│   └── report.py                    # totals + targets → adequacy tables, comparator
├── reference/                        # bug-free reference solutions (per phase; learning project only)
│   ├── __init__.py
│   ├── data_loader.py               # Phase 2 reference (verified working)
│   ├── build_parquet.py             # Phase 2 reference (verified working)
│   └── README.md
├── app/                              # the Streamlit layer — see MAINTAINING.md,
│   │                                 # "Where new code goes"
│   ├── __init__.py
│   ├── streamlit_app.py             # the page: three tabs, in the order they appear
│   ├── add_food.py                  # the reusable add-a-food component
│   ├── ui_common.py                 # _note() and _narrow()
│   └── styles.css                   # the stylesheet (plain CSS, not a Python string)
├── scripts/                          # check_*.py drive the real app via AppTest;
│   │                                 # GitHub Actions runs every one on each push
│   ├── check_app_imports.py         # the app imports without raising
│   ├── check_blend_switching.py     # switching blends keeps your work
│   ├── check_blend_without_volume.py # a volume-less blend degrades, never crashes
│   ├── check_day_save_load.py       # a saved record round-trips
│   ├── check_export_sheets.py       # near-identical blends stay distinguishable
│   ├── check_food_search.py         # search is wired up; the duplicate-food note
│   ├── check_label_photo_fill.py    # label photo → filled custom-food form
│   ├── check_recipe_record.py       # per-blend flow test + named chart note
│   ├── check_tab_restructure.py     # every section is where it should be
│   ├── verify_backend.py            # full backend integration test
│   └── trace_calculation.py         # hand-checkable calculation + registry trace
├── tests/                            # ~236 unit tests over src/, run in ~1 second
├── notebooks/
│   ├── 00_explore_cnf.ipynb         # data-exploration sandbox
│   ├── 01_learn_cnf.ipynb           # guided CNF learning notebook (9 parts, executed)
│   └── PHASE2_SPEC.md               # spec, hint list, verification for Phase 2
├── BUSINESS_CASE.md                  # Week 1 deliverable + full methodology
├── CONTEXT.md                       # this file (internal project management)
├── FEED_LOG_REWORK.md                # design doc for the Intake Record model;
│                                     #   cited by ~30 comments in src/ — live reference,
│                                     #   not a finished plan
├── MAINTAINING.md                    # day-to-day workflows; where new code goes
├── README.md                         # newbie-friendly setup + usage guide
├── requirements.txt
└── .gitignore
```

**`HANDOFF.md` was retired 2026-08-17.** It was a paste-ready prompt for
handing the project to a different AI agent (Cline + GLM-5.2), written
2026-07-19 and untouched since 2026-07-31 while everything around it moved.
Nothing in `src/` or `app/` ever cited it. Older §9 entries below still
refer to it, and are left as written — they are a record of what was true
at the time. To read it: `git log --diff-filter=D -- HANDOFF.md` for the
commit that removed it, then `git show <commit>^:HANDOFF.md`.

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

#### The official brief, verbatim (recorded 2026-07-31)

The organiser's wording, kept here because **the author's own roadmap
below has already diverged from it once**: her Week 1 plan called Week 3
"Tests, CI, public deploy, **USDA**", while the real brief said nothing
about adding data and asked whether the app could be *maintained*.
Following the roadmap literally would have spent that week building the
feature that was ultimately deleted. Where the two disagree, this wins.

> — **Week 1 — Plan It:** this week is planning only. Your concept, your
> market research, your requirements. No code yet. Plan it right and the
> build barely takes an afternoon.
> — **Week 2 — Core Feature Complete:** now you build it end-to-end.
> Your main function works, start to finish.
> — **Week 3 — Build It to Last:** refinement and a real development
> pipeline, so it holds up long-term — maintainable and supportable, not
> held together with tape.
> — **Week 4 — Ship + Pitch:** the final live app + a 2–3 minute demo,
> pitched like a real product.

**Week 4 therefore requires a 2–3 minute video.** Week 2 was accepted as
written paragraphs and `drafts/WEEK2_POST.md`'s video script went unused;
Week 4 is not optional in the same way. Note "**pitched like a real
product**" — a tab-by-tab feature tour (the shape of the unused Week 2
script) is the wrong format. A pitch leads with the problem and who has
it.

#### The author's roadmap

| Week | Deliverable | What gets built |
|---|---|---|
| **1 — Plan It** | `BUSINESS_CASE.md` posted publicly | Concept, market, requirements, methodology |
| **2 — Core Feature** | Working Streamlit app | Build calculator, measures, targets/report, Streamlit UI |
| **3 — Build to Last** | Tests, CI, public deploy | 159 pytest tests + 8 CI-gated checks, GitHub Actions with blocking lint, dev/runtime dependency split, Streamlit Cloud (done 2026-07-23), recipe record (multi-blend files), water ledger, three-layer food search, save/reopen a day, label-photo entry |
| **4 — Ship + Pitch** | Live app + write-up | Polish from RD pilot feedback, validation appendix, AI-assist features (label-photo extraction, PDF → formulas), possible JSON save/load |

> **One definition of Week 3.** This row, `BUSINESS_CASE.md` §12, and
> `HANDOFF.md` Phase 2 (retired 2026-08-17) previously disagreed about
> whether the AI-assist
> features belonged to Week 3. Settled 2026-07-30: **they are Week 4.**
> Week 3 is durability plus the recipe record and the food-search
> rework. Custom food entry from a
> nutrition-facts label (typed by hand) already shipped in Week 2 — it is
> the *photo* extraction that moved.

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
- **The two constraints** — a workable recipe is both "thin enough to
  flow" (the RD's drip test) and "dense enough to nourish" (the app's
  density calculation). Called "the sweet spot" until 2026-08-17, when
  the author retired the phrase as marketing language.
- **Drip test** — hands-on check: pull blended food in a 50–60 mL
  syringe without resistance (AHS 2021). The tool can't replace this.
- **Thickness ceiling** — BTF recipes should be at most as thick as
  Resource 2.0; thicker won't flow through a tube.

---

## 9. Current status

**Competition-week framing (see `BUSINESS_CASE.md` §12 for the 4-week plan):**

- [x] Week 1 — Plan It — COMPLETE (`BUSINESS_CASE.md` posted; `CONTEXT.md`
  merged and aligned with it as of this repo audit)
- [x] Week 2 — Core Feature — **COMPLETE** (2026-07-30). Calculator,
  measures, targets/report, and the Streamlit UI are all built and
  backend-verified; the app is deployed and live at
  <https://btfcalc.streamlit.app>; the Week 2 write-up was submitted as
  written paragraphs (no demo video was required, so the video script in
  `drafts/WEEK2_POST.md` is moot and describes a superseded example day).
  See the phase-level record below for detail. **The UI is PINNED at the
  author's request** — see the pinned-issues list below before touching
  layout.
- [ ] Week 3 — Build to Last — IN PROGRESS (2026-07-30; first batch landed
  in commits 4aa69d7, b1453b5, e9b4f33, 4d50166). Sub-items:
  - [x] **Streamlit Community Cloud deploy — DONE 2026-07-23.** Live at
    <https://btfcalc.streamlit.app>, auto-deploying from `main`. See the
    deploy entry in this section and §11 for the version-skew gotchas.
  - [x] **pytest suite — DONE** (2026-07-30, commits 4aa69d7 + b1453b5).
    **57 tests, 0.07s, no CNF load** — small hand-built fixture
    DataFrames only; `verify_backend.py` keeps the real-data integration
    role. `tests/conftest.py` + `test_calculator.py` (15) +
    `test_intake.py` (12) + `test_nutrients.py` (13) + `test_report.py`
    (13) + `test_targets.py` (5). Two things worth knowing about how
    they're written: (1) the tests read the **registry at test time**
    rather than hardcoding a nutrient list, so they survive an RD editing
    `nutrients.csv`; the three deliberately frozen values (sodium's code
    307 and its UL `target_type`, magnesium/phosphorus having no target)
    are commented with which documented decision each one guards.
    (2) The over-draw bug is pinned **structurally**, not just
    numerically — `test_intake.py` asserts the *absence* of any
    over-draw field on `IntakeTotals` by checking the dataclass's field
    set, so re-adding a batch-mismatch flag fails the suite rather than
    passing quietly. Neither agent found a backend bug; behaviour matched
    the documentation throughout.
  - [x] **GitHub Actions CI — DONE** (2026-07-30, commit e9b4f33).
    `.github/workflows/ci.yml`, two jobs. Fast job on push/PR: pytest +
    ruff + black. **Both lint steps are `continue-on-error` on purpose**
    — black would reformat 22 of 25 files (~1,571 lines) and that diff is
    not approved, so failing CI on day one for pre-existing style would
    be noise, not signal. Drop `continue-on-error` once the reformat
    lands. Separate `verify-backend` job on manual dispatch + weekly
    schedule (not every push): the CNF CSVs **are** committed (13 tracked
    files, ~14 MB history) so a runner genuinely can run it, but a
    565k-row parse shouldn't gate every push. Note `"on":` is quoted in
    the YAML — bare `on` parses as boolean `true` under YAML's default
    resolver.
  - [x] **Runtime/dev dependency split — DONE** (2026-07-30, commit
    e9b4f33). Runtime is now pandas + streamlit (pin intact) + openpyxl.
    **pyarrow moved to dev, and the reasoning matters:** `data_loader`
    prefers a Parquet cache under `data/processed/`, but that directory
    is gitignored with zero tracked files, so the deployed app — always a
    fresh clone — has **never once called `read_parquet`** and has been
    on the CSV fallback since launch. The dependency was already dead
    weight in production. **The local case is the reverse and is a
    trap:** a local checkout usually *does* have the cache, and
    `data_loader.py:53-54` calls `read_parquet` as soon as those files
    exist with no `try`/`except`, so a runtime-only `pip install` would
    `ImportError` on startup. `requirements.txt` now opens with a pointer
    to install `requirements-dev.txt` locally. **Open, needs author
    approval:** a two-line `try/except ImportError` fallback to CSV in
    `data_loader` removes the sharp edge entirely, but touches verified
    backend code, so it was not done unasked.
  - [x] **`scripts/check_tab_restructure.py` — FIXED** (2026-07-30,
    commit e9b4f33). One character: `split(" — ", 1)[-1]` → `[0]`, since
    1f3af36 moved the feed name to *before* the separator. Assertion
    strength unchanged. Now prints `=== TAB RESTRUCTURE APPTTEST
    PASSED ===`.
  - [x] **Formula rows contribute `nutrient_coverage` — DONE**
    (2026-07-30, commit e00320f). A formula now counts as one product
    instance per tracked nutrient: `(1,1)` when its `formulas.csv` row
    discloses it, `(0,1)` when it doesn't — never `(0,0)` (which would
    make the gap invisible) and never a fabricated 0. **Behaviour change
    worth knowing:** on a formula-only day, a nutrient the product
    doesn't disclose (fibre, for Resource 2.0) is now hidden from the
    adequacy table and **named in the footnote**, where before it stayed
    visible with nothing behind it. Verified against a real 1000 mL
    Resource 2.0 day. **Open follow-up:** `report.py::_coverage_text`
    renders "N/M **ingredients**", but a formula adds 1 to the
    denominator regardless of how many ingredients are in the product —
    "sources" is now the accurate word. Left for the author.
  - [x] **`thinning_liquids.csv` pack-awareness — DONE** (2026-07-30,
    commit c4da8a1). `_load_thinning_liquids(pack=...)` via a new
    `_thinning_csv_path()`; the last loader reading a hardcoded `canada`
    path. Inert until a second pack exists.
  - [x] **Recipe record — DONE** (2026-07-30, commits a011cfb, 59d00f8).
    Save a blend — ingredients, measured volume and flow test — as a
    two-sheet `.xlsx` you keep; load one back. Author's framing: *the
    calculator computes, the record remembers.* See the entry below.
  - [x] **Water ledger — DONE** (2026-07-30, commit 232dc8c). Every
    water source on its own line. See the entry below.
  - [x] **Dilution What-If narrowed to water — DONE** (2026-07-30,
    commit c4da8a1). See the entry below.
  - [x] **USDA SR Legacy supplement — CLOSED. Author rejected it
    2026-07-30: "shall we remove USDA entirely... it seems like combining
    this database is more trouble than it's worth."** Both proposal
    documents and the candidate CSV were deleted from the working tree;
    they remain in git history at 4d50166 (`USDA_SUPPLEMENT.md`) and
    8210d52 (`USDA_CANDIDATES.md`, `data/usda_candidates.csv`). **Do not
    re-open without the author's say-so** — it looks like an obvious idea
    and will be proposed again. Three findings closed it:
    - **CNF already IS a merged database.** Every row of
      `Nutrient_Amount.csv` carries a `Nutrient_Source_Code`. Of 565,409
      values: **55.4% are "No change from USDA" (code 0)**, 13.5%
      analyzed in a Canadian government lab, 2.6% calculated from USDA,
      2.1% imputed from a similar USDA food. Health Canada already did
      this merge and localised the fortification. Doing it again, from
      outside, would do it worse.
    - **The gap was a search bug, not a data gap. 1,628 → ~12 foods**
      once two method faults were fixed. (a) Substring matching against
      CNF descriptions invents gaps, because CNF inverts and prefixes its
      names — searching "wild rice" returns zero while CNF holds it as
      "Grains, rice, wild, dry". (b) A join bug: CNF's `USDA_NDB_Code`
      is inconsistently zero-padded, so string comparison found only
      3,333 links to SR Legacy where int-normalising recovers 4,448.
      Both faults *understated* CNF's existing coverage. Of the 1,568
      surviving mechanically, 73% are fine-grained butchery cuts. The
      real shortlist is ~12, led by four Mexican cheeses CNF genuinely
      lacks (queso fresco/blanco/seco/cotija — verified: CNF has exactly
      three, anejo/asadero/chihuahua, of 328 cheese entries). These are
      handled by the existing custom-food-from-label form.
    - **Merging nutrient databases hides unit mismatches.** Vitamin A as
      RAE vs RE vs IU (3–12× apart), folate as DFE vs food folate,
      niacin as NE vs preformed, vitamin E as α-tocopherol vs α-TE. A
      missing value is visible in the UI; a silently mismatched unit is
      not. This is the clinical argument, and it is the strongest one.
    - **Indigenous foods — checked, at the author's explicit request.**
      All 94 unlinked rows in USDA's "American Indian/Alaska Native
      Foods" category were reviewed. **Zero made the shortlist.** CNF's
      own "Game meat, Indigenous" series is richer for shared species —
      caribou 20 entries, seal 24, moose 15, walrus 12, plus beluga,
      narwhal, muktuk, arctic char and cloudberry/bakeapple that USDA
      doesn't emphasise. USDA's genuinely novel rows are US tribal dishes
      (Navajo, Hopi, Apache, Klamath) with no Canadian equivalent. The
      author's instinct to check was correct; the answer is that Health
      Canada already did this work, better, for Canada.
    - **Consequence for the roadmap:** a US edition is a **separate data
      pack selected whole** (Appendix C), never a blend. Packs are
      switched, not merged: mixing sources *within* one food produces a
      number no RD can defend and no one can trace. Revisit after Week 4.
    - `data/raw/usda/` (69 MB, gitignored) is a local download only. It
      never reached the repo or Streamlit Cloud, and nothing reads it.
      Left on disk for the author to delete at her convenience.
  - [x] **Food search rework — DONE** (2026-07-30). `src/food_search.py`,
    `data/packs/canada/food_synonyms.csv`, `tests/test_food_search.py`,
    `scripts/check_food_search.py`. The direct consequence of the USDA
    finding: the fix for "the food isn't in there" is search, not more
    data. The old box was `str.contains(term, regex=False)` — a literal
    substring, whole phrase, in order — which returned **zero results**
    for "wild rice" and "greek yogurt", and found 2 of the 22 ground
    beef entries. Three layers now, stopping at the first that hits:
    - **Layer 1 — all words, any order, prefix-matched.** "wild rice" →
      "Grains, rice, wild, dry". Also reads CNF's own
      `Alternate_Description_EN` (populated for 1,384 foods), which the
      old search ignored entirely — that column is why "hamburger" now
      finds ground beef.
    - **Layer 3 — curated synonyms**, runs *before* fuzzy: a human
      statement about this database outranks a machine's spelling
      hunch. 22 rows, every one verified against real CNF. Only for
      terms CNF holds under neither spelling (courgette → zucchini,
      prawns → shrimp, mangetout → peas edible-podded).
    - **Layer 2 — typo tolerance**, per word, via stdlib `difflib`
      against CNF's 2,510-word vocabulary. **No new dependency**: it was
      measured at ~1.3 ms, so `rapidfuzz` was not worth the deploy risk
      (§11 pin history). Whole-corpus difflib was both slower *and*
      worse — token-level is what works.
    - **`FUZZY_CUTOFF = 0.84` is measured, not guessed, and is a safety
      setting.** At the 0.75 it started on, the search confidently
      answered "skyr" with a **Skor chocolate bar**, "maize" with a
      **Marie biscuit**, "rocket" with spiny lobster and "prawns" with
      animal crackers. Scoring real typos (brocolli→broccoli 0.875,
      yoghurt→yogourt 0.857, chikpeas→chickpeas 0.941; lowest wanted
      0.857) against words CNF lacks (maize→marie 0.800, prawns→paws
      0.800, skyr→skor 0.750; highest unwanted 0.800) leaves a clean
      gap. **Do not lower it** — `test_words_cnf_lacks_return_nothing_
      rather_than_nonsense` guards it.
    - **Search ranks; it never auto-selects.** Same rule as AI label
      extraction (§11): a substitution is allowed to be wrong only
      because it is never silent. Every reinterpretation prints a
      caption ("No exact match — showing results for …").
    - **Two synonyms proposed from memory were wrong and measurement
      caught both**: CNF writes "sweet potato" as two words (a
      `sweetpotato` row would have found 0 foods instead of 23), and
      "oatmeal" already finds 65 where "oats" finds 51 — the synonym
      would have *discarded* results. A third, `peppers sweet`, failed
      because CNF uses the singular "Pepper, sweet". Hence
      `test_every_synonym_resolves`, which loads real CNF and asserts
      every row still resolves. **A synonym table is data that rots
      silently; that test is the only thing that notices.**
    - The best argument for layer 3 is `bicarbonate of soda`: without
      its row, layer 2 spell-corrects it to "carbonated soda" and
      returns **club soda and cream soda** — a soft drink where the RD
      asked for a leavening agent.
    - Tests: 80 → **106**. Checks: 5 → **6** (new
      `scripts/check_food_search.py`, an AppTest that types into the
      real box against real CNF — the module being correct and the app
      being *wired* to it are separate claims, and the old search was a
      perfectly correct substring match).
    - **Ranking: headword tier added 2026-08-07** (RD pilot feedback:
      "egg" offered "Bagel, egg" before chicken eggs; "milk" offered
      "Cracker, milk" before fluid milk). Root cause: after the
      desc-vs-alt and whole-word-vs-prefix tiers tied, *description
      length* was the only tiebreaker, so a short composite food beat
      the basic food. CNF files foods headword-first, so the new third
      tier ranks a row whose FIRST word a query word prefixes ("Milk,
      fluid, ..." IS milk) above one that merely contains the word
      deeper in ("Cracker, milk" CONTAINS milk). The tier sits BELOW
      the whole-word tier on purpose: a prefix-only headword
      ("Eggplant, raw" for "egg") must not outrank a real whole-word
      match ("Roll, dinner, egg"). Pinned by two fixture tests plus
      `test_real_cnf_basic_foods_rank_above_contains_foods` (real-CNF
      guard, skip-gated like the synonym guard). Debugging aid:
      `scripts/try_food_search.py "<query>"` prints each result's rank
      with the sort-key tiers that produced it. Tests 154 → **157**.
    - **Ranking round 2: inverted-filing tier + 3 synonyms, same day.**
      The headword tier alone still let the DISH "Egg Benedict" (12
      chars) lead "egg" over every real egg entry — length cannot tell
      a short dish name from a short commodity. New tier 4: CNF files
      commodities inverted ("Egg, chicken," — comma straight after the
      headword) but dishes as spoken ("Egg Benedict", "Eggnog"), so
      inverted filings rank above natural-language names sharing the
      headword; it sits BELOW the headword tier (an inverted
      contains-food like "Bagel, egg" still loses to a headword dish).
      Author's reasoning, recorded: *"for prepared foods people will
      type something specific like chicken a la king."* A 26-query
      spelling audit the same session found CNF's own parenthetical
      variants (donut, catsup, cilantro, swede, pierogi) and the fuzzy
      layer (omelette→omelet, pitta→pita) already cover nearly
      everything; the three genuine gaps became synonym rows:
      **houmous→hummus, liquorice→licorice, perogies→pierogi**
      (19 → 22 rows; the resolve/shadow guards cover them
      automatically). A curated "common preparation" ranking (boiled
      egg above dried yolk) was considered and REJECTED by the author
      as unmaintainable — nothing in CNF's data encodes commonness, and
      the search never auto-selects, so a scroll is the worst cost.
      Tests 157 → **159**.
  - [x] **Multi-recipe files + the pipeline holes — DONE 2026-07-30.**
    - **Recipe files now hold every blend** (format v2, commit 3cf3bd9).
      Author: *"if there is an option to add multiple BTFs... the output
      should be able to provide all of these recipes."* Correct — the app
      always held several blends and the export wrote only the selected
      one. The Recipe sheet gets one row per blend; every Ingredients row
      is tagged with `Recipe id` + `Recipe name`. **Matched on the id,
      not the name**, because blend names are free text and two can
      collide. A multi-recipe file arriving with no link column is
      **REFUSED, not merged** — pooling two recipes would invent a feed
      nobody wrote with a plausible kcal/mL, the same failure family as
      FEED_LOG_REWORK.md §6.2. v1 files still load, verified against a
      real file saved from the deployed app before the change.
    - **Bug the new tests caught:** with several recipes where one has a
      flow-test date and another doesn't, pandas types the column as
      datetime and fills the blank with `pd.NaT` — which subclasses
      `datetime`, so the old `isinstance` check accepted it and a "no
      flow test" recipe came back carrying a date-shaped non-date. Same
      trap as blank cells reading back as the literal `"nan"`. Fixed with
      `_coerce_date()`. **Impossible in a single-recipe file**, which is
      why it surfaced only now.
    - **All six checks now run in CI** (commit 61558e4). CI ran pytest
      and nothing else, so the other five ran only when someone
      remembered — *the exact failure this repo already suffered* when
      `check_tab_restructure.py` sat broken for a week. The old workflow
      parked `verify_backend.py` on a weekly schedule as "slow"; measured
      from a cold checkout with no Parquet cache it is **0.53s**, and
      every check is under two seconds. The weekly run is kept for a real
      reason instead: `pandas` floats in requirements.txt, and a floating
      dependency is how the Streamlit 1.60 deploy broke.
    - **Lint now gates.** Both steps carried `continue-on-error`, so 61
      findings never failed anything. 25 were fixed (f-strings without
      placeholders, unused imports removed from *both* branches of the
      try/except import fallbacks, one unused variable); the rest are
      configured with the reason recorded — E501 defers to black, E402 is
      per-file for the files that must put code above imports, notebooks
      are excluded as learning material.
  - [x] **Three author decisions — CLOSED 2026-07-30.**
    - **Assumed zeros: investigated, NOT a defect — do not "fix" it.**
      Reversal of a recommendation I had given her the previous message,
      on measurement. CNF's 65,887 "assumed zero" values sit almost
      entirely on foods that genuinely contain none of the nutrient:
      fibre is assumed-zero in 94% of Lamb/Veal/Game, 91% of Finfish,
      78% of Poultry — and in **0%** of Vegetables, Fruits, Grains,
      Legumes and Nuts. In the real example blend the two assumed-zero
      fibre ingredients are canola oil and municipal water. Treating
      code 12 as "unknown" would flag every meat/fish/oil ingredient and
      never fire where it matters — a warning that cries wolf teaches
      the RD to ignore the coverage note, so it then fails silently on
      the day it is real. Full evidence: `HANDOFF.md` item 8
      (retired 2026-08-17; `git log --diff-filter=D -- HANDOFF.md` finds it).
    - **`"N/M ingredients"` → `"N/M sources"`** in
      `report.py::_coverage_text`. The denominator counts three
      different kinds of thing and only one is an ingredient: the real
      example day reads **36/40** — 4 blend feeds × 9 ingredients, + 3
      formula feeds, + 1 banana — for a day involving 11 distinct foods.
      **The number is deliberately unchanged**; counting a blend once
      per feed weights the note by actual contribution, which is the
      question being asked. Only the noun was wrong.
    - **Excel export blend sheets are prefixed `BTF `.** The tab was
      named only after the blend, sat between "Intake Record" and
      "Adequacy", and did not announce itself — the author opened her
      own export, saw the macro sheets, and concluded the ingredients
      weren't in the file. Her suggested `BTF:` **would have crashed the
      export**: Excel rejects `: \ / ? * [ ]` in a sheet title outright
      (openpyxl raises `ValueError`), so the space form is used instead.
      31-character cap still applies, with the blend name keeping the
      budget.
  - [x] **Save and reopen a whole day — DONE 2026-07-31** (48ad6b3).
    `src/day_io.py`, `tests/test_day_io.py`,
    `scripts/check_day_save_load.py`. Closing the tab used to lose
    everything. A file, not an account: the deploy has no per-user
    storage and holds no patient data by design, which is what makes
    public deployment safe. **The Custom foods sheet is the non-obvious
    part** — a label-entered food lives only in session state under a
    negative code, and both blend ingredients and oral rows reference it,
    so a file without those values reloads a blend whose protein and
    sodium have quietly shrunk. **Loading REPLACES and confirms first**
    (recipes still load alongside); merging two days would produce an
    intake record that never happened. The apply step runs at the top of
    the script because it writes widget-owned keys (§11).
  - [x] **Label photo → NFt form — DONE 2026-07-31** (854a82c, 24e74c0,
    a723603, fe684b0, 2e9ac91). The flagship AI feature, shipped under
    the rule agreed *before* it existed: the cap ships in the same
    commit, and the photo fills the form rather than writing to a blend.
    - **Never fabricates.** A nutrient with no line on the label comes
      back ABSENT, never 0; a printed "0 g" IS kept. Schema and prompt
      are generated from the registry, so the 13 fields cannot drift
      from the form they fill.
    - **The cap, all three parts:** console spend limit (the author's,
      and the only one that survives a bug here), 10 per session plus a
      shared 200/day via `cache_resource` (a per-session limit alone is
      beaten by a second tab), and a visible per-use notice.
    - **The key** is read in one place from `st.secrets`. Streamlit runs
      server-side so it never reaches the browser; API exception text is
      swallowed rather than shown, since it can carry request details.
      Without a key the control does not render and the app is unchanged.
    - **Three bugs made every call fail**, all mine, all in the request:
      the undated model alias `claude-haiku-4-5` (this account resolves
      `claude-haiku-4-5-20251001` — `client.models.list()` is free and is
      the authority); an `enum` on a nullable field (400); and 17
      nullable fields against a hard limit of 16 (400). The nullable
      budget now goes entirely to nutrients — the other four use
      sentinels a real label cannot produce, safe for the same reason 0
      is a safe "no target": **a sentinel only works when the sentinel
      value is impossible as a real answer.**
    - **Then it crashed the app on first success** — writing the basis
      radio's state after that widget existed (§11, in a file that
      documents §11). Fixed by staging and applying at the top of the
      component, not by reordering.
    - **And the form never cleared after adding**, so a second label
      inherited the first food's numbers in any field not overwritten —
      Ensure's sodium into Boost, invisibly. Now wiped via the same
      staged-flag pattern.
  - [x] **Two AI-assist features REJECTED 2026-07-31** on the author's
    clinical objections; reasoning kept in `BUSINESS_CASE.md` §7.
    - *Plain-words recipe matching* ("a scoop of oats"). Her objection:
      *"for an RD a scoop of oats would be terrible for a tube feed
      recipe."* The document's own value proposition is **"Actual grams,
      not fixed servings"** — a feature whose input is "a scoop" invites
      imprecision into the one calculation that must be precise. Kept
      from it: the COOKED-preparations constraint for any future matcher.
    - *Semantic food search.* Proposed with the example "something to
      thicken a blend" — which is a suggestion engine, not a search box,
      and thickness is in the same document's **Out of scope** list
      (viscosity is not computable from nutrient data; the drip test is
      the RD's domain). It was added to that file earlier in the same
      week while rewriting §8, contradicting a section three paragraphs
      down.
  - [x] **CI: eight checks + blocking lint — DONE 2026-07-31** (61558e4).
    CI ran pytest and nothing else, so five checks ran only when someone
    remembered — *the exact failure this repo already suffered*. All
    eight now gate every push. `verify_backend.py`'s "too slow" note was
    wrong when measured: **0.53s** from a cold checkout.
  - [x] **CI went red for three commits — pyarrow 25 SEGFAULTS**
    (37fcfc8, 2026-07-31). `requirements-dev.txt` had unbounded
    `pyarrow>=15.0`; a fresh machine resolved 25.0.0 while the author's
    laptop had 24.0.0. Three AppTest checks died with **exit 139 and no
    traceback**, inside `libarrow`'s `PoolBuffer::Reserve` when Streamlit
    converts a DataFrame to Arrow for display. Now `<25.0`.
    - **pytest would never have caught it** — the crash is in Streamlit's
      table rendering, which only the AppTests exercise. Moving all eight
      checks into CI the day before is what surfaced it.
    - **The deploy was never affected**: pyarrow is deliberately absent
      from `requirements.txt`, so Cloud never takes that path. A CI-only
      crash in a package production doesn't install.
    - **How to diagnose this class of failure:** `python -X faulthandler
      -u script.py` names the offending C library on a silent crash; and
      reproduce CI by cloning to a temp dir with a **fresh venv** built
      from `requirements-dev.txt`, because version drift is invisible
      otherwise.
    - It also exposed the photo summary being gated on having an API key
      — it described values already in the form, so it should never have
      depended on the client. Moved.
  - Tests **159**, checks **8**, ruff and black clean and blocking.
- [ ] Week 4 — Ship + Pitch — NOT STARTED (polish from RD pilot feedback,
  validation appendix, and the AI-assist features moved here from Week 3:
  label-photo extraction and PDF → formulas extraction. Saving/loading a
  blend or a day (JSON persistence) is the other strong Week 4 candidate —
  closing the browser tab currently loses everything, which is the most
  likely first complaint from an RD pilot; it needs a design pass against
  the no-PHI-by-design commitment before anything is built.)
  - **2026-07-30:** Added `notebooks/01_learn_cnf.ipynb` — a guided,
    part-by-part tutorial notebook (9 sections + Answers + cheat sheet)
    that teaches the CNF database and pandas manipulation by hand, with
    "Your turn" exercises. All cells executed, outputs visible. Built to
    answer "what's in the CNF?" with the author's own hands. No `src/` or
    app changes; raw data untouched; 106 tests still pass.

**Phase-level record (module breakdown, kept for detail):**

- [x] Phase 1 setup — COMPLETE (venv, requirements.txt, .gitignore, git init, first commit 852cc9e)
- [x] Phase 2 data_loader — COMPLETE (working `src/data_loader.py` + `src/build_parquet.py`; parquet files built and verified 2026-07-15; reference solutions in `reference/` match src/)
- [x] Week 1 planning — COMPLETE (`BUSINESS_CASE.md` written with full market analysis, competitors, methodology, and 4-week build plan)
- [x] Phase 3 calculator — COMPLETE & VERIFIED (`src/models.py`, `src/calculator.py`)
- [x] Phase 4 measures — COMPLETE & VERIFIED (`src/measures.py`)
- [x] Phase 5 targets/report — COMPLETE & VERIFIED (`src/targets.py`, `src/report.py`, `data/targets/dri_adult_default.csv` as of 2026-07-15 — since moved to `data/packs/canada/targets.csv`, see the nutrient-registry entry below)
- [x] Phase 6 Streamlit UI — SCAFFOLDED, bug-fixed post-audit, restructured 2026-07-17, restructured again 2026-07-19 (`app/streamlit_app.py`; recipe builder with CNF search + food-group filter + custom food from label, delivery input, targets (including fluid mL/day), live density panel, adequacy report with color-coded status (including a Free water row), dilution what-if with thinning liquid presets, commercial formula comparator, Excel export with a sanitized filename; import-verified 2026-07-15; commercial formulas + thinning liquids externalized to CSV in `data/`; widget session state warning fixed; **current layout (2026-07-19) is Build/Intake/Results `st.tabs` with a collapsed "Patient & Targets" expander above them — the persistent banner described in the "UI restructure" entry below no longer exists, see the 2026-07-19 entry near the end of this section**)
- [ ] Phase 7 polish — NOT STARTED

**Pinned issues (to revisit after user testing):**

- **Free water vs. water flushes — the author's clinical ruling
  (2026-07-30).** Recorded because it was nearly "fixed" the wrong way.
  **Free water is water that arrived as part of something fed** — and
  that INCLUDES tap water blended into a recipe, because once it's in the
  recipe it *is* the recipe, exactly like the moisture in a banana. Do
  **not** split "added water" back out of a blend's `water_g`; the
  `Recipe.added_water_mL` field exists but is deliberately unused (see
  `BUSINESS_CASE.md` A3). **Only a flush is water given as water**, which
  is why flushes are excluded from `free_water_mL` and counted separately
  — that exclusion is correct, not a bug. Total daily water = free water
  + flushes, which is what the water ledger now shows.
- **Water ledger (2026-07-30, commit 232dc8c).** `IntakeTotals` gained
  `water_sources`, populated in the same single pass. Renders as "Where
  the Water Came From" on the Daily Intake Record tab and as its own
  Excel sheet: one line per source, then a total, **deliberately with no
  intermediate "free water subtotal"** (author's call — she wants the
  sources visible, then the total). For the example day: blend 850,
  formula 491, oral 76, flushes 1032, total 2448. **No calculation
  changed** — those numbers were always computed, just summed away before
  anyone could see them.
- **Recipe record (2026-07-30, commits a011cfb, 59d00f8).** The flow test
  now belongs to a blend rather than floating on the page, so the chart
  note can name which recipe passed the syringe test. Everything else in
  a recipe recomputes from the ingredient list; the flow test is the one
  thing that exists only in the RD's hands, which is what makes a saved
  recipe worth having. File format: one `.xlsx`, two sheets, both food
  code and description in every ingredient row — code so the app's own
  files reload exactly, description so a human can read and type one.
  **An uploaded recipe lands as a draft** for the RD to confirm, per the
  §11 rule: "chicken, broiler, breast" is three CNF foods with three
  different protein figures, so ambiguous rows show candidates rather
  than a silent pick. Files download to the RD's own machine — the
  deployed app is a shared public server with no per-user storage.
  Verified by `scripts/check_recipe_record.py` (AppTest).
- **Blank vs 0 in the forms (author observation, 2026-07-30 — no change
  made).** `st.number_input` has no empty state, so captions promising
  "Blank = no target" describe something the widget can't do. The app
  resolves it by treating 0 as "not provided" (`if val > 0` filters the
  custom-food label form). Consequence: **a genuine zero can't be
  recorded** — a label stating "Sodium 0 mg" is indistinguishable from a
  label that omits sodium. Totals are unaffected (zero adds zero); only
  the coverage/confidence note shifts, and it errs toward understating
  what's known, which is the safe direction for a clinical tool. Open
  option: reword the captions to "0 = no target" so they match what's
  possible. A per-nutrient "not on this label" toggle would make the
  distinction real but is UI churn on a pinned layout for a small gain.
- **THE UI IS PINNED (2026-07-30, author's explicit instruction).** The
  author is satisfied with the current layout and typography and expects
  to revise them again *as new features land*. Until she says otherwise:
  do not restructure tabs, retheme, resize type, or reorder sections —
  and do not start the three parked UI items below unasked. "Pinned"
  means deliberately settled, not abandoned.
  - Parked, not cancelled: the volume-needed planning aid in the Daily
    Intake Record; the Excel export usefulness review.
  - **Delivered 2026-08-09, reshaped 2026-08-10: the chart note.** Now
    the Delivery method field verbatim as line 1, then three lines by
    category (Feed regimen / Oral Intake / Total daily intake). The
    chronological timeline and the flow-test line were both removed —
    too long to paste into an EHR, and the Intake Record above already
    is that list. Delivery method is seeded empty with a greyed example
    so the format teaches itself. See `FEED_LOG_REWORK.md` §3.5.
  - **Layout revised 2026-08-09 at the author's direction** (the "as new
    features land" case, not a break in the pin): onboarding row (demo
    video, Load example day) above the patient/day label, "Open a saved
    day" left top right; top padding 2.5rem → 3.75rem to clear
    Streamlit's header; footer reworded to four bullets with a contact
    line (GitHub issues + LinkedIn, no email).
- ~~**`scripts/check_tab_restructure.py` is FAILING on `main`**~~ —
  **RESOLVED 2026-07-30 (commit e9b4f33)**, a one-character fix
  (`o.split(" — ", 1)[-1]` -> `[0]`). Kept because the *cause* is the
  argument for CI: it asserted that `Nepro` appears under the Abbott
  company filter, and commit 1f3af36 changed formula labels to
  feed-name-first, so the parse yielded the brand instead of the feed
  name. **It was broken for a week and nobody noticed, because nothing
  ran it automatically.** The app was fine the whole time; only the
  checker was stale.
- ~~**`dilute()` models only kcal/protein/water from the added liquid**~~
  — **RESOLVED 2026-07-30 (commit c4da8a1)** by narrowing the Dilution
  What-If to water rather than by extending `dilute()`. The reasoning is
  worth keeping: for plain water, three terms ARE the complete picture,
  so the preview is exact; for broth/juice/milk it is not, and adding
  200 mL of broth to a blend **is a recipe change**, which the recipe
  editor already computes correctly through the full CNF row — every
  nutrient, not three. So for anything nutritive the preview was strictly
  the worse of two tools the app already had. Presets are now filtered to
  liquids contributing no kcal and no protein (the CSV stays the
  RD-editable source — add "Sterile water" and it appears); the "Custom"
  free-entry option is gone for the same reason. The rule, now in the
  caption: **thinning with water is a preview; thinning with anything
  nutritive is a recipe edit.** This continues the 2026-07-17 round-2
  ruling that live recipe adjustment is the core interaction and the
  editor itself is the what-if. Original finding, kept for context:
  `src/calculator.py:337-343` takes `liquid_kcal`, `liquid_protein_g` and
  `liquid_water_g` and nothing else, and `thinning_liquids.csv` has
  matching columns — so the **"Broth (chicken)" preset contributes no
  sodium**. Nothing misleading is displayed today: the Dilution What-If
  panel renders only volume, kcal/mL, protein/mL and free-water fraction,
  which is exactly what the function models, and the diluted profile only
  feeds `required_daily_volume()` (kcal/protein based). **The trap:** if
  that panel ever grows a micronutrient row, or a diluted profile is fed
  into the adequacy table, thinning with broth would show sodium density
  *falling* while real broth adds a sodium load. Whether that is worth
  modelling is a clinical call for the author.
- **Formula rows don't contribute `nutrient_coverage`** (known limitation,
  recorded 2026-07-23, still open). `aggregate_intake()`'s `formula`
  branch sums every disclosed per-mL nutrient into the daily totals
  correctly, but does not add to the per-nutrient coverage counts. On a
  *mixed* day (a blend row and a formula row both supplying, say, sodium)
  the adequacy table's "N/M ingredients" provenance note reflects only
  the food/CNF side. **Summed values are unaffected and a formula-only
  day is unaffected** — the defect is in the note that tells an RD how
  complete the row's data is, which in a clinical table is the part that
  sets trust. Small fix, Week 3 scope.
- ~~App not matching expectations~~ — **RESOLVED.** The author's original
  "it's not quite what I expected" was addressed across the 2026-07-20
  three-tab restructure and UI feedback rounds 1–8, the 2026-07-23
  pre-deploy pass, and the example-day rewrite. Superseded by the UI pin
  above.
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
  - **Partially met, as of 2026-07-19:** `_load_commercial_formulas()`
    (`src/calculator.py`) now takes `pack: str = DEFAULT_PACK`, matching
    `load_registry()`'s idiom — done as a side effect of the same-day
    commercial-formula catalog overhaul (see the 2026-07-19 entry near
    the end of this section), not a deliberate Appendix C push. **Still
    NOT met** for `thinning_liquids.csv`: `_load_thinning_liquids()`
    (`app/streamlit_app.py`) is still a module-level constant loaded
    once from a hardcoded `canada` path. A US pack would today get US
    nutrients + US targets + US commercial formulas (if a second pack's
    `formulas.csv` existed) but **Canadian thinning liquids** —
    **outstanding work:** parameterize `_load_thinning_liquids()` by
    `pack` the same way.
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
  intake, plus water flushes — drives the adequacy row, and the oral
  half of it drives the chart note's "Oral Intake" fluid figure; the
  note's feed line counts free water + flushes instead, see
  `FEED_LOG_REWORK.md` §3.5)
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
- **Next milestone (author-approved 2026-07-17):** the **label-photo →
  custom food** feature plus **public deployment** (Streamlit Community
  Cloud, API key in app secrets, no PHI by design) so practicing RDs can
  pilot-test the whole tool. The AI roadmap and its governing principle
  ("the agent is in the workflow, not in the math"), the
  cooked-preparations design constraint for future recipe matching, and
  the explicit rejection of AI-written ADIME notes are all recorded in
  `BUSINESS_CASE.md` §7 ("Where AI belongs in a clinical calculator").
  - **Status update 2026-07-30:** the deployment half is **done**
    (2026-07-23, <https://btfcalc.streamlit.app>). The label-photo half
    is **scheduled for Week 4**, not Week 3. Note the specific phrase
    "API key in app secrets" above — that is precisely the arrangement
    that makes the **spend cap non-negotiable**, because a key in the
    secrets of a *public* app means every call any visitor makes is
    billed to the author personally. Read §11's "HARD RULES for
    paid-API features" before writing a line of that feature. Cost
    estimate for sizing the cap: a nutrition-label extraction on
    Claude Haiku 4.5 runs roughly US$0.0035 per photo (~1,600 image
    tokens + ~400 prompt tokens in, ~300 structured-output tokens back,
    at $1/$5 per million) — about 285 labels per dollar. Cheap per
    photo is exactly why an uncapped loop is dangerous rather than
    reassuring.

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
- **Roadmap ideas raised 2026-07-20 (author, not started):**
  following a patient over time — holding/storing day records so intake
  can be tracked across encounters (needs a design pass against the
  no-PHI-by-design commitment before anything is built; JSON
  save/load from Phase 7 is the likely substrate); a mobile-friendly
  interface — the author can see phone-sized entry being genuinely
  useful for Feed Recipes and the Daily Intake Record, with the
  laptop view unchanged. Streamlit notes for when this is picked up:
  it is a responsive web app, so it *runs* in a phone browser already
  (once deployed, e.g. Streamlit Cloud on the Week 3 roadmap), but the
  current layout assumes a wide screen (`layout="wide"`, multi-column
  `st.columns` blocks, wide dataframes) — a mobile pass would mean
  auditing every columns/dataframe site for narrow-screen stacking,
  not a rewrite. Verify on a real phone over local network first
  (Streamlit prints a Network URL when run).

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

Last updated: 2026-07-20 (three-tab restructure to Nutrition Targets /
Feed Recipes / Daily Intake Record + author UI feedback rounds 1–8 +
maroon theming + typography pass — see the newest entry just above §10.
Queued next:
HANDOFF.md steps 3 (volume-needed planning aid), 5 (two-section chart
note), 6 (Excel export review), then Week 3 scope.)
Previous update: 2026-07-19 (Intake Record rework complete — see the
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

**Layout restructure (Build/Intake/Results tabs, no persistent banner) +
commercial formula catalog overhaul (2026-07-19, this session) — NOT
clinically reviewed yet; nothing pinned in this project is resolved by
this entry:**

- **Layout, display-only:** split the persistent banner (Patient,
  Targets, and the Intake Record all in one bordered container above
  two tabs) into three peer `st.tabs` — **"Build"**, **"Intake"**,
  **"Results"** — plus a collapsed **"Patient & Targets"** expander
  above them (settings, not a workflow step). The Intake Record editor
  (delivery method, live totals summary, "Add tube feed"/"Add
  food/drink" expanders, chronological row list) moved wholesale into
  the new Intake tab; `session_state["intake_log"]`'s shape and
  `aggregate_intake()` are untouched — this is display-only, per
  `.clinerules` §2's invariant. Removed the 🔨/📊 tab-label emojis per
  the author's request ("not the best icons"); other emojis (➕, ❌,
  🗑️, 🥣) were deliberately left alone — not asked. Stale captions/
  docstrings that said "in the banner above" were corrected to "in the
  Intake tab."
- **Commercial formula data — provenance fix:** re-verified all 8
  original `data/packs/canada/formulas.csv` rows against the two
  manufacturer HCP product guides now archived in
  `data/packs/canada/formula_sources/` (`2026_nestle-product-guide.pdf`,
  `2024_abbott-adult-product-guide.pdf`) — the data had been a
  near-verbatim, unverified copy of the author's 2018 EN spreadsheet.
  Found and fixed two real errors: "Isosource Fibre 1.5" had been
  carrying the non-fibre "Isosource 1.5" product's numbers, and
  "Resource 2.0" understated protein by ~5% (0.08 vs. actual
  0.084 g/mL).
- **Commercial formula data — catalog expansion:** grown from 8 to
  **33 adult Canadian tube-feeding formulas** (21 Nestlé Health
  Science, 12 Abbott Nutrition). Pediatric/Junior lines and oral-only
  supplements (Boost, Ensure, Pedialyte, PediaSure) explicitly excluded
  per the author's scope call — ask before adding those. Every row
  cites its source PDF filename + page number and `verified: 2026-07-19`.
- **Commercial formula data — schema expansion:** added `brand`
  (drives a new company radio filter + brand-prefixed labels in the
  Results tab comparator's multiselect and the Intake tab's tube-feed
  selectbox) and, after the author asked why the catalog only carried
  3 numeric columns when her own spreadsheet tracked more, 9 more
  per-mL nutrient columns: `fat_per_mL`/`carbohydrate_per_mL`/
  `fibre_per_mL` (g/mL) and `sodium_per_mL`/`potassium_per_mL`/
  `calcium_per_mL`/`iron_per_mL`/`magnesium_per_mL`/`phosphorus_per_mL`
  (mg/mL) — the same Nutrition Facts panel lens already used for BTF
  recipes (`nutrients.csv`'s label tier) plus magnesium/phosphorus per
  the EN spreadsheet. Deliberately excludes osmolality (author's call:
  not relevant outside hospital). All new fields are optional/
  `None`-safe, identical contract to `free_water_per_mL` — a formula
  whose label doesn't disclose a nutrient (e.g. fibre in an elemental
  formula) gets `None`, never a fabricated 0.
  **This fuller nutrient set is captured in the CSV but NOT surfaced in
  the Results tab's comparator table**, which still shows only
  kcal/protein/water — see the new pinned item below.
- `src/calculator.py::_load_commercial_formulas()` now takes
  `pack: str = DEFAULT_PACK` (imported from `src.nutrients`) instead of
  a hardcoded `_FORMULAS_CSV` path constant, matching the
  `load_registry()` idiom Appendix C mandates. `_FORMULAS_FALLBACK`
  (the CSV-missing safety net) was deliberately NOT expanded to mirror
  all 33 rows/12 columns — it stays the original curated 8-formula/
  4-field dict; a comment above it in `calculator.py` says so
  explicitly so this isn't mistaken for a bug later.
- `data/packs/canada/formulas.csv` gained a UTF-8 BOM prefix — opening
  it in Excel for Mac without one rendered "Nestlé" as "Nestl√©" (Excel
  guessed Mac Roman instead of UTF-8 for the accented character).
  Confirmed `pd.read_csv()` auto-strips a BOM (column names unaffected)
  before adding it; re-verified in Excel by the author after the fix.
- `data/packs/canada/formula_sources/README.md` updated: documents
  `brand` and the 9 new nutrient columns (g/mL vs. mg/mL called out
  explicitly), the adult-tube-feeding-only scope convention, and was
  reworded to be AI-tool-agnostic rather than Claude-Code-specific, per
  the author's wish to keep the option of using other AI tools for
  future formula updates.
- `BUSINESS_CASE.md` Appendix A7 rewritten to describe the 33-formula
  catalog and point at the CSV rather than reproducing a now-33-row
  table inline.

**New pinned items from this session:**

- **None of the above is clinically reviewed.** The author's own words:
  "I don't know that we can cross anything out yet... putting my
  clinical hat on and have to think hard." Treat every number, every
  scope call (adult-only formulas, no osmolality, which nutrients to
  add), and every UI change above as pending her hands-on scrutiny —
  this entry documents what changed, not that it's been validated.
- **Results tab commercial formula comparator is a known-unhappy
  design, not yet redesigned** [the comparator now lives in the Feed
  Recipes tab, per the 2026-07-20 restructure below]. Author's own
  framing: the nutrients monitored for a commercial formula "should be
  the nutrients we are monitoring regularly when we eat regular foods
  in the community" — i.e. rethink the comparator around the same
  label-tier lens as BTF recipes, not just widen the existing
  kcal/protein/water table. Ask her before redesigning it; she said she
  hasn't gotten to it yet.

**Three-tab restructure + author UI feedback rounds 1–6 (2026-07-20,
this session) — display-only throughout; `intake_log`,
`aggregate_intake()`, and all clinical logic untouched:**

- **Layout (322620d):** the 2026-07-19 Build/Intake/Results tabs +
  collapsed "Patient & Targets" expander are replaced by three
  encounter-order tabs — **Nutrition Targets** (patient weight +
  targets, promoted out of the collapsed expander), **Feed Recipes**
  (blend pages: selector, ingredients, per-blend density panel,
  dilution what-if, comparator, flow test), **Daily Intake Record**
  (the record editor with daily totals/adequacy/per-source breakdown/
  chart note/export directly beneath the record they summarize). Top
  bar keeps only the patient/day label and "Load example day"; the
  sidebar is gone.
- **Round 2 (3c42a3c):** patient weight gained a kg/lbs toggle; a
  dedicated "Add water flushes" expander with three precisions (single
  flush / with-feeds calculated from the feed count / med-flush rough
  daily figure) — all produce ordinary flush rows in the one
  `intake_log`, per the one-list invariant.
- **Round 3 (1d9978c):** `%g` number formatting on NFt fields,
  ingredient amounts, and measured volume (no forced trailing
  decimals); the Daily Total column is now formatted per-cell through
  the Styler — the status-coloring Styler was re-rendering values at
  pandas' 6-decimal default, overriding the registry rounding that was
  already in place. Add-expanders gained emojis (➕ 💉 tube feed /
  🍌 food-drink / 💧 water flushes); the comparator Company radio
  filter was restored as a scroll-list filter defaulting to All.
- **Round 4 (aec3197):** the food-source radio option was renamed
  "Enter a Nutrition Facts label (custom food)" — the NFt form was
  always available in the oral entry (shared `render_add_food_ui()`)
  but not discoverable behind the old label; comparator picks now
  persist across Company switches (multiselect options = narrowed pool
  ∪ current selections, because Streamlit silently drops selected
  values absent from `options`).
- **Round 5 (d687de2, 716bd61, fb22736):** Dietitians-of-Canada-style
  maroon theming — NEW `.streamlit/config.toml` with
  `primaryColor #A4243A` (selected-tab indicator, radios, checkboxes,
  sliders; the theme is read at server startup, so theme edits need an
  app restart); tab labels bold 1.6rem with 1.25rem spacing, selected
  tab maroon text (a maroon-background + black-text variant was tried
  live and reverted at the author's request); a new `_note()` helper
  replaces every `st.info()` blue box with a pale-maroon call-out
  (`#f9e8eb` background, `#A4243A` left border) — chosen after grepping
  Streamlit's compiled bundle confirmed alert kinds aren't exposed as
  DOM attributes to CSS-select on.
- **Round 6 (b6ee0ed):** `secondaryBackgroundColor #f9e8eb` added to
  the theme — the grey fill behind input boxes, code blocks, and
  dataframes is now the same pale-pink tint (author: "the pale pink
  instead of the grey"); the NFt form was scaled down to match the
  page (title 1.9→1.25rem, calories line 1.3→1.05rem, row padding
  0.5→0.1rem) and its vertical rhythm tightened via a scoped
  `.st-key-<box> [data-testid="stVerticalBlock"] { gap: 0.35rem }`
  override.
- **Verification each round:** `scripts/check_tab_restructure.py`
  (AppTest — tab names, section placement, chart note, kg/lbs toggle,
  Company filter default, flush helpers, cross-company comparator
  persistence) plus `verify_backend.py`; live server boot checks
  (HTTP 200) after each theme restart. One new gotcha learned for
  §11's collection: AppTest's `multiselect.options` returns the
  format_func-FORMATTED labels, not raw values — set raw values,
  assert against formatted ones.
- **Rounds 7–8 (db48e22, 3b85100, 03e1b78, daeb488, e81ccaa):**
  typography pass — base font 16px → 20px (`html { font-size: 125% }`
  — one labeled knob resizes the whole app since Streamlit sizes
  everything in rem); explicit heading scale (h1 2rem / h2 1.5rem /
  h3 1.25rem) below the tab labels (1.9rem) after the default
  hierarchy inverted at the larger root; Daily Intake Record adders
  reordered to tube feed → water flushes → oral intake (flushes are
  part of the tube-feeding routine, so they group with the tube-side
  entry; the oral route is its own category), oral expander renamed
  "Add oral intake (food/drink)".
- **Still queued from the author's plan (HANDOFF.md steps):**
  volume-needed planning aid in the Daily Intake Record (step 3);
  two-section chart note — summary + breakdown (step 5); Excel export
  usefulness review (step 6). Then Week 3 scope per HANDOFF.md
  Phase 2.
- **Week-2 pre-deploy pass (2026-07-23, commits 0971142, a6e77d4):**
  two usability fixes ahead of the Streamlit Cloud deploy. (1) A
  commercial-tube-feed-only intake day previously showed only calories
  and protein — `formulas.csv` already stores fat/carbohydrate/fibre/
  sodium/potassium/calcium/iron/magnesium/phosphorus per mL for each
  formula and `_load_commercial_formulas()` already loaded every
  column into `COMMERCIAL_FORMULAS`, but `aggregate_intake()`'s
  `formula` branch (`src/intake.py`) only mapped kcal/protein (+ free
  water) into daily totals, silently dropping the rest. Added
  `_FORMULA_COLUMN_TO_NUTRIENT`, a module-level per-mL-column ->
  registry-nutrient-key mapping, looped in the `formula` branch,
  skipping any column whose value is `None` (never fabricating a 0) —
  same optional/None contract the loader already documents. Verified
  against a single 1185 mL Resource 2.0 row: `energy_kcal`/`protein_g`
  match exactly, all eight optional nutrients present and > 0,
  `fibre_g` correctly absent (Resource 2.0's fibre cell is blank).
  Known limitation, noted in a code comment: formula rows still don't
  contribute `nutrient_coverage`, so on a *mixed* day (food/blend row +
  formula row touching the same nutrient) the adequacy table's "N/M
  ingredients" provenance note reflects only the food/CNF side — summed
  values are unaffected, and a formula-only day is unaffected.
  `compare_with_formula` in `src/calculator.py` (kcal/protein-only
  comparator) is untouched — separate feature, out of scope. (2) On the
  Daily Intake Record tab, swapped on-screen order so "Per-Source
  Breakdown" renders before "Daily Totals & Adequacy" (author
  preference), keeping the micro screen and per-kg metrics grouped
  with Daily Totals & Adequacy; moved the "Daily Totals & Adequacy"
  subheader+caption inside the `else` branch so an empty log shows
  only the "Add rows…" note. Pure display reorder, no variable
  dependency between the two blocks; Excel export sheet order
  untouched. Verified: `verify_backend.py`, `check_app_imports.py`,
  and `trace_calculation.py` all pass after each change; a throwaway
  AppTest confirms "Per-Source Breakdown" precedes "Daily Totals &
  Adequacy" in render order after loading the example day.
- **"Load example day" rewritten for a specific synthetic case (2026-07-23):**
  the button now loads a realistic H&N radiotherapy syringe-bolus day
  ("James W (H&N RT wk 5)") instead of the old generic chicken/rice/oil/
  water blend, AND now presets the Nutrition Targets tab (patient/day
  label, delivery method, weight, energy/protein/fluid targets) — the
  loader previously left that tab untouched.
  - **Blend** ("Whole-food blend", measured_volume_mL 1000): real CNF
    foods, cooked variants preferred where the case calls for them —
    Milk, fluid, whole, pasteurized, homogenized, 3.25% M.F. (code 113,
    257 g, counts as fluid); Yogourt (yogurt), Greek style, 2% M.F.,
    plain (7469, 100 g); Cereal, hot, oats (oatmeal), large flakes,
    prepared, Rogers (1463, 100 g — CNF has no "rolled oats" entry by
    that name, "large flakes, prepared" is the closest real cooked-oatmeal
    match); Chicken, broiler, breast, skinless, boneless, meat, braised
    (7321, 50 g — chosen over code 842 "breast, meat, roasted" because
    7321's description explicitly parallels the existing raw-chicken
    example ingredient's "skinless, boneless" wording; nutritionally
    near-identical, ~157 kcal/100 g either way); Banana, raw (1704,
    100 g); Avocado, raw, all commercial varieties (1511, 50 g); Carrot,
    boiled, drained (2381, 75 g — find_food()'s substring match also
    catches "Carrot, boiled, drained, with salt", but CNF's Food_Code
    ordering puts the unsalted row first, verified, not assumed); Vegetable
    oil, canola (451, 14 g); Water, municipal (2933, 250 g, counts as
    fluid). Full 1000 mL batch delivered across 4 bolus feeds (250 mL x 4).
  - **Intake Record** (19 rows, every source_type): 4 blend rows (08:00/
    12:00/17:00/21:00, 250 mL each, summing to the full 1000 mL batch —
    no over-draw bookkeeping, just what was actually given); 3 Resource
    2.0 formula rows (10:00/14:00/20:00, 237 mL each = 711 mL); 11 water-
    flush rows (before/after several feeds + free-water sips) summing to
    exactly 1032 mL; 1 oral row (small banana, ~101 g via the real "1
    small" CNF household measure, for QOL).
  - **Verified computed totals** (AppTest, read off the rendered Adequacy
    table): **2228 kcal, 100.8 g protein, 2255 mL fluid** against targets
    of 2250/100/2250 — 99%, 101% and 100% adequacy. Still real, verified
    CNF values for the grams specified, not a fudge, and not adjusted
    further per the instruction to report rather than force-fit.

    Restated 2026-08-15, up from **2204.2 kcal / 100.4 g / 2250.0 mL**.
    The example's ingredients used to be typed in grams; they now carry
    the CNF household measure an RD would actually have picked when
    searching ("250 ml" milk, "1 small" banana), and their weights are
    that measure's own weight, resolved from the lookup at runtime. The
    small shifts are those measures' real weights (250 mL of milk is
    257.8 g, not 257), so the day drifted a little closer to target
    rather than away from it. Chicken keeps a typed 50 g on purpose —
    CNF offers it only as "1 piece" (181 g) or "1 food guide serving =
    75g", so it is the case that proves why entering grams directly has
    to stay available.
  - **Widget-state gotcha (§11) hit again, this time on STATIC widget
    keys** (not a fresh-ID widget like `vol_{blend_id}`): the "Patient /
    day label" text_input, weight number_input, delivery-method
    text_input, and the three target number_inputs (`target_energy_kcal`/
    `target_protein_g`/`target_fluid_mL`) all needed explicit `key=`
    arguments added (previously unkeyed) so the Load Example handler
    could preset them. Two distinct fixes were required, not one:
    (a) the "Patient / day label" text_input is coded ABOVE the button's
    click-handler in the script (even though it renders to the button's
    LEFT — `with top_l:`/`with top_r:` control layout position, not
    script execution order) — setting `st.session_state["recipe_name_input"]`
    from the handler would otherwise try to modify a key whose widget was
    already instantiated earlier in that same run, raising
    `StreamlitAPIException`; fixed by moving the `with top_l:` block to
    execute AFTER the button/handler in the script. (b) every one of
    these widgets used to pass a hardcoded `value=0.0`/`value="..."`
    alongside its new `key=` — legal, but once the handler's preset
    value lands in `st.session_state[key]`, passing `value=` too trips
    Streamlit's (non-fatal) "created with a default value but also had
    its value set via Session State API" warning on every subsequent
    run; fixed by dropping `value=` entirely and seeding the key's
    default with a one-time `if key not in st.session_state: ...` guard
    instead, for all four sites (recipe label, weight, delivery method,
    the three targets).
  - `scripts/check_tab_restructure.py` hardcoded the old example's tube-
    feed row count (`n_feeds == 2`) in its "with-feeds flush helper"
    check; updated to `n_feeds == 7` (4 blend + 3 formula) for the new
    case. That script's separate, PRE-EXISTING Abbott/Nepro comparator
    assertion still fails on `main` before this change too (confirmed via
    `git stash`) — unrelated to this work, not fixed here.
  - Verified: `scripts/verify_backend.py` ("=== ALL BACKEND MODULES
    VERIFIED ==="), `scripts/check_app_imports.py` ("IMPORTS OK"),
    `scripts/trace_calculation.py` ("CROSS-CHECK PASSED"), and a new
    throwaway AppTest (blend + all 19 intake rows present with correct
    grams/amounts; targets-tab widgets show 2250/100/2250 + weight 75;
    computed totals as above) all pass.

2026-08-17 — **codebase cleanup, six phases, one commit each.** No
behaviour change anywhere: every phase was a move, a deletion of
something unreachable, or a reorder, verified after each by the full
gate (pytest, all eight `check_*.py`, `black --check`, `ruff`).

The rule it applied, which had held in practice but was never written
down: **`src/` never imports Streamlit; anything not needing Streamlit
belongs there.** That boundary is what makes `src/` unit-testable, and it
is now stated in `MAINTAINING.md` under "Where new code goes".

`app/streamlit_app.py`: **4,235 → 3,100 lines.** Tests 215 → 236.

1. Retired 178 lines of `if __name__ == "__main__":` smoke tests from five
   `src/` modules — hand-run leftovers from before pytest, never run by
   CI. Kept `build_parquet.py`'s block: that one is the real CSV→parquet
   build step. Deleted `calculator.volume_to_match_formula_kcal()`, the
   one function left with no caller at all. **Kept** `data_loader`'s
   `load_all()` and friends despite a scan calling them dead — the scan
   excluded same-module callers and missed that `notebooks/PHASE2_SPEC.md`
   specifies them and `reference/data_loader.py` mirrors them.
2. Stylesheet → `app/styles.css` (313 lines), read once behind
   `@st.cache_data`. Byte-identical to what was inline.
3. Four Streamlit-free helpers → `src/`, each with the tests it could not
   have before: thinning-liquid presets → `nutrients.py`, `find_food()` →
   `food_search.py`, `default_counts_as_fluid()` → `intake.py`,
   `color_status()` → `report.py` (beside `_adequacy_status()`, which
   produces the strings it matches on).
4. `render_add_food_ui()` (570 lines) → `app/add_food.py`, with the
   label-API ledger and food-search index that only it used. `app/` is now
   a package: `__init__.py`, `add_food.py`, `ui_common.py`, `styles.css`.
   The body is verbatim bar one call; the rendered widget-key set is
   byte-identical.
5. Each tab is now ONE contiguous block. The file used to open
   `recipes_tab` three times and `record_tab` three times, so its reading
   order matched the page in neither direction; a dependency scan found
   nothing load-bearing about it. Verified by comparing keyed widgets,
   subheader order (i.e. page order) and the whole `session_state` key set
   before and after, plus driving the documented widget-state landmines by
   hand (rename via `on_change`, New blend, thinning, delete blend).
6. Docs: this folder map corrected (it listed 8 of 14 `src/` modules and 3
   of 9 scripts); `MAINTAINING.md` gained the `src/`-vs-`app/` rule;
   `HANDOFF.md` retired. **`FEED_LOG_REWORK.md` was NOT retired** as the
   plan first proposed — ~30 comments in `src/` cite it, so it is a live
   specification, not a finished plan.

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

### HARD RULES for paid-API features (set 2026-07-30, before any were built)

These two rules were agreed *before* the label-photo extraction feature
exists, precisely so they are not negotiated under deadline pressure later.
They are not suggestions.

- **Any feature that calls a paid API ships with a spend cap in the SAME
  COMMIT.** Not a follow-up task, not a TODO, not "we'll add it before
  launch." The app is deployed publicly at <https://btfcalc.streamlit.app>
  with the API key in Streamlit secrets, which means **every call any
  visitor makes is billed to the author's personal account.** An uncapped
  image-extraction endpoint on a public URL is an open invitation to drain
  it. All three of the following are required:
  1. A per-session call limit enforced in `st.session_state`.
  2. A spend limit set on the API key itself in the provider console — so
     that a bug in (1) cannot run away. **This is the one that actually
     protects the author**, because it holds even when the app code is
     wrong.
  3. A visible per-use notice, so an RD knows each photo costs the author
     money.

  If any of the three is missing, the feature does not ship. An agent that
  implements the API call and leaves the cap for later has not completed
  the task.

- **A label photo fills the form; it never writes a value straight into a
  blend.** Extraction output lands in the existing "custom food from
  label" NFt form fields as **editable drafts**. The RD reads every field
  and confirms before anything commits to a recipe. Rationale: a misread
  digit in sodium or protein flows into a patient's daily total. The AI is
  a typing shortcut, not a data source — and **the interface must say so**,
  not just this document.

### General conventions & gotchas

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
- **Desktop layout conventions (author feedback 2026-08-14), all in the
  single `<style>` block in `app/streamlit_app.py`.** Type-vs-pick: typed
  fields (`st.text_input`, `st.number_input`, `st.text_area`) get a white
  fill and a maroon outline; dropdowns/radios/checkboxes keep the flat
  pink `secondaryBackgroundColor`, untouched — don't add either style to
  the other input family. **`st.text_input` / `st.text_area` and
  `st.number_input` need DIFFERENT selectors** — this cost two attempts.
  Text inputs carry their radius and border on `[data-baseweb="input"]`;
  number inputs do not, because Streamlit hands BaseWeb a Root override
  zeroing all four radii and all four border widths and puts the radius,
  the border and `overflow: hidden` on
  `[data-testid="stNumberInputContainer"]` instead. Style the container
  for number inputs; styling `[data-baseweb="input"]` there draws a
  square box inside a rounded clipping parent and the corners come out
  visibly cut off. Leave the `+/-` step buttons their pale pink — white
  where you type, pink where you click is the same convention as the
  dropdowns. Page width: `layout="wide"` stays, but the main container is
  capped at `max-width: 60rem` and **left-justified**, not centred; a
  table that genuinely needs the full screen breaks out via
  `st.container(key="fullbleed_*")`, which the CSS matches on
  `[class*="st-key-fullbleed"]` and widens rightward from that shared left
  edge — reuse that key prefix, and do not reintroduce negative margins,
  which made the wide tables straddle the page. Table toolbars are forced
  visible at 55% opacity because Streamlit hides them behind `:hover`,
  which does not exist on a phone. Mobile tab
  strip: labels drop to `1rem` only below 640px (desktop stays 1.25rem
  bold, unchanged) and the scroll chevrons are recoloured maroon so they
  read as a control. A future style-block edit should preserve these
  selectors rather than quietly overwrite them.

### Editing `src/` locally needs a FULL restart (learned 2026-07-31)

Streamlit re-runs `app/streamlit_app.py` when it changes, and the
"Rerun" button and a browser refresh both re-run the script. **None of
them reload a module under `src/`.** Those are imported once and cached
in `sys.modules` for the life of the process, so an edit to
`src/label_extract.py`, `src/calculator.py` or any sibling is invisible
until the server is stopped and started again.

    Ctrl+C in the Terminal running the app, then launch it again.

Cost the author a debugging round on 2026-07-31: three bugs in the
label-photo request had just been fixed and committed, and the running
app kept showing the *previous* error message word for word. The message
text was what proved the process was stale -- the wording had changed in
the fix, so seeing the old sentence meant old code, not a new failure.

If an on-screen string doesn't match the source, suspect this first.

### Streamlit Community Cloud deploy gotchas (learned 2026-07-23)

Recorded here because all three cost real debugging time on the first
deploy, and the third is open Week 3 work.

- **Cloud resolves NEWER package versions than the local `.venv`.** With
  `streamlit>=1.58`, Cloud installed **streamlit 1.60.0** while local ran
  1.58.0. 1.60's tab DOM differs from 1.58's, so tab-label CSS that worked
  locally silently missed on the deploy. The symptom is the nasty one:
  **local looked right, deployed didn't, from identical code.** Two-part
  fix landed it — target the ARIA `button[role="tab"]` selector (stable
  across versions) with `!important` in the injected `<style>`, and pin
  `streamlit==1.58.0` in `requirements.txt`. Cloud's environment is Python
  3.14.6, uv-installed, and pulls newer pandas/numpy/pyarrow too.
- **"Reboot app" restarts the process but does NOT reliably reinstall
  dependencies.** Only a `requirements.txt` change dependably triggers the
  uv dependency rebuild. A code push redeploys the Python (so labels and
  logic update) while the runtime version stays put — which is exactly how
  the tab bug stayed hidden while a formula-label change went live in the
  same push. Logs live under "Manage app" (bottom-right of the running app
  while logged in as owner); the line that matters on a rebuild is
  `Installing streamlit==...` / `Found Streamlit version X`.
- **A hot reload can leave modules under `src/` stale, and the crash
  blames code that is actually correct.** On 2026-08-01, one commit
  added a keyword argument to `day_to_workbook_bytes()` in `src/day_io.py`
  and updated its call site in `app/streamlit_app.py`. The live app died
  with `TypeError: day_to_workbook_bytes() got an unexpected keyword
  argument 'delivery_method'` — Cloud logged `🔄 Updated app!`, re-ran the
  **main script** with the new call, and kept the **already-imported**
  `src.day_io` from the previous commit. New caller, old callee, from one
  self-consistent commit.
  - Diagnose: is `git status -sb` in sync, and do the COMMITTED versions
    of both files agree (`git show HEAD:src/day_io.py | grep ...`)? If
    they do, the repo is fine and the running process is not.
  - Fix: **Reboot app**. That restarts Python and re-imports everything.
  - Expect it for any signature or constant change under `src/`. A change
    confined to `app/` never hits it.
  - Corollary: **don't trust what you see on the deploy — screenshots
    included — until you've confirmed it rebooted since the last push.**
    A stale deploy the same week showed the blend selector reading
    "Blend 1" while the name field read "Whole-food blend", which was
    unreproducible on current code and cost a round of investigation.
- **`requirements.txt` used to ship dev tooling to production.** jupyter,
  pytest, black, and ruff were all in it, so Cloud installed ~130 packages
  the app never imports and rebuilds were slow. **Resolved:**
  `requirements.txt` now carries runtime dependencies only (pandas,
  streamlit, openpyxl, anthropic, pillow) and the dev tooling moved to
  `requirements-dev.txt`, which pulls the runtime file in via `-r
  requirements.txt`. CI installs the dev file; Cloud installs only the
  runtime one.
