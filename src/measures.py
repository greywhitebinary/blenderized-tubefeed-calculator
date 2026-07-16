"""
measures.py — Household measure → grams conversion for BTF ingredients.

Phase 4 of the BTF Calculator.

CNF provides a Measure_Weight_Conversion table that maps (Food_Code +
Measure_Code) → grams. For example, Food_Code 4473 (cooked rice) +
Measure_Code for "1 cup" → 158 g.

The table includes three Measure_Types:
  3 = Refuse (inedible parts — bones, peels — not useful for recipe entry)
  6 = User-defined (the household measures RDs actually use: cup, tbsp, etc.)
  9 = Yield (cooked/raw conversions — not for recipe entry)

We filter to Measure_Type=6 only, as specified in CONTEXT.md §6.

This module lets the RD enter "1 cup rice" instead of "158 g rice" —
but grams are always the canonical unit internally.
"""

import pandas as pd

from src.data_loader import (
    load_measure_name,
    load_measure_weight_conversion,
)


# Measure_Type_Code 6 = User-defined household measures
HOUSEHOLD_MEASURE_TYPE = 6


def load_measure_lookup() -> pd.DataFrame:
    """Build a lookup table: Food_Code + Measure_Code → grams + description.

    Joins Measure_Weight_Conversion with Measure_Name to get human-readable
    measure descriptions alongside the gram weights. Filters to household
    measures only (Measure_Type=6).

    Returns:
        DataFrame with columns:
            Food_Code, Measure_Code, Measure_Weight_Conversion (grams),
            Measure_Description_and_Unit_EN
    """
    mwc = load_measure_weight_conversion()
    mn = load_measure_name()

    # Filter to household measures only
    household = mwc[mwc["Measure_Type_Code"] == HOUSEHOLD_MEASURE_TYPE].copy()

    # Join with measure names for human-readable descriptions
    merged = household.merge(mn, on="Measure_Code", how="left")

    # Select and rename columns for clarity
    result = merged[
        ["Food_Code", "Measure_Code", "Measure_Weight_Conversion",
         "Measure_Description_and_Unit_EN"]
    ].rename(columns={"Measure_Weight_Conversion": "grams"})

    return result


def measure_to_grams(
    food_code: int,
    measure_code: int,
    quantity: float = 1.0,
    lookup_df: pd.DataFrame | None = None,
) -> float:
    """Convert a household measure to grams for a specific food.

    Example: measure_to_grams(4473, <cup_code>, quantity=1.5) → 237.0
    (1.5 cups of cooked rice = 237 g)

    Args:
        food_code:    CNF Food_Code.
        measure_code: CNF Measure_Code.
        quantity:     How many of this measure (e.g., 1.5 for "1.5 cups").
        lookup_df:    Pre-loaded lookup table (avoids re-loading on each call).

    Returns:
        Grams (float). Raises ValueError if the food/measure combo isn't found.
    """
    if lookup_df is None:
        lookup_df = load_measure_lookup()

    row = lookup_df[
        (lookup_df["Food_Code"] == food_code)
        & (lookup_df["Measure_Code"] == measure_code)
    ]

    if len(row) == 0:
        raise ValueError(
            f"No household measure found for Food_Code {food_code}, "
            f"Measure_Code {measure_code}"
        )

    grams_per_measure = float(row.iloc[0]["grams"])
    return grams_per_measure * quantity


def get_measures_for_food(
    food_code: int,
    lookup_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Get all available household measures for a given food.

    Useful for populating a dropdown in the UI: "Select measure for
    cooked rice → [1 cup (158 g), 1 tbsp (9.9 g), ...]"

    Args:
        food_code:  CNF Food_Code.
        lookup_df:  Pre-loaded lookup table (avoids re-loading on each call).

    Returns:
        DataFrame of available measures for this food, sorted by grams descending.
    """
    if lookup_df is None:
        lookup_df = load_measure_lookup()

    measures = lookup_df[lookup_df["Food_Code"] == food_code].copy()
    return measures.sort_values("grams", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")

    from src.data_loader import load_food_name

    print("Loading measure lookup...")
    lookup = load_measure_lookup()
    print(f"  {len(lookup)} household measures available")

    # Show measures for cooked rice (Food_Code 4473)
    fn = load_food_name()
    rice = fn[fn["Food_Code"] == 4473].iloc[0]
    print(f"\nMeasures for: {rice['Food_Description_EN']}")

    rice_measures = get_measures_for_food(4473, lookup)
    print(rice_measures.to_string(index=False))

    # Convert 1.5 cups of rice to grams
    if len(rice_measures) > 0:
        cup_measure = rice_measures[
            rice_measures["Measure_Description_and_Unit_EN"].str.contains(
                "cup", case=False, na=False
            )
        ]
        if len(cup_measure) > 0:
            cup_code = int(cup_measure.iloc[0]["Measure_Code"])
            grams = measure_to_grams(4473, cup_code, quantity=1.5, lookup_df=lookup)
            print(f"\n1.5 cups of cooked rice = {grams:.1f} g")

    # Show measures for chicken breast (Food_Code 841)
    chicken = fn[fn["Food_Code"] == 841].iloc[0]
    print(f"\nMeasures for: {chicken['Food_Description_EN']}")
    chicken_measures = get_measures_for_food(841, lookup)
    print(chicken_measures.to_string(index=False))

    print("\n✅ Measures smoke test passed.")