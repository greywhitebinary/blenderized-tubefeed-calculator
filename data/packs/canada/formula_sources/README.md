# formula_sources/ — manufacturer PDFs behind formulas.csv

Drop the manufacturer's healthcare-professional product PDF for each
commercial formula in this folder. These PDFs are the **audit trail** for
the numbers in `../formulas.csv` — the "no black boxes" philosophy applied
to reference data: every kcal/mL and protein/mL in the comparator should
be traceable to a document a colleague can open and check.

## The workflow (no parser, no code)

Automated PDF table-scraping is deliberately NOT built here. Every vendor
lays out their PDFs differently, per-mL vs per-serving vs per-1000-kcal,
and a silent mis-parse would put a wrong number in a clinical comparator.
Instead, the update loop is:

1. **Download** the product information PDF from the manufacturer's
   healthcare-professional site (Nestlé Health Science, Abbott Nutrition,
   etc.) into this folder. Keep the vendor's filename, prefix the year if
   it isn't in it (e.g. `2026_peptamen-1.5-product-info.pdf`).
2. **Open a Claude Code session** in this project and say:

   > Read the new PDFs in data/packs/canada/formula_sources/ and update
   > formulas.csv — kcal_per_mL and protein_per_mL, with the source and
   > verified columns filled in. Show me each extracted value next to
   > the PDF text you got it from.

   Claude reads PDFs natively; no parsing code to maintain.
3. **Verify the diff yourself** — you are the RD; the two numbers per
   formula take seconds to check against the PDF. Then commit.

The RD check in step 3 is the safety mechanism. Never skip it.

## Conversion reminders (the usual PDF → per-mL traps)

- PDFs often state **per 250 mL tetra** or **per 1000 mL**: divide
  accordingly (e.g. 375 kcal / 250 mL = 1.5 kcal/mL).
- Protein is usually **g per 100 mL** or per serving → convert to g/mL
  (e.g. 6.8 g/100 mL = 0.068 g/mL).
- Watch for **reformulations**: same product name, new numbers. The
  `verified` date in formulas.csv is what tells you how stale a row is.

## Columns in ../formulas.csv

| column | meaning |
|---|---|
| `name` | display name in the app's comparator dropdown |
| `kcal_per_mL` | energy density |
| `protein_per_mL` | protein density (g/mL) |
| `source` | filename of the PDF in this folder (or "EN spreadsheet 2018" for legacy rows) |
| `verified` | date the numbers were last checked against the source |

The app only reads `name`, `kcal_per_mL`, `protein_per_mL` — the last two
columns are documentation for humans and never touch the calculator.
