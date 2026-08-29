"""
test_intake.py — tests for src/intake.py, the Intake Record aggregation.

Read FEED_LOG_REWORK.md sections 2 and 6.2 before touching this file:
the entire point of this module is that a day's totals are a DIRECT SUM
over intake-record rows, never a schedule volume extrapolated against a
blend's measured batch volume. That extrapolation was a real, shipped
bug (fixed 2026-07-19) -- see section 1 of that doc. This file exists
to pin the fix shut: if a future change reintroduces any "logged more
than the batch made" check, the tests below should fail loudly.

Per the project's hard rules: this file does NOT add or test for any
over-draw / batch-mismatch flag -- see class TestNoOverDrawFlag's
docstring for exactly what that means and why logging a blend twice is
normal, expected behavior, not an anomaly to catch.
"""

from datetime import time as dtime

import pytest

from src.intake import (
    WATER_BLEND_LABEL,
    WATER_FLUSH_LABEL,
    aggregate_intake,
    resolve_blend_profile,
    sorted_intake_log,
    default_counts_as_fluid,
    thinned_blend_name,
    unique_blend_name,
    InvalidBlendError,
)

from tests.conftest import FOOD_BANANA, FOOD_CHICKEN, FOOD_ABSENT

# ---------------------------------------------------------------------------
# aggregate_intake() for each source_type
# ---------------------------------------------------------------------------


class TestAggregateIntakeBySourceType:
    def test_blend_row_scales_by_the_blends_own_densities(self, blends, nutrient_amount_df):
        """A blend row's contribution = that blend's per-mL density x the
        row's amount (calculate_daily_totals() reused with "amount"
        standing in for "daily volume" -- see aggregate_intake()'s
        docstring). The fixture blend is 1.05 kcal/mL (see conftest.py's
        `blends` fixture docstring for the full hand-check); logging
        200 mL of it should give exactly 1.05 x 200 = 210.0 kcal.
        """
        intake_log = [
            {
                "id": 1,
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": 1,
                "amount": 200.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(1.05 * 200.0)
        # Fluid fraction of this blend is 0.3 (150 mL water / 500 mL) --
        # see conftest.py's `blends` fixture.
        assert totals.fluid_provided_mL == pytest.approx(0.3 * 200.0)

    def test_formula_row_scales_by_its_per_mL_label_values(
        self, blends, nutrient_amount_df, formulas
    ):
        """A formula row uses formulas.csv's disclosed per-mL values
        directly (no CNF lookup at all) -- 400 mL of a 1.2 kcal/mL,
        0.05 g-protein/mL formula gives 480 kcal, 20 g protein. A
        formula is entirely liquid, so its full amount counts as fluid.
        """
        intake_log = [
            {
                "id": 1,
                "time": dtime(12, 0),
                "source_type": "formula",
                "source_id": "Test Formula 1.2",
                "amount": 400.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df, formulas=formulas)

        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(1.2 * 400.0)
        assert totals.nutrient_totals["protein_g"] == pytest.approx(0.05 * 400.0)
        assert totals.fluid_provided_mL == pytest.approx(400.0)
        # free_water_per_mL (0.85) folds into water_g, alongside CNF moisture.
        assert totals.nutrient_totals["water_g"] == pytest.approx(0.85 * 400.0)

    def test_flush_row_is_fluid_only_no_nutrients(self, blends, nutrient_amount_df):
        """A water flush contributes fluid volume and NOTHING else --
        FEED_LOG_REWORK.md section 2: "flush rows contribute fluid only"."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(15, 0),
                "source_type": "flush",
                "source_id": None,
                "amount": 100.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert totals.fluid_provided_mL == pytest.approx(100.0)
        assert totals.nutrient_totals == {}

    def test_oral_row_scales_a_single_food_directly_no_density_concept(
        self, blends, nutrient_amount_df
    ):
        """An oral row is a single food scaled the same way a blend
        ingredient is -- no volume/density wrapper needed (section 3.1).
        118 g of banana (89 kcal/100g) gives 89 x 1.18 = 105.02 kcal.
        Not flagged counts_as_fluid, so it contributes 0 fluid (a
        banana isn't a drink).
        """
        intake_log = [
            {
                "id": 1,
                "time": None,
                "source_type": "oral",
                "source_id": FOOD_BANANA,
                "food_description": "Banana, raw",
                "amount": 118.0,
                "unit": "g",
                "counts_as_fluid": False,
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(89.0 * 1.18)
        assert totals.nutrient_totals["potassium_mg"] == pytest.approx(358.0 * 1.18)
        assert totals.fluid_provided_mL == 0.0

    def test_oral_row_counted_as_fluid_when_flagged(self, blends, nutrient_amount_df):
        """An oral item the RD flags "counts as fluid" (e.g. a cup of
        juice) contributes its full amount to the fluid ledger -- the
        same per-ingredient judgment call already used for blend
        ingredients (CONTEXT.md section 9's fluids-ledger note), just
        applied to a Food & Drink row."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(10, 0),
                "source_type": "oral",
                "source_id": FOOD_BANANA,
                "food_description": "Banana smoothie (counted as fluid for this test)",
                "amount": 200.0,
                "unit": "g",
                "counts_as_fluid": True,
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert totals.fluid_provided_mL == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# The original bug, pinned shut: no batch-volume extrapolation, ever.
# ---------------------------------------------------------------------------


class TestNoOverDrawFlag:
    """FEED_LOG_REWORK.md section 1: the app used to compute daily totals
    as density x SCHEDULE volume, silently assuming a recipe's measured
    batch volume (e.g. 500 mL) scaled up to however much the schedule
    claimed was delivered (e.g. 1200 mL/day => 3 silent "batches"). The
    rework (section 2 / 6.2) replaced this with a direct sum over
    intake-record rows: each row contributes exactly its own share, and
    there is deliberately NO flag for "logged more than one batch's
    worth" -- that's normal use (the fridge-batch case), not an anomaly.
    These tests protect that fix from silently regressing.
    """

    def test_one_logged_row_contributes_only_its_own_share_not_the_full_batch(
        self, blends, nutrient_amount_df
    ):
        """THE BUG THIS PROTECTS: the pre-rework app would have computed
        daily kcal as (blend's kcal/mL) x (schedule's total daily
        volume) regardless of how much of the 500 mL batch was actually
        logged as given. Here we log exactly HALF the batch (250 mL of
        the 500 mL "Morning blend") and assert the row contributes
        exactly its own 250 mL share -- 1.05 kcal/mL x 250 mL = 262.5
        kcal -- NOT the blend's full-batch total (525 kcal), and NOT
        some schedule-derived number unrelated to what was actually
        logged.
        """
        intake_log = [
            {
                "id": 1,
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": 1,
                "amount": 250.0,  # exactly half of the blend's 500 mL batch
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(262.5)
        # Specifically NOT the full 500 mL batch's 525 kcal:
        assert totals.nutrient_totals["energy_kcal"] != pytest.approx(525.0)

    def test_logging_the_same_blend_twice_in_a_day_just_sums(self, blends, nutrient_amount_df):
        """Logging a blend more than once a day is the ordinary
        fridge-batch case (make it once, draw from it across the day) --
        not an anomaly. Two 300 mL boluses of the same 500 mL-batch
        blend logged the same day must simply sum: 1.05 kcal/mL x 600 mL
        total = 630 kcal. This deliberately logs MORE than the batch's
        measured 500 mL (600 mL total) with no error, no cap, and no
        special "over-draw" field anywhere in the result -- see
        FEED_LOG_REWORK.md section 6.2: a blend is a scale-free
        formulation, so this is exactly like saying "the blend was made
        more than once today," which is normal.
        """
        intake_log = [
            {
                "id": 1,
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": 1,
                "amount": 300.0,
                "unit": "mL",
            },
            {
                "id": 2,
                "time": dtime(14, 0),
                "source_type": "blend",
                "source_id": 1,
                "amount": 300.0,
                "unit": "mL",
            },
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(1.05 * 600.0)
        assert totals.fluid_provided_mL == pytest.approx(0.3 * 600.0)
        # No over-draw / batch-mismatch field exists anywhere on the
        # result -- IntakeTotals carries exactly these attributes and no
        # "over_drawn"/"batch_mismatch"/"excess" field of any kind.
        #
        # This set is deliberately exact rather than a substring check, so
        # that ADDING a field is a decision someone has to make on purpose
        # here. If you are reading this because the assertion just failed:
        # confirm your new field is a legitimate one and add it below --
        # but if it compares "how much was logged" against "how much the
        # batch made", stop, and read FEED_LOG_REWORK.md section 6.2. That
        # comparison is the bug this whole module was rewritten to remove.
        #
        # water_sources added 2026-07-30: splits the day's water by where
        # it came from (blend/formula/oral free water vs flushes) for the
        # ledger. It records provenance of water actually given -- it does
        # not compare anything against a batch volume.
        from dataclasses import fields

        field_names = {f.name for f in fields(totals)}
        assert field_names == {
            "nutrient_totals",
            "fluid_provided_mL",
            "subtotals",
            "nutrient_coverage",
            "water_sources",
        }


# ---------------------------------------------------------------------------
# InvalidBlendError -- the one guard that DOES survive the rework
# ---------------------------------------------------------------------------


class TestOralRowWithNoFoodCode:
    def test_an_oral_row_missing_its_source_id_is_skipped_not_fatal(
        self, nutrient_amount_df, custom_foods
    ):
        """The "blend" and "formula" branches of aggregate_intake() both
        skip a row whose source_id resolves to nothing; the "oral" branch
        used to hand it straight to Ingredient(). A None food_code then
        reached `ing.food_code < 0` in the custom-foods path and raised
        TypeError -- and ONLY when the day already held a custom food, so
        it would have arrived as a crash on one RD's record and not
        another's. day_io.py warn-and-skips the same shape of row on load
        (2026-08-20 review).

        `custom_foods` is not incidental here: without it the comparison
        that raised is never reached, so a test that omitted it would
        pass against the unfixed code.
        """
        log = [
            {
                "id": 1,
                "source_type": "oral",
                "source_id": None,
                "food_description": "typed nothing",
                "amount": 100.0,
                "unit": "g",
            },
            {
                "id": 2,
                "source_type": "oral",
                "source_id": FOOD_BANANA,
                "food_description": "Banana, raw",
                "amount": 100.0,
                "unit": "g",
            },
        ]
        totals = aggregate_intake(log, {}, nutrient_amount_df, custom_foods=custom_foods)

        # The good row still counts; the unusable one contributed nothing.
        assert totals.nutrient_totals["energy_kcal"] > 0


class TestInvalidBlendError:
    def test_zero_volume_blend_with_ingredients_raises(self, nutrient_amount_df):
        """A blend with ingredients but no measured volume can't produce
        densities (division by zero) -- this is a real invalidity, not a
        judgment call, and is the one guard FEED_LOG_REWORK.md section
        6.2 explicitly keeps."""
        bad_blend = {
            "name": "Unmeasured blend",
            "ingredients": [
                {
                    "id": 1,
                    "food_code": 1001,
                    "food_description": "Chicken breast, cooked",
                    "grams": 100.0,
                    "unit": "g",
                    "counts_as_fluid": False,
                }
            ],
            "measured_volume_mL": 0.0,
        }
        with pytest.raises(InvalidBlendError):
            resolve_blend_profile(bad_blend, nutrient_amount_df)

    def test_blend_with_no_ingredients_and_zero_volume_does_not_raise(self, nutrient_amount_df):
        """An empty, brand-new blend (no ingredients yet, volume not
        measured yet) is not invalid -- it just has nothing in it. The
        guard is specifically "has ingredients but no volume", not "has
        no volume"."""
        empty_blend = {"name": "Brand new blend", "ingredients": [], "measured_volume_mL": 0.0}
        profile, fluid_frac = resolve_blend_profile(empty_blend, nutrient_amount_df)

        assert profile.nutrient_totals == {}
        assert fluid_frac == 0.0


# ---------------------------------------------------------------------------
# sorted_intake_log() -- unset-time rows sort last
# ---------------------------------------------------------------------------


class TestSortedIntakeLog:
    def test_rows_sort_chronologically_with_unset_time_last(self):
        """Design doc section 6.1: a real Intake Record has PRN doses,
        "overnight," or genuinely unremembered times -- unset-time rows
        must sort LAST, not first and not raise on comparison against
        rows that do have a time."""
        rows = [
            {"id": 1, "time": dtime(14, 0), "source_type": "flush", "amount": 50.0},
            {"id": 2, "time": None, "source_type": "oral", "amount": 10.0},
            {"id": 3, "time": dtime(8, 0), "source_type": "blend", "amount": 100.0},
            {"id": 4, "time": None, "source_type": "flush", "amount": 20.0},
        ]
        sorted_rows = sorted_intake_log(rows)

        ids_in_order = [r["id"] for r in sorted_rows]
        assert ids_in_order == [3, 1, 2, 4]  # 08:00, 14:00, then both None-time rows

    def test_all_rows_unset_time_preserves_relative_order(self):
        """When nothing has a time, sorting shouldn't scramble the rows
        -- Python's sort is stable, so equal sort keys keep their
        original order."""
        rows = [
            {"id": 1, "time": None, "source_type": "oral", "amount": 1.0},
            {"id": 2, "time": None, "source_type": "flush", "amount": 2.0},
        ]
        sorted_rows = sorted_intake_log(rows)
        assert [r["id"] for r in sorted_rows] == [1, 2]


# ---------------------------------------------------------------------------
# A mixed day: blend + formula + flush + oral, subtotals sum to the total
# ---------------------------------------------------------------------------


class TestMixedDay:
    def test_subtotals_sum_to_the_total(self, blends, nutrient_amount_df, formulas):
        """One realistic day: a bolus of the Morning blend, a can of a
        commercial formula, a water flush, and a banana eaten by mouth.
        "Tube Feed" (blend/formula/flush) and "Food & Drink" (oral) are
        a DISPLAY grouping over one list (design doc section 6.3) -- so
        their nutrient totals and fluid must sum exactly to "Total",
        which must in turn equal the top-level IntakeTotals fields.
        """
        intake_log = [
            {
                "id": 1,
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": 1,
                "amount": 300.0,
                "unit": "mL",
            },
            {
                "id": 2,
                "time": dtime(12, 0),
                "source_type": "formula",
                "source_id": "Test Formula 1.2",
                "amount": 400.0,
                "unit": "mL",
            },
            {
                "id": 3,
                "time": dtime(15, 0),
                "source_type": "flush",
                "source_id": None,
                "amount": 100.0,
                "unit": "mL",
            },
            {
                "id": 4,
                "time": None,
                "source_type": "oral",
                "source_id": FOOD_BANANA,
                "food_description": "Banana, raw",
                "amount": 118.0,
                "unit": "g",
                "counts_as_fluid": False,
            },
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df, formulas=formulas)

        tube_feed = totals.subtotals["Tube Feed"]
        food_drink = totals.subtotals["Food & Drink"]
        total = totals.subtotals["Total"]

        # Energy: blend (1.05*300=315) + formula (1.2*400=480) + flush (0)
        #       = 795 tube-feed kcal; oral banana = 89*1.18 = 105.02 kcal.
        assert tube_feed["nutrient_totals"]["energy_kcal"] == pytest.approx(795.0)
        assert food_drink["nutrient_totals"]["energy_kcal"] == pytest.approx(105.02)
        assert total["nutrient_totals"]["energy_kcal"] == pytest.approx(795.0 + 105.02)
        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(900.02)

        # Fluid: blend 0.3*300=90 + formula 400 (full, I&O convention) +
        # flush 100 = 590 mL tube-feed fluid; oral banana isn't flagged
        # as fluid, so Food & Drink fluid is 0.
        assert tube_feed["fluid_provided_mL"] == pytest.approx(90.0 + 400.0 + 100.0)
        assert food_drink["fluid_provided_mL"] == pytest.approx(0.0)
        assert total["fluid_provided_mL"] == pytest.approx(590.0)
        assert totals.fluid_provided_mL == pytest.approx(590.0)

        # Every nutrient in "Total" must equal Tube Feed + Food & Drink,
        # not just energy_kcal -- check this holds for the whole set of
        # nutrient keys either subtotal produced.
        all_keys = set(tube_feed["nutrient_totals"]) | set(food_drink["nutrient_totals"])
        for key in all_keys:
            expected = tube_feed["nutrient_totals"].get(key, 0.0) + food_drink[
                "nutrient_totals"
            ].get(key, 0.0)
            assert total["nutrient_totals"].get(key, 0.0) == pytest.approx(expected)
            assert totals.nutrient_totals.get(key, 0.0) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Formula rows now contribute to nutrient_coverage (the fix under test).
#
# CONTEXT.md's pinned-issues list and the comment that used to live in
# aggregate_intake()'s formula branch documented this as a known
# limitation: formula rows summed their disclosed nutrients into the
# daily totals correctly but left row_coverage == {}, so on a mixed day
# the adequacy table's "N/M sources" note reflected only the
# food/CNF side. A commercial formula is one product, not a CNF
# ingredient list, so it counts as ONE instance per tracked nutrient --
# (1, 1) for what its CSV row discloses (kcal/protein always, since
# those columns are mandatory; the optional per-mL columns and free
# water when the product's row has them), (0, 1) for what it doesn't
# (a None column, or a tracked nutrient formulas.csv has no column for
# at all, e.g. the clinical-tier zinc/vitamin D/B12 fields). Never
# (0, 0) -- that would make the row invisible to the count instead of
# flagging it as "we don't know".
# ---------------------------------------------------------------------------


class TestFormulaCoverage:
    def test_formula_row_supplies_coverage_for_disclosed_nutrients(
        self, blends, nutrient_amount_df, formulas
    ):
        """A formula-only day: energy_kcal/protein_g are always disclosed
        (mandatory CSV columns -- see _load_commercial_formulas), and this
        fixture's formula also discloses sodium_per_mL and
        free_water_per_mL -- all four should show full (1, 1) coverage,
        not the empty {} the old code left behind."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(12, 0),
                "source_type": "formula",
                "source_id": "Test Formula 1.2",
                "amount": 400.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df, formulas=formulas)

        assert totals.nutrient_coverage["energy_kcal"] == (1, 1)
        assert totals.nutrient_coverage["protein_g"] == (1, 1)
        assert totals.nutrient_coverage["sodium_mg"] == (1, 1)
        assert totals.nutrient_coverage["water_g"] == (1, 1)

    def test_formula_row_flags_undisclosed_nutrient_without_fabricating_a_zero(
        self, blends, nutrient_amount_df, formulas
    ):
        """fibre_g has no fibre_per_mL value in this fixture's formula
        (the column is simply absent, matching the real loader's
        "missing column -> None" contract), and zinc_mg has no formula
        column AT ALL -- it's a clinical-tier nutrient formulas.csv never
        tracks. Both must show n_total=1, n_supplying=0: the "we don't
        know" signal, never a fabricated 0 folded into the total AND
        never a silently-dropped coverage entry either."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(12, 0),
                "source_type": "formula",
                "source_id": "Test Formula 1.2",
                "amount": 400.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df, formulas=formulas)

        assert totals.nutrient_coverage["fibre_g"] == (0, 1)
        assert totals.nutrient_coverage["zinc_mg"] == (0, 1)
        assert "fibre_g" not in totals.nutrient_totals

    def test_formula_only_day_disclosed_nutrients_are_not_hidden(
        self, blends, nutrient_amount_df, formulas
    ):
        """report.py's _zero_coverage() hides a row when n_supplying == 0
        and n_total > 0. For nutrients the formula DOES disclose, coverage
        must come out fully supplied (n_supplying == n_total) so those
        rows are never mistakenly hidden on a formula-only day -- this is
        the "formula-only day is unaffected" guarantee the fix must not
        regress, checked directly against the coverage tuples that drive
        report.py's hiding logic (without importing report.py, which this
        task doesn't touch)."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(12, 0),
                "source_type": "formula",
                "source_id": "Test Formula 1.2",
                "amount": 400.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df, formulas=formulas)

        for name in ("energy_kcal", "protein_g", "sodium_mg", "water_g"):
            n_supplying, n_total = totals.nutrient_coverage[name]
            assert n_total > 0
            assert n_supplying == n_total  # full coverage -- report.py would not hide this

    def test_mixed_day_coverage_reflects_both_blend_and_formula(self, nutrient_amount_df, formulas):
        """The bug this task exists to fix. A 2-ingredient blend where
        only chicken has a sodium row (FOOD_ABSENT has no CNF data at
        all) gives an intentionally partial sodium_mg coverage of
        (1, 2) from the blend alone. Before the fix, that (1, 2) was ALL
        a mixed day would ever show for sodium, because the formula row
        contributed nothing -- the adequacy table's "N/M sources"
        note reflected only the food/CNF side even though the formula
        (which also discloses sodium_per_mL) was part of the day. After
        the fix, the formula's own (1, 1) folds in via _add_coverage to
        give (2, 3) -- reflecting BOTH sources.
        """
        blends_local = {
            1: {
                "name": "Partial-data blend",
                "ingredients": [
                    {
                        "id": 1,
                        "food_code": FOOD_CHICKEN,
                        "food_description": "Chicken breast, cooked",
                        "grams": 100.0,
                        "unit": "g",
                        "counts_as_fluid": False,
                    },
                    {
                        "id": 2,
                        "food_code": FOOD_ABSENT,
                        "food_description": "Food with no CNF data",
                        "grams": 100.0,
                        "unit": "g",
                        "counts_as_fluid": False,
                    },
                ],
                "measured_volume_mL": 200.0,
            }
        }
        blend_row = {
            "id": 1,
            "time": dtime(8, 0),
            "source_type": "blend",
            "source_id": 1,
            "amount": 200.0,
            "unit": "mL",
        }
        formula_row = {
            "id": 2,
            "time": dtime(12, 0),
            "source_type": "formula",
            "source_id": "Test Formula 1.2",
            "amount": 400.0,
            "unit": "mL",
        }

        # Isolated baseline: the blend alone really is partial (1, 2) --
        # confirms the mixed-day number below isn't an artifact of the
        # blend's own coverage math.
        blend_only = aggregate_intake([blend_row], blends_local, nutrient_amount_df)
        assert blend_only.nutrient_coverage["sodium_mg"] == (1, 2)

        # Mixed day: the formula's own (1, 1) must fold in on top of the
        # blend's (1, 2), not be dropped.
        mixed = aggregate_intake(
            [blend_row, formula_row], blends_local, nutrient_amount_df, formulas=formulas
        )
        assert mixed.nutrient_coverage["sodium_mg"] == (2, 3)


# ---------------------------------------------------------------------------
# The 2026-08-20 vitamin/mineral columns (formula_sources/UNIT_CONVERSIONS.md)
# reaching the daily totals and coverage, against the REAL Canadian catalog
# rather than the small hand-written `formulas` fixture -- the fixture
# proves the mechanism works for whatever formulas.csv discloses, but only
# reading the real CSV (via src.calculator.commercial_formulas, exactly as
# the app does) catches a real wiring gap: a column present in the CSV that
# _FORMULA_COLUMN_TO_NUTRIENT or _OPTIONAL_NUTRIENT_COLUMNS forgot to list.
# ---------------------------------------------------------------------------


class TestRealCatalogVitaminMineralColumns:
    def test_disclosed_vitamins_reach_totals_and_full_coverage(self, blends, nutrient_amount_df):
        """Glucerna 1.2 Cal (data/packs/canada/formulas.csv) discloses
        vitamin C, vitamin D and vitamin A (RAE) but not retinol (its
        beta-carotene is disclosed unsplit from the Vitamin A IU total --
        UNIT_CONVERSIONS.md section 2). A day of nothing but 500 mL of it
        should show all three in nutrient_totals, scaled by the label's
        own per-mL values, and (1, 1) coverage -- not "not disclosed"."""
        from src.calculator import commercial_formulas

        real_formulas = commercial_formulas("canada")
        glucerna = real_formulas["Glucerna 1.2 Cal"]
        intake_log = [
            {
                "id": 1,
                "time": dtime(12, 0),
                "source_type": "formula",
                "source_id": "Glucerna 1.2 Cal",
                "amount": 500.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df, formulas=real_formulas)

        assert totals.nutrient_totals["vitamin_c_mg"] == pytest.approx(
            glucerna["vitamin_c_mg_per_mL"] * 500.0
        )
        assert totals.nutrient_totals["vitamin_d_ug"] == pytest.approx(
            glucerna["vitamin_d_ug_per_mL"] * 500.0
        )
        assert totals.nutrient_totals["vitamin_a_rae_ug"] == pytest.approx(
            glucerna["vitamin_a_rae_ug_per_mL"] * 500.0
        )
        assert totals.nutrient_coverage["vitamin_c_mg"] == (1, 1)
        assert totals.nutrient_coverage["vitamin_d_ug"] == (1, 1)
        assert totals.nutrient_coverage["vitamin_a_rae_ug"] == (1, 1)

        # Glucerna's beta-carotene is disclosed unsplit from the Vitamin A
        # total (no separate Retinol line on the panel), so per
        # UNIT_CONVERSIONS.md section 2 retinol_ug stays blank -- this
        # must read as "not disclosed" (0, 1), never a fabricated 0 folded
        # into the total.
        assert glucerna["retinol_ug_per_mL"] is None
        assert "retinol_ug" not in totals.nutrient_totals
        assert totals.nutrient_coverage["retinol_ug"] == (0, 1)

    def test_every_catalog_formula_column_reaches_nutrient_totals(self, blends, nutrient_amount_df):
        """Every one of the 51 real formulas, fed alone for a day: every
        vitamin/mineral column that row discloses must show up in
        nutrient_totals at the right scaled value, and every one it
        leaves blank must show (0, 1) coverage rather than vanishing.
        Guards against a column landing in formulas.csv without a
        matching entry in _FORMULA_COLUMN_TO_NUTRIENT (the total would
        silently be missing) or in _OPTIONAL_NUTRIENT_COLUMNS (the value
        would silently never be read off the CSV at all)."""
        from src.calculator import commercial_formulas
        from src.intake import _FORMULA_COLUMN_TO_NUTRIENT

        real_formulas = commercial_formulas("canada")
        assert len(real_formulas) == 51, "expected the full Canadian catalog"

        amount = 300.0
        for name, formula in real_formulas.items():
            intake_log = [
                {
                    "id": 1,
                    "time": dtime(12, 0),
                    "source_type": "formula",
                    "source_id": name,
                    "amount": amount,
                    "unit": "mL",
                }
            ]
            totals = aggregate_intake(
                intake_log, blends, nutrient_amount_df, formulas=real_formulas
            )
            for col, nutrient_key in _FORMULA_COLUMN_TO_NUTRIENT.items():
                per_mL = formula.get(col)
                if per_mL is None:
                    assert nutrient_key not in totals.nutrient_totals, (
                        f"{name}: {nutrient_key} should be absent (blank {col}), "
                        f"not fabricated as 0"
                    )
                    assert totals.nutrient_coverage[nutrient_key] == (
                        0,
                        1,
                    ), f"{name}: {nutrient_key} should read 'not disclosed'"
                else:
                    assert totals.nutrient_totals[nutrient_key] == pytest.approx(
                        per_mL * amount
                    ), f"{name}: {nutrient_key} did not scale from {col}"
                    assert totals.nutrient_coverage[nutrient_key] == (
                        1,
                        1,
                    ), f"{name}: {nutrient_key} should read fully disclosed"


class TestWaterSources:
    """Every water source kept on its own line (author, 2026-07-30).

    The clinical rule being encoded: water that arrived as PART OF
    SOMETHING FED is free water -- tap water stirred into a blend
    included, because once it's in the recipe it is the recipe, exactly
    like the moisture in a banana. Only a flush is water given as water.
    """

    def test_tap_water_in_a_blend_stays_blend_free_water(self, blends, nutrient_amount_df):
        """Water poured into the blender is NOT broken out separately --
        it's part of the recipe, so it belongs to the blend's free water."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": 1,
                "amount": 500.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert WATER_BLEND_LABEL in totals.water_sources
        assert WATER_FLUSH_LABEL not in totals.water_sources
        # The blend's free water equals its water_g -- one number, not
        # split into "food moisture" and "added water".
        assert totals.water_sources[WATER_BLEND_LABEL] == pytest.approx(
            totals.nutrient_totals["water_g"]
        )

    def test_a_flush_is_its_own_source_at_full_volume(self, blends, nutrient_amount_df):
        """A flush is water given as water: its own line, full volume, and
        it stays OUT of the free-water figure."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(9, 0),
                "source_type": "flush",
                "source_id": None,
                "amount": 200.0,
                "unit": "mL",
            }
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        assert totals.water_sources == {WATER_FLUSH_LABEL: 200.0}
        # Deliberately absent from free water -- see IntakeTotals.free_water_mL
        assert totals.free_water_mL == 0.0

    def test_sources_are_listed_separately_and_sum_to_all_water(self, blends, nutrient_amount_df):
        """A mixed day: each source on its own line, and free water plus
        flushes accounts for every drop."""
        intake_log = [
            {
                "id": 1,
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": 1,
                "amount": 500.0,
                "unit": "mL",
            },
            {
                "id": 2,
                "time": dtime(9, 0),
                "source_type": "flush",
                "source_id": None,
                "amount": 200.0,
                "unit": "mL",
            },
            {
                "id": 3,
                "time": dtime(10, 0),
                "source_type": "flush",
                "source_id": None,
                "amount": 150.0,
                "unit": "mL",
            },
        ]
        totals = aggregate_intake(intake_log, blends, nutrient_amount_df)

        # Flushes accumulate onto one line rather than one line each.
        assert totals.water_sources[WATER_FLUSH_LABEL] == pytest.approx(350.0)
        assert set(totals.water_sources) == {WATER_BLEND_LABEL, WATER_FLUSH_LABEL}
        # Total water = free water (in the feeds) + flushes.
        assert sum(totals.water_sources.values()) == pytest.approx(totals.free_water_mL + 350.0)

    def test_a_day_with_no_water_reports_no_sources(self, blends, nutrient_amount_df):
        """An empty ledger shows nothing rather than a row of zeroes."""
        totals = aggregate_intake([], blends, nutrient_amount_df)
        assert totals.water_sources == {}


# ---------------------------------------------------------------------------
# unique_blend_name() -- blend names must never repeat (author, 2026-08-16)
# ---------------------------------------------------------------------------


class TestUniqueBlendName:
    """A name is what identifies a recipe on every screen it appears on,
    so two blends reading the same is a real ambiguity for the RD even
    though the app itself tells them apart by id. app/streamlit_app.py
    calls this from _new_blend() (the single point where a blend is born)
    and from the Blend name box's on_change.
    """

    def test_a_free_name_is_returned_untouched(self):
        assert unique_blend_name("Renal", ["Whole-food blend"]) == "Renal"

    def test_a_taken_name_gets_the_first_free_number(self):
        assert unique_blend_name("Renal", ["Renal"]) == "Renal (2)"
        assert unique_blend_name("Renal", ["Renal", "Renal (2)"]) == "Renal (3)"

    def test_gaps_in_the_numbering_are_filled_not_skipped(self):
        """Deleting "Renal (2)" should let the next duplicate reuse it,
        rather than counting the list and landing on (4)."""
        assert unique_blend_name("Renal", ["Renal", "Renal (3)"]) == "Renal (2)"

    def test_an_already_numbered_name_is_renumbered_not_double_suffixed(self):
        """Loading the same file twice would otherwise produce
        "Renal (2) (2)" -- the stem is re-used instead."""
        assert unique_blend_name("Renal (2)", ["Renal", "Renal (2)"]) == "Renal (3)"

    def test_a_free_numbered_name_keeps_its_number(self):
        """The suffix is only ever re-stemmed on COLLISION: a blend the RD
        deliberately called "Trial (2)" stays that, given nothing else has
        the name."""
        assert unique_blend_name("Trial (2)", ["Renal"]) == "Trial (2)"

    def test_parenthesised_text_is_not_mistaken_for_a_number(self):
        """Only a bare integer in brackets is a suffix, so a clinically
        meaningful tail like "(low K)" stays part of the stem."""
        assert unique_blend_name("Renal (low K)", ["Renal (low K)"]) == "Renal (low K) (2)"

    def test_loading_the_example_day_twice_does_not_repeat_its_names(self):
        """The concrete case that motivated this: "Load example day" keeps
        any blend that already has ingredients and adds its own on top, so
        without this the RD ends up with two "Whole-food blend" rows."""
        taken = ["Whole-food blend", "Vegan blend"]
        assert unique_blend_name("Whole-food blend", taken) == "Whole-food blend (2)"
        assert unique_blend_name("Vegan blend", taken) == "Vegan blend (2)"


class TestThinnedBlendName:
    """Thinning makes a SEPARATE recipe, so it needs a name of its own.
    The name was shortened from "X (thinned with 150 mL apple juice)" to
    "X (thinned)" on 2026-08-16: the long form crowded the blend selector,
    and what it spelled out is already recorded as an ingredient of the
    copy and as the copy's measured volume, neither of which can drift out
    of step with the recipe the way a name can.
    """

    def test_a_plain_blend_gains_the_suffix(self):
        assert thinned_blend_name("Whole-food blend") == "Whole-food blend (thinned)"

    def test_thinning_a_thinned_blend_does_not_compound(self):
        """The failure this guards: "X (thinned) (thinned)". Asking for the
        same name again is correct -- unique_blend_name() turns it into
        "(thinned) (2)", so repeats use ONE numbering scheme rather than a
        second one owned by thinning."""
        assert thinned_blend_name("Whole-food blend (thinned)") == "Whole-food blend (thinned)"
        assert thinned_blend_name("Whole-food blend (thinned) (2)") == "Whole-food blend (thinned)"

    def test_the_full_progression_through_unique_blend_name(self):
        """Thin, thin again, thin again -- the sequence an RD building
        progressively thinner versions actually walks."""
        names = ["Whole-food blend"]
        for _ in range(3):
            names.append(unique_blend_name(thinned_blend_name(names[-1]), names))
        assert names == [
            "Whole-food blend",
            "Whole-food blend (thinned)",
            "Whole-food blend (thinned) (2)",
            "Whole-food blend (thinned) (3)",
        ]

    def test_a_number_that_is_not_a_thinned_suffix_is_kept(self):
        """ "Renal (2)" is a blend in its own right, distinguished from
        "Renal" by that number, so thinning it must not quietly drop it."""
        assert thinned_blend_name("Renal (2)") == "Renal (2) (thinned)"

    def test_a_parenthesised_word_is_not_mistaken_for_the_suffix(self):
        assert thinned_blend_name("Renal (low K)") == "Renal (low K) (thinned)"


class TestDefaultCountsAsFluid:
    """Seeds the counts-as-fluid checkbox. Moved out of the app on
    2026-08-17, which is the first time it could be tested at all -- and
    it is a clinical display rule, not a cosmetic one: it decides what a
    food contributes to the fluids ledger unless the RD overrides it.
    """

    def test_anything_in_cnfs_beverages_group_counts(self):
        assert default_counts_as_fluid("Cola, carbonated", 14) is True

    def test_a_food_named_water_counts_outside_that_group(self):
        assert default_counts_as_fluid("Water, municipal", 1) is True
        assert default_counts_as_fluid("Water, mineral, bottled", 1) is True

    def test_watermelon_is_not_water(self):
        """The reason this matches on the WORD at the start, not a plain
        substring: "Watermelon, raw" is a food, not a drink."""
        assert default_counts_as_fluid("Watermelon, raw", 1) is False

    def test_a_soup_with_water_added_is_not_water(self):
        """176 CNF descriptions carry "water added" mid-string. Matching
        anywhere would sweep every one of them into the fluids ledger."""
        assert default_counts_as_fluid("Soup, tomato, canned, water added", 1) is False

    def test_an_ordinary_food_does_not_count(self):
        assert default_counts_as_fluid("Chicken, broiler, breast, braised", 1) is False

    def test_a_missing_description_does_not_raise(self):
        assert default_counts_as_fluid("", 1) is False
        assert default_counts_as_fluid(None, 1) is False
