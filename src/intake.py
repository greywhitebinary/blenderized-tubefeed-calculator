"""
intake.py — Intake Record aggregation.

FEED_LOG_REWORK.md is the design doc for this module; read it before
changing anything here (especially section 2 "the model" and section 6.2
"over-draw flag: removed entirely").

Replaces the old delivery-schedule extrapolation model
(density x schedule_volume, which silently assumed a recipe's measured
batch volume scaled to however much the schedule claimed was given). The
Intake Record is instead ONE chronological list of rows -- blend / formula
/ flush / oral -- each contributing exactly what it says it gave, summed
directly. No batch bookkeeping, no over-draw flag: a blend is a
formulation (its densities are scale-free), a batch is one physical
making of it, and an intake-record row is what was actually given,
referencing a blend by name without needing to know how many times it was
made (section 6.2 of the design doc).

Row shape (session_state["intake_log"] items in app/streamlit_app.py):
    {
        "id": int,                          # unique row id (widget keys, deletion)
        "time": datetime.time | None,        # optional -- unset rows sort last
        "source_type": "blend"|"formula"|"flush"|"oral",
        "source_id": int | str | None,       # blend id / formula name / None / food_code
        "food_description": str | None,      # oral rows only (display name)
        "amount": float,                     # mL for blend/formula/flush; g or mL for oral
        "unit": "mL" | "g",
        "counts_as_fluid": bool,
    }

Blend shape (session_state["blends"] values):
    {"name": str, "ingredients": [ing_dict, ...], "measured_volume_mL": float}
    where each ing_dict is {"id", "food_code", "food_description", "grams",
    "unit", "counts_as_fluid"} -- the same shape the pre-rework app used
    for its single flat ingredient list.

Only one real guard survives from the old model (section 6.2): a blend with
ingredients but no measured volume can't produce densities (division by
zero) -- that must still surface as a clear error. There is deliberately
NO "logged more than the batch made" flag of any kind.
"""

from dataclasses import dataclass, field

import pandas as pd

try:
    from src.models import Ingredient, Recipe, NutrientProfile
    from src.calculator import (
        calculate_profile,
        calculate_daily_totals,
        compute_nutrient_totals,
        compute_nutrient_totals_and_coverage,
        COMMERCIAL_FORMULAS,
        NUTRIENT_CODES,
    )
except ImportError:
    from models import Ingredient, Recipe, NutrientProfile
    from calculator import (
        calculate_profile,
        calculate_daily_totals,
        compute_nutrient_totals,
        compute_nutrient_totals_and_coverage,
        COMMERCIAL_FORMULAS,
        NUTRIENT_CODES,
    )


# Which source_types display under which Intake Record section header
# (FEED_LOG_REWORK.md section 6.3 -- "Tube Feed" and "Food & Drink" are a
# DISPLAY grouping over one list, not two separately-maintained logs).
TUBE_FEED_SOURCE_TYPES = ("blend", "formula", "flush")
FOOD_DRINK_SOURCE_TYPES = ("oral",)

# Water-source labels for IntakeTotals.water_sources. "Free water" here
# means water that arrived as part of something fed (a blend, a formula,
# a food) -- tap water stirred into a blend included, because in the
# recipe it IS the recipe. A flush is the only water given as water.
WATER_BLEND_LABEL = "BTF blend — free water"
WATER_FORMULA_LABEL = "Commercial formula — free water"
WATER_ORAL_LABEL = "Oral food & drink — free water"
WATER_FLUSH_LABEL = "Water flushes"

TUBE_FEED_LABEL = "Tube Feed"
FOOD_DRINK_LABEL = "Food & Drink"
TOTAL_LABEL = "Total"

# Per-mL formula columns (data/packs/<pack>/formulas.csv, loaded via
# src.calculator._OPTIONAL_NUTRIENT_COLUMNS) mapped onto their registry
# nutrient key (data/packs/<pack>/nutrients.csv's `name` column). Units
# already match: fat/carbohydrate/fibre are g/mL -> *_g; sodium/potassium/
# calcium/iron/magnesium/phosphorus are mg/mL -> *_mg. Any column a
# formula's label doesn't disclose loads as None (see
# _load_commercial_formulas' docstring) and is skipped in the formula
# branch below, never fabricated as 0. Also drives that branch's
# row_coverage (a formula is one product, not an ingredient list -- see
# the "formula:" bullet in aggregate_intake()'s docstring): this same
# mapping tells us which NUTRIENT_CODES entries a formula's CSV row is
# even capable of disclosing, so we know which "not disclosed" cases are
# "this product's label doesn't say" (counts toward n_total) vs. which
# tracked nutrients (e.g. the clinical-tier zinc/vitamin D/B12 fields)
# formulas.csv has no column for at all -- both count toward n_total
# without incrementing n_supplying, the same "we don't know" contract
# already used for a custom food's unfilled label fields
# (src/calculator.py::_coverage_from_merged()). Never fabricate a 0.
_FORMULA_COLUMN_TO_NUTRIENT: dict[str, str] = {
    "fat_per_mL": "fat_g",
    "carbohydrate_per_mL": "carbohydrate_g",
    "fibre_per_mL": "fibre_g",
    "sodium_per_mL": "sodium_mg",
    "potassium_per_mL": "potassium_mg",
    "calcium_per_mL": "calcium_mg",
    "iron_per_mL": "iron_mg",
    "magnesium_per_mL": "magnesium_mg",
    "phosphorus_per_mL": "phosphorus_mg",
}


class InvalidBlendError(ValueError):
    """A blend has ingredients but no measured volume -- the one real
    invalidity that survives the rework (section 6.2): densities can't be
    computed without a volume to divide by. Not a judgment call, not an
    over-draw flag -- a genuine division-by-zero guard.
    """


def blend_fluid_fraction(ingredients: list[dict], measured_volume_mL: float) -> float:
    """Fraction of a blend's measured volume that counts as fluid (I&O
    convention) -- mirrors the Build tab's per-ingredient counts_as_fluid
    toggle. `ingredients` are the raw session-state ingredient dicts
    (food_code, food_description, grams, unit, counts_as_fluid), not
    Ingredient dataclass instances (which carry no counts_as_fluid field).

    Returns 0.0 when there's no volume to divide by (no ZeroDivisionError).
    """
    if measured_volume_mL <= 0:
        return 0.0
    fluid_mL = sum(
        ing.get("grams", 0.0) for ing in ingredients if ing.get("counts_as_fluid", False)
    )
    return fluid_mL / measured_volume_mL


def resolve_blend_profile(
    blend: dict,
    nutrient_amount_df: pd.DataFrame,
    custom_foods: dict[int, dict[str, float]] | None = None,
) -> tuple[NutrientProfile, float]:
    """Turn a blend dict into (NutrientProfile, fluid_fraction).

    Raises InvalidBlendError if the blend has ingredients but no measured
    volume -- the one guard that survives the rework (section 6.2).
    """
    ingredients = blend.get("ingredients", [])
    volume = float(blend.get("measured_volume_mL", 0.0) or 0.0)
    if ingredients and volume <= 0:
        raise InvalidBlendError(
            f"Blend '{blend.get('name', '')}' has ingredients but no measured "
            "volume -- densities need a measured volume to divide by."
        )
    recipe = Recipe(
        name=blend.get("name", ""),
        ingredients=[
            Ingredient(
                food_code=ing["food_code"],
                food_description=ing.get("food_description", ""),
                grams=ing["grams"],
            )
            for ing in ingredients
        ],
        measured_final_volume_mL=volume,
    )
    profile = calculate_profile(recipe, nutrient_amount_df, custom_foods=custom_foods)
    fluid_frac = blend_fluid_fraction(ingredients, volume)
    return profile, fluid_frac


@dataclass
class IntakeTotals:
    """Aggregated Intake Record totals -- everything the Results tab and
    banner summary need, all derived from one pass over intake_log rows.

    Attributes:
        nutrient_totals:   nutrient_name -> total for the day (already
                            "daily", since each row's amount is what was
                            actually given -- no further scaling needed).
                            "water_g" here is the estimated free-water
                            total (CNF food moisture from blend/oral rows
                            + formula-declared free_water_per_mL from
                            formula rows) -- see the module docstring.
        fluid_provided_mL: Full-volume I&O-convention fluid total across
                            every row (blend rows via their own fluid
                            fraction; formula and flush rows at full
                            volume; oral rows via their own counts_as_fluid
                            toggle).
        subtotals:         {"Tube Feed": {...}, "Food & Drink": {...},
                            "Total": {...}} -- each value has the same
                            three keys as this dataclass's own fields
                            (nutrient_totals, fluid_provided_mL) plus
                            nutrient_coverage, for the Results-tab
                            per-source breakdown (design doc section 3.5).
        nutrient_coverage: nutrient_name -> (n_supplying, n_total), summed
                            across every row's contribution: blend/oral
                            rows contribute per-ingredient CNF-derived
                            counts (as before); a formula row counts as
                            ONE instance per tracked nutrient -- supplying
                            it if formulas.csv discloses a value, adding
                            to n_total either way (see the "formula:"
                            bullet below and _FORMULA_COLUMN_TO_NUTRIENT's
                            comment). Flush rows have no nutrient content
                            at all and don't contribute to either count.
    """

    nutrient_totals: dict[str, float] = field(default_factory=dict)
    fluid_provided_mL: float = 0.0
    subtotals: dict[str, dict] = field(default_factory=dict)
    nutrient_coverage: dict[str, tuple[int, int]] = field(default_factory=dict)
    # Every water source the day drew on, kept apart so the ledger can
    # show them as separate lines rather than two figures that don't
    # obviously relate (author, 2026-07-30).
    #
    # The distinction being preserved is clinical, not arithmetic:
    # water that is PART OF SOMETHING FED is free water -- including tap
    # water poured into a blend, because once it's in the recipe it is
    # part of that recipe, exactly like the moisture in a banana. Only a
    # flush is water given AS water. Nothing here is a new calculation:
    # these are the same per-row numbers that already feed
    # nutrient_totals and fluid_provided_mL, retained by source instead
    # of being summed away.
    water_sources: dict[str, float] = field(default_factory=dict)

    @property
    def free_water_mL(self) -> float:
        """Estimated free water for the day -- see nutrient_totals'
        docstring note: CNF food moisture (blend/oral rows) blended with
        formula-declared free_water_per_mL (formula rows). Flush rows are
        deliberately NOT included here (design doc section 2: "flush rows
        contribute fluid only") -- a flush is 100% fluid but is not itself
        part of the CNF/formula free-water estimate.
        """
        return self.nutrient_totals.get("water_g", 0.0)


def _empty_family_totals() -> dict:
    return {
        "nutrient_totals": {},
        "fluid_provided_mL": 0.0,
        "nutrient_coverage": {},
    }


def _add_coverage(into: dict[str, tuple[int, int]], extra: dict[str, tuple[int, int]]) -> None:
    for name, (n_sup, n_tot) in extra.items():
        cur_sup, cur_tot = into.get(name, (0, 0))
        into[name] = (cur_sup + n_sup, cur_tot + n_tot)


def aggregate_intake(
    intake_log: list[dict],
    blends: dict[int, dict],
    nutrient_amount_df: pd.DataFrame,
    custom_foods: dict[int, dict[str, float]] | None = None,
    formulas: dict[str, dict] | None = None,
) -> IntakeTotals:
    """Aggregate the Intake Record into daily totals (FEED_LOG_REWORK.md
    section 3.1 / section 2). Sums each row's contribution directly -- no
    batch/schedule extrapolation, no over-draw flag (section 6.2).

    Each row resolves differently by source_type:
      - "blend":   that blend's per-mL densities (via calculate_profile())
                   x the row's amount -- calculate_daily_totals() already
                   does exactly this scaling, just reused with the row's
                   amount standing in for "daily volume". Fluid = the
                   blend's own fluid fraction x amount.
      - "formula": formulas.csv per-mL kcal/protein x amount, plus every
                   other per-mL nutrient the formula's CSV row discloses
                   (fat/carbohydrate/fibre/sodium/potassium/calcium/iron/
                   magnesium/phosphorus -- see _FORMULA_COLUMN_TO_NUTRIENT)
                   x amount, skipping any column that's None rather than
                   fabricating a 0. Free water (free_water_per_mL x amount,
                   when the formula's CSV row has it) is folded into
                   nutrient_totals["water_g"] alongside CNF food moisture
                   -- see IntakeTotals' docstring for why that's a
                   deliberate, not accidental, mixing. Fluid = full amount
                   (I&O convention -- a formula is entirely liquid).
                   Coverage: a commercial formula is one product, not a
                   CNF ingredient list, so it counts as ONE instance per
                   tracked nutrient rather than contributing an
                   ingredient-by-ingredient count -- (1, 1) for a nutrient
                   the formula's CSV row discloses (kcal/protein always;
                   the optional columns and free water when present),
                   (0, 1) for one it doesn't (a None column, or a tracked
                   nutrient formulas.csv has no column for at all, e.g.
                   zinc/vitamin D/B12). The (0, 1) case is the fix this
                   docstring is pinning: it's what makes a mixed day's "N/M
                   ingredients" note reflect the formula's row instead of
                   silently dropping it, and it's also what makes a
                   formula's non-disclosed nutrients correctly read as
                   "we don't know" instead of a fabricated 0 -- see
                   src/calculator.py::_coverage_from_merged() for the
                   identical contract on the CNF/custom-food side.
      - "flush":   fluid only (full amount), no nutrient contribution at
                   all -- section 2: "flush rows contribute fluid only".
      - "oral":    compute_nutrient_totals() on the single food, at the
                   row's amount directly -- no volume/density concept
                   needed (section 3.1). Fluid = amount if the row's own
                   counts_as_fluid toggle is set, else 0.

    Rows referencing a blend id that no longer exists are skipped rather
    than raising -- the app is responsible for pruning intake_log rows
    when a blend is deleted (see the Build tab's blend-delete handler);
    this is a defensive fallback, not the expected path.

    Returns an IntakeTotals with Tube-Feed/Food-and-Drink/Total subtotals
    for the Results-tab per-source breakdown (design doc section 3.5).
    """
    if formulas is None:
        formulas = COMMERCIAL_FORMULAS

    family_totals = {
        TUBE_FEED_LABEL: _empty_family_totals(),
        FOOD_DRINK_LABEL: _empty_family_totals(),
    }

    _blend_cache: dict[int, tuple[NutrientProfile, float, dict]] = {}

    def _get_blend(blend_id):
        if blend_id not in _blend_cache:
            blend = blends[blend_id]
            profile, fluid_frac = resolve_blend_profile(blend, nutrient_amount_df, custom_foods)
            ingredients = [
                Ingredient(ing["food_code"], ing.get("food_description", ""), ing["grams"])
                for ing in blend.get("ingredients", [])
            ]
            _, coverage = compute_nutrient_totals_and_coverage(
                ingredients, nutrient_amount_df, custom_foods
            )
            _blend_cache[blend_id] = (profile, fluid_frac, coverage)
        return _blend_cache[blend_id]

    water_sources: dict[str, float] = {}

    for row in intake_log:
        source_type = row.get("source_type")
        amount = float(row.get("amount", 0.0) or 0.0)
        family = TUBE_FEED_LABEL if source_type in TUBE_FEED_SOURCE_TYPES else FOOD_DRINK_LABEL

        row_nutrients: dict[str, float] = {}
        row_fluid = 0.0
        row_coverage: dict[str, tuple[int, int]] = {}

        if source_type == "blend":
            blend_id = row.get("source_id")
            if blend_id not in blends:
                continue
            profile, fluid_frac, coverage = _get_blend(blend_id)
            row_nutrients = calculate_daily_totals(profile, amount)
            row_fluid = fluid_frac * amount
            row_coverage = coverage

        elif source_type == "formula":
            formula = formulas.get(row.get("source_id"))
            if formula is None:
                continue
            row_nutrients = {
                "energy_kcal": formula["kcal_per_mL"] * amount,
                "protein_g": formula["protein_per_mL"] * amount,
            }
            for col, nutrient_key in _FORMULA_COLUMN_TO_NUTRIENT.items():
                per_mL = formula.get(col)
                if per_mL is not None:
                    row_nutrients[nutrient_key] = per_mL * amount
            fw_per_mL = formula.get("free_water_per_mL")
            if fw_per_mL is not None:
                row_nutrients["water_g"] = fw_per_mL * amount
            row_fluid = amount
            # Coverage: a commercial formula is ONE product, not a CNF
            # ingredient list -- there's no "ingredient instance" to
            # count the way _coverage_from_merged() counts CNF rows. So
            # this row counts as exactly one instance PER TRACKED
            # NUTRIENT (the same NUTRIENT_CODES universe
            # _coverage_from_merged() iterates -- never a hardcoded
            # list): "supplying" (1, 1) for a nutrient this formula's CSV
            # row actually discloses a value for, "not supplying" (0, 1)
            # for one it doesn't. kcal_per_mL/protein_per_mL are
            # mandatory columns (see _load_commercial_formulas -- never
            # None), so energy_kcal/protein_g are always "supplying".
            # Everything else -- an optional column that's None for this
            # product, or a tracked nutrient formulas.csv has no column
            # for at all (e.g. the clinical-tier zinc/vitamin D/B12
            # fields) -- is "not disclosed": n_total still gets this row
            # (that's the "we don't know" signal an RD needs), n_supplying
            # doesn't. Never fabricate a 0. On a mixed day this makes the
            # formula's contribution show up in the "N/M sources"
            # note alongside the food/CNF side, fixing the limitation
            # this branch used to carry a comment about.
            disclosed = {"energy_kcal", "protein_g"}
            disclosed.update(
                nutrient_key
                for col, nutrient_key in _FORMULA_COLUMN_TO_NUTRIENT.items()
                if formula.get(col) is not None
            )
            if fw_per_mL is not None:
                disclosed.add("water_g")
            row_coverage = {name: (1 if name in disclosed else 0, 1) for name in NUTRIENT_CODES}

        elif source_type == "flush":
            row_fluid = amount

        elif source_type == "oral":
            ing = Ingredient(
                food_code=row.get("source_id"),
                food_description=row.get("food_description", ""),
                grams=amount,
            )
            row_nutrients, row_coverage = compute_nutrient_totals_and_coverage(
                [ing], nutrient_amount_df, custom_foods
            )
            if row.get("counts_as_fluid", False):
                row_fluid = amount

        else:
            continue

        fam = family_totals[family]
        for name, val in row_nutrients.items():
            fam["nutrient_totals"][name] = fam["nutrient_totals"].get(name, 0.0) + val
        fam["fluid_provided_mL"] += row_fluid
        _add_coverage(fam["nutrient_coverage"], row_coverage)

        # Keep this row's water under its own source. Same numbers as
        # above, retained rather than summed away -- a flush contributes
        # its full volume as water-given-as-water; every other row
        # contributes whatever water_g it already computed.
        if source_type == "flush":
            water_sources[WATER_FLUSH_LABEL] = water_sources.get(WATER_FLUSH_LABEL, 0.0) + amount
        else:
            row_water = row_nutrients.get("water_g", 0.0)
            if row_water:
                label = {
                    "blend": WATER_BLEND_LABEL,
                    "formula": WATER_FORMULA_LABEL,
                    "oral": WATER_ORAL_LABEL,
                }[source_type]
                water_sources[label] = water_sources.get(label, 0.0) + row_water

    total_nutrients: dict[str, float] = {}
    total_fluid = 0.0
    total_coverage: dict[str, tuple[int, int]] = {}
    for fam in family_totals.values():
        for name, val in fam["nutrient_totals"].items():
            total_nutrients[name] = total_nutrients.get(name, 0.0) + val
        total_fluid += fam["fluid_provided_mL"]
        _add_coverage(total_coverage, fam["nutrient_coverage"])

    subtotals = dict(family_totals)
    subtotals[TOTAL_LABEL] = {
        "nutrient_totals": total_nutrients,
        "fluid_provided_mL": total_fluid,
        "nutrient_coverage": total_coverage,
    }

    return IntakeTotals(
        nutrient_totals=total_nutrients,
        fluid_provided_mL=total_fluid,
        subtotals=subtotals,
        nutrient_coverage=total_coverage,
        water_sources=water_sources,
    )


def sorted_intake_log(intake_log: list[dict]) -> list[dict]:
    """Sort Intake Record rows chronologically by time; rows with no time
    sort last (design doc section 6.1 -- unset-time rows sort last, a
    required field would invent false precision for PRN doses/overnight
    feeds/genuinely unremembered times)."""
    return sorted(
        intake_log,
        key=lambda r: (r.get("time") is None, r.get("time") or ""),
    )
