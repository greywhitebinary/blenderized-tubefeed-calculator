"""
test_modulars.py — the modular table and the "modular" intake row type.

A modular is an additive, not a feed: a scoop of protein powder, a dose
of liquid fibre. Two things make it different from everything already in
the Intake Record, and both are what this file guards.

THE BASIS. `modulars.csv` is per UNIT, and a unit is a millilitre for a
liquid (MCT Oil, HiFibre) or a GRAM for a powder (BeneProtein,
BanatrAll). Every other per-quantity table in this project is per
millilitre throughout, so this is the one place where multiplying an
amount by a column requires knowing which unit the row is in.

THE FLUID. A liquid modular is fluid given. A powder is not -- the water
it is stirred into is the RD's own flush row. Counting a scoop as
millilitres of fluid would inflate a patient's recorded intake, and the
manufacturers' own dilutions disagree with each other (60 mL a scoop in
hospital practice for BeneProtein, 120 mL a packet on Banatrol's sheet,
30 mL on ProSource's), so the app must never infer that water.
"""

import pytest

from src.calculator import _load_modulars, _MODULAR_NUTRIENT_COLUMNS, MODULARS
from src.intake import aggregate_intake


@pytest.fixture
def modular_table() -> dict[str, dict]:
    """One powder and one liquid, each disclosing only some nutrients.

    Deliberately NOT the shipped table: these tests are about the
    contract, and pinning them to real products would make them fail
    whenever a manufacturer reformulates.
    """
    return {
        "Test Powder": {
            "basis": "g",
            "brand": "Test Brand",
            "kcal_per_unit": 3.5,
            "protein_per_unit": 0.85,
            "sodium_per_unit": 2.0,
            # Everything else undisclosed -- the powder's panel doesn't say.
            "free_water_per_unit": None,
            "directions": "Mix into water or food.",
            "source": "test",
        },
        "Test Liquid": {
            "basis": "mL",
            "brand": "Test Brand",
            "kcal_per_unit": 2.0,
            "protein_per_unit": 0.5,
            "sodium_per_unit": 1.5,
            "free_water_per_unit": 0.8,
            "directions": None,
            "source": "test",
        },
    }


def _row(source_id: str, amount: float, unit: str) -> dict:
    return {
        "id": 1,
        "time": None,
        "source_type": "modular",
        "source_id": source_id,
        "food_description": None,
        "amount": amount,
        "unit": unit,
        "counts_as_fluid": False,
    }


class TestBasisDrivesFluid:
    def test_powder_contributes_nutrients_but_no_fluid(
        self, blends, nutrient_amount_df, modular_table
    ):
        """A 7 g scoop is 7 grams of powder, not 7 mL of anything.

        This is the whole reason "modular" is a separate source_type
        rather than another formula row: the formula branch sets
        row_fluid = amount unconditionally, because a formula is entirely
        liquid. A powder is not.
        """
        totals = aggregate_intake(
            [_row("Test Powder", 7.0, "g")],
            blends,
            nutrient_amount_df,
            modular_table=modular_table,
        )

        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(3.5 * 7.0)
        assert totals.nutrient_totals["protein_g"] == pytest.approx(0.85 * 7.0)
        assert totals.nutrient_totals["sodium_mg"] == pytest.approx(2.0 * 7.0)
        assert totals.fluid_provided_mL == pytest.approx(0.0)

    def test_liquid_contributes_fluid_and_free_water(
        self, blends, nutrient_amount_df, modular_table
    ):
        """A liquid modular behaves like any other liquid given."""
        totals = aggregate_intake(
            [_row("Test Liquid", 30.0, "mL")],
            blends,
            nutrient_amount_df,
            modular_table=modular_table,
        )

        assert totals.nutrient_totals["energy_kcal"] == pytest.approx(2.0 * 30.0)
        assert totals.fluid_provided_mL == pytest.approx(30.0)
        assert totals.nutrient_totals["water_g"] == pytest.approx(0.8 * 30.0)

    def test_the_same_number_means_different_things_per_basis(
        self, blends, nutrient_amount_df, modular_table
    ):
        """30 of the powder and 30 of the liquid must not agree on fluid.

        The failure this catches is a caller that stops consulting
        `basis` and treats every modular as millilitres -- which would
        look right for the two liquids in the shipped table and silently
        invent 30 mL of intake for every powder.
        """
        powder = aggregate_intake(
            [_row("Test Powder", 30.0, "g")],
            blends,
            nutrient_amount_df,
            modular_table=modular_table,
        )
        liquid = aggregate_intake(
            [_row("Test Liquid", 30.0, "mL")],
            blends,
            nutrient_amount_df,
            modular_table=modular_table,
        )
        assert powder.fluid_provided_mL == pytest.approx(0.0)
        assert liquid.fluid_provided_mL == pytest.approx(30.0)


class TestUndisclosedIsNotZero:
    def test_an_undisclosed_nutrient_is_absent_not_zero(
        self, blends, nutrient_amount_df, modular_table
    ):
        """The powder's panel discloses no calcium, so the day must not
        claim it received 0 mg of calcium from it.

        Modular panels disclose far less than a feed's -- a Canadian
        Nutrition Facts table carries no vitamins at all -- so this
        distinction does more work here than anywhere else in the app.
        """
        totals = aggregate_intake(
            [_row("Test Powder", 7.0, "g")],
            blends,
            nutrient_amount_df,
            modular_table=modular_table,
        )
        supplying, total = totals.nutrient_coverage["calcium_mg"]
        assert supplying == 0, "calcium was never disclosed; nothing may claim to supply it"
        assert total >= 1, "the row must still count toward 'we don't know', not vanish"

    def test_a_disclosed_nutrient_counts_as_supplying(
        self, blends, nutrient_amount_df, modular_table
    ):
        totals = aggregate_intake(
            [_row("Test Powder", 7.0, "g")],
            blends,
            nutrient_amount_df,
            modular_table=modular_table,
        )
        supplying, _ = totals.nutrient_coverage["sodium_mg"]
        assert supplying == 1


class TestUnknownModularIsSkippedNotCrashed:
    def test_a_row_naming_a_missing_modular_is_ignored(
        self, blends, nutrient_amount_df, modular_table
    ):
        """Same guard as the blend/formula/oral branches: a row whose
        product isn't in the table is skipped, not fed to a KeyError. A
        day file written against a newer pack must still open."""
        totals = aggregate_intake(
            [_row("No Such Modular", 10.0, "g")],
            blends,
            nutrient_amount_df,
            modular_table=modular_table,
        )
        assert totals.nutrient_totals.get("energy_kcal", 0.0) == pytest.approx(0.0)


class TestShippedTable:
    def test_every_shipped_row_declares_a_valid_basis(self):
        for name, m in MODULARS.items():
            assert m["basis"] in ("mL", "g"), f"{name} has basis {m['basis']!r}"

    def test_kcal_and_protein_are_mandatory_on_every_row(self):
        for name, m in MODULARS.items():
            assert isinstance(m["kcal_per_unit"], float), name
            assert isinstance(m["protein_per_unit"], float), name

    def test_nutrient_columns_mirror_the_formula_tables_set(self):
        """The two tables must not drift: modulars.csv carries the same
        nutrient set as formulas.csv, under `_per_unit` names."""
        for m in MODULARS.values():
            for col in _MODULAR_NUTRIENT_COLUMNS:
                assert col in m, col

    def test_a_bad_basis_is_refused_loudly(self):
        """A row that doesn't say millilitres or grams cannot be scaled,
        and guessing between them is exactly the silent unit error this
        table's column naming exists to prevent."""
        import pandas as pd

        from src.calculator import _modular_entry

        bad = pd.Series(
            {
                "name": "Broken",
                "brand": "b",
                "basis": "scoops",
                "kcal_per_unit": 1.0,
                "protein_per_unit": 0.1,
            }
        )
        with pytest.raises(ValueError, match="basis"):
            _modular_entry(bad)

    def test_a_missing_basis_is_refused_too(self):
        import pandas as pd

        from src.calculator import _modular_entry

        bad = pd.Series(
            {
                "name": "Broken",
                "brand": "b",
                "basis": None,
                "kcal_per_unit": 1.0,
                "protein_per_unit": 0.1,
            }
        )
        with pytest.raises(ValueError, match="basis"):
            _modular_entry(bad)


def test_loader_reads_the_real_pack():
    table = _load_modulars("canada")
    assert table, "the shipped pack must have modulars"
    assert all("basis" in m for m in table.values())
