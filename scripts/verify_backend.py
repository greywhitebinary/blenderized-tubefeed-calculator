"""
verify_backend.py — Full backend integration test (Phases 2-5).

Run from the project root:
    .venv/bin/python scripts/verify_backend.py

Exercises every backend module end-to-end with real CNF data:
data_loader → models → measures → calculator → targets → report.
Exits 0 on success, non-zero on any failure.
"""

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path regardless of where this is run from
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_nutrient_amount, load_food_name, PARQUET_DIR
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
    generate_clinical_screen,
    generate_formula_comparison,
    generate_density_summary,
)
from src.nutrients import load_registry, defs_for_tier, DEFAULT_PACK


def find_food(fn, desc):
    m = fn[fn["Food_Description_EN"].str.contains(desc, case=False, na=False, regex=False)]
    if len(m) == 0:
        raise ValueError(f"No food found for {desc!r}")
    return int(m.iloc[0]["Food_Code"])


def main() -> int:
    print("=== FULL BACKEND INTEGRATION TEST ===\n")

    # 1. Load CNF data
    print("[1] Loading CNF data...")
    source = "Parquet" if PARQUET_DIR.exists() and any(PARQUET_DIR.glob("*.parquet")) else "CSV"
    t0 = time.perf_counter()
    na = load_nutrient_amount()
    fn = load_food_name()
    load_seconds = time.perf_counter() - t0
    print(f"    Nutrient_Amount: {na.shape[0]} rows")
    print(f"    Food_Name: {fn.shape[0]} rows")
    print(f"    Loaded from {source} in {load_seconds:.3f}s "
          f"(data/processed/ preferred when present, CSV fallback otherwise)")
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
    assert targets.get("fluid_mL", 0.0) > 0, "default targets missing fluid_mL"
    adequacy = generate_adequacy_report(profile, daily_vol, targets)
    print(adequacy.to_string(index=False))
    assert len(adequacy) > 0, "adequacy report is empty"
    assert "Free water" in adequacy["Nutrient"].values, (
        "adequacy report missing the Free water row"
    )
    free_water_row = adequacy[adequacy["Nutrient"] == "Free water"].iloc[0]
    assert free_water_row["Unit"] == "mL", "Free water row should be in mL"

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

    # 9. Custom food folding (Appendix A9) — calculate_profile() takes an
    # optional custom_foods dict so this math lives in the backend, not the
    # Streamlit view layer.
    print("\n[9] Custom food folding...")
    custom_recipe = Recipe(
        name="Custom food test",
        ingredients=[
            Ingredient(
                food_code=-1,
                food_description="Protein shake (custom)",
                grams=100,
            ),
        ],
        added_water_mL=0,
        measured_final_volume_mL=100,
    )
    custom_foods = {-1: {"energy_kcal": 50.0, "protein_g": 5.0}}
    custom_profile = calculate_profile(custom_recipe, na, custom_foods=custom_foods)
    print(f"    Custom-food kcal/mL: {custom_profile.kcal_per_mL:.3f}")
    print(f"    Custom-food protein/mL: {custom_profile.protein_per_mL:.3f}")
    assert custom_profile.kcal_per_mL == 0.5, "custom food kcal/mL should be 50/100 = 0.5"
    assert custom_profile.protein_per_mL == 0.05, "custom food protein/mL should be 5/100 = 0.05"

    # 10. Nutrient registry + tier-based reporting (the data-pack refactor)
    print("\n[10] Nutrient registry + tier-based reporting...")
    registry = load_registry(DEFAULT_PACK)
    print(f"    Registry: {len(registry)} nutrients loaded from "
          f"data/packs/{DEFAULT_PACK}/nutrients.csv")
    assert len(registry) == 19, f"expected 19 registry rows, got {len(registry)}"
    label_defs = defs_for_tier("label", pack=DEFAULT_PACK)
    clinical_defs = defs_for_tier("clinical", pack=DEFAULT_PACK)
    engine_defs = defs_for_tier("engine", pack=DEFAULT_PACK)
    assert len(label_defs) == 13, f"expected 13 label-tier nutrients, got {len(label_defs)}"
    assert len(clinical_defs) == 5, f"expected 5 clinical-tier nutrients, got {len(clinical_defs)}"
    assert len(engine_defs) == 1, f"expected 1 engine-tier nutrient (water_g), got {len(engine_defs)}"
    assert engine_defs[0].name == "water_g"

    # Main adequacy table: only tier="label" nutrients + Free water. No
    # vitamin D / B12 / zinc — they aren't on a Canadian label (tier="clinical").
    main_names = set(adequacy["Nutrient"].values)
    for forbidden in ("Vitamin D", "Vitamin B12", "Zinc"):
        assert forbidden not in main_names, (
            f"'{forbidden}' leaked into the main adequacy report — it's "
            f"tier=clinical, not tier=label, and must only appear in the "
            f"clinical screen"
        )
    assert "Free water" in main_names
    assert len(adequacy) == 14, (  # 13 label rows + Free water
        f"expected 14 rows (13 label-tier + Free water), got {len(adequacy)}"
    )
    print(f"    Main adequacy report: {len(adequacy)} rows, no vitamin D/B12/zinc — OK")

    # tier="clinical" screen: the one-time ASPEN-style micro screen.
    clinical = generate_clinical_screen(profile, daily_vol, targets)
    print(clinical.to_string(index=False))
    assert len(clinical) == 5, f"expected 5 clinical-screen rows, got {len(clinical)}"
    assert set(clinical["Nutrient"].values) == {
        "Magnesium", "Phosphorus", "Zinc", "Vitamin D", "Vitamin B12"
    }
    assert (clinical["Source"] == "CNF only — labels don't carry this").all(), (
        "every clinical-tier nutrient should be marked as not on a Canadian label"
    )

    # target_type="UL" semantics (sodium): must say "Above UL"/"Below UL",
    # never the old "Above target"/"Meeting target" wording.
    sodium_row = adequacy[adequacy["Nutrient"] == "Sodium"].iloc[0]
    assert sodium_row["Status"] in ("Above UL", "Below UL"), (
        f"sodium (target_type=UL) should report 'Above UL'/'Below UL', "
        f"got {sodium_row['Status']!r}"
    )
    print(f"    Sodium status: {sodium_row['Status']!r} (UL vocabulary) — OK")

    # load_registry() must raise loudly for a pack with no nutrients.csv —
    # this is deliberate (see src/nutrients.py); a silent fallback would
    # defeat the whole data-pack design. Confirm the guard is live.
    try:
        load_registry("no_such_pack")
        raise AssertionError("load_registry() should raise FileNotFoundError for a missing pack")
    except FileNotFoundError:
        pass
    print("    load_registry() raises FileNotFoundError for a missing pack — OK")

    print("\n=== ALL BACKEND MODULES VERIFIED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
