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
2. **Open a session with an AI coding assistant** (Claude Code or any
   other assistant able to read PDFs and edit files in this project) and
   say something like:

   > Read the new PDFs in data/packs/canada/formula_sources/ and update
   > formulas.csv — name, brand, kcal_per_mL, protein_per_mL, the
   > nutrient columns listed below, and free_water_per_mL if the PDF
   > states a water content, with the source (filename + page number)
   > and verified columns filled in. Scope: adult tube-feeding formulas
   > only, not pediatric/Junior lines or oral-only supplements. Show me
   > each extracted value next to the PDF text you got it from.

   The assistant reads PDFs natively; no parsing code to maintain, and
   no dependency on any one AI tool or vendor.
3. **Verify the diff yourself** — you are the RD; the numbers per
   formula take seconds to check against the PDF. Then commit.

The RD check in step 3 is the safety mechanism. Never skip it.

## Conversion reminders (the usual PDF → per-mL traps)

- PDFs often state **per 250 mL tetra** or **per 1000 mL**: divide
  accordingly (e.g. 375 kcal / 250 mL = 1.5 kcal/mL).
- Protein is usually **g per 100 mL** or per serving → convert to g/mL
  (e.g. 6.8 g/100 mL = 0.068 g/mL).
- Watch for **reformulations**: same product name, new numbers. The
  `verified` date in formulas.csv is what tells you how stale a row is.

## Scope

Adult tube-feeding-labeled formulas only — not pediatric/Junior lines
(e.g. Compleat Junior, Peptamen Junior, Nutren Junior, Alfamino Junior)
and not oral-only supplements not meant for tube delivery (e.g. Boost,
BeneProtein). If you want one of those added anyway, just say so
explicitly when asking for the update.

## Columns in ../formulas.csv

The nutrient set mirrors the same lens already used for BTF recipes
(`../nutrients.csv`'s label tier — i.e. the same nutrients on a regular
food's Nutrition Facts table), plus magnesium and phosphorus per the
author's EN spreadsheet. Deliberately excludes osmolality — clinically
relevant in hospital but not something a home-blend RD needs to track
here.

| column | meaning |
|---|---|
| `name` | display name in the app's comparator and tube-feed dropdown |
| `brand` | manufacturer, e.g. "Nestlé Health Science" / "Abbott Nutrition" — drives the company filter in the Results tab comparator. Optional: a row without one gets grouped under "Other" rather than a fabricated guess. |
| `kcal_per_mL` | energy density |
| `protein_per_mL` | protein density (g/mL) |
| `fat_per_mL` | fat density (g/mL) |
| `carbohydrate_per_mL` | carbohydrate density (g/mL) |
| `fibre_per_mL` | fibre density (g/mL). Many formulas (elemental diets, non-fibre variants) genuinely have none — leave blank, not 0. |
| `sodium_per_mL` | sodium density (**mg**/mL — note the unit change from the g/mL columns above) |
| `potassium_per_mL` | potassium density (mg/mL) |
| `calcium_per_mL` | calcium density (mg/mL) |
| `iron_per_mL` | iron density (mg/mL) |
| `magnesium_per_mL` | magnesium density (mg/mL) — not on any Canadian label, but on every manufacturer's technical-data panel |
| `phosphorus_per_mL` | phosphorus density (mg/mL) — same as magnesium |
| `free_water_per_mL` | free-water content per mL. |
| `source` | filename of the PDF in this folder + page number (or "EN spreadsheet 2018" for not-yet-re-verified legacy rows) |
| `verified` | date the numbers were last checked against the source |

All nutrient columns except `kcal_per_mL`/`protein_per_mL` are
OPTIONAL — leave a cell blank if the PDF doesn't state it; the app
treats a blank as "unknown" (renders "—") rather than assuming 0, since
0 would falsely claim the formula has none of that nutrient.

The app reads every column above except `source` and `verified`, which
are documentation for humans and never touch the calculator. As of
2026-07-19 the full nutrient set isn't yet surfaced in the Results tab's
comparator table (still just kcal/protein/water there) — it's captured
in the CSV for future use.
