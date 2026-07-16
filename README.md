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

All reference data is in CSV files. You can edit these in VS Code, Excel,
or any text editor. Save the file and rerun the app — changes take
effect on next load.

| Data | File | Format |
|---|---|---|
| DRI targets | `data/targets/dri_adult_default.csv` | nutrient, target, unit, source |
| Commercial formulas | `data/formulas/commercial_formulas.csv` | name, kcal_per_mL, protein_per_mL |
| Thinning liquid presets | `data/thinning_liquids.csv` | name, kcal_per_100mL, protein_g_per_100mL, water_g_per_100mL |

### To add a new commercial formula:

1. Open `data/formulas/commercial_formulas.csv` in VS Code.
2. Add a new line at the bottom, e.g.:
   ```
   Ensure Plus,1.5,0.063
   ```
3. Save the file (`Cmd + S`).
4. Rerun the app. The new formula appears in the comparator dropdown.

### To add a new thinning liquid:

1. Open `data/thinning_liquids.csv` in VS Code.
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
├── src/                          ← backend logic (calculator, data loader, etc.)
├── data/                         ← editable reference data (CSVs)
│   ├── targets/                  ← DRI targets
│   ├── formulas/                 ← commercial formula profiles
│   └── thinning_liquids.csv      ← thinning liquid presets
├── cnf_fcen_all-files-data_2026/ ← raw CNF data (DO NOT MODIFY)
├── scripts/                      ← verification scripts
├── CONTEXT.md                    ← full project context (read this first)
└── requirements.txt              ← Python dependencies
```

For the full project context, design decisions, and phase-by-phase
history, see **`CONTEXT.md`**.