# Blenderized Tube Feed Calculator

A clinical nutrition tool that characterizes a real, working blenderized
tube-feed (BTF) recipe and helps navigate changes to it. Built for RDs
(registered dietitians), estimates only.

Built on the **Canadian Nutrient File (CNF) 2026 edition**.

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

- Click **"Load example recipe"** in the sidebar (left side) to quickly
  see all the results panels with a preloaded chicken/rice/oil recipe.
- Try the **dilution slider** — slide it to 150 mL and switch between
  Water, Broth, and Milk to see how densities change.
- Try searching for a food (e.g., type "banana" in the search box).

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

## How to edit reference data (no Python needed)

All reference data lives under `data/packs/canada/` — Canada is one
"data pack" (see `BUSINESS_CASE.md` Appendix C); a future country would
be a new `data/packs/<country>/` folder with the same four files, no
Python changes. You can edit these CSVs in VS Code, Excel, or any text
editor. Save the file and rerun the app — changes take effect on next
load.

| Data | File | Format |
|---|---|---|
| Nutrient registry (what to track, and why) | `data/packs/canada/nutrients.csv` | name, code, label, unit, tier, on_label, decimals, notes |
| DRI targets | `data/packs/canada/targets.csv` | nutrient, target, unit, target_type, source |
| Commercial formulas | `data/packs/canada/formulas.csv` | name, kcal_per_mL, protein_per_mL |
| Thinning liquid presets | `data/packs/canada/thinning_liquids.csv` | name, kcal_per_100mL, protein_g_per_100mL, water_g_per_100mL |

### To add a nutrient to track:

1. Open `data/packs/canada/nutrients.csv` in VS Code.
2. Add a new line with the CNF `Nutrient_Code` (look it up in
   `cnf_fcen_all-files-data_2026/Nutrient Name.csv`), a `tier` of
   `label` (on the Canadian Nutrition Facts panel — shown in the main
   adequacy table), `clinical` (a BTF-specific reason to track it —
   shown in the collapsed BTF micro screen), or `engine` (internal use
   only, never shown), and `on_label` of `yes`/`no` (can a nutrition
   facts label supply it?).
3. Save the file. Optionally add a matching row to `targets.csv` if the
   nutrient should show an adequacy target.
4. Rerun the app. No Python change needed — this is the whole point of
   the registry design (see `CONTEXT.md` §11 for why `nutrients.csv`
   has no hardcoded fallback, unlike the other three files below).

### To add a new commercial formula:

1. Open `data/packs/canada/formulas.csv` in VS Code.
2. Add a new line at the bottom, e.g.:
   ```
   Ensure Plus,1.5,0.063
   ```
3. Save the file (`Cmd + S`).
4. Rerun the app. The new formula appears in the comparator dropdown.

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
│       ├── nutrients.csv         ← nutrient registry (what to track, and why)
│       ├── targets.csv           ← DRI targets
│       ├── formulas.csv          ← commercial formula profiles
│       └── thinning_liquids.csv  ← thinning liquid presets
├── cnf_fcen_all-files-data_2026/ ← raw CNF data (DO NOT MODIFY)
├── scripts/                      ← verification scripts
├── CONTEXT.md                    ← full project context (read this first)
├── BUSINESS_CASE.md              ← methodology + data-pack design (Appendix C)
└── requirements.txt              ← Python dependencies
```

For the full project context, design decisions, and phase-by-phase
history, see **`CONTEXT.md`**.