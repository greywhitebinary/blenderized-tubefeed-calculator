"""
calculator.py — Core nutrition math for the Blenderized Tube Feed Calculator.

Phase 3 of the BTF Calculator.

This module turns a Recipe (ingredients + measured volume) into a
NutrientProfile (totals + densities), then provides daily totals,
dilution what-ifs, required-volume calculations, and commercial formula
comparison.

Every equation here is documented in BUSINESS_CASE.md Appendix A
("Methodology — every equation, no black boxes").

Core calculation (Appendix A2):
    nutrient_from_ingredient = grams × (Nutrient_Amount / 100)
    recipe_total[nutrient] = Σ ( ingredient_grams × (Nutrient_Amount / 100) )

Densities (Appendix A3):
    kcal_per_mL     = recipe_total_kcal / measured_final_volume_mL
    protein_per_mL  = recipe_total_protein_g / measured_final_volume_mL
    free_water_frac = (recipe_total_water_g + added_water_mL) / measured_final_volume_mL
"""

import pandas as pd
from pathlib import Path

try:
    from src.models import Ingredient, Recipe, NutrientProfile, Delivery, DeliveryMethod
    from src.nutrients import NUTRIENT_CODES, NUTRIENT_LABELS, DEFAULT_PACK
except ImportError:
    # Allow running as a script (python src/calculator.py) without the
    # project root on sys.path — fall back to a relative-style import.
    from models import (
        Ingredient,
        Recipe,
        NutrientProfile,
        Delivery,
        DeliveryMethod,
    )
    from nutrients import NUTRIENT_CODES, NUTRIENT_LABELS, DEFAULT_PACK


# ---------------------------------------------------------------------------
# Nutrient codes — CNF Nutrient_Code → internal name
# ---------------------------------------------------------------------------

# NUTRIENT_CODES / NUTRIENT_LABELS now live in src/nutrients.py, built from
# the per-country registry at data/packs/<pack>/nutrients.csv — re-exported
# here for back-compat (this module, scripts/trace_calculation.py, and
# scripts/verify_backend.py all historically imported them from here).
# Not every CNF nutrient is tracked — only the ones on this country's
# Nutrition Facts panel (tier="label"), plus a small clinical screen and
# the "engine" nutrient (water_g) the calculator needs internally. See
# src/nutrients.py's module docstring and BUSINESS_CASE.md Appendix C for
# the full rationale.

# Reverse lookup: CNF Nutrient_Code → internal name
_CODE_TO_NAME: dict[int, str] = {v: k for k, v in NUTRIENT_CODES.items()}


# ---------------------------------------------------------------------------
# Core: Recipe → NutrientProfile
# ---------------------------------------------------------------------------


def _scale_ingredients(
    ingredients: list[Ingredient],
    nutrient_amount_df: pd.DataFrame,
    custom_foods: dict[int, dict[str, float]] | None = None,
) -> tuple[dict[str, float], pd.DataFrame]:
    """The ingredient-scaling core (steps 1-6) shared by every caller that
    needs "grams of these foods -> nutrient totals", with NO volume/density
    concept at all. Extracted per FEED_LOG_REWORK.md section 3.1 so the Intake
    Record's oral rows (a single food, no batch/volume to divide by) can
    call this directly instead of duplicating it or faking a placeholder
    volume just to satisfy calculate_profile()'s density wrapper.

    How it works (vectorized, no .iterrows()):
      1. Build a small DataFrame of the ingredients (food_code, grams).
      2. Filter Nutrient_Amount to only the nutrient codes we track.
      3. Merge ingredients with nutrient amounts on Food_Code.
      4. Scale: each row's amount x (grams / 100) -> nutrient from that ingredient.
      5. Group by nutrient code, sum -> totals.
      6. Map codes to internal names, build the totals dict, and fold in
         any custom-food contributions (Appendix A9).

    Returns (nutrient_totals, merged) -- `merged` is the intermediate
    ingredient x nutrient-amount join, returned so calculate_profile() can
    build its per-recipe coverage provenance (see _coverage_from_merged())
    without re-deriving the join. Callers that only want totals should use
    compute_nutrient_totals() instead, which discards `merged`.
    """
    if not ingredients:
        return {}, pd.DataFrame(columns=["Food_Code", "Nutrient_Code"])

    # Step 1: Build ingredient table
    ingr_df = pd.DataFrame(
        [{"Food_Code": ing.food_code, "grams": ing.grams} for ing in ingredients]
    )

    # Step 2: Filter Nutrient_Amount to only the codes we track
    tracked_codes = list(NUTRIENT_CODES.values())
    na_filtered = nutrient_amount_df[
        nutrient_amount_df["Nutrient_Code"].isin(tracked_codes)
    ].copy()

    # Step 3: Merge ingredients with nutrient amounts
    #   inner join: only rows where the food_code exists in both tables.
    #   Custom foods (negative food_code) have no match in CNF data, so
    #   they simply drop out here -- their contribution is folded in below.
    merged = ingr_df.merge(na_filtered, on="Food_Code", how="inner")

    # Step 4: Scale per-100g amounts to actual grams used
    #   nutrient_from_ingredient = grams x (Nutrient_Amount / 100)
    merged["scaled_amount"] = merged["grams"] * (merged["Nutrient_Amount"] / 100.0)

    # Step 5: Group by nutrient code, sum across all ingredients
    totals_by_code = merged.groupby("Nutrient_Code")["scaled_amount"].sum()

    # Step 6: Map codes to internal names, build the nutrient totals dict,
    # then fold in custom-food contributions (Appendix A9). Negative
    # food_codes identify custom foods entered from a nutrition facts label;
    # their per-100g values are scaled by grams used, same as CNF foods.
    nutrient_totals: dict[str, float] = {}
    for code, total in totals_by_code.items():
        name = _CODE_TO_NAME.get(int(code))
        if name:
            nutrient_totals[name] = float(total)

    if custom_foods:
        for ing in ingredients:
            if ing.food_code < 0:
                custom_data = custom_foods.get(ing.food_code, {})
                for nutrient_name, per_100g_value in custom_data.items():
                    scaled = per_100g_value * (ing.grams / 100.0)
                    nutrient_totals[nutrient_name] = (
                        nutrient_totals.get(nutrient_name, 0.0) + scaled
                    )

    return nutrient_totals, merged


def _coverage_from_merged(
    ingredients: list[Ingredient],
    merged: pd.DataFrame,
    custom_foods: dict[int, dict[str, float]] | None = None,
) -> dict[str, tuple[int, int]]:
    """Per-ingredient-list coverage provenance (calculate_profile()'s old
    step 8), factored out so both calculate_profile() and the Intake Record
    aggregation (src/intake.py) can attach coverage to an arbitrary
    ingredient list -- a recipe's ingredients, or a single oral food -- not
    only a full Recipe wrapped in a NutrientProfile.

    A missing CNF row and a true zero are otherwise indistinguishable: both
    simply don't appear in `merged` (the inner join drops them) and so
    contribute nothing to the totals. This counts, per tracked nutrient,
    how many of the given ingredients actually supplied a value for that
    nutrient (a CNF row was present, or -- for a custom food -- the RD
    entered that field), out of the ingredient count.
    """
    n_total = len(ingredients)
    # merged is already one row per (ingredient instance, nutrient code)
    # supplied by CNF -- counting rows per Nutrient_Code counts ingredients,
    # even when two ingredients share the same Food_Code, because the
    # merge preserves the ingredient table's row-per-ingredient granularity.
    cnf_supplying_counts = merged.groupby("Nutrient_Code")["Food_Code"].count()
    coverage: dict[str, tuple[int, int]] = {
        name: (int(cnf_supplying_counts.get(code, 0)), n_total)
        for name, code in NUTRIENT_CODES.items()
    }
    if custom_foods:
        for ing in ingredients:
            if ing.food_code < 0:
                custom_data = custom_foods.get(ing.food_code, {})
                for nutrient_name in custom_data:
                    if nutrient_name in coverage:
                        n_supplying, n_tot = coverage[nutrient_name]
                        coverage[nutrient_name] = (n_supplying + 1, n_tot)
    return coverage


def compute_nutrient_totals(
    ingredients: list[Ingredient],
    nutrient_amount_df: pd.DataFrame,
    custom_foods: dict[int, dict[str, float]] | None = None,
) -> dict[str, float]:
    """Standalone entry point for the ingredient-scaling core (steps 1-6),
    with NO volume/density wrapper at all (FEED_LOG_REWORK.md section 3.1).

    This is what an Intake Record oral row calls: a single food (or small
    list of foods) has no batch/density concept -- there's no "volume" to
    measure for one banana -- so it goes straight through the same
    grams x per-100g merge-and-scale math a blend ingredient uses, without
    calculate_profile()'s measured_volume_mL > 0 guard (which exists only
    to make density *properties* meaningful, not because steps 1-6 need a
    volume). calculate_profile() calls the same shared core internally
    (via _scale_ingredients) -- this function and calculate_profile() can
    never diverge, by construction.

    Args:
        ingredients:         List of Ingredient (food_code, description, grams).
        nutrient_amount_df:  The CNF Nutrient_Amount DataFrame (from data_loader).
        custom_foods:        Optional dict of food_code -> per-100g nutrient dict
                              (Appendix A9), same convention as calculate_profile().

    Returns:
        Dict of nutrient_name -> total amount (e.g. "energy_kcal": 74.3).
    """
    nutrient_totals, _merged = _scale_ingredients(
        ingredients, nutrient_amount_df, custom_foods
    )
    return nutrient_totals


def compute_nutrient_totals_and_coverage(
    ingredients: list[Ingredient],
    nutrient_amount_df: pd.DataFrame,
    custom_foods: dict[int, dict[str, float]] | None = None,
) -> tuple[dict[str, float], dict[str, tuple[int, int]]]:
    """Same core as compute_nutrient_totals(), but also returns per-nutrient
    coverage provenance (n_supplying, n_total — see _coverage_from_merged()'s
    docstring). Used by the Intake Record aggregation (src/intake.py) so
    coverage-provenance / zero-coverage hiding stays available for blend
    and oral rows outside a full Recipe/NutrientProfile, without
    duplicating the merge-and-scale logic a second time.
    """
    nutrient_totals, merged = _scale_ingredients(
        ingredients, nutrient_amount_df, custom_foods
    )
    coverage = _coverage_from_merged(ingredients, merged, custom_foods)
    return nutrient_totals, coverage


def calculate_profile(
    recipe: Recipe,
    nutrient_amount_df: pd.DataFrame,
    custom_foods: dict[int, dict[str, float]] | None = None,
) -> NutrientProfile:
    """Calculate the nutrient profile for a recipe.

    Takes a Recipe (ingredients with grams + measured volume) and the
    CNF Nutrient_Amount DataFrame, returns a NutrientProfile with
    per-recipe totals and derived densities.

    The ingredient-scaling core (steps 1-6 -- build ingredient table, filter
    Nutrient_Amount to tracked codes, merge, scale, groupby+sum, fold in
    custom foods) lives in _scale_ingredients() and is also available
    standalone via compute_nutrient_totals() (FEED_LOG_REWORK.md section 3.1)
    for callers with no volume/density concept (Intake Record oral rows).
    This function wraps that core with the density-bearing NutrientProfile
    and the measured-volume guard below; the guard is about making
    densities meaningful, not about the scaling math, which is why
    compute_nutrient_totals() doesn't need it.

    Args:
        recipe:              A Recipe with ingredients and measured_final_volume_mL.
        nutrient_amount_df:  The CNF Nutrient_Amount DataFrame (from data_loader).
        custom_foods:        Optional dict of food_code -> per-100g nutrient dict,
                              for foods entered from a nutrition facts label
                              (Appendix A9). Custom foods use negative food_codes
                              so they never collide with real CNF Food_Codes and
                              simply drop out of the CNF merge; their nutrient
                              contribution is added in via _scale_ingredients().

    Returns:
        NutrientProfile with totals and densities.
    """
    if not recipe.ingredients or recipe.measured_final_volume_mL <= 0:
        return NutrientProfile(
            measured_final_volume_mL=recipe.measured_final_volume_mL,
            added_water_mL=recipe.added_water_mL,
        )

    nutrient_totals, merged = _scale_ingredients(
        recipe.ingredients, nutrient_amount_df, custom_foods
    )

    # Per-recipe coverage provenance (strictly additive -- does not change
    # any total computed above). Complements the registry's static
    # on_label flag (P1), which flags nutrients a LABEL can never supply
    # regardless of the recipe; this flags nutrients THIS recipe happens to
    # be missing data for. See _coverage_from_merged()'s docstring.
    nutrient_coverage = _coverage_from_merged(recipe.ingredients, merged, custom_foods)

    return NutrientProfile(
        nutrient_totals=nutrient_totals,
        measured_final_volume_mL=recipe.measured_final_volume_mL,
        added_water_mL=recipe.added_water_mL,
        nutrient_coverage=nutrient_coverage,
    )


# ---------------------------------------------------------------------------
# Daily totals (Appendix A5)
# ---------------------------------------------------------------------------


def calculate_daily_totals(
    profile: NutrientProfile,
    daily_volume_mL: float,
) -> dict[str, float]:
    """Scale per-recipe nutrient totals to daily intake.

    daily_[nutrient] = (recipe_[nutrient] / measured_volume_mL) × daily_volume_mL

    This is the same as density × daily_volume for each nutrient.

    Args:
        profile:         The NutrientProfile (per-recipe totals + measured volume).
        daily_volume_mL: Total mL delivered per day (from Delivery or direct input).

    Returns:
        Dict of nutrient_name → daily total amount.
    """
    if profile.measured_final_volume_mL <= 0:
        return {name: 0.0 for name in NUTRIENT_CODES}

    scale = daily_volume_mL / profile.measured_final_volume_mL
    return {name: amount * scale for name, amount in profile.nutrient_totals.items()}


def daily_volume_from_delivery(delivery: Delivery) -> float:
    """Extract the daily volume from a Delivery object.

    Syringe bolus:  bolus_volume_mL × times_per_day
    Pump:           rate_mL_per_hr × hours_per_day
    Direct:         daily_volume_mL
    """
    return delivery.calculated_daily_volume_mL


# ---------------------------------------------------------------------------
# Dilution what-if (Appendix A8)
# ---------------------------------------------------------------------------


def dilute(
    profile: NutrientProfile,
    added_liquid_mL: float,
    liquid_kcal: float = 0.0,
    liquid_protein_g: float = 0.0,
    liquid_water_g: float = 0.0,
) -> NutrientProfile:
    """Simulate adding a thinning liquid to the recipe.

    This is the core what-if feature. The RD asks: "If I add 150 mL of
    [water/juice/broth/milk/oil], what happens to the densities?"

    For pure water: liquid_kcal=0, liquid_protein_g=0, liquid_water_g=150.
    For juice/broth/milk/oil: both numerator and denominator change.

    new_volume_mL      = measured_final_volume_mL + added_liquid_mL
    new_kcal_per_mL    = (recipe_total_kcal + liquid_kcal) / new_volume_mL
    new_protein_per_mL = (recipe_total_protein_g + liquid_protein_g) / new_volume_mL
    new_water_frac     = (recipe_total_water_g + liquid_water_g) / new_volume_mL

    Args:
        profile:          The original recipe's NutrientProfile.
        added_liquid_mL:  Volume of liquid being added (mL).
        liquid_kcal:      kcal in the added liquid (0 for water).
        liquid_protein_g: Protein (g) in the added liquid (0 for water).
        liquid_water_g:   Water (g) in the added liquid (for water, ≈ added_liquid_mL).

    Returns:
        A new NutrientProfile reflecting the diluted recipe.
    """
    new_volume = profile.measured_final_volume_mL + added_liquid_mL

    # Build new totals: original + added liquid's contribution
    new_totals = dict(profile.nutrient_totals)
    new_totals["energy_kcal"] = new_totals.get("energy_kcal", 0.0) + liquid_kcal
    new_totals["protein_g"] = new_totals.get("protein_g", 0.0) + liquid_protein_g
    new_totals["water_g"] = new_totals.get("water_g", 0.0) + liquid_water_g

    return NutrientProfile(
        nutrient_totals=new_totals,
        measured_final_volume_mL=new_volume,
        added_water_mL=profile.added_water_mL,  # original added water unchanged
    )


def required_daily_volume(
    profile: NutrientProfile,
    target_kcal: float,
    target_protein_g: float,
) -> float:
    """Calculate the daily volume needed to meet both kcal and protein targets.

    volume_to_meet_kcal    = target_kcal / kcal_per_mL
    volume_to_meet_protein = target_protein_g / protein_per_mL
    required_daily_volume  = max(volume_to_meet_kcal, volume_to_meet_protein)

    The binding constraint (whichever is larger) determines the required volume.

    Args:
        profile:          The NutrientProfile (with densities).
        target_kcal:      RD's target daily kcal.
        target_protein_g: RD's target daily protein (g).

    Returns:
        Required daily volume in mL (0 if densities are zero).
    """
    vol_for_kcal = target_kcal / profile.kcal_per_mL if profile.kcal_per_mL > 0 else float("inf")
    vol_for_protein = (
        target_protein_g / profile.protein_per_mL
        if profile.protein_per_mL > 0
        else float("inf")
    )
    return max(vol_for_kcal, vol_for_protein)


# ---------------------------------------------------------------------------
# Commercial formula comparator (Appendix A7)
# ---------------------------------------------------------------------------


# Formula profiles (BUSINESS_CASE.md Appendix A7), re-verified 2026-07-19
# against manufacturer HCP product guides in
# data/packs/canada/formula_sources/ — see that folder's README for the
# update workflow. These are the Canadian commercial formulas RDs
# commonly compare against.
#
# The canonical source is data/packs/<pack>/formulas.csv — an RD can add
# or update formulas there without touching Python. The hardcoded dict
# below is a fallback used only if the CSV is missing (e.g., running in a
# stripped-down environment). Unlike src/nutrients.py::load_registry(),
# this IS allowed to fall back — formula profiles are reference data, not
# structural (see src/nutrients.py's module docstring for that distinction).
# Deliberately NOT kept in lockstep with every CSV column/row (e.g. it
# has 4 fields and 8 formulas where the CSV has 12 and 33) -- it exists
# only so the app still runs with *some* reference data if the CSV is
# ever missing, not as a mirror of the full catalog.
_FORMULAS_FALLBACK: dict[str, dict[str, float]] = {
    "Isosource Fibre 1.5": {"kcal_per_mL": 1.5, "protein_per_mL": 0.070, "free_water_per_mL": 0.766, "brand": "Nestlé Health Science"},
    "Isosource Fibre 1.2": {"kcal_per_mL": 1.2, "protein_per_mL": 0.054, "free_water_per_mL": 0.805, "brand": "Nestlé Health Science"},
    "Isosource Fibre 1.0 HP": {"kcal_per_mL": 1.0, "protein_per_mL": 0.064, "free_water_per_mL": 0.840, "brand": "Nestlé Health Science"},
    "Nepro": {"kcal_per_mL": 1.8, "protein_per_mL": 0.081, "free_water_per_mL": 0.727, "brand": "Abbott Nutrition"},
    "Peptamen AF 1.2": {"kcal_per_mL": 1.2, "protein_per_mL": 0.076, "free_water_per_mL": 0.810, "brand": "Nestlé Health Science"},
    "Peptamen Intense 1.0 HP": {"kcal_per_mL": 1.0, "protein_per_mL": 0.092, "free_water_per_mL": 0.840, "brand": "Nestlé Health Science"},
    "Resource 2.0": {"kcal_per_mL": 2.0, "protein_per_mL": 0.084, "free_water_per_mL": 0.690, "brand": "Nestlé Health Science"},
    "Peptamen 1.5": {"kcal_per_mL": 1.5, "protein_per_mL": 0.068, "free_water_per_mL": 0.770, "brand": "Nestlé Health Science"},
}

# Per-mL nutrient columns beyond kcal/protein — same "Nutrition Facts
# panel" lens already used for BTF recipes (data/packs/<pack>/nutrients.csv's
# label tier), plus magnesium/phosphorus per the EN spreadsheet's own
# tracked set. fat/carbohydrate/fibre are g/mL; sodium/potassium/calcium/
# iron/magnesium/phosphorus are mg/mL (see formula_sources/README.md).
# All OPTIONAL, same contract as free_water_per_mL below: a formula
# whose label doesn't disclose one of these gets None, never a
# fabricated 0.
_OPTIONAL_NUTRIENT_COLUMNS = (
    "fat_per_mL", "carbohydrate_per_mL", "fibre_per_mL",
    "sodium_per_mL", "potassium_per_mL", "calcium_per_mL",
    "iron_per_mL", "magnesium_per_mL", "phosphorus_per_mL",
)


def _load_commercial_formulas(pack: str = DEFAULT_PACK) -> dict[str, dict[str, float]]:
    """Load commercial formulas from CSV, falling back to hardcoded dict.

    CSV format: name,brand,kcal_per_mL,protein_per_mL,<_OPTIONAL_NUTRIENT_COLUMNS>,
    free_water_per_mL,source,verified

    free_water_per_mL (round-2 clinical feedback, Part 2.6) is the
    formula's free-water content per mL, from the author's own EN
    spreadsheet. It's OPTIONAL in the CSV — an RD adding a new formula
    row without knowing this figure gets None here rather than a
    fabricated number; callers (the comparator, the combined regimen
    summary) must handle None (e.g. render "—" / skip the free-water
    line) rather than treating it as 0, since 0 would falsely claim the
    formula has zero free water. The columns in _OPTIONAL_NUTRIENT_COLUMNS
    follow the identical optional/None contract.

    brand (the manufacturer, e.g. "Nestlé Health Science" / "Abbott
    Nutrition") is likewise OPTIONAL — a hand-added formula row without
    one recorded gets None, not a fabricated guess; UI grouping code
    treats None as an "Other" bucket rather than erroring.

    Args:
        pack: Data pack name (e.g. "canada"). Defaults to DEFAULT_PACK,
              matching the same idiom as src/nutrients.py::load_registry().
    """
    formulas_csv = Path(__file__).resolve().parent.parent / "data" / "packs" / pack / "formulas.csv"
    if not formulas_csv.exists():
        return dict(_FORMULAS_FALLBACK)

    df = pd.read_csv(formulas_csv)
    formulas: dict[str, dict[str, float]] = {}
    for _, row in df.iterrows():
        free_water = row.get("free_water_per_mL")
        brand = row.get("brand")
        entry: dict[str, float] = {
            "kcal_per_mL": float(row["kcal_per_mL"]),
            "protein_per_mL": float(row["protein_per_mL"]),
            "free_water_per_mL": (
                float(free_water) if pd.notna(free_water) else None
            ),
            "brand": brand if pd.notna(brand) else None,
        }
        for col in _OPTIONAL_NUTRIENT_COLUMNS:
            val = row.get(col)
            entry[col] = float(val) if pd.notna(val) else None
        formulas[row["name"]] = entry
    return formulas


COMMERCIAL_FORMULAS: dict[str, dict[str, float]] = _load_commercial_formulas()


def compare_with_formula(
    profile: NutrientProfile,
    formula_name: str,
    daily_volume_mL: float,
) -> dict[str, dict[str, float]]:
    """Compare BTF recipe against a commercial formula at the same daily volume.

    BTF daily kcal     = kcal_per_mL × daily_volume_mL
    formula daily kcal = formula_kcal_per_mL × daily_volume_mL

    Args:
        profile:         The BTF recipe's NutrientProfile.
        formula_name:    Key into COMMERCIAL_FORMULAS.
        daily_volume_mL: The daily volume to compare at.

    Returns:
        {"btf": {"kcal": ..., "protein_g": ...},
         "formula": {"kcal": ..., "protein_g": ...}}
    """
    formula = COMMERCIAL_FORMULAS.get(formula_name)
    if formula is None:
        raise ValueError(
            f"Unknown formula '{formula_name}'. "
            f"Available: {list(COMMERCIAL_FORMULAS.keys())}"
        )

    return {
        "btf": {
            "kcal": profile.kcal_per_mL * daily_volume_mL,
            "protein_g": profile.protein_per_mL * daily_volume_mL,
        },
        "formula": {
            "kcal": formula["kcal_per_mL"] * daily_volume_mL,
            "protein_g": formula["protein_per_mL"] * daily_volume_mL,
        },
    }


def volume_to_match_formula_kcal(
    profile: NutrientProfile,
    formula_name: str,
    daily_volume_mL: float,
) -> float:
    """How much BTF volume is needed to match the formula's kcal at the same volume?

    formula_kcal = formula_kcal_per_mL × daily_volume_mL
    btf_volume_needed = formula_kcal / btf_kcal_per_mL

    This answers: "The formula gives X kcal at 1200 mL — how much BTF do I
    need to get the same X kcal?"

    Args:
        profile:         The BTF recipe's NutrientProfile.
        formula_name:    Key into COMMERCIAL_FORMULAS.
        daily_volume_mL: The formula's daily volume.

    Returns:
        BTF volume (mL) needed to match the formula's kcal output.
    """
    formula = COMMERCIAL_FORMULAS[formula_name]
    formula_kcal = formula["kcal_per_mL"] * daily_volume_mL
    if profile.kcal_per_mL <= 0:
        return float("inf")
    return formula_kcal / profile.kcal_per_mL


# ---------------------------------------------------------------------------
# Custom food from label (Appendix A9)
# ---------------------------------------------------------------------------


def label_to_per_100g(label_value: float, serving_size_g: float) -> float:
    """Convert a nutrition facts label value to per-100g basis.

    per_100g_value = label_value × (100 / serving_size_g)

    Example: 175 g serving has 130 kcal → per 100 g = 130 × (100/175) = 74.3 kcal

    Args:
        label_value:     The nutrient amount on the label (per serving).
        serving_size_g:  The serving size in grams (from the label).

    Returns:
        The nutrient amount per 100 g.
    """
    if serving_size_g <= 0:
        raise ValueError("serving_size_g must be positive")
    return label_value * (100.0 / serving_size_g)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # Quick test: build a simple recipe and calculate its profile.
    # Uses real CNF data — chicken breast + rice + canola oil.
    import sys
    sys.path.insert(0, ".")

    from src.data_loader import load_nutrient_amount, load_food_name

    print("Loading CNF data...")
    na = load_nutrient_amount()
    fn = load_food_name()

    # Find some food codes to test with
    def find_food(description: str) -> int:
        match = fn[fn["Food_Description_EN"].str.contains(description, case=False, na=False)]
        if len(match) == 0:
            raise ValueError(f"No food found for '{description}'")
        return int(match.iloc[0]["Food_Code"])

    chicken_code = find_food("Chicken, broiler, breast, skinless, boneless, meat, raw")
    rice_code = find_food("Grains, rice, white, long-grain, parboiled, cooked")
    oil_code = find_food("Vegetable oil, canola")

    print(f"  Chicken breast: Food_Code {chicken_code}")
    print(f"  Rice (cooked):  Food_Code {rice_code}")
    print(f"  Canola oil:     Food_Code {oil_code}")

    # Build a test recipe: 200g chicken, 150g rice, 15g oil, 200mL water, 550mL final
    recipe = Recipe(
        name="Test chicken-rice blend",
        ingredients=[
            Ingredient(food_code=chicken_code, food_description="Chicken breast", grams=200),
            Ingredient(food_code=rice_code, food_description="Rice, cooked", grams=150),
            Ingredient(food_code=oil_code, food_description="Canola oil", grams=15),
        ],
        added_water_mL=200,
        measured_final_volume_mL=550,
    )

    print(f"\nRecipe: {recipe.name}")
    print(f"  {len(recipe.ingredients)} ingredients, {recipe.added_water_mL} mL added water, "
          f"{recipe.measured_final_volume_mL} mL measured volume")

    print("\nCalculating profile...")
    profile = calculate_profile(recipe, na)

    print(f"\n--- Nutrient totals (per recipe) ---")
    for name in NUTRIENT_CODES:
        val = profile.nutrient_totals.get(name, 0.0)
        label = NUTRIENT_LABELS[name]
        print(f"  {label:<25} {val:>10.1f}")

    print(f"\n--- Densities (primary outputs) ---")
    print(f"  kcal/mL:         {profile.kcal_per_mL:.3f}")
    print(f"  protein g/mL:    {profile.protein_per_mL:.3f}")
    print(f"  free water frac: {profile.free_water_fraction:.3f}")

    # Daily totals at 1200 mL/day
    daily = calculate_daily_totals(profile, 1200)
    print(f"\n--- Daily totals at 1200 mL/day ---")
    for name in ["energy_kcal", "protein_g", "fibre_g", "sodium_mg", "potassium_mg"]:
        val = daily.get(name, 0.0)
        label = NUTRIENT_LABELS[name]
        print(f"  {label:<25} {val:>10.1f}")

    # Dilution what-if: add 100 mL water
    diluted = dilute(profile, added_liquid_mL=100, liquid_water_g=100)
    print(f"\n--- After adding 100 mL water ---")
    print(f"  New volume:      {diluted.measured_final_volume_mL:.0f} mL")
    print(f"  kcal/mL:         {diluted.kcal_per_mL:.3f} (was {profile.kcal_per_mL:.3f})")
    print(f"  protein g/mL:    {diluted.protein_per_mL:.3f} (was {profile.protein_per_mL:.3f})")
    print(f"  free water frac: {diluted.free_water_fraction:.3f} (was {profile.free_water_fraction:.3f})")

    # Required volume to meet 1800 kcal, 75g protein
    req_vol = required_daily_volume(profile, target_kcal=1800, target_protein_g=75)
    print(f"\n--- Required daily volume for 1800 kcal + 75g protein ---")
    print(f"  {req_vol:.0f} mL")

    # Formula comparison
    comparison = compare_with_formula(profile, "Peptamen 1.5", 1200)
    print(f"\n--- BTF vs Peptamen 1.5 at 1200 mL/day ---")
    print(f"  BTF:     {comparison['btf']['kcal']:.0f} kcal, {comparison['btf']['protein_g']:.1f} g protein")
    print(f"  Formula: {comparison['formula']['kcal']:.0f} kcal, {comparison['formula']['protein_g']:.1f} g protein")

    vol_needed = volume_to_match_formula_kcal(profile, "Peptamen 1.5", 1200)
    print(f"\n  BTF volume needed to match Peptamen 1.5's kcal: {vol_needed:.0f} mL")

    print("\n✅ Calculator smoke test passed.")