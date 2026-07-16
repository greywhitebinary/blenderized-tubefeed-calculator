"""
verify_backend.py — Full backend integration test (Phases 2-5).

Run from the project root:
    .venv/bin/python scripts/verify_backend.py

Exercises every backend module end-to-end with real CNF data:
data_loader → models → measures → calculator → targets → report.
Exits 0 on success, non-zero on any failure.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of where this is run from
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_nutrient_amount, load_food_name
from src.models import Ingredient, Recipe, Delivery, DeliveryMethod
from src.calculator import (
    calculate_profile,
    calculate_daily_totals,
    daily_volume_from_delivery,
)
from src.measures import load_measure_lookup, measure_to_grams
from src.targets import default_targets
from src.report import (
    generate_adequacy_report,
    generate_formula_comparison,
    generate_density_summary,
)


def find_food(fn, desc):
    m = fn[fn["Food_Description_EN"].str.contains(desc, case=False, na=False, regex=False)]
    if len(m) == 0:
        raise ValueError(f"No food found for {desc!r}")
    return int(m.iloc[0]["Food_Code"])


def main() -> int:
    print("=== FULL BACKEND INTEGRATION TEST ===\n")

    # 1. Load CNF data
    print("[1] Loading CNF data...")
    na = load_nutrient_amount()
    fn = load_food_name()
    print(f"    Nutrient_Amount: {na.shape[0]} rows")
    print(f"    Food_Name: {fn.shape[0]} rows")
    assert na.shape[0] > 500_000, "Nutrient_Amount looks truncated"
    assert fn.shape[0] > 5_000, "Food_Name looks truncated"

    # 2. Build recipe using household measures
    print("\n[2] Building recipe from household measures...")
    lookup = load_measure_lookup()

    chicken_code = find_food(fn, "Chicken, broiler, breast, skinless, boneless, meat, raw")
    rice_code = find_food(fn, "Grains, rice, white, long-grain, parboiled, cooked")
    oil_code = find_food(fn, "Vegetable oil, canola")

    rice_measures = lookup[lookup["Food_Code"] == rice_code]
    cup_row = rice_measures[
        rice_measures["Measure_Description_and_Unit_EN"].str.contains(
            "250 ml", case=False, na=False
        )
    ]
    if len(cup_row) > 0:
        rice_grams = measure_to_grams(
            rice_code, int(cup_row.iloc[0]["Measure_Code"]), 1.0, lookup
        )
    else:
        rice_grams = 150.0
    print(f"    Rice (1 x 250ml measure): {rice_grams:.1f} g")
    assert rice_grams > 0, "measure_to_grams returned non-positive grams"

    recipe = Recipe(
        name="Integration test blend",
        ingredients=[
            Ingredient(food_code=chicken_code, food_description="Chicken breast", grams=200),
            Ingredient(food_code=rice_code, food_description="Rice, cooked", grams=rice_grams),
            Ingredient(food_code=oil_code, food_description="Canola oil", grams=15),
        ],
        added_water_mL=200,
        measured_final_volume_mL=550,
    )
    print(f"    Recipe: {recipe.name} ({len(recipe.ingredients)} ingredients)")

    # 3. Calculate nutrient profile
    print("\n[3] Calculating nutrient profile...")
    profile = calculate_profile(recipe, na)
    print(f"    kcal/mL: {profile.kcal_per_mL:.3f}")
    print(f"    protein g/mL: {profile.protein_per_mL:.3f}")
    print(f"    free water frac: {profile.free_water_fraction:.3f}")
    assert profile.kcal_per_mL > 0, "kcal/mL should be positive"
    assert profile.protein_per_mL > 0, "protein/mL should be positive"
    assert 0 < profile.free_water_fraction <= 1.2, "free water fraction out of range"

    # 4. Delivery
    print("\n[4] Setting up delivery (syringe bolus: 300mL x 4/day)...")
    delivery = Delivery(
        method=DeliveryMethod.SYRINGE_BOLUS,
        bolus_volume_mL=300,
        times_per_day=4,
    )
    daily_vol = daily_volume_from_delivery(delivery)
    print(f"    Daily volume: {daily_vol} mL")
    assert daily_vol == 1200, "syringe bolus daily volume should be 1200 mL"

    # 5. Daily totals
    print("\n[5] Calculating daily totals...")
    daily = calculate_daily_totals(profile, daily_vol)
    print(f"    Daily kcal: {daily.get('energy_kcal', 0):.0f}")
    print(f"    Daily protein: {daily.get('protein_g', 0):.1f} g")
    assert daily.get("energy_kcal", 0) > 0, "daily kcal should be positive"

    # 6. Targets + adequacy report
    print("\n[6] Loading targets and generating adequacy report...")
    targets = default_targets()
    adequacy = generate_adequacy_report(profile, daily_vol, targets)
    print(adequacy.to_string(index=False))
    assert len(adequacy) > 0, "adequacy report is empty"

    # 7. Formula comparison
    print("\n[7] Formula comparison (vs Peptamen 1.5)...")
    formula_cmp = generate_formula_comparison(profile, "Peptamen 1.5", daily_vol)
    print(formula_cmp.to_string(index=False))
    assert len(formula_cmp) == 4, "formula comparison should have 4 metric rows"

    # 8. Density summary
    print("\n[8] Density summary...")
    density = generate_density_summary(profile)
    print(density.to_string(index=False))
    assert len(density) == 6, "density summary should have 6 rows"

    print("\n=== ALL BACKEND MODULES VERIFIED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
