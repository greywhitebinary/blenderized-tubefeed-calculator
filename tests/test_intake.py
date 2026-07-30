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
    blend_fluid_fraction,
    InvalidBlendError,
)

from tests.conftest import FOOD_BANANA

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
