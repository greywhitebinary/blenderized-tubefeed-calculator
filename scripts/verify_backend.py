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
from src.targets import empty_targets
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
    #
    # Round-2 clinical feedback (Part 0 #2): there are NO default targets
    # anywhere in this app anymore — default_targets()/load_targets() are
    # deleted along with data/packs/canada/targets.csv. empty_targets()
    # only hands back a blank scaffold (every offer_target=yes nutrient +
    # fluid_mL, all zero); a real caller (the RD, via the app) fills in
    # patient-specific numbers. This test stands in for the RD by setting
    # a few by hand, purely so the adequacy-status logic below has
    # something non-zero to classify — these are NOT defaults, they are
    # this test's own fixture values.
    print("\n[6] Building a blank targets scaffold and filling in test values...")
    targets = empty_targets()
    assert targets.get("fluid_mL", 0.0) == 0.0, "empty_targets() should start every target at 0"
    assert set(targets.keys()) == {
        "energy_kcal", "protein_g", "fat_g", "carbohydrate_g", "fibre_g",
        "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg", "fluid_mL",
    }, f"empty_targets() keys should be exactly the 9 offer_target=yes nutrients + fluid_mL, got {sorted(targets.keys())}"
    targets["energy_kcal"] = 1800.0
    targets["protein_g"] = 70.0
    targets["fluid_mL"] = 1400.0
    targets["sodium_mg"] = 2300.0  # target_type=UL — exercises "Above/Below UL" wording below
    fluid_provided_test_mL = 950.0  # stand-in for the app's fluids-ledger figure
    adequacy, hidden_main = generate_adequacy_report(
        profile, daily_vol, targets, fluid_provided_mL=fluid_provided_test_mL
    )
    print(adequacy.to_string(index=False))
    assert len(adequacy) > 0, "adequacy report is empty"
    assert hidden_main == [], f"expected nothing hidden for a full-coverage recipe, got {hidden_main}"
    assert "Fluid provided" in adequacy["Nutrient"].values, (
        "adequacy report missing the Fluid provided row"
    )
    fluid_row = adequacy[adequacy["Nutrient"] == "Fluid provided"].iloc[0]
    assert fluid_row["Unit"] == "mL", "Fluid provided row should be in mL"
    assert fluid_row["Daily Total"] == fluid_provided_test_mL, (
        "Fluid provided row should carry the fluid_provided_mL value passed in, "
        f"got {fluid_row['Daily Total']} expected {fluid_provided_test_mL}"
    )
    assert "Free water (CNF-estimated)" in adequacy["Nutrient"].values, (
        "adequacy report missing the secondary Free water row"
    )
    free_water_row = adequacy[adequacy["Nutrient"] == "Free water (CNF-estimated)"].iloc[0]
    assert free_water_row["Unit"] == "mL", "Free water row should be in mL"
    assert free_water_row["Target"] == "—", (
        "Free water is secondary/informational now — it should carry no target "
        "of its own (Fluid provided is the row compared against the fluid target)"
    )

    # 7. Formula comparison
    print("\n[7] Formula comparison (vs Peptamen 1.5)...")
    formula_cmp = generate_formula_comparison(profile, "Peptamen 1.5", daily_vol)
    print(formula_cmp.to_string(index=False))
    assert len(formula_cmp) == 4, "formula comparison should have 4 metric rows"

    # 7b. free_water_per_mL (round-2 clinical feedback, Part 2.6) — loaded
    # from data/packs/canada/formulas.csv, values from the author's own EN
    # spreadsheet. Every shipped Canadian formula has this column; a
    # missing/absent value (an RD-added row that omits it) must come back
    # as None, never a fabricated 0 (0 would falsely claim zero free water).
    from src.calculator import COMMERCIAL_FORMULAS as _formulas_check
    peptamen_fw = _formulas_check["Peptamen 1.5"]["free_water_per_mL"]
    print(f"    Peptamen 1.5 free_water_per_mL: {peptamen_fw}")
    assert peptamen_fw == 0.770, f"expected 0.770, got {peptamen_fw}"
    assert all(
        f.get("free_water_per_mL") is not None for f in _formulas_check.values()
    ), "every shipped Canadian formula should have a free_water_per_mL value"

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

    # show_in_report / offer_target / target_type (round-2 registry columns):
    # 9 of the 13 label-tier nutrients are displayed daily (sat fat/trans
    # fat/cholesterol/sugars are tracked+exported but not shown); the
    # same 9 are the only offer_target=yes nutrients; only sodium is a UL.
    shown_label = [d for d in label_defs if d.show_in_report]
    hidden_label = [d for d in label_defs if not d.show_in_report]
    offer_target_defs = [d for d in registry if d.offer_target]
    assert len(shown_label) == 9, f"expected 9 displayed label nutrients, got {len(shown_label)}"
    assert {d.name for d in hidden_label} == {
        "saturated_fat_g", "trans_fat_g", "cholesterol_mg", "sugars_g"
    }, f"unexpected hidden label-tier set: {sorted(d.name for d in hidden_label)}"
    assert {d.name for d in offer_target_defs} == {d.name for d in shown_label}, (
        "offer_target=yes should be exactly the 9 displayed label nutrients"
    )
    assert all(not d.offer_target for d in clinical_defs), (
        "no clinical-tier nutrient (magnesium/phosphorus/zinc/vitamin D/B12) "
        "should offer a target field"
    )
    sodium_def = next(d for d in registry if d.name == "sodium_mg")
    assert sodium_def.target_type == "UL", f"sodium target_type should be 'UL', got {sodium_def.target_type!r}"
    non_sodium_types = {d.target_type for d in registry if d.name != "sodium_mg"}
    assert non_sodium_types == {""}, (
        f"only sodium should carry a target_type; found others: {non_sodium_types}"
    )
    print(f"    9 displayed label nutrients == 9 offer_target nutrients — OK")
    print(f"    Hidden (tracked, not displayed): {sorted(d.name for d in hidden_label)}")
    print(f"    Only sodium is target_type=UL — OK")

    # Main adequacy table: only tier="label"+show_in_report nutrients + the
    # two fluid rows. No vitamin D / B12 / zinc (tier=clinical) and no
    # saturated/trans fat, cholesterol, or sugars (show_in_report=no).
    main_names = set(adequacy["Nutrient"].values)
    for forbidden in (
        "Vitamin D", "Vitamin B12", "Zinc",
        "Saturated Fat", "Trans Fat", "Cholesterol", "Sugars",
    ):
        assert forbidden not in main_names, (
            f"'{forbidden}' leaked into the main adequacy report — it's "
            f"either tier=clinical or show_in_report=no, and must not "
            f"appear in the main daily-tracked table"
        )
    assert "Fluid provided" in main_names and "Free water (CNF-estimated)" in main_names
    assert len(adequacy) == 11, (  # 9 displayed label rows + 2 fluid rows
        f"expected 11 rows (9 displayed label-tier + Fluid provided + Free water), "
        f"got {len(adequacy)}"
    )
    print(f"    Main adequacy report: {len(adequacy)} rows, no sat-fat/trans-fat/"
          f"cholesterol/sugars/vitamin D/B12/zinc — OK")

    # tier="clinical" screen: the one-time ASPEN-style micro screen.
    clinical, hidden_clinical = generate_clinical_screen(profile, daily_vol, targets)
    print(clinical.to_string(index=False))
    assert hidden_clinical == [], f"expected nothing hidden for a full-coverage recipe, got {hidden_clinical}"
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

    # 11. Per-recipe coverage provenance (P2) — a missing CNF row and a true
    # zero both sum to 0 in nutrient_totals; nutrient_coverage tells us,
    # per nutrient, how many of THIS recipe's ingredients actually had
    # data. Food_Code 9 ("Meat loaf with tomato sauce, mashed potatoes and
    # peas") is a real CNF food verified to have no row for trans_fat_g
    # (605) or vitamin_d_ug (328) — pairing it with chicken (which has
    # both) gives a recipe with known, deliberately partial coverage.
    print("\n[11] Per-recipe coverage provenance...")
    incomplete_food_code = 9
    incomplete_desc = fn[fn["Food_Code"] == incomplete_food_code]["Food_Description_EN"].iloc[0]
    print(f"    Incomplete-coverage food: Food_Code {incomplete_food_code} ({incomplete_desc})")
    coverage_recipe = Recipe(
        name="Coverage test blend",
        ingredients=[
            Ingredient(food_code=chicken_code, food_description="Chicken breast", grams=200),
            Ingredient(food_code=incomplete_food_code, food_description=incomplete_desc, grams=150),
        ],
        added_water_mL=100,
        measured_final_volume_mL=450,
    )
    coverage_profile = calculate_profile(coverage_recipe, na)
    trans_fat_coverage = coverage_profile.nutrient_coverage.get("trans_fat_g")
    vit_d_coverage = coverage_profile.nutrient_coverage.get("vitamin_d_ug")
    energy_coverage = coverage_profile.nutrient_coverage.get("energy_kcal")
    print(f"    trans_fat_g coverage:  {trans_fat_coverage} (expect 1 of 2 ingredients)")
    print(f"    vitamin_d_ug coverage: {vit_d_coverage} (expect 1 of 2 ingredients)")
    print(f"    energy_kcal coverage:  {energy_coverage} (expect 2 of 2 -- full coverage)")
    assert trans_fat_coverage == (1, 2), f"expected (1, 2), got {trans_fat_coverage}"
    assert vit_d_coverage == (1, 2), f"expected (1, 2), got {vit_d_coverage}"
    assert energy_coverage == (2, 2), f"expected (2, 2) full coverage, got {energy_coverage}"

    # Trans Fat itself is show_in_report=no (round-2 registry column) so it
    # no longer appears in the main adequacy table at all — its coverage is
    # still tracked in the backend dict (asserted above) and exported (see
    # calculate_daily_totals via profile.nutrient_totals); the *report*-
    # level partial-coverage flag ("N/M ingredients") is instead checked
    # here on Vitamin D within the clinical screen, since Vitamin D *is*
    # displayed there (tier=clinical, show_in_report=yes) and is the other
    # nutrient this fixture recipe deliberately leaves partially covered.
    coverage_adequacy, coverage_hidden_main = generate_adequacy_report(
        coverage_profile, daily_vol, targets
    )
    energy_row = coverage_adequacy[coverage_adequacy["Nutrient"] == "Energy"].iloc[0]
    assert energy_row["Coverage"] == "—", (
        f"fully-covered nutrients should show '—', not be flagged: {energy_row['Coverage']!r}"
    )

    coverage_clinical, coverage_hidden_clinical = generate_clinical_screen(
        coverage_profile, daily_vol, targets
    )
    vit_d_row = coverage_clinical[coverage_clinical["Nutrient"] == "Vitamin D"].iloc[0]
    assert vit_d_row["Coverage"] == "1/2 ingredients", vit_d_row["Coverage"]

    # Strictly additive (P2's core constraint): the SAME recipe's
    # already-verified totals (stage 3's chicken/rice/oil recipe) must be
    # byte-for-byte unchanged now that calculate_profile() also computes
    # coverage -- coverage is new information, not a rewrite of existing math.
    reverified_profile = calculate_profile(recipe, na)
    assert reverified_profile.nutrient_totals == profile.nutrient_totals, (
        "adding coverage provenance changed existing nutrient totals -- "
        "P2 must be strictly additive"
    )
    print("    Coverage flags incomplete nutrients, leaves full-coverage nutrients "
          "unflagged, and does not alter existing totals — OK")

    # 12. Zero-coverage hiding (round-2 clinical feedback, Part 0 #6 / 2.2):
    # a nutrient row with ZERO ingredients supplying a value must be hidden
    # from display entirely, not shown as a confident "0" — and the report
    # must say what it hid. A custom-food-only recipe that supplies just
    # energy_kcal + protein_g is the sharpest fixture: every other
    # displayed label nutrient (fat/carb/fibre/sodium/potassium/calcium/
    # iron) and every clinical-tier nutrient has 0/1 coverage.
    print("\n[12] Zero-coverage hiding...")
    custom_only_recipe = Recipe(
        name="Custom-food-only blend",
        ingredients=[
            Ingredient(food_code=-1, food_description="Protein shake (custom)", grams=100),
        ],
        added_water_mL=0,
        measured_final_volume_mL=100,
    )
    custom_only_foods = {-1: {"energy_kcal": 50.0, "protein_g": 5.0}}
    custom_only_profile = calculate_profile(custom_only_recipe, na, custom_foods=custom_only_foods)
    hidden_adequacy, hidden_main_names = generate_adequacy_report(
        custom_only_profile, 1000.0, targets, fluid_provided_mL=0.0
    )
    print(f"    Hidden from main table: {hidden_main_names}")
    # The custom food supplies only energy_kcal + protein_g — no water_g
    # either (no label carries moisture), so the secondary Free water row
    # is zero-coverage too and gets hidden right along with the 7 label
    # nutrients. Fluid provided is NOT hidden — it's not a CNF-coverage
    # concept (it's computed from the app-level counts-as-fluid ledger,
    # passed in directly), so it's always shown.
    assert set(hidden_main_names) == {
        "Fat", "Carbohydrate", "Fibre", "Sodium", "Potassium", "Calcium", "Iron",
        "Free water (CNF-estimated)",
    }, f"expected 7 zero-coverage label nutrients + Free water hidden, got {hidden_main_names}"
    visible_names = set(hidden_adequacy["Nutrient"].values)
    assert visible_names == {"Energy", "Protein", "Fluid provided"}, (
        f"expected only Energy/Protein/Fluid provided visible, got {visible_names}"
    )
    for name in hidden_main_names:
        assert name not in visible_names, f"{name!r} should be hidden but is still visible"

    hidden_clinical_df, hidden_clinical_names = generate_clinical_screen(
        custom_only_profile, 1000.0, targets
    )
    print(f"    Hidden from clinical screen: {hidden_clinical_names}")
    assert set(hidden_clinical_names) == {
        "Magnesium", "Phosphorus", "Zinc", "Vitamin D", "Vitamin B12"
    }, f"expected all 5 clinical nutrients hidden (custom food supplies none), got {hidden_clinical_names}"
    assert len(hidden_clinical_df) == 0, "clinical screen should be fully empty for this fixture"
    print("    Zero-coverage rows hidden from both tables, with names reported — OK")

    print("\n=== ALL BACKEND MODULES VERIFIED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
