# Blenderized Tube Feed Calculator

A clinical nutrition tool that characterizes a real, working blenderized
tube-feed (BTF) recipe and helps navigate changes to it. Built for RDs
(registered dietitians), estimates only.

Built on the **Canadian Nutrient File (CNF) 2026 edition**.

---

## Coming back after time away? Start here.

Five steps to get re-oriented, in order. Total time: ~5 minutes.

1. **Open the project in VS Code** (steps 1–3 in "How to run the app"
   below: open VS Code → open the
   `Documents/GitHub/blenderized-tubefeed-calculator` folder → open a
   terminal).
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
5. **Start the app** (step 4 below) and pick up where you left off.

---

## Prerequisites (one-time setup, already done)

These were set up in Phase 1 and should already be in place:

- **Python 3.12+** installed on your Mac
- **VS Code** installed
- **This project folder** cloned from GitHub
- **Virtual environment (`.venv`)** created inside the project folder
- **Dependencies installed** (pandas, streamlit, openpyxl, pyarrow)

If any of these are missing, see `CONTEXT.md` §3 for the tech stack and
`requirements.txt` for the dependency list.

---

## How to run the app (step by step, after restarting your computer)

### Step 1: Open VS Code

- Open the **VS Code** application from your Applications folder (or
  Spotlight: press `Cmd + Space`, type "Visual Studio Code", press Enter).

### Step 2: Open the project folder

- In VS Code, go to **File → Open Folder...** (or press `Cmd + O`).
- Navigate to `Documents/GitHub/blenderized-tubefeed-calculator`.
- Click **Open**.

### Step 3: Open a terminal

- In VS Code, go to **Terminal → New Terminal** (or press `` Ctrl + ` ``
  — that's the backtick key, usually above the Tab key).
- A terminal panel should open at the bottom of the VS Code window.
- You should see a prompt like:
  ```
  hjc@MacBook-Pro blenderized-tubefeed-calculator %
  ```

### Step 4: Start the app

- In the terminal, type (or copy-paste) this exact command:

  ```
  .venv/bin/streamlit run app/streamlit_app.py
  ```

- Press **Enter**.
- You should see output like:
  ```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  ```

### Step 5: Open the app in your browser

- The app should open automatically in your default browser.
- If it doesn't, open your browser (Safari, Chrome, etc.) and type:
  ```
  http://localhost:8501
  ```
- If port 8501 is already in use, Streamlit will use 8502, 8503, etc.
  Check the terminal output for the exact URL.

### Step 6: Use the app

- Click **"Load example day"** in the top row to quickly see all the
  results panels with a preloaded blend (chicken/rice/water/oil) plus a
  small example Intake Record (two feeds of that blend, a water flush,
  and a banana eaten by mouth).
- In the **"Patient, Targets & Intake Record"** banner: expand "Targets"
  for the blank target fields (there are no default targets — enter
  your own or leave them blank); the **Intake Record** below it is the
  single source of truth for everything the client actually received —
  use "➕ Add tube feed" (time + a blend/commercial-formula/water-flush
  source + volume) and "➕ Add food/drink" (search CNF or enter a custom
  food from a label, same as the Build tab) to log rows. Rows display
  chronologically, grouped under "Tube Feed" and "Food & Drink" headers,
  and are individually removable. The always-visible summary line
  (`~kcal | g protein | mL fluid provided`) updates as you add rows.
- In the **🔨 Build** tab, use the blend selector at the top to create,
  rename, or delete blends (a blend is a *recipe formulation* — its
  densities don't depend on how many times it's made or how much of it
  gets logged in the Intake Record, by design; see `FEED_LOG_REWORK.md`
  if you're curious why). Try searching for a food (e.g., type "banana"
  in the search box), or switch to "Enter information on the food
  label" to see the Nutrition-Facts-lookalike custom-food form.
- In the **📊 Results** tab, daily totals/adequacy/the BTF micro screen
  come from the Intake Record above — add a few rows in the banner
  first if the tables look empty. Try the **Per-Source Breakdown**
  table (Tube Feed vs. Food & Drink vs. Total), the **Dilution
  What-If** slider — a secondary aid ("what would thinning cost?"), not
  the main way to change the recipe (that's editing ingredients
  directly in the Build tab, which updates every number live) — the
  formula comparator multiselect, and the copy-pasteable chart note at
  the bottom (the Intake Record read aloud chronologically, tube and
  oral interleaved).

### Step 7: Stop the app

- Go back to the terminal in VS Code.
- Press **`Ctrl + C`** (hold Control, press C).
- The terminal prompt should return, meaning the server has stopped.

---

## How to verify the backend (optional)

If you've made code changes and want to make sure the backend still
works:

```
.venv/bin/python scripts/verify_backend.py
```

You should see `=== ALL BACKEND MODULES VERIFIED ===` at the end.

## How to verify app imports (optional)

```
.venv/bin/python scripts/check_app_imports.py
```

You should see `IMPORTS OK` at the end.

---

## How to check you can trust the numbers (the ~20-minute ritual)

The pipeline has four hops: **load CNF data → scale by grams → divide
by volume → multiply by daily volume.** You verify it by catching any
hop being wrong, with a calculator and a browser — no code reading.
Do this once thoroughly; afterwards, re-check only the hop you doubt.

### Hop 1+2 — the trace script (scaling)

```
.venv/bin/python scripts/trace_calculation.py
```

This prints every intermediate table for the example recipe. Find the
step **[4] SCALE** table, pick any row, and check it on a calculator:

> 200 g chicken × (120 kcal per 100 g ÷ 100) = **240 kcal** ✓

Pick two or three rows, including one mg-unit row (e.g. potassium).
If they check out, the grams-scaling math is right.

### Hop 1 (again) — the source data, through a different door

Look up the same food on **Health Canada's own CNF search**:
https://food-nutrition.canada.ca/cnf-fce/?lang=eng

Search "chicken breast raw", find the same food, and compare its
per-100g values against the trace's step [2]/[4] `Nutrient_Amount`
column. Same numbers = the app is loading the database faithfully
(BOM handling, parquet conversion, all of it).

### Hop 3 — the density division

In the running app, load the example day, then on a calculator:

> total kcal ÷ measured volume = the kcal/mL shown on screen?

(e.g. 557 kcal ÷ 550 mL = 1.013 kcal/mL)

### Hop 4 — your own spreadsheet as the referee (the strongest test)

Your EN spreadsheet computes Peptamen 1.5 at any volume, and the app's
formula profiles came from that spreadsheet. So:

1. In the app's Results tab, set the comparator's **"Compare at daily
   volume (mL)"** field to **1200** and add **Peptamen 1.5** to the
   comparator's multiselect.
2. In your spreadsheet, run Peptamen 1.5 at 1200 mL.
3. The kcal and protein must match (1800 kcal, 81.6 g protein).

If the spreadsheet and app agree on the formula side, and Health
Canada's website and the app agree on the food side, the whole data
model is triangulated from two independent directions.

### The one caveat to remember forever

**A zero can mean "CNF never measured it," not "this food has none."**
The trace script's *missing-data audit* (bottom of its output) and the
report's *Coverage* column (e.g. "1/2 ingredients") exist to surface
this. Sparse nutrients (vitamin D: 88% of CNF foods) can read low
partly from missing data.

---

## How to update commercial formulas from manufacturer PDFs

Full instructions live in `data/packs/canada/formula_sources/README.md`.
The short version:

1. **Download** the product's healthcare-professional PDF from the
   manufacturer's site into `data/packs/canada/formula_sources/`.
2. **Ask Claude** (in a Claude Code session in this project):
   > Read the new PDFs in data/packs/canada/formula_sources/ and update
   > formulas.csv — show me each extracted value next to the PDF text
   > you got it from.
3. **You verify the diff** — two numbers per formula, seconds to check
   against the PDF. You are the safety mechanism; never skip this.
4. Commit (see "How to save your work" below).

---

## How to save your work with git (the 3-command loop)

After you've changed something (a CSV, a note in CONTEXT.md) and want
it saved to the project's history:

```
git status
```
Shows what changed. Read the list — is it what you expect?

```
git add -A
git commit -m "Update Peptamen 1.5 numbers from 2026 product PDF"
```
Saves a snapshot with your message (write what/why in plain words).

```
git push
```
Sends your snapshots to GitHub (the cloud backup). If you skip this,
your work is saved locally but only on this Mac.

**If git says something scary:** don't guess — copy the message and ask
Claude. Nothing in git is truly lost; wrong moves are almost always
recoverable.

---

## How to edit reference data (no Python needed)

All reference data lives under `data/packs/canada/` — Canada is one
"data pack" (see `BUSINESS_CASE.md` Appendix C); a future country would
be a new `data/packs/<country>/` folder with the same files, no Python
changes. You can edit these CSVs in VS Code, Excel, or any text editor.
Save the file and rerun the app — changes take effect on next load.

**There is no `targets.csv`.** It was deleted — a default target (even
a "just a guideline") isn't defensible for tube-fed patients (e.g.
protein practice runs 1.0-1.5 g/kg, not the 0.8 g/kg population RDA a
default would imply). The RD always enters patient-specific targets in
the app itself, at runtime, or leaves them blank.

| Data | File | Format |
|---|---|---|
| Nutrient registry (what to track, why, and target_type) | `data/packs/canada/nutrients.csv` | name, code, label, unit, tier, on_label, show_in_report, offer_target, target_type, decimals, notes |
| Commercial formulas | `data/packs/canada/formulas.csv` | name, kcal_per_mL, protein_per_mL, free_water_per_mL, source, verified |
| Thinning liquid presets | `data/packs/canada/thinning_liquids.csv` | name, kcal_per_100mL, protein_g_per_100mL, water_g_per_100mL |

### To add a nutrient to track:

1. Open `data/packs/canada/nutrients.csv` in VS Code.
2. Add a new line with the CNF `Nutrient_Code` (look it up in
   `cnf_fcen_all-files-data_2026/Nutrient Name.csv`), a `tier` of
   `label` (on the Canadian Nutrition Facts panel — eligible for the
   main adequacy table), `clinical` (a BTF-specific reason to track it —
   shown in the collapsed BTF micro screen), or `engine` (internal use
   only, never shown); `on_label` of `yes`/`no` (can a nutrition facts
   label supply it?); `show_in_report` of `yes`/`no` (is it actually
   displayed daily, or just tracked/exported? — this is how "show what's
   needed, not everything" works: a nutrient can be `tier=label` but
   `show_in_report=no`); `offer_target` of `yes`/`no` (does the
   custom-targets form in the banner offer a field for it?); and an
   optional `target_type` (`RDA`/`AI`/`UL`/`estimate` — only `UL`
   changes the adequacy wording; leave blank otherwise).
3. Save the file.
4. Rerun the app. No Python change needed — this is the whole point of
   the registry design (see `CONTEXT.md` §11 for why `nutrients.csv`
   has no hardcoded fallback, unlike the other two files below).

### To add a new commercial formula:

1. Open `data/packs/canada/formulas.csv` in VS Code.
2. Add a new line at the bottom, e.g.:
   ```
   Ensure Plus,1.5,0.063,0.80,2026_ensure-plus-hcp.pdf,2026-07-16
   ```
   `free_water_per_mL` is optional — leave it blank if you don't have
   the figure (the app shows "—" rather than guessing 0). The last two
   columns (`source`, `verified`) are your audit trail — which PDF the
   numbers came from and when you checked them. The app ignores them;
   they're for the next human. Fine to leave empty.
3. Save the file (`Cmd + S`).
4. Rerun the app. The new formula appears in the comparator's multiselect.

### To add a new thinning liquid:

1. Open `data/packs/canada/thinning_liquids.csv` in VS Code.
2. Add a new line at the bottom, e.g.:
   ```
   Coconut water,19.0,0.7,95.0
   ```
3. Save the file (`Cmd + S`).
4. Rerun the app. The new liquid appears in the dilution what-if dropdown.

---

## Project structure (quick overview)

```
blenderized-tubefeed-calculator/
├── app/streamlit_app.py          ← the UI (this is what you run)
├── src/                          ← backend logic (calculator, data loader, nutrients registry, etc.)
├── data/
│   └── packs/canada/             ← editable Canadian reference data (CSVs) — one "data pack"
│       ├── nutrients.csv         ← nutrient registry (what to track, why, and target_type; no targets.csv -- no default targets anywhere)
│       ├── formulas.csv          ← commercial formula profiles (incl. free_water_per_mL)
│       └── thinning_liquids.csv  ← thinning liquid presets
├── cnf_fcen_all-files-data_2026/ ← raw CNF data (DO NOT MODIFY)
├── scripts/                      ← verification scripts
├── CONTEXT.md                    ← full project context (read this first)
├── BUSINESS_CASE.md              ← methodology + data-pack design (Appendix C)
└── requirements.txt              ← Python dependencies
```

For the full project context, design decisions, and phase-by-phase
history, see **`CONTEXT.md`**.