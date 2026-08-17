# Maintaining this project

Day-to-day workflows for whoever is running and updating the BTF
Calculator. If you're just trying the app, the [README](README.md) is the
place to start.

Written on a Mac with VS Code. The commands work anywhere; the menu
clicks are Mac-specific.

---

## Coming back after time away? Start here.

Five steps to get re-oriented, in order. Total time: ~5 minutes.

1. **Open the project in VS Code** (steps 1–3 in "Running the app" below).
2. **Ask git what state things are in.** In the terminal:
   ```
   git status
   ```
   - `nothing to commit, working tree clean` → nothing half-finished,
     you're safe to start.
   - A list of modified files → something was left mid-change. Look at
     what changed with `git diff`, or ask Claude "what's uncommitted
     and why?"
3. **Read the status section of CONTEXT.md.** Open `CONTEXT.md` and
   scroll to **§9 Current status** — the last entry tells you what was
   done most recently and what's next. (Every work session updates it,
   so it's always the freshest summary.)
4. **Confirm everything still works** (takes ~30 seconds):
   ```
   .venv/bin/python scripts/verify_backend.py
   ```
   You want `=== ALL BACKEND MODULES VERIFIED ===` at the end.
5. **Start the app** and pick up where you left off.

---

## Prerequisites

- **Python 3.14 or newer.** This is a hard requirement, not a
  preference — parts of `src/` use syntax that does not exist in 3.13
  and earlier, so an older Python fails at import with a `SyntaxError`.
- **VS Code**
- **This project folder** cloned from GitHub
- **A virtual environment (`.venv`)** inside the project folder
- **Dependencies installed** from `requirements.txt` (runtime) or
  `requirements-dev.txt` (adds pytest, black, ruff, jupyter, pyarrow)

---

## Running the app

### Step 1: Open VS Code

Open **VS Code** from your Applications folder (or Spotlight: `Cmd +
Space`, type "Visual Studio Code", press Enter).

### Step 2: Open the project folder

**File → Open Folder...** (or `Cmd + O`), navigate to the
`blenderized-tubefeed-calculator` folder, click **Open**.

### Step 3: Open a terminal

**Terminal → New Terminal** (or `` Ctrl + ` `` — the backtick key, usually
above Tab). A panel opens at the bottom of the window.

### Step 4: Start the app

```
.venv/bin/streamlit run app/streamlit_app.py
```

You should see:

```
You can now view your Streamlit app in your browser.
Local URL: http://localhost:8501
```

### Step 5: Open it

It usually opens automatically. If not, go to http://localhost:8501. If
port 8501 is busy Streamlit uses 8502, 8503 and so on — check the
terminal for the exact address.

### Step 6: Stop the app

Back in the terminal, press **`Ctrl + C`**. The prompt returns when the
server has stopped.

---

## Verifying your changes

Run the whole gate the way CI does:

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/verify_backend.py
.venv/bin/python scripts/check_app_imports.py
.venv/bin/ruff check . && .venv/bin/black --check .
```

The other verification scripts under `scripts/` each drive the real app
through Streamlit's `AppTest`. GitHub Actions runs all of them on every
push, so a green push means all nine passed.

**One rule about `black`:** if it wants to reformat something, let it.
Do not hand-edit code to fight the formatter — `black --check` gates the
build, so the formatter always wins.

---

## Where new code goes: `src/` or `app/`

One rule decides it:

> **`src/` never imports Streamlit. `app/` is the Streamlit layer.**
> Anything that doesn't need Streamlit belongs in `src/`.

This isn't style — it's what makes the project testable. Code in `src/`
can be called directly by a test, so it's covered by the ~236 tests in
`tests/`, which run in about a second. Code in `app/` can only be reached
by starting the whole app through Streamlit's `AppTest`, which is what the
`scripts/check_*.py` files do: slower, clumsier, and far harder to write a
sharp test in.

So when you add something, ask: *does this need to draw on the screen?*

- **No** — a calculation, a naming rule, a lookup, a formatting decision →
  put it in `src/`, and write a test for it.
- **Yes** — a widget, a layout, a button handler → it goes in `app/`.

A good sign you've got it right: the thing in `src/` can be explained
without mentioning the app at all.

`app/` itself is a small package, not one file:

| File | What's in it |
|---|---|
| `streamlit_app.py` | The page: the three tabs, in the order they appear |
| `add_food.py` | The reusable "add a food" search-and-entry component |
| `ui_common.py` | Two shared helpers, `_note()` and `_narrow()` |
| `styles.css` | The stylesheet (plain CSS, not a Python string) |

---

## The strongest check: your own spreadsheet as referee

Your EN spreadsheet computes Peptamen 1.5 at any volume, and the app's
formula profiles came from that spreadsheet. So:

1. In the app's **Feed Recipes** tab, set the comparator's "Compare at
   daily volume (mL)" to **1200** and add **Peptamen 1.5** to the
   multiselect.
2. In your spreadsheet, run Peptamen 1.5 at 1200 mL.
3. The kcal and protein must match (1800 kcal, 81.6 g protein).

If the spreadsheet and the app agree on the formula side, and Health
Canada's website and the app agree on the food side (see the README),
the data model is triangulated from two independent directions.

### The one caveat to remember forever

**A zero can mean "CNF never measured it," not "this food has none."**
The trace script's missing-data audit and the report's *Coverage* column
exist to surface this. Sparse nutrients (vitamin D is in 88% of CNF
foods) can read low partly from missing data.

---

## Updating commercial formulas from manufacturer PDFs

Full instructions live in `data/packs/canada/formula_sources/README.md`.
The short version:

1. **Download** the product's healthcare-professional PDF from the
   manufacturer's site into `data/packs/canada/formula_sources/`.
2. **Ask an AI coding assistant** able to read PDFs and edit files here:
   > Read the new PDFs in data/packs/canada/formula_sources/ and update
   > formulas.csv — show me each extracted value next to the PDF text
   > you got it from.
3. **You verify the diff** — the numbers per formula, seconds to check
   against the PDF. You are the safety mechanism; never skip this.
4. Commit.

---

## Saving your work with git (the 3-command loop)

```
git status
```
Shows what changed. Read the list — is it what you expect?

```
git add -A
git commit -m "Update Peptamen 1.5 numbers from 2026 product PDF"
```
Saves a snapshot with your message (write what and why in plain words).

```
git push
```
Sends your snapshots to GitHub. Skip this and the work is saved only on
this Mac.

**If git says something scary:** don't guess — copy the message and ask
Claude. Nothing in git is truly lost; wrong moves are almost always
recoverable.

---

## Editing reference data

All reference data lives under `data/packs/canada/` — Canada is one
"data pack" (see `BUSINESS_CASE.md` Appendix C); a future country would
be a new `data/packs/<country>/` folder with the same files, no Python
changes.

**There is no `targets.csv`.** It was deleted — a default target isn't
defensible for tube-fed patients (protein practice runs 1.0–1.5 g/kg,
not the 0.8 g/kg population RDA a default would imply). The RD always
enters patient-specific targets in the app, or leaves them blank.

### To add a nutrient to track

1. Open `data/packs/canada/nutrients.csv`.
2. Add a line with the CNF `Nutrient_Code` (look it up in
   `cnf_fcen_all-files-data_2026/Nutrient_Name.csv`) and set:
   - `tier` — `label` (on the Canadian Nutrition Facts panel; eligible
     for the main adequacy table), `clinical` (a BTF-specific reason to
     track it; shown in the collapsed micro screen), or `engine`
     (internal only, never shown)
   - `on_label` — `yes`/`no`: can a nutrition facts label supply it?
   - `show_in_report` — `yes`/`no`: displayed daily, or just tracked and
     exported? This is how "show what's needed, not everything" works —
     a nutrient can be `tier=label` but `show_in_report=no`
   - `offer_target` — `yes`/`no`: does the targets form offer a field?
   - `target_type` — optional `RDA`/`AI`/`UL`/`estimate`; only `UL`
     changes the adequacy wording. Leave blank otherwise.
3. Save and rerun the app. No Python change needed — that's the point of
   the registry design. `nutrients.csv` deliberately has **no hardcoded
   fallback**: if it's missing the app fails loudly rather than silently
   serving a stale nutrient list (see `CONTEXT.md` §11).

### To add a commercial formula

1. Open `data/packs/canada/formulas.csv`.
2. Add a line at the bottom. `free_water_per_mL` is optional — leave it
   blank if you don't have the figure and the app shows "—" rather than
   guessing 0. The last two columns (`source`, `verified`) are your audit
   trail: which PDF the numbers came from and when you checked them. The
   app ignores them; they're for the next human.
3. Save and rerun. The formula appears in the comparator.

### To add a thinning liquid

1. Open `data/packs/canada/thinning_liquids.csv`.
2. Add a line, e.g. `Coconut water,19.0,0.7,95.0`.
3. Save and rerun.

Note the app only offers **non-nutritive** thinning liquids in the
dilution what-if. Anything carrying calories or protein also carries
sodium and potassium, which the what-if doesn't model — so those belong
in the ingredient list, where every nutrient is counted.

---

For full design history and the reasoning behind each decision, see
`CONTEXT.md`.
