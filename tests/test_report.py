"""
test_report.py — tests for src/report.py's two adequacy tables
(generate_adequacy_report -- the daily main table -- and
generate_clinical_screen -- the collapsed BTF micro screen) and the
helper functions that decide their wording.

A quick pytest primer for a reader who knows nutrition, not testing
jargon: `assert` means "this must be true or the test fails". A
fixture (the `@pytest.fixture`-decorated functions below) is reusable
setup other tests ask for by naming it as an argument -- here, mostly
small hand-built "daily totals" and "coverage" dictionaries standing in
for a real Intake Record day, per the brief's instruction not to load
the 565k-row CNF table for these tests.

The point of this file is the TIER rule: a nutrient's `tier` (from the
registry, src/nutrients.py) decides which of the two tables it can ever
appear in, and tier="engine" (water_g) must never appear in either --
getting this wrong would either clutter the daily table with one-time
screening nutrients, or silently drop mandatory-label nutrients from the
table an RD actually reads every day.

None of these tests hardcode "the Canadian nutrient list" as a
correctness assertion -- they read the registry (src/nutrients.py) at
test time and check that report.py's tier-filtering honours whatever
the registry says, so they keep passing if an RD edits nutrients.csv to
add/remove a nutrient. The one deliberate exception is called out where
it happens: sodium's target_type="UL" is a real, documented Canada-pack
fact (the only UL nutrient today) and is exactly the case the brief asks
to test directly.
"""

from dataclasses import replace

import pandas as pd
import pytest

from src.calculator import calculate_profile, compute_ingredient_breakdown
from src.intake import InvalidBlendError, resolve_blend_profile
from src.models import Ingredient, Recipe
from src.nutrients import DEFAULT_PACK, defs_for_tier, registry_by_name
from src.report import (
    EDITING_MARKER,
    _adequacy_status,
    _formula_daily,
    color_status,
    _coverage_text,
    _ordered_label_defs,
    _zero_coverage,
    format_ingredient_breakdown,
    generate_adequacy_report,
    generate_clinical_screen,
    generate_comparator_table,
)

from tests.conftest import FOOD_CHICKEN, FOOD_RICE, CUSTOM_PROTEIN_SHAKE

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def label_defs():
    """The nutrients that belong in the MAIN daily adequacy table:
    tier="label" (on Canada's mandatory Nutrition Facts table) AND
    show_in_report=True (the author's "show what's needed" subset --
    e.g. saturated fat is tier="label" but show_in_report=False, so it's
    excluded here too, matching what generate_adequacy_report() itself
    filters on).
    """
    return [d for d in defs_for_tier("label", pack="canada") if d.show_in_report]


@pytest.fixture
def clinical_defs():
    """The nutrients that belong in the BTF micro screen: tier="clinical"
    and show_in_report=True (every clinical-tier row is show_in_report=
    True in the Canada pack, but we filter the same way report.py does
    rather than assuming that).
    """
    return [d for d in defs_for_tier("clinical", pack="canada") if d.show_in_report]


@pytest.fixture
def engine_defs():
    """The nutrients that must NEVER get their own row in either table
    (water_g today) -- tracked only so the calculator can compute
    free-water internally.
    """
    return defs_for_tier("engine", pack="canada")


def _full_coverage(defs):
    """Build a nutrient_coverage dict saying "every ingredient in this
    (fictional) recipe supplied a value" for each of the given
    NutrientDefs -- i.e. 1 of 1 ingredients had data. Use this when a
    test doesn't care about coverage/hiding and just wants ordinary rows.
    """
    return {d.name: (1, 1) for d in defs}


def _totals(defs, value=100.0):
    """A daily_totals dict giving every one of the given NutrientDefs the
    same made-up daily amount. The exact number doesn't matter for the
    tier-placement tests -- only that every nutrient in play has SOME
    value so its row isn't hidden for zero coverage.
    """
    return {d.name: value for d in defs}


# ---------------------------------------------------------------------------
# Tier placement: the whole point of having two report tables
# ---------------------------------------------------------------------------


def test_label_tier_nutrients_appear_in_main_table_only(label_defs, clinical_defs):
    """Every tier="label" (+ show_in_report) nutrient must show up as a
    row in generate_adequacy_report()'s table, by its registry `label`
    text, and must NOT show up in generate_clinical_screen()'s table.
    """
    all_defs = label_defs + clinical_defs
    totals = _totals(all_defs)
    coverage = _full_coverage(all_defs)

    main_df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)
    screen_df, _ = generate_clinical_screen(totals, targets={}, nutrient_coverage=coverage)

    main_names = set(main_df["Nutrient"])
    screen_names = set(screen_df["Nutrient"])

    for d in label_defs:
        assert d.label in main_names, f"{d.label} (tier=label) missing from main adequacy table"
        assert d.label not in screen_names, f"{d.label} (tier=label) leaked into the micro screen"


def test_clinical_tier_nutrients_appear_in_micro_screen_only(label_defs, clinical_defs):
    """The mirror image of the test above: every tier="clinical" nutrient
    (magnesium, phosphorus, zinc, vitamin D, B12 in the Canada pack)
    belongs in generate_clinical_screen()'s table and must never leak
    into the daily main table an RD checks every day.
    """
    all_defs = label_defs + clinical_defs
    totals = _totals(all_defs)
    coverage = _full_coverage(all_defs)

    main_df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)
    screen_df, _ = generate_clinical_screen(totals, targets={}, nutrient_coverage=coverage)

    main_names = set(main_df["Nutrient"])
    screen_names = set(screen_df["Nutrient"])

    for d in clinical_defs:
        assert d.label in screen_names, f"{d.label} (tier=clinical) missing from the micro screen"
        assert d.label not in main_names, f"{d.label} (tier=clinical) leaked into the main table"


def test_engine_tier_nutrient_never_rendered_in_either_table(
    label_defs, clinical_defs, engine_defs
):
    """tier="engine" (water_g) exists purely so the calculator can derive
    free-water internally -- it must never appear as its OWN row (by its
    registry label, "Water (moisture)") in either report table. Note
    generate_adequacy_report() DOES render a derived "Free water
    (estimated)" row from the water_g total -- that's a different,
    deliberately-named summary row, not water_g's registry row, so this
    test checks for the registry label specifically, not for the mere
    presence of the word "water".
    """
    assert engine_defs, "expected at least one engine-tier nutrient (water_g) to test against"

    all_defs = label_defs + clinical_defs + engine_defs
    totals = _totals(all_defs)
    coverage = _full_coverage(all_defs)

    main_df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)
    screen_df, _ = generate_clinical_screen(totals, targets={}, nutrient_coverage=coverage)

    main_names = set(main_df["Nutrient"])
    screen_names = set(screen_df["Nutrient"])

    for d in engine_defs:
        assert d.label not in main_names
        assert d.label not in screen_names


# ---------------------------------------------------------------------------
# _adequacy_status(): UL wording vs ordinary target wording
# ---------------------------------------------------------------------------


def test_adequacy_status_ul_wording_is_above_below_ul_not_target():
    """A target_type="UL" (a ceiling, e.g. sodium) must never say "Above
    target"/"Meeting target"/"Below target" -- those phrases imply 90-110%
    is the goal, which is wrong for a ceiling nutrient where the goal is
    simply staying under it. Getting this wrong would mislead an RD about
    whether a number is a limit or something to aim for.
    """
    # 50% of the UL -> under the ceiling.
    assert _adequacy_status(daily_total=50, target=100, target_type="UL") == "Below UL"
    # Exactly at the ceiling (100%) is still "Below UL" -- only strictly
    # OVER the ceiling counts as "Above UL" (src/report.py: `pct > 1.0`).
    assert _adequacy_status(daily_total=100, target=100, target_type="UL") == "Below UL"
    # Over the ceiling -> "Above UL".
    assert _adequacy_status(daily_total=150, target=100, target_type="UL") == "Above UL"

    # And never the ordinary-target vocabulary for a UL nutrient:
    ul_status = _adequacy_status(daily_total=150, target=100, target_type="UL")
    assert "target" not in ul_status.lower()


def test_adequacy_status_ordinary_target_wording_for_non_ul_types():
    """RDA/AI/estimate (i.e. anything that isn't a ceiling) use the
    below/meeting/above TARGET vocabulary, with the documented 90%/110%
    thresholds.
    """
    assert _adequacy_status(daily_total=50, target=100, target_type="RDA") == "Below target"
    assert _adequacy_status(daily_total=95, target=100, target_type="AI") == "Meeting target"
    assert _adequacy_status(daily_total=150, target=100, target_type="estimate") == "Above target"
    # An empty target_type ("" -- every nutrient except sodium in the
    # Canada pack) should behave the same as "estimate" once _tier_rows()
    # has substituted the default; _adequacy_status() itself just takes
    # whatever string it's handed, so we call it with "estimate" directly
    # here (the "" -> "estimate" substitution is _tier_rows()'s job,
    # exercised by the sodium test below and the full-report test after
    # it).


def test_adequacy_status_no_target_entered_returns_no_target_regardless_of_type():
    """Targets always start blank in this app (no defaults anywhere --
    see src/targets.py's module docstring). A target of 0 (not entered)
    must render "No target", for EVERY target_type, including UL -- a
    dietitian who hasn't set a sodium ceiling yet should see "No target",
    not a false "Below UL" implying 0% of an unset ceiling.
    """
    assert _adequacy_status(daily_total=50, target=0, target_type="UL") == "No target"
    assert _adequacy_status(daily_total=50, target=0, target_type="RDA") == "No target"
    assert _adequacy_status(daily_total=50, target=0, target_type="") == "No target"


def test_sodium_reports_ul_wording_through_the_full_adequacy_report():
    """End-to-end version of the UL check, through the real
    generate_adequacy_report() path rather than calling _adequacy_status()
    directly -- this is what an RD actually sees on screen.

    NOTE: this pins a real Canada-pack fact -- sodium_mg is the only
    nutrient with target_type="UL" in data/packs/canada/nutrients.csv
    today. That's intentional per the test brief ("a test asserting this
    is well worth having"): sodium's UL-ness is a clinical fact (a
    ceiling, not a goal) independent of which OTHER nutrients the
    registry happens to track, so pinning it doesn't freeze the
    tracked-nutrient set the way asserting "there are exactly 10 rows in
    the main table" would.
    """
    sodium_def = registry_by_name("canada")["sodium_mg"]
    assert sodium_def.target_type == "UL"  # the documented Canada-pack fact

    totals = {"sodium_mg": 3000.0}
    targets = {"sodium_mg": 2300.0}
    coverage = {"sodium_mg": (1, 1)}

    df, hidden = generate_adequacy_report(totals, targets=targets, nutrient_coverage=coverage)
    row = df[df["Nutrient"] == sodium_def.label].iloc[0]

    assert row["Status"] == "Above UL"
    assert "target" not in row["Status"].lower()
    assert sodium_def.label not in hidden


# ---------------------------------------------------------------------------
# Zero-coverage hiding and the "N/M sources" provenance note
# ---------------------------------------------------------------------------


def test_zero_coverage_helper_flags_only_the_zero_of_n_case():
    """_zero_coverage() should be True only when the recipe has at least
    one ingredient that COULD have supplied this nutrient (n_total > 0)
    but NONE actually did (n_supplying == 0). An empty recipe (0/0, no
    ingredients at all) is a different case and must not be flagged --
    src/report.py's own docstring calls this out explicitly.
    """
    assert _zero_coverage("some_nutrient", {"some_nutrient": (0, 3)}) is True
    assert _zero_coverage("some_nutrient", {"some_nutrient": (1, 3)}) is False
    assert _zero_coverage("some_nutrient", {"some_nutrient": (0, 0)}) is False
    # A nutrient absent from the coverage dict entirely defaults to (0, 0)
    # -- also not the zero-coverage case.
    assert _zero_coverage("not_in_dict", {}) is False


def test_coverage_text_helper_always_shows_n_of_m():
    """_coverage_text() renders "n/m sources" for every row that has any
    sources at all, complete or not.

    Full coverage used to render "—", on the "nothing to flag" convention
    the Target/% Target columns use. It misled the author, who read a dash
    beside a 297.6 mg vitamin C row as meaning the blend's carrots,
    avocado and banana had contributed nothing (2026-08-21). This column
    exists to justify a number, so its quiet case has to speak: 40/40
    against 36/40 needs no explaining.

    A row with NO sources (0, 0) still renders "—": there is no fraction
    to show, and that is a genuinely empty case rather than a complete
    one.
    """
    assert _coverage_text("x", {"x": (1, 2)}) == "1/2 sources"
    assert _coverage_text("x", {"x": (2, 2)}) == "2/2 sources"
    assert _coverage_text("x", {"x": (0, 0)}) == "—"
    assert _coverage_text("missing", {}) == "—"


def test_zero_coverage_row_is_hidden_and_named_in_the_footnote_list(label_defs):
    """A nutrient with 0/N coverage (no ingredient in the recipe had CNF
    data for it at all) should be DROPPED from the visible table -- a
    confident-looking "0" would misrepresent "no data" as "measured
    zero" -- and its label should come back in the second return value so
    the caller can render the "not shown — no data from any ingredient:
    X, Y" footnote.
    """
    assert len(label_defs) >= 2, "need at least two label nutrients to isolate one"
    zero_def, *rest = label_defs

    totals = _totals(rest)
    totals[zero_def.name] = 0.0
    coverage = _full_coverage(rest)
    coverage[zero_def.name] = (0, 3)  # 3 ingredients in this fictional recipe, none had data

    df, hidden = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)

    assert zero_def.label in hidden
    assert zero_def.label not in set(df["Nutrient"])
    # The rest of the table is unaffected.
    for d in rest:
        assert d.label in set(df["Nutrient"])


def test_partial_coverage_shows_n_of_m_sources_note_in_the_real_table(label_defs):
    """Same idea as the helper-level test above, but through the real
    generate_adequacy_report() DataFrame, checking the actual "Coverage"
    column text an RD would see.
    """
    assert len(label_defs) >= 2
    partial_def, full_def, *_ = label_defs

    totals = _totals(label_defs)
    coverage = _full_coverage(label_defs)
    coverage[partial_def.name] = (1, 2)  # only 1 of 2 ingredients had data

    df, hidden = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)

    partial_row = df[df["Nutrient"] == partial_def.label].iloc[0]
    full_row = df[df["Nutrient"] == full_def.label].iloc[0]

    assert partial_row["Coverage"] == "1/2 sources"
    # Complete coverage speaks too, rather than rendering a dash an RD
    # reads as "nothing" (2026-08-21 -- see the helper test above).
    assert full_row["Coverage"] == "1/1 sources"
    assert partial_def.label not in hidden  # incomplete, not zero -- still shown


# ---------------------------------------------------------------------------
# No target set -- targets always start blank in this app
# ---------------------------------------------------------------------------


def test_nutrient_with_no_target_set_shows_no_target_status_and_blank_dashes(label_defs):
    """Targets always start blank (no default targets anywhere -- see
    src/targets.py's module docstring). With an empty targets dict, every
    ordinary nutrient row should show Status="No target" and both Target
    and % Target as "—", never a fabricated percentage against a target
    of zero.
    """
    totals = _totals(label_defs, value=50.0)
    coverage = _full_coverage(label_defs)

    df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)

    for d in label_defs:
        row = df[df["Nutrient"] == d.label].iloc[0]
        assert row["Status"] == "No target"
        assert row["Target"] == "—"
        assert row["% Target"] == "—"


# ---------------------------------------------------------------------------
# format_ingredient_breakdown() -- Change 1.4's Nutrition view formatting
# (plan you-know-the-line-vectorized-milner.md)
# ---------------------------------------------------------------------------


def test_columns_match_the_adequacy_tables_label_tier_in_the_same_order(nutrient_amount_df):
    """The Nutrition view's nutrient columns must be the same nine
    nutrients, in the same clinical reading order, that the Adequacy
    table leads with (_ordered_label_defs() -- energy/protein/carb/fat
    first, per REPORT_LEAD_ORDER, then registry order) -- so a figure
    means the same thing and sits in the same place wherever an RD
    looks for it. Uses _ordered_label_defs() itself, not the label_defs
    fixture (plain registry order, unordered by REPORT_LEAD_ORDER), since
    that's the exact function format_ingredient_breakdown() calls."""
    ingredients = [Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0)]
    breakdown = compute_ingredient_breakdown(ingredients, nutrient_amount_df)
    display = format_ingredient_breakdown(breakdown)

    expected_cols = ["Ingredient", "Amount"] + [
        f"{d.label} ({d.unit})" for d in _ordered_label_defs("canada")
    ]
    assert list(display.columns) == expected_cols


def test_each_nutrient_keeps_its_own_registry_decimals(nutrient_amount_df):
    """Energy (0 dp in the Canada registry) must render with no decimal
    point even though other columns (e.g. protein, 1 dp) carry one --
    same "own precision, as text" rule _fmt() enforces for the Adequacy
    table (see report.py's _fmt() docstring)."""
    ingredients = [Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0)]
    breakdown = compute_ingredient_breakdown(ingredients, nutrient_amount_df)
    display = format_ingredient_breakdown(breakdown)

    row = display.iloc[0]
    assert row["Energy (kcal)"] == "330"  # 165 kcal/100g x 200 g, 0 dp
    assert row["Protein (g)"] == "62.0"  # 31 g/100g x 200 g, 1 dp


def test_total_row_reconciles_with_the_unformatted_breakdown_sum(nutrient_amount_df):
    """The trailing Total row is computed from the RAW breakdown numbers,
    not by re-parsing the formatted text -- so it must equal the exact
    column sum of compute_ingredient_breakdown()'s own DataFrame."""
    ingredients = [
        Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
        Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
    ]
    breakdown = compute_ingredient_breakdown(ingredients, nutrient_amount_df)
    display = format_ingredient_breakdown(breakdown)

    total_row = display.iloc[-1]
    assert total_row["Ingredient"] == "Total"
    assert total_row["Energy (kcal)"] == f"{breakdown['energy_kcal'].sum():.0f}"
    assert total_row["Protein (g)"] == f"{breakdown['protein_g'].sum():.1f}"
    assert total_row["Amount"] == "350 g"  # 200 + 150, both default "g"


def test_custom_food_row_is_not_silently_zero_in_the_display_table(
    nutrient_amount_df, custom_foods
):
    """The same clinical-safety case as
    TestComputeIngredientBreakdown.test_custom_food_row_is_not_silently_zero,
    carried through the display-formatting step: a label-entered food's
    row must show its real numbers, not zeros, after _fmt() formatting."""
    ingredients = [
        Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 100.0),
        Ingredient(CUSTOM_PROTEIN_SHAKE, "Protein shake (label)", 50.0),
    ]
    breakdown = compute_ingredient_breakdown(ingredients, nutrient_amount_df, custom_foods)
    display = format_ingredient_breakdown(breakdown)

    shake_row = display[display["Ingredient"] == "Protein shake (label)"].iloc[0]
    assert shake_row["Energy (kcal)"] == "125"  # 250 kcal/100g x 50 g
    assert shake_row["Protein (g)"] == "5.0"  # 10 g/100g x 50 g


def test_amount_column_respects_units_by_food_code(nutrient_amount_df):
    """A food entered in mL (a custom liquid, or a CNF beverage) prints
    its Amount with "mL", not the default "g" -- from the caller-supplied
    units_by_food_code mapping, since compute_ingredient_breakdown()
    itself works in grams only (Ingredient carries no unit field)."""
    ingredients = [Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 100.0)]
    breakdown = compute_ingredient_breakdown(ingredients, nutrient_amount_df)
    display = format_ingredient_breakdown(breakdown, units_by_food_code={FOOD_CHICKEN: "mL"})

    assert display.iloc[0]["Amount"] == "100 mL"


def test_empty_breakdown_returns_empty_display_with_correct_columns(nutrient_amount_df):
    """An empty blend (no ingredients yet) must not crash the formatter --
    it should return an empty table with the right header, same
    convention as compute_ingredient_breakdown() itself."""
    empty = compute_ingredient_breakdown([], nutrient_amount_df)
    display = format_ingredient_breakdown(empty)
    assert len(display) == 0
    assert "Ingredient" in display.columns
    assert "Amount" in display.columns


# ---------------------------------------------------------------------------
# generate_comparator_table() -- blends vs blends vs formulas (Change 1/2/3,
# plan you-know-the-line-vectorized-milner.md, 2026-08-15). The comparator
# used to take ONE blend profile plus commercial formulas; it now takes an
# ORDERED LIST of (name, profile) pairs so an RD can put several of their
# OWN blends side by side, not just one blend against a formula.
# ---------------------------------------------------------------------------


def test_two_blends_produce_two_rows_named_and_ordered_as_given(nutrient_amount_df):
    """Two (name, profile) pairs must become two rows, in the order
    given -- the FIRST pair is the blend being edited, so its Name gets
    EDITING_MARKER prefixed (the approved marking); the second pair keeps
    its plain name. Two different recipes (chicken vs rice) so the
    numbers can't accidentally match and mask a mix-up."""
    whole_food = calculate_profile(
        Recipe(
            name="Whole-food blend",
            ingredients=[Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0)],
            measured_final_volume_mL=500.0,
        ),
        nutrient_amount_df,
    )
    vegan = calculate_profile(
        Recipe(
            name="Vegan blend",
            ingredients=[Ingredient(FOOD_RICE, "Rice, white, cooked", 200.0)],
            measured_final_volume_mL=500.0,
        ),
        nutrient_amount_df,
    )

    df = generate_comparator_table(
        [("Whole-food blend", whole_food), ("Vegan blend", vegan)],
        daily_volume_mL=1000.0,
        formula_names=[],
    )

    assert len(df) == 2
    assert list(df["Name"]) == [f"{EDITING_MARKER} Whole-food blend", "Vegan blend"]
    # Different recipes -> different densities -> different Energy figures,
    # confirming the second row isn't just a copy of the first.
    assert df.iloc[0]["Energy (kcal)"] != df.iloc[1]["Energy (kcal)"]


def test_the_columns_are_the_four_macros_plus_free_water_and_energy_density(
    nutrient_amount_df,
):
    """Column set fixed by the author 2026-08-16: the four macros at the
    chosen volume, free water, and kcal/mL. "Protein g/mL" was dropped for
    being the only density shown and a restatement of Protein (g); no
    other per-mL column replaced it, because kcal/mL is the one density
    that does not fall out of the daily figures.

    Hand-checked against conftest's foods. 200 g of rice in a 500 mL blend
    is 56.0 g carbohydrate and 0.6 g fat (28.0 and 0.3 per 100 g), so at a
    1000 mL daily volume the table doubles the density: 112.0 g and 1.2 g.
    Chicken carries no carbohydrate at all, which is what makes the two
    rows tell a story rather than just differ.
    """
    chicken = calculate_profile(
        Recipe(
            name="Chicken blend",
            ingredients=[Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0)],
            measured_final_volume_mL=500.0,
        ),
        nutrient_amount_df,
    )
    rice = calculate_profile(
        Recipe(
            name="Rice blend",
            ingredients=[Ingredient(FOOD_RICE, "Rice, white, cooked", 200.0)],
            measured_final_volume_mL=500.0,
        ),
        nutrient_amount_df,
    )

    df = generate_comparator_table(
        [("Chicken blend", chicken), ("Rice blend", rice)],
        daily_volume_mL=1000.0,
        formula_names=[],
    )

    assert list(df.columns) == [
        "Name",
        "Energy (kcal)",
        "Protein (g)",
        "Carbohydrate (g)",
        "Fat (g)",
        "Free water (mL)",
        "kcal/mL",
    ]
    assert "Protein g/mL" not in df.columns

    assert df.iloc[1]["Carbohydrate (g)"] == pytest.approx(112.0)
    assert df.iloc[1]["Fat (g)"] == pytest.approx(1.2)
    # 3.6 g fat per 100 g of chicken -> 7.2 g in 200 g -> doubled to 1000 mL.
    assert df.iloc[0]["Fat (g)"] == pytest.approx(14.4)
    assert df.iloc[0]["Carbohydrate (g)"] == pytest.approx(0.0)


def test_a_formula_column_the_csv_leaves_blank_shows_a_dash_not_a_zero(
    nutrient_amount_df,
):
    """The never-fabricate-a-0 contract, tested on _formula_daily directly
    because all 33 shipped formulas currently disclose every macro, so no
    real row can exercise it. A blank column means the manufacturer did
    not say, which is a different claim from "contains none" -- printing
    0.0 g of fat against a feed would be the app inventing a label value.
    """
    disclosed = {"fat_per_mL": 0.04}
    silent: dict = {}

    assert _formula_daily(disclosed, "fat_per_mL", 1000.0) == pytest.approx(40.0)
    assert _formula_daily(silent, "fat_per_mL", 1000.0) == "—"
    # A disclosed ZERO is a real claim and must survive as a number.
    assert _formula_daily({"fat_per_mL": 0.0}, "fat_per_mL", 1000.0) == 0.0


def test_blend_with_no_measured_volume_is_skipped_not_raised(nutrient_amount_df):
    """The most likely runtime failure: a blend with ingredients but no
    measured volume raises InvalidBlendError from resolve_blend_profile()
    (src/intake.py) -- densities can't be computed without a volume to
    divide by. The comparator must SKIP that blend rather than crash the
    whole tab (app/streamlit_app.py's comparator block wraps each
    resolve_blend_profile() call in exactly this try/except). Both
    example-day blends have volumes, so manual testing would never catch
    a regression here -- only a test that deliberately omits one."""
    measured_blend = {
        "name": "Whole-food blend",
        "ingredients": [
            {
                "food_code": FOOD_CHICKEN,
                "food_description": "Chicken breast, cooked",
                "grams": 200.0,
            }
        ],
        "measured_volume_mL": 500.0,
    }
    unmeasured_blend = {
        "name": "Vegan blend",
        "ingredients": [
            {"food_code": FOOD_RICE, "food_description": "Rice, white, cooked", "grams": 200.0}
        ],
        "measured_volume_mL": 0.0,
    }

    # Sanity check: resolving the unmeasured blend directly really does
    # raise -- if this stops raising, the skip below would be testing
    # nothing.
    with pytest.raises(InvalidBlendError):
        resolve_blend_profile(unmeasured_blend, nutrient_amount_df)

    # Same skip idiom the app uses: try each blend, skip on
    # InvalidBlendError, never let it propagate out of the loop.
    comparator_blends = []
    for blend in (measured_blend, unmeasured_blend):
        try:
            profile, _fluid_frac = resolve_blend_profile(blend, nutrient_amount_df)
        except InvalidBlendError:
            continue
        comparator_blends.append((blend["name"], profile))

    df = generate_comparator_table(comparator_blends, daily_volume_mL=1000.0, formula_names=[])

    assert list(df["Name"]) == [f"{EDITING_MARKER} Whole-food blend"]


class TestColorStatus:
    """The Styler CSS for an adequacy Status cell. Moved out of the app on
    2026-08-17 to sit beside _adequacy_status(), which produces the exact
    strings it matches on -- these tests are what stops the two drifting
    apart, since a status string with no colour rule fails silently as a
    blank cell.
    """

    def test_every_status_adequacy_can_produce_has_a_colour(self):
        """The real coupling: iterate the statuses _adequacy_status()
        actually returns and require a rule for each. Add a status there
        without a colour here and this fails."""
        produced = {
            _adequacy_status(50.0, 100.0),  # Below target
            _adequacy_status(100.0, 100.0),  # Meeting target
            _adequacy_status(200.0, 100.0),  # Above target
            _adequacy_status(50.0, 100.0, "UL"),  # Below UL
            _adequacy_status(200.0, 100.0, "UL"),  # Above UL
        }
        assert len(produced) == 5, produced
        for status in produced:
            assert color_status(status), f"{status!r} has no colour rule"

    def test_concerning_statuses_are_red(self):
        red = "background-color: #ffcccc; color: #1a1a1a"
        assert color_status("Below target") == red
        assert color_status("Above UL") == red

    def test_fine_statuses_are_green(self):
        """A UL is a ceiling, not an aim, so "Below UL" reads as fine the
        same way "Meeting target" does for an RDA/AI nutrient."""
        green = "background-color: #c8e6c9; color: #1a1a1a"
        assert color_status("Meeting target") == green
        assert color_status("Below UL") == green

    def test_above_target_is_amber_not_red(self):
        assert color_status("Above target") == "background-color: #ffe0b2; color: #1a1a1a"

    def test_no_target_gets_no_colour(self):
        assert color_status(_adequacy_status(100.0, 0.0)) == ""

    def test_every_rule_sets_text_colour_with_its_background(self):
        """Without an explicit text colour a dark theme renders near-white
        text on pale pink and the status becomes unreadable."""
        for status in ("Below target", "Above target", "Meeting target", "Below UL", "Above UL"):
            css = color_status(status)
            assert "background-color:" in css and "color: #1a1a1a" in css, (status, css)


class TestBreakdownTotalRowTolerance:
    def test_a_registry_nutrient_missing_from_the_frame_totals_as_zero(self, monkeypatch):
        """The per-ingredient rows read the frame with .get(name, 0.0);
        the Total row indexed it directly. compute_ingredient_breakdown()
        has no `pack` argument, so its columns always come from the
        DEFAULT pack while this function's `defs` follow the `pack` it was
        given -- a nutrient the registry defines and the frame lacks
        rendered 0.0 on every ingredient row and then raised KeyError on
        the total, i.e. a crash at the very bottom of a report the RD had
        already read (2026-08-20 review)."""
        import src.report as report_module

        real_defs = report_module._ordered_label_defs(DEFAULT_PACK)
        absent = replace(real_defs[-1], name="not_in_the_frame_ug", label="Absent", unit="ug")
        monkeypatch.setattr(
            report_module,
            "_ordered_label_defs",
            lambda pack=DEFAULT_PACK: list(real_defs) + [absent],
        )

        frame = pd.DataFrame(
            [
                {
                    "food_code": 1704,
                    "food_description": "Banana, raw",
                    "grams": 100.0,
                    **{d.name: 1.0 for d in real_defs},
                }
            ]
        )
        out = report_module.format_ingredient_breakdown(frame)

        assert out.iloc[-1]["Absent (ug)"] == "0.0"
