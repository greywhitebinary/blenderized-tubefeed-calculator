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

import re

import pandas as pd

try:
    from src.data_loader import (
        load_measure_name,
        load_measure_weight_conversion,
    )
except ImportError:
    # Allow running as a script (python src/measures.py) without the
    # project root on sys.path — fall back to a relative-style import.
    from data_loader import (
        load_measure_name,
        load_measure_weight_conversion,
    )

# Measure_Type_Code 6 = User-defined household measures
HOUSEHOLD_MEASURE_TYPE = 6

# ---------------------------------------------------------------------------
# Change 1.5 (plan you-know-the-line-vectorized-milner.md): drop the plain
# gram weights out of the household-measure list.
# ---------------------------------------------------------------------------
# CNF's own Measure_Type=6 filter above already narrows to "household
# measures", but 38 of those rows are themselves nothing but a bare gram
# figure -- "125 g", "90 g", "55 g". With plain "g" already offered
# separately (meaning "type any weight"), a bare-gram measure is not a
# genuine kitchen measure at all -- it's the exact same choice as "g" with
# one arbitrary number baked in, sitting in the dropdown as if it were a
# third, different kind of thing (see CONTEXT for item 3 of the Feed
# Recipes rework: "the unit dropdown mixes unlike things"). Filtering
# these out loses nothing: any weight is still typeable under "g".
#
# Matches a bare number (optional decimal, optional space before "g") and
# NOTHING else -- "1/2 foot", "250 ml chopped or diced", and the four
# "yield from ... ear" labels (verbose, but genuine measures -- CNF tags
# them User-defined too, per CNF's own Measure_Type_Code) all keep at
# least one non-numeric, non-gram word, so none of them match.
_BARE_GRAM_WEIGHT = re.compile(r"^\d+(\.\d+)?\s*g$")


def is_bare_gram_weight(description: str | None) -> bool:
    """True for a measure description that is nothing but a number of
    grams (e.g. "125 g") -- see the module-level note above. A
    documented rule, not an app-layer string hack, so it has one
    definition and one test (tests/test_measures.py).

    Guards against a missing description (a left-joined Measure_Code with
    no matching Measure_Name row) rather than raising on `.strip()`.
    """
    if not isinstance(description, str):
        return False
    return bool(_BARE_GRAM_WEIGHT.match(description.strip()))


# A CNF measure description that opens with its own count: "250 ml",
# "1 extra large (23cm or longer)", "1/2 egg". 98.5% of the 1146 labels in
# the filtered lookup are this shape, which is what makes scaling them
# readable rather than printing "2 x 1 extra large ..." (author, 2026-08-15).
# Requires whitespace after the number so "4.5oz cocktail" and the range
# labels ("8-14 seeds", "15-20 nachos") fall through to the multiplier form
# instead of being half-parsed.
_LEADING_COUNT = re.compile(r"^\s*(\d+(?:\.\d+)?|\d+/\d+)\s+(\S.*)$")


def scale_measure_label(description: str | None, quantity: float) -> str:
    """Fold `quantity` INTO a CNF measure description.

    "250 ml" x 2 -> "500 ml"; "1 extra large (23cm or longer)" x 2 ->
    "2 extra large (23cm or longer)"; "1/2 egg" x 2 -> "1 egg". The point
    is a recipe line that reads like a recipe: multiplying the count out
    beats printing "2 x 1 extra large ..." (author, 2026-08-15).

    Falls back to "<qty> x <description>" in two cases:

      1. The description does not open with a count (17 labels, e.g.
         "yield from 1 large ear (20cm to 23cm long)", "8-14 seeds").
      2. The description contains "=" (4 labels). Scaling those states
         something FALSE: "1/2 bagel = 1 food guide serving" doubled would
         print "1 bagel = 1 food guide serving", when one bagel is two
         servings. A clumsy line is fine; a wrong equation on a recipe is
         not.

    Quantity 1 returns the description unchanged, since CNF labels already
    carry their own count.
    """
    if not isinstance(description, str) or not description.strip():
        return f"{quantity:g}"
    text = description.strip()
    if quantity == 1:
        return text
    match = None if "=" in text else _LEADING_COUNT.match(text)
    if match is None:
        return f"{quantity:g} × {text}"
    count_text, rest = match.group(1), match.group(2)
    if "/" in count_text:
        numerator, denominator = count_text.split("/")
        count = float(numerator) / float(denominator)
    else:
        count = float(count_text)
    return f"{count * quantity:g} {rest}"


def group_ingredients_for_card(ingredients: list[dict]) -> list[dict]:
    """Collapse ingredient rows that would render as the same recipe-card
    line, summing their grams. First-occurrence order is preserved.

    FOR THE RECIPE CARD ONLY (author, 2026-08-16). The card is the "hand
    it to a caregiver" artefact, where the same food listed twice reads as
    a mistake. Nothing else collapses: the editable rows, the export, the
    Nutrition view and the stored blend all stay row-per-entry, and the
    nutrient maths never sees this function. Merging the STORED rows was
    considered and rejected -- see this plan's Context, or
    compute_ingredient_breakdown() in src/calculator.py for the separate
    per-FOOD reading that already exists.

    The group key is deliberately conservative -- every field the card
    actually PRINTS:

        (food_code, food_description, unit, measure_label, measure_grams)

    Rows differing in unit or measure stay separate lines, because there
    is no honest way to merge "1 large egg" with "75 g" -- and the card
    prints the measure, so a merged line would have to pick one and lie
    about the other. Two rows of "1 extra large" DO merge, and the card's
    existing rendering then scales the label to "2 extra large" via
    scale_measure_label() with no extra formatting.

    food_description is in the key for the same reason, and it is not
    redundant with food_code: the Dilution What-If writes its added liquid
    as "Water (added to thin)" against the SAME CNF code as a plain
    "Water, municipal" ingredient. Merging those would print one
    description and silently drop the other, hiding the fact that some of
    the water was there to thin the blend.

    `counts_as_fluid` is deliberately NOT part of the key. A card line is
    an amount and a description; the fluid flag cannot change it, so
    splitting on it would leave two lines the card renders identically.

    Grams are summed, never recomputed, so the total across the returned
    list always equals the total across the input -- the one property that
    would let the card disagree with the nutrient maths if it broke.
    """
    grouped: dict[tuple, dict] = {}
    for ing in ingredients:
        key = (
            ing.get("food_code"),
            ing.get("food_description"),
            ing.get("unit", "g"),
            ing.get("measure_label"),
            ing.get("measure_grams"),
        )
        if key in grouped:
            grouped[key]["grams"] += ing.get("grams", 0.0)
        else:
            grouped[key] = {**ing, "grams": ing.get("grams", 0.0)}
    return list(grouped.values())


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
        [
            "Food_Code",
            "Measure_Code",
            "Measure_Weight_Conversion",
            "Measure_Description_and_Unit_EN",
        ]
    ].rename(columns={"Measure_Weight_Conversion": "grams"})

    # Change 1.5: drop bare gram-weight labels -- see is_bare_gram_weight()
    # above. Filtered here, once, so every caller (the ingredient rows, the
    # add-food search, get_measures_for_food()) sees the same narrowed list
    # without re-implementing the rule.
    result = result[~result["Measure_Description_and_Unit_EN"].apply(is_bare_gram_weight)]

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
        (lookup_df["Food_Code"] == food_code) & (lookup_df["Measure_Code"] == measure_code)
    ]

    if len(row) == 0:
        raise ValueError(
            f"No household measure found for Food_Code {food_code}, " f"Measure_Code {measure_code}"
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
