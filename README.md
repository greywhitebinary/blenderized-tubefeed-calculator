# Blenderized Tube Feeding Calculator

Estimate the calories, protein, fluid, and micronutrients in a home-blended
tube feed, then see how changes to the blend or daily intake affect the total.

BTFCalc is designed for dietitians and teams supporting blenderized tube
feeding. It uses the 2026 Canadian Nutrient File (CNF) as its food reference
data and supports, but does not replace, clinical judgement.

### ▶ Try it: [btfcalc.feedformflow.ca](https://btfcalc.feedformflow.ca)

**[Watch the 3-minute demo](https://vimeo.com/1216832087)**, which follows
the tool from targets through to the chart note.

There is nothing to install and no account to create. Load the example record
to see a worked case with a nine-ingredient blend, a commercial formula, water
flushes, and one oral food.

![The Daily intake record tab: the day's intake summarised in one line, a per-source breakdown of energy, macros and minerals split into Tube Feed, Food & Drink and Total, and a water ledger showing where every millilitre came from](docs/screenshot-daily-intake-record.png)

---

## What it does

- **Characterises a blend you already use.** Enter the ingredients and
  measured final volume to calculate kcal/mL, protein g/mL and free-water
  fraction. Ingredient weights cannot reliably predict blended volume.
  When you save a thinned copy, its starting volume is the original measured
  volume plus the water added; you can correct it after remeasuring.
- **Records a whole day.** Blends, commercial formulas, modulars, water
  flushes and food by mouth in one chronological list. Daily totals are a
  direct sum of the amounts entered, whether recording intake or planning
  what will be given.
- **Includes modulars.** Enter powders in grams and
  liquids in millilitres, and specify whether they are given by tube or
  by mouth. Record any water used to mix a powder separately under water
  flushes; the calculator does not assume a dilution volume.
- **Compares against commercial formulas.** 51 adult Canadian tube-feeding
  formulas, filterable by manufacturer, at a daily volume you choose. Sip
  feeds are included for comparison. The clinician determines whether a
  product is suitable for the patient's feeding route and nutritional needs.
- **Searches 5,993 CNF foods** by all your words in any order, with typo
  tolerance. It never chooses a food for you.
- **Reads a nutrition label from a photo** into a form you check against
  the label in your hand. A nutrient that isn't printed comes back blank,
  never as zero.
- **Saves your day to a spreadsheet** you can reopen later or edit in
  Excel, and writes a chart note with a **Copy note** button beside it. If
  you change a value after copying, the note says so rather than letting you
  paste numbers that have moved on.

![The Feed recipes tab: a blend's ingredient list with per-ingredient amounts and counts-as-fluid toggles, its measured final volume, and the live kcal/mL and protein g/mL above them](docs/screenshot-feed-recipes.png)

![The Nutrition targets tab: optional patient weight, and blank per-nutrient target fields with no defaults filled in](docs/screenshot-nutrition-targets.png)

## Scope and safety

- **Canada only, for now.** Nutrient tracking follows the Canadian
  Nutrition Facts panel and uses Canadian reference data. Supporting
  another country would require a reviewed data pack and validation of
  its nutrient and reporting conventions.
- **No default targets.** Targets start blank. Enter patient-specific values or
  leave them blank and review the totals.
- **A zero can mean "never measured", not "none present".** The report's
  *Coverage* column shows how many of your sources actually supplied a
  value for each nutrient, and rows where nothing did are hidden rather
  than shown as a confident 0.
- **Records are saved by downloading them.** The hosted app processes
  inputs on its server during the active session, but has no patient-record
  database or account-based record storage. Download a workbook to keep
  your work; it includes whatever you entered in the record label. Store
  and share it according to local privacy policy.
- **Label photos use an external service.** When photo reading is enabled,
  the uploaded image is sent to Anthropic to extract the printed values.
  Upload the product label only, without patient information. You can also
  enter the values manually.
- **Clinical decisions remain with the clinician.** The calculator cannot
  measure viscosity, tube flow, or tolerance. It does not set targets,
  recommend a feeding plan, or assess an individual.

If local policy requires calculation inputs to remain on your device, run
BTFCalc locally and enter label values manually.

---

## Run it on your own machine

You need **Python 3.14 or newer**. Older versions will not run it.

```bash
git clone https://github.com/greywhitebinary/blenderized-tubefeed-calculator.git
cd blenderized-tubefeed-calculator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/streamlit_app.py
```

It opens at http://localhost:8501. The CNF data ships with the repo, so
there is nothing else to download.

**Optional:** the label-photo feature calls the Anthropic API. Without a
key the photo control does not appear, and label values can be entered
manually. To enable it, put your own key in `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "your-key-here"
```

You are billed for your own usage. Caps live in `src/label_extract.py`.

## Check that you can trust the numbers

The math has four steps: load CNF data, scale by grams, divide by
measured volume, multiply by daily volume. You can check every one with a
calculator and a browser, without reading any code.

**Scaling.** Run `python scripts/trace_calculation.py`. It prints every
intermediate table for a worked recipe. Find the `[4] SCALE` table and
check any row:

> 200 g chicken × (120 kcal per 100 g ÷ 100) = **240 kcal**

**Source data.** Look the same food up on [Health Canada's own CNF
search](https://food-nutrition.canada.ca/cnf-fce/?lang=eng) and compare
its per-100 g values against the trace. Matching numbers mean the app is
reading the database faithfully.

**Density.** In the app, total kcal ÷ measured volume should equal the
kcal/mL on screen. For example, 557 kcal ÷ 550 mL = 1.013 kcal/mL.

Every equation is written out in `BUSINESS_CASE.md`, Appendix A.

## Editing the reference data

All of it is CSV under `data/packs/canada/`. Edit in Excel or any text
editor, save, and rerun the app. No Python required.

| What | File |
|---|---|
| Which nutrients are tracked, and why | `nutrients.csv` |
| Commercial formula profiles | `formulas.csv` |
| Modular profiles | `modulars.csv` |
| Thinning liquid presets | `thinning_liquids.csv` |
| Lay-term search synonyms | `food_synonyms.csv` |

`nutrients.csv` drives the calculator, both report tables, the targets
form and the label-photo schema. Adding a row there adds the nutrient
everywhere. See `MAINTAINING.md` for the column meanings and the workflow
for updating formulas from manufacturer PDFs.

Manufacturer source documents are not needed to run the app and are not
stored in this public repository. Keep them locally under
`reference_documents/<country>/`; Git ignores that folder. The public source
register in `data/packs/SOURCES.md` maps each regional CSV to the official
manufacturer source and explains how to review an update without publishing
the document.

## How it's built

Streamlit and pandas, with the math in plain Python under `src/`.

- Automated tests cover the calculation layer and key Streamlit workflows
- GitHub Actions runs all of it on every push and fails the build on lint
- `src/` is Streamlit-free, so the calculations are testable without a
  browser

```
app/                   UI modules for targets, recipes, intake, and shared state
src/                   calculator, data loading, nutrient registry, file I/O
data/packs/canada/     editable reference data
scripts/               verification checks
tests/                 unit tests
```

For the current file map and the path from an entered value to totals and
chart notes, see [Where new code goes](MAINTAINING.md#where-new-code-goes-src-or-app).

### Shared with EN-Calc

BTFCalc and the [Adult Inpatient Enteral Nutrition Calculator](https://encalc.feedformflow.ca)
share presentation components. See the [maintenance guide](MAINTAINING.md#shared-components-and-streamlit-compatibility)
before changing those components.

### Why `streamlit` is pinned exactly

The stylesheet depends on Streamlit's internal markup, so upgrades need
compatibility checks. The [maintenance guide](MAINTAINING.md#why-streamlit-is-pinned-exactly)
explains the version pin and the automated checks.

## Further reading

| Document | What's in it |
|---|---|
| `BUSINESS_CASE.md` | The clinical problem, and every equation (Appendix A) |
| `CONTEXT.md` | Full design history and the reasoning behind each decision |
| `MAINTAINING.md` | Day-to-day workflows for running and updating the project |

## Get in touch

I'd like to hear from you if you manage blenderized tube feeds and have
thoughts on this, if you've found a wrong number or a bug, or if you want
to adapt it for another country's data.

- **Bugs, wrong numbers, ideas:** open a
  [GitHub issue](https://github.com/greywhitebinary/blenderized-tubefeed-calculator/issues).
  Public, so the next person with the same question finds the answer.
- **To find me:** [LinkedIn](https://www.linkedin.com/in/hui-jun-gail-chew/)
- **About the publication:** [Feed. Form. Flow.](https://feedformflow.substack.com/p/feed-form-flow)

**I can't advise on a specific person's care.** I'm a registered
dietitian, but not your dietitian. See the
[medical disclaimer](#medical-disclaimer) below.

## Medical disclaimer

This tool does not create a dietitian–client or other professional
relationship and is not a substitute for professional medical advice, diagnosis,
or treatment. For advice about an individual’s care, consult their physician,
registered dietitian, or other qualified health professional. Do not delay
seeking that advice because of a result from this calculator.

The author is a registered dietitian, but is not your dietitian and cannot
advise on any individual's care.

## Licence

[MIT](LICENSE). Use it, fork it, adapt it for another country's data.

The licence includes the standard warranty disclaimer, which matters here:
the software is provided as is, and clinical responsibility stays with the
dietitian using it.

---

*Built with AI assistance. The reasoning behind each decision is recorded
in `CONTEXT.md` and in the commit history.*
