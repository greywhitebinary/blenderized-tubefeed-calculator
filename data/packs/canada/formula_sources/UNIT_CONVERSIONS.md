# Unit conversions — manufacturer panels → `formulas.csv`

Manufacturers print their nutrition panels in the units a **label** uses.
CNF, and therefore this app, uses a different set. Every value in
`../formulas.csv` that needed converting was converted by the rules on
this page.

**This is the file to correct first.** If a conversion here is wrong,
every affected feed is wrong in the same direction, and the fix is to
change the factor here and re-derive — not to hand-edit the CSV.

Author decisions are marked **DECISION** with the date. They are
judgment calls, not arithmetic, and they are the lines most worth
re-examining.

---

## 1. The basis: which volume the panel is printed for

`formulas.csv` stores everything **per mL**.

The two guides use **seven different bases between them** — per 100,
235, 237, 250, 300, 1000 and 1500 mL — and they vary product to product
within one guide, so the basis must be READ PER FEED, never assumed from
the vendor.

Do not trust the column header: a PDF text layer reorders it (Nestlé's
extracts as "250 ml100 mlUnits"). Derive it instead from the ENERGY row
and the feed's already-verified kcal/mL:

```
column volume mL = printed Cal in that column ÷ kcal_per_mL
```

A correct parse lands on a round volume; anything else means the row was
misread, which fails loudly instead of producing a plausible wrong
number. Powdered feeds (Tolerex, both Vivonex) are per PREPARED volume —
an 80 g packet in 255 ml water makes 300 ml — which is the basis that
compares like-for-like against a blend.

Take the **largest** column available: it carries more significant
figures, so the per-mL value loses less to rounding.

## 2. Vitamin A → µg RAE

Panels print International Units. CNF uses **retinol activity
equivalents** (µg RAE).

```
retinol_µg        = retinol IU        × 0.3
beta_carotene_µg  = beta-carotene IU  × 0.6
vitamin_a_rae_µg  = retinol_µg + (beta_carotene_µg ÷ 2)
```

**DECISION (author, 2026-08-20): beta-carotene is divided by 2, the
SUPPLEMENTAL factor, not 12.** The DRI conversion is 1 µg RAE = 12 µg
beta-carotene *from food*, but 2 µg when it is purified beta-carotene
added to a manufactured product — which is what a tube feed contains.
Using 12 would understate vitamin A in every fortified feed sixfold.

**Which factor applies is decided by the INGREDIENTS list, not by how the
product is marketed.** Read the "Vitamins (...)" premix on the same page:

- premix NAMES beta-carotene → the carotene was added. Use ÷2, even for a
  whole-food blend. Compleat 1.06 and Compleat 1.5 are real-food formulas
  that ALSO add beta-carotene, so their panel figure merges food and added
  carotene into one number the manufacturer does not split. Accepting
  their merged figure at ÷2 is the author's decision (2026-08-20): it is
  the upper estimate, it matches the conversion the manufacturer's own
  vitamin A claim assumes, and splitting a figure they merged would be
  inventing precision. Retinol — the figure an upper limit is judged on —
  is stored exactly and separately either way.
- premix does NOT name beta-carotene while the panel reports some → it
  came from the food. Use ÷12. **Compleat Organic Blends 1.25 is the only
  feed in this pack where this applies**: its premix lists vitamin A
  palmitate and no carotene, and 5200 of its 5600 IU come from sweet
  potato and pear purée. At ÷2 it read 5.6 µg RAE/mL, roughly four times
  any comparable feed; at ÷12 it reads 1.27.

**A consequence worth knowing:** when the carotene IS supplemental, 1 IU
of retinol and 1 IU of beta-carotene both convert to 0.3 µg RAE, so a
panel giving only a TOTAL vitamin A still converts exactly (total IU
× 0.3). That identity does NOT hold at ÷12, which is another reason the
food-factor exception must stay narrow and evidenced by the premix.

**Where the panel gives only a total vitamin A IU** (Abbott does this):

- beta-carotene absent from the ingredients → the vitamin A is all
  preformed. Treat the whole IU figure as retinol (× 0.3), and record
  beta-carotene as blank, not 0 — the base may contribute traces nobody
  discloses.
- beta-carotene present but unsplit → convert the TOTAL at × 0.3. No
  split is needed or guessed: as shown above, both components convert at
  0.3 µg RAE per IU under the supplemental factor, so the total is exact.
  `retinol_ug` and `beta_carotene_ug` are then left blank for that feed,
  because those two ARE unknown — only their RAE sum is known.

## 3. Vitamin D → µg

```
vitamin_d_µg = vitamin D IU ÷ 40
```

40 IU = 1 µg cholecalciferol. No judgment involved.

## 4. Vitamin E → mg alpha-tocopherol

The factor depends on the FORM, which is named in the ingredients list
on the same page:

| Ingredient says | Form | mg per IU |
|---|---|---|
| `DL-alpha-tocopheryl acetate`, `dl-` | synthetic | **0.45** |
| `D-alpha-tocopheryl acetate`, `d-`, "natural" | natural | **0.67** |

Read this per feed. Both manufacturers have used both forms across
their ranges; assuming one silently changes the number by half again.

## 5. Folate → µg DFE

```
folate_dfe_µg = folic acid µg × 1.7
```

Verified against CNF itself: "Corn fritter" carries 35.4 µg food folate
and 45.2 µg added folic acid, and CNF prints 112.3 µg DFE —
35.4 + (45.2 × 1.7) = 112.2. Same factor.

**`folate_food_ug` stays BLANK for every commercial feed**, not 0.
Manufacturers disclose only the folic acid they add; the milk-protein
and corn-syrup base presumably contributes some naturally occurring
folate, and they simply do not say how much. CNF does not zero this
column for fortified foods either — only 30 of its 1,176 folic-acid
fortified foods record food folate as exactly 0.

## 6. Niacin

**DECISION (author, 2026-08-20): the panel figure goes in
`niacin_preformed_mg`, and `niacin_ne` is left BLANK.**

The guides print one "Niacin" number and their ingredients list
niacinamide — that is preformed niacin, the vitamin as added. CNF's
niacin equivalents (NE) additionally counts the niacin a body makes from
tryptophan in dietary protein, which no manufacturer discloses. Putting
the panel figure in the NE column would look complete while omitting the
protein-derived part, so the app reports NE as "not disclosed" instead.

## 7. Straight unit changes, no judgment

| Panel prints | CSV stores | Multiply by |
|---|---|---|
| B12 in mg | µg | 1000 |
| Selenium in mg | µg | 1000 |
| Folic acid in mg | µg | 1000 |
| Vitamin K in mg | µg | 1000 |

Vitamin C, thiamine, riboflavin, B6, pantothenic acid, zinc, copper and
manganese are printed in mg and stored in mg — no conversion.

## 8. Blank vs zero

A blank cell means **the manufacturer did not disclose it**. A zero
means they disclosed a zero. The app treats these differently: a blank
counts the feed as "not supplying" and says so in the coverage column,
where a 0 would be taken as a measured absence and drag a total down.
Never fill a blank with 0 to tidy the table.

## 9. Nutrients deliberately not carried

The guides disclose choline, chloride, iodine, molybdenum, chromium,
biotin, taurine and L-carnitine. These are **not** tracked.

**DECISION (author, 2026-08-20):** they matter clinically, but CNF does
not cover them for whole foods, so a blend-plus-feed day would show a
real feed number against an empty food column and read as though the
food contributed nothing. An RD who needs to track a trace element can
open the product guide, which is in this folder. Revisit if CNF coverage
changes.
