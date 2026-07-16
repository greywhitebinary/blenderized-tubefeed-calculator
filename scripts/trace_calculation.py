"""
trace_calculation.py — Show every intermediate step from CNF CSV to kcal/mL.

Purpose: let the RD hand-check the data pipeline, not just the final
answer. verify_backend.py asserts the outputs are sane; THIS script
prints every intermediate table so you can recompute any number with a
calculator and confirm the pipeline does what an RD would do by hand.

Run from the project root:
    .venv/bin/python scripts/trace_calculation.py

The pipeline it traces (src/calculator.py::calculate_profile):

    Food_Name.csv          Nutrient_Amount.csv
    (find Food_Code)       (per-100g values, keyed Food_Code+Nutrient_Code)
          |                        |
          v                        v
    [1] ingredient table    [2] filter to the 11 tracked nutrient codes
          \\                       /
           \\                     /
            [3] merge on Food_Code  (inner join — see the missing-data
                                     audit at the end!)
                     |
            [4] scaled_amount = grams x (Nutrient_Amount / 100)
                     |
            [5] groupby Nutrient_Code -> sum  = recipe totals
                     |
            [6] divide by MEASURED volume     = densities (kcal/mL ...)
                     |
            [7] x daily volume                = daily totals
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_food_name, load_nutrient_amount
from src.models import Ingredient, Recipe
from src.calculator import (
    NUTRIENT_CODES,
    NUTRIENT_LABELS,
    calculate_profile,
    calculate_daily_totals,
)

pd.set_option("display.width", 120)
pd.set_option("display.float_format", lambda v: f"{v:,.3f}")

_CODE_TO_NAME = {v: k for k, v in NUTRIENT_CODES.items()}


def find_food(fn: pd.DataFrame, desc: str) -> int:
    m = fn[fn["Food_Description_EN"].str.contains(desc, case=False, na=False, regex=False)]
    if len(m) == 0:
        raise ValueError(f"No food found for {desc!r}")
    return int(m.iloc[0]["Food_Code"])


def main() -> int:
    print("=" * 72)
    print("CALCULATION TRACE — every intermediate step, hand-checkable")
    print("=" * 72)

    fn = load_food_name()
    na = load_nutrient_amount()

    # The same example recipe the app's "Load example" button uses.
    chicken = find_food(fn, "Chicken, broiler, breast, skinless, boneless, meat, raw")
    rice = find_food(fn, "Grains, rice, white, long-grain, parboiled, cooked")
    oil = find_food(fn, "Vegetable oil, canola")

    recipe = Recipe(
        name="Trace example",
        ingredients=[
            Ingredient(chicken, "Chicken breast, raw", 200),
            Ingredient(rice, "Rice, parboiled, cooked", 150),
            Ingredient(oil, "Canola oil", 15),
        ],
        added_water_mL=200,
        measured_final_volume_mL=550,
    )

    # ---- [1] Ingredient table -------------------------------------------
    ingr_df = pd.DataFrame(
        [{"Food_Code": i.food_code, "food": i.food_description, "grams": i.grams}
         for i in recipe.ingredients]
    )
    print("\n[1] INGREDIENT TABLE (what you put in the blender)")
    print(ingr_df.to_string(index=False))

    # ---- [2] Nutrient_Amount, filtered ----------------------------------
    tracked = list(NUTRIENT_CODES.values())
    na_filtered = na[na["Nutrient_Code"].isin(tracked)]
    print(f"\n[2] NUTRIENT_AMOUNT FILTER")
    print(f"    Full table: {len(na):,} rows (every food x every nutrient CNF measured)")
    print(f"    After keeping only the {len(tracked)} tracked nutrient codes: "
          f"{len(na_filtered):,} rows")
    print(f"    Every value is PER 100 g of edible food — the CNF convention.")

    # ---- [3] The merge ---------------------------------------------------
    merged = ingr_df.merge(
        na_filtered[["Food_Code", "Nutrient_Code", "Nutrient_Amount"]],
        on="Food_Code", how="inner",
    )
    merged["nutrient"] = merged["Nutrient_Code"].map(_CODE_TO_NAME)
    print(f"\n[3] MERGE ingredients x nutrient amounts ON Food_Code (inner join)")
    print(f"    3 ingredients x up to 11 nutrients = up to 33 rows; got {len(merged)}.")
    print(f"    (Fewer than 33 means some food LACKS a CNF row for some nutrient —")
    print(f"     see the missing-data audit at the end.)")

    # ---- [4] Scaling -----------------------------------------------------
    merged["scaled_amount"] = merged["grams"] * (merged["Nutrient_Amount"] / 100.0)
    print(f"\n[4] SCALE: scaled_amount = grams x (per-100g value / 100)")
    print(f"    e.g. chicken energy: 200 g x (120 kcal per 100 g / 100)")
    print(f"         = 200 x 1.20 = 240 kcal   <- check this by hand!")
    show = merged[["food", "grams", "nutrient", "Nutrient_Amount", "scaled_amount"]]
    print(show.sort_values(["food", "nutrient"]).to_string(index=False))

    # ---- [5] Group + sum -------------------------------------------------
    totals = (
        merged.groupby("nutrient")["scaled_amount"].sum().reindex(NUTRIENT_CODES.keys())
    )
    print(f"\n[5] RECIPE TOTALS: sum scaled_amount across ingredients, per nutrient")
    print(f"    (This is the column-sum of table [4], grouped by nutrient.)")
    print(totals.to_string())

    # ---- [6] Densities — via the real calculator ------------------------
    profile = calculate_profile(recipe, na)
    v = recipe.measured_final_volume_mL
    print(f"\n[6] DENSITIES: divide totals by the MEASURED volume ({v:.0f} mL)")
    print(f"    Measured, not computed — blending air and rinse water make")
    print(f"    volume incalculable from weights; you read it off the container.")
    print(f"    kcal/mL      = {profile.total_kcal:,.1f} / {v:.0f} = {profile.kcal_per_mL:.4f}")
    print(f"    protein g/mL = {profile.total_protein_g:,.1f} / {v:.0f} = {profile.protein_per_mL:.4f}")
    fw = profile.total_water_g + recipe.added_water_mL
    print(f"    free water   = (food water {profile.total_water_g:,.1f} g "
          f"+ added {recipe.added_water_mL:.0f} mL) / {v:.0f} = {profile.free_water_fraction:.4f}")
    print(f"    (1 g water ~ 1 mL — standard clinical approximation)")

    # Cross-check: trace totals must equal the calculator's totals exactly.
    for name, traced in totals.items():
        calc = profile.nutrient_totals.get(name, 0.0)
        traced = 0.0 if pd.isna(traced) else float(traced)
        assert abs(traced - calc) < 1e-9, f"trace != calculator for {name}"
    print("\n    CROSS-CHECK PASSED: hand-trace totals == calculator totals, exactly.")

    # ---- [7] Daily totals ------------------------------------------------
    daily_vol = 1200.0
    daily = calculate_daily_totals(profile, daily_vol)
    print(f"\n[7] DAILY TOTALS at {daily_vol:.0f} mL/day: density x daily volume")
    print(f"    equivalently: recipe_total x ({daily_vol:.0f} / {v:.0f}) "
          f"= recipe_total x {daily_vol / v:.4f}")
    for name in NUTRIENT_CODES:
        print(f"    {NUTRIENT_LABELS[name]:<20} {profile.nutrient_totals.get(name, 0.0):>10,.2f} "
              f"-> {daily.get(name, 0.0):>10,.2f} /day")

    # ---- Missing-data audit ----------------------------------------------
    print("\n" + "=" * 72)
    print("MISSING-DATA AUDIT — the one place the pipeline can mislead you")
    print("=" * 72)
    print("""
CNF does not have a row for every nutrient for every food. When a row is
absent, the inner join in step [3] simply produces no row — and the sum
in step [5] treats that as contributing ZERO. The report cannot tell
"truly zero" apart from "CNF never measured it". Totals can only be
UNDER-estimated, never over — but for sparse nutrients (vitamin D is the
sparsest at ~88% coverage) a "Below target" flag may partly reflect
missing data, not missing nutrition.
""")
    any_missing = False
    for i in recipe.ingredients:
        have = set(
            na_filtered[na_filtered["Food_Code"] == i.food_code]["Nutrient_Code"]
        )
        missing = [
            _CODE_TO_NAME[c] for c in tracked if c not in have
        ]
        status = ", ".join(missing) if missing else "none — full coverage"
        if missing:
            any_missing = True
        print(f"  {i.food_description:<28} missing: {status}")
    if not any_missing:
        print("\n  (This example recipe happens to have full coverage. Try a")
        print("   recipe with less-common foods and re-run to see gaps.)")

    print("\nTrace complete. Every number above is recomputable by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
