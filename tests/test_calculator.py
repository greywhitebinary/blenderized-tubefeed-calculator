"""
test_calculator.py — tests for src/calculator.py.

Covers the per-100 g scaling core (compute_nutrient_totals), the
density math (calculate_profile: kcal/mL, protein/mL, free-water
fraction), the dilution what-if (dilute), the label-to-per-100g
conversion, and custom-food-from-label folding into a blend.

Every expected number in this file was cross-checked by running the
real src/calculator.py against the tests/conftest.py fixtures before
being written down here (not just hand-arithmetic) -- see each test's
comment for the arithmetic so a reader who knows nutrition but not
pytest can follow along.

Per the project's hard rules: src/ is NOT modified by this file, and no
real CNF data is loaded (see conftest.py's module docstring).
"""

import pytest

from src.calculator import (
    compute_nutrient_totals,
    compute_nutrient_totals_and_coverage,
    calculate_profile,
    dilute,
    label_to_per_100g,
)
from src.models import Ingredient, Recipe

from tests.conftest import (
    FOOD_CHICKEN,
    FOOD_RICE,
    FOOD_OIL,
    FOOD_WATER,
    FOOD_ABSENT,
    CUSTOM_PROTEIN_SHAKE,
)

# ---------------------------------------------------------------------------
# compute_nutrient_totals() -- the per-100 g scaling core
# ---------------------------------------------------------------------------


class TestComputeNutrientTotals:
    def test_scales_grams_times_amount_over_100(self, nutrient_amount_df):
        """Core formula: nutrient_from_ingredient = grams x (amount / 100).

        200 g chicken (165 kcal/100g) + 150 g rice (130 kcal/100g):
            energy_kcal = 165*2.00 + 130*1.50 = 330.0 + 195.0 = 525.0
            protein_g   = 31*2.00  + 2.7*1.50 =  62.0 +   4.05 =  66.05
        """
        ingredients = [
            Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
            Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
        ]
        totals = compute_nutrient_totals(ingredients, nutrient_amount_df)

        assert totals["energy_kcal"] == pytest.approx(525.0)
        assert totals["protein_g"] == pytest.approx(66.05)
        assert totals["water_g"] == pytest.approx(65 * 2 + 68 * 1.5)  # 232.0

    def test_food_absent_from_nutrient_table_contributes_nothing_and_does_not_raise(
        self, nutrient_amount_df
    ):
        """A food_code with zero rows in Nutrient_Amount (e.g. an
        incomplete CNF record) must silently contribute 0 to every
        nutrient -- not raise, and not be mistaken for a true
        zero-value ingredient (see the coverage test below for how the
        two are told apart)."""
        ingredients = [
            Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
            Ingredient(FOOD_ABSENT, "Mystery food, not in CNF fixture", 50.0),
        ]
        totals = compute_nutrient_totals(ingredients, nutrient_amount_df)

        # Same as chicken alone -- the absent food adds exactly zero.
        assert totals["energy_kcal"] == pytest.approx(165 * 2.0)
        assert totals["protein_g"] == pytest.approx(31 * 2.0)

    def test_zero_gram_ingredient_contributes_zero(self, nutrient_amount_df):
        """An ingredient present in the recipe at 0 g (e.g. an oil the RD
        added and then removed, or a placeholder row) must scale to
        exactly zero -- grams x (amount/100) = 0 x anything = 0."""
        ingredients = [
            Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
            Ingredient(FOOD_OIL, "Canola oil", 0.0),
        ]
        totals = compute_nutrient_totals(ingredients, nutrient_amount_df)

        assert totals["energy_kcal"] == pytest.approx(165 * 2.0)
        assert totals["fat_g"] == pytest.approx(3.6 * 2.0)  # oil's fat: 0

    def test_coverage_distinguishes_missing_data_from_a_true_zero(self, nutrient_amount_df):
        """A missing CNF row and an ingredient that truly has 0 g both
        sum to 0 in nutrient_totals -- indistinguishable from the total
        alone. nutrient_coverage is what tells them apart: the 0-gram
        oil still HAS a fat_g row in the CNF table, so it counts as
        "supplying" data (even though its contribution is zero);
        the absent food has no row at all, so it does NOT count.

        4 ingredients total: chicken, rice, absent-food, 0g-oil.
        fat_g is supplied by chicken, rice, and oil (3 of 4) --
        the absent food is the only one NOT counted.
        """
        ingredients = [
            Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
            Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
            Ingredient(FOOD_ABSENT, "Mystery food, not in CNF fixture", 50.0),
            Ingredient(FOOD_OIL, "Canola oil", 0.0),
        ]
        _totals, coverage = compute_nutrient_totals_and_coverage(ingredients, nutrient_amount_df)

        n_supplying, n_total = coverage["fat_g"]
        assert n_total == 4
        assert n_supplying == 3  # chicken, rice, 0g-oil -- NOT the absent food


# ---------------------------------------------------------------------------
# calculate_profile() -- densities against a MEASURED final volume
# ---------------------------------------------------------------------------


class TestCalculateProfileDensities:
    def test_densities_use_measured_volume_as_denominator(self, nutrient_amount_df):
        """The blend: 200 g chicken + 150 g rice + 150 g water, measured
        (poured into a jug and read the mark) to 500 mL.

        energy_kcal = 165*2 + 130*1.5           = 525.0
        protein_g   = 31*2  + 2.7*1.5           =  66.05
        water_g     = 65*2  + 68*1.5 + 100*1.5  = 382.0

        kcal_per_mL         = 525.0  / 500 = 1.05
        protein_per_mL      = 66.05  / 500 = 0.1321
        free_water_fraction = 382.0  / 500 = 0.764   (added_water_mL=0)
        """
        recipe = Recipe(
            name="Morning blend",
            ingredients=[
                Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
                Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
                Ingredient(FOOD_WATER, "Water", 150.0),
            ],
            measured_final_volume_mL=500.0,
        )
        profile = calculate_profile(recipe, nutrient_amount_df)

        assert profile.kcal_per_mL == pytest.approx(1.05)
        assert profile.protein_per_mL == pytest.approx(0.1321)
        assert profile.free_water_fraction == pytest.approx(0.764)

    def test_measured_volume_is_an_input_never_computed_from_ingredients(self, nutrient_amount_df):
        """The measured final volume is a number the RD reads off a jug --
        it is NOT derived from summing ingredient grams (blending adds
        air, some water evaporates or is absorbed, etc. -- see
        src/models.py::Recipe's docstring). Proof: two recipes with the
        IDENTICAL ingredients but two different measured volumes must
        produce identical totals and DIFFERENT densities -- if the
        calculator were secretly deriving volume from grams, the
        densities would come out the same regardless of what
        measured_final_volume_mL says.
        """
        ingredients = [
            Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
            Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
        ]
        # 350 g of ingredients went in, but the two batches were measured
        # (post-blend) at very different volumes -- e.g. one had a lot
        # more added water than the other's jug reading reflects.
        recipe_a = Recipe(ingredients=ingredients, measured_final_volume_mL=400.0)
        recipe_b = Recipe(ingredients=ingredients, measured_final_volume_mL=800.0)

        profile_a = calculate_profile(recipe_a, nutrient_amount_df)
        profile_b = calculate_profile(recipe_b, nutrient_amount_df)

        # Totals (grams-based) are identical -- same ingredients.
        assert profile_a.total_kcal == pytest.approx(profile_b.total_kcal)
        # Densities are NOT identical -- they depend on the measured
        # volume, not on ingredient weight.
        assert profile_a.kcal_per_mL == pytest.approx(profile_a.total_kcal / 400.0)
        assert profile_b.kcal_per_mL == pytest.approx(profile_b.total_kcal / 800.0)
        assert profile_a.kcal_per_mL == pytest.approx(profile_b.kcal_per_mL * 2)

    def test_zero_measured_volume_returns_zero_densities_not_a_crash(self, nutrient_amount_df):
        """A recipe with ingredients but no measured volume yet (RD
        hasn't measured the jug) must not raise ZeroDivisionError --
        calculate_profile()'s guard returns an empty-totals profile, and
        NutrientProfile's density properties themselves guard <= 0 too."""
        recipe = Recipe(
            ingredients=[Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0)],
            measured_final_volume_mL=0.0,
        )
        profile = calculate_profile(recipe, nutrient_amount_df)

        assert profile.kcal_per_mL == 0.0
        assert profile.protein_per_mL == 0.0
        assert profile.free_water_fraction == 0.0

    def test_no_ingredients_returns_zero_densities(self, nutrient_amount_df):
        """An empty recipe (no ingredients yet) must not crash either."""
        recipe = Recipe(ingredients=[], measured_final_volume_mL=500.0)
        profile = calculate_profile(recipe, nutrient_amount_df)

        assert profile.nutrient_totals == {}
        assert profile.kcal_per_mL == 0.0


# ---------------------------------------------------------------------------
# dilute() -- adding a thinning liquid
# ---------------------------------------------------------------------------


class TestDilute:
    def test_adding_pure_water_lowers_kcal_and_protein_density_raises_free_water(
        self, nutrient_amount_df
    ):
        """Adding 100 mL of pure water (0 kcal, 0 protein, 100 g water):
        new_volume = 500 + 100 = 600
        new_kcal_per_mL = 525.0 / 600 = 0.875          (was 1.05)
        new_free_water  = (382 + 100) / 600 = 0.8033   (was 0.764)
        """
        recipe = Recipe(
            ingredients=[
                Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
                Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
                Ingredient(FOOD_WATER, "Water", 150.0),
            ],
            measured_final_volume_mL=500.0,
        )
        profile = calculate_profile(recipe, nutrient_amount_df)

        diluted = dilute(profile, added_liquid_mL=100.0, liquid_water_g=100.0)

        assert diluted.measured_final_volume_mL == pytest.approx(600.0)
        assert diluted.kcal_per_mL == pytest.approx(0.875)
        assert diluted.kcal_per_mL < profile.kcal_per_mL
        assert diluted.free_water_fraction == pytest.approx((382.0 + 100.0) / 600.0)
        assert diluted.free_water_fraction > profile.free_water_fraction

    def test_adding_a_caloric_liquid_changes_both_numerator_and_denominator(
        self, nutrient_amount_df
    ):
        """Adding 100 mL of a caloric liquid (e.g. juice: 50 kcal, 1 g
        protein, 90 g water) changes BOTH the top and bottom of the
        density fraction, not just the volume:
        new_kcal_per_mL    = (525.0 + 50) / 600 = 0.9583
        new_protein_per_mL = (66.05 + 1)  / 600 = 0.11175
        Nutrients dilute() doesn't know how to add (e.g. sodium) are
        left as absolute totals, unchanged -- dilute() only models
        kcal/protein/water contributions from the added liquid (see
        its docstring); this is a scope note, not a bug.
        """
        recipe = Recipe(
            ingredients=[
                Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
                Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
                Ingredient(FOOD_WATER, "Water", 150.0),
            ],
            measured_final_volume_mL=500.0,
        )
        profile = calculate_profile(recipe, nutrient_amount_df)

        diluted = dilute(
            profile,
            added_liquid_mL=100.0,
            liquid_kcal=50.0,
            liquid_protein_g=1.0,
            liquid_water_g=90.0,
        )

        assert diluted.kcal_per_mL == pytest.approx((525.0 + 50.0) / 600.0)
        assert diluted.protein_per_mL == pytest.approx((66.05 + 1.0) / 600.0)
        # sodium_mg wasn't passed to dilute() at all -- stays as the
        # original absolute total (dilute() only models kcal/protein/water).
        assert diluted.nutrient_totals["sodium_mg"] == pytest.approx(
            profile.nutrient_totals["sodium_mg"]
        )


# ---------------------------------------------------------------------------
# label_to_per_100g() -- label value + serving size -> per-100 g
# ---------------------------------------------------------------------------


class TestLabelToPer100g:
    def test_converts_a_non_100g_serving(self):
        """The exact worked example from calculator.py's own docstring:
        a 175 g serving with 130 kcal -> 130 x (100/175) = 74.2857... kcal
        per 100 g."""
        assert label_to_per_100g(130, 175) == pytest.approx(130 * 100 / 175)
        assert label_to_per_100g(130, 175) == pytest.approx(74.2857142857, rel=1e-6)

    def test_100g_serving_is_the_identity(self):
        """If the label's serving size already IS 100 g, per-100g equals
        the label value unchanged."""
        assert label_to_per_100g(250.0, 100.0) == pytest.approx(250.0)

    def test_zero_or_negative_serving_size_raises(self):
        """A serving size of 0 g (or negative -- a data-entry typo) can't
        be divided by -- must raise, not silently return inf/NaN into a
        patient's nutrient totals."""
        with pytest.raises(ValueError):
            label_to_per_100g(100.0, 0.0)
        with pytest.raises(ValueError):
            label_to_per_100g(100.0, -5.0)


# ---------------------------------------------------------------------------
# Custom-food-from-label folding into a blend alongside CNF foods
# ---------------------------------------------------------------------------


class TestCustomFoodFolding:
    def test_custom_food_contributes_alongside_cnf_foods(self, nutrient_amount_df, custom_foods):
        """A blend of 100 g CNF chicken + 50 g of a custom "protein shake"
        food entered from a nutrition-facts label (250 kcal, 10 g
        protein, 120 mg sodium per 100 g -- see conftest.py's
        `custom_foods` fixture), measured to 300 mL.

        CNF side (chicken, 100 g):  energy=165, protein=31,  sodium=74
        Custom side (shake, 50 g):  energy=125, protein= 5,  sodium=60
                                    (250*0.5)   (10*0.5)     (120*0.5)
        Combined totals:            energy=290, protein=36,  sodium=134
        """
        recipe = Recipe(
            name="Blend with a custom food",
            ingredients=[
                Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 100.0),
                Ingredient(CUSTOM_PROTEIN_SHAKE, "Protein shake (label)", 50.0),
            ],
            measured_final_volume_mL=300.0,
        )
        profile = calculate_profile(recipe, nutrient_amount_df, custom_foods=custom_foods)

        assert profile.nutrient_totals["energy_kcal"] == pytest.approx(165.0 + 125.0)
        assert profile.nutrient_totals["protein_g"] == pytest.approx(31.0 + 5.0)
        assert profile.nutrient_totals["sodium_mg"] == pytest.approx(74.0 + 60.0)
        assert profile.kcal_per_mL == pytest.approx(290.0 / 300.0)

    def test_custom_food_credits_its_own_coverage(self, nutrient_amount_df, custom_foods):
        """The custom food only discloses energy/protein/sodium (matching
        what a real nutrition-facts label actually shows) -- coverage for
        those three nutrients should count BOTH ingredients as
        "supplying" (2/2), while a nutrient the custom food doesn't carry
        (e.g. fibre_g, which no NFt panel gives a "custom food" a value
        for here) should count only the CNF ingredient (1/2)."""
        ingredients = [
            Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 100.0),
            Ingredient(CUSTOM_PROTEIN_SHAKE, "Protein shake (label)", 50.0),
        ]
        _totals, coverage = compute_nutrient_totals_and_coverage(
            ingredients, nutrient_amount_df, custom_foods
        )

        assert coverage["energy_kcal"] == (2, 2)
        assert coverage["protein_g"] == (2, 2)
        assert coverage["sodium_mg"] == (2, 2)
        assert coverage["fibre_g"] == (1, 2)  # only chicken supplies fibre data
