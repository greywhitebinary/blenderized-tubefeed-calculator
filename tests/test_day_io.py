"""
test_day_io.py — tests for saving and reopening a whole day (src/day_io.py).

The round-trip tests are the obvious half. The half that matters more is
what happens when a day file is *incomplete*, because those are the cases
that produce a day which loads cleanly and is quietly wrong:

  - a custom food's values missing, leaving an ingredient pointing at a
    food code with no nutrients behind it;
  - an intake row referring to a blend the file doesn't contain, which
    would contribute nothing to the totals with no visible sign.

Both are skipped-with-a-warning rather than silently dropped. A day that
loads with a message an RD can read beats a day that loads looking
complete.
"""

from datetime import time as dtime

import pytest

from src.day_io import (
    DAY_FORMAT_VERSION,
    INTAKE_SHEET,
    LEGACY_RECORD_SHEET,
    RECORD_SHEET,
    DayFileError,
    ParsedDay,
    day_to_workbook_bytes,
    suggested_day_filename,
    workbook_bytes_to_day,
)
from src.recipe_io import recipe_to_workbook_bytes


@pytest.fixture
def blends():
    return {
        1: {
            "name": "Morning blend",
            "measured_volume_mL": 1000.0,
            "flow_test": {"date": None, "result": "Passed", "notes": "60 mL syringe"},
            "ingredients": [
                {
                    "id": 1,
                    "food_code": 1704,
                    "food_description": "Banana, raw",
                    "grams": 100.0,
                    "unit": "g",
                    "counts_as_fluid": False,
                },
                {
                    "id": 2,
                    "food_code": -1,
                    "food_description": "Protein shake (label)",
                    "grams": 200.0,
                    "unit": "mL",
                    "counts_as_fluid": True,
                },
            ],
        }
    }


@pytest.fixture
def intake_log():
    return [
        {
            "id": 1,
            "time": dtime(8, 0),
            "source_type": "blend",
            "source_id": 1,
            "food_description": None,
            "amount": 250.0,
            "unit": "mL",
            "counts_as_fluid": False,
        },
        {
            "id": 2,
            "time": dtime(10, 0),
            "source_type": "formula",
            "source_id": "Resource 2.0",
            "food_description": None,
            "amount": 237.0,
            "unit": "mL",
            "counts_as_fluid": False,
        },
        {
            "id": 3,
            "time": None,
            "source_type": "flush",
            "source_id": None,
            "food_description": None,
            "amount": 30.0,
            "unit": "mL",
            "counts_as_fluid": True,
        },
        {
            "id": 4,
            "time": dtime(8, 30),
            "source_type": "oral",
            "source_id": 1704,
            "food_description": "Banana, raw — 1 small",
            "amount": 101.0,
            "unit": "g",
            "counts_as_fluid": False,
        },
    ]


@pytest.fixture
def custom_foods():
    return {-1: {"energy_kcal": 250.0, "protein_g": 10.0, "sodium_mg": 120.0}}


def _save(blends, intake_log, custom_foods, **overrides):
    kwargs = {
        "label": "James W",
        "patient_weight": 62.5,
        "weight_unit": "kg",
        "targets": {"energy_kcal": 2000.0, "protein_g": 95.0},
        "blends": blends,
        "intake_log": intake_log,
        "custom_foods": custom_foods,
    }
    kwargs.update(overrides)
    return day_to_workbook_bytes(**kwargs)


class TestRoundTrip:
    def test_the_whole_day_comes_back(self, blends, intake_log, custom_foods):
        day = workbook_bytes_to_day(_save(blends, intake_log, custom_foods))

        assert day.label == "James W"
        assert day.patient_weight == 62.5
        assert day.weight_unit == "kg"
        assert day.format_version == DAY_FORMAT_VERSION
        assert len(day.blends) == 1
        assert len(day.intake_log) == 4
        assert day.warnings == []

    def test_every_source_type_survives(self, blends, intake_log, custom_foods):
        """A day is not just blends. Lose the flushes and the fluid total
        is wrong; lose the oral row and the day under-reports."""
        day = workbook_bytes_to_day(_save(blends, intake_log, custom_foods))
        assert sorted(r["source_type"] for r in day.intake_log) == [
            "blend",
            "flush",
            "formula",
            "oral",
        ]

    def test_source_ids_keep_their_types(self, blends, intake_log, custom_foods):
        """A formula is named, a blend and a food are numbered, a flush is
        neither. All three go through one spreadsheet column."""
        day = workbook_bytes_to_day(_save(blends, intake_log, custom_foods))
        by_type = {r["source_type"]: r["source_id"] for r in day.intake_log}
        assert by_type["formula"] == "Resource 2.0"
        assert by_type["blend"] == 1
        assert by_type["oral"] == 1704
        assert by_type["flush"] is None

    def test_times_survive_including_the_missing_one(self, blends, intake_log, custom_foods):
        day = workbook_bytes_to_day(_save(blends, intake_log, custom_foods))
        times = {r["source_type"]: r["time"] for r in day.intake_log}
        assert times["blend"] == dtime(8, 0)
        assert times["flush"] is None

    def test_custom_food_values_survive(self, blends, intake_log, custom_foods):
        """The one that would break the day silently.

        A label-entered food exists only in session state under a negative
        code. An ingredient references that code, so a file without these
        values reloads into a blend whose protein and sodium quietly
        vanish -- no error, just smaller numbers.
        """
        day = workbook_bytes_to_day(_save(blends, intake_log, custom_foods))
        assert day.custom_foods == {
            -1: {"energy_kcal": 250.0, "protein_g": 10.0, "sodium_mg": 120.0}
        }

        codes_used = {ing["food_code"] for b in day.blends.values() for ing in b["ingredients"]}
        assert -1 in codes_used
        assert all(code in day.custom_foods for code in codes_used if code < 0)

    def test_ingredients_stay_with_their_blend(self, blends, intake_log, custom_foods):
        day = workbook_bytes_to_day(_save(blends, intake_log, custom_foods))
        loaded = day.blends[1]
        assert [i["food_code"] for i in loaded["ingredients"]] == [1704, -1]
        assert loaded["ingredients"][1]["unit"] == "mL"
        assert loaded["ingredients"][1]["counts_as_fluid"] is True

    def test_flow_test_with_no_date_stays_none(self, blends, intake_log, custom_foods):
        """Not pandas NaT, which subclasses datetime and passes a naive
        isinstance check (the bug found in recipe_io the same week)."""
        day = workbook_bytes_to_day(_save(blends, intake_log, custom_foods))
        assert day.blends[1]["flow_test"]["date"] is None
        assert day.blends[1]["flow_test"]["result"] == "Passed"

    def test_targets_of_zero_are_not_written(self, blends, intake_log, custom_foods):
        """0 means "no target" in this app, since the number_input can't be
        blank. Writing zeros would turn "not set" into a deliberate 0."""
        day = workbook_bytes_to_day(
            _save(
                blends,
                intake_log,
                custom_foods,
                targets={"energy_kcal": 2000.0, "protein_g": 0.0, "fluid_mL": 0.0},
            )
        )
        assert day.targets == {"energy_kcal": 2000.0}

    def test_an_empty_day_is_still_a_valid_file(self):
        day = workbook_bytes_to_day(
            day_to_workbook_bytes(
                label="",
                patient_weight=0.0,
                weight_unit="kg",
                targets={},
                blends={},
                intake_log=[],
                custom_foods={},
            )
        )
        assert day.blends == {}
        assert day.intake_log == []
        assert day.warnings == []


class TestBadFiles:
    def test_a_recipe_file_is_refused_with_a_useful_message(self):
        """Easy mistake: two spreadsheets download from this app."""
        recipe = recipe_to_workbook_bytes(
            {"name": "Morning blend", "measured_volume_mL": 1000.0, "ingredients": []}
        )
        with pytest.raises(DayFileError) as excinfo:
            workbook_bytes_to_day(recipe)
        assert "Feed Recipes" in str(excinfo.value)

    def test_not_a_spreadsheet_at_all(self):
        with pytest.raises(DayFileError):
            workbook_bytes_to_day(b"this is not a spreadsheet")

    def test_intake_row_for_a_missing_blend_is_skipped_and_reported(
        self, blends, intake_log, custom_foods
    ):
        """Would otherwise contribute nothing to the totals, invisibly."""
        orphaned = intake_log + [
            {
                "id": 9,
                "time": dtime(12, 0),
                "source_type": "blend",
                "source_id": 99,
                "food_description": None,
                "amount": 300.0,
                "unit": "mL",
                "counts_as_fluid": False,
            }
        ]
        day = workbook_bytes_to_day(_save(blends, orphaned, custom_foods))
        assert len(day.intake_log) == 4
        assert any("99" in w for w in day.warnings), day.warnings

    def test_unknown_source_type_is_skipped_and_reported(self, blends, intake_log, custom_foods):
        bad = intake_log + [
            {
                "id": 9,
                "time": None,
                "source_type": "telepathy",
                "source_id": None,
                "food_description": None,
                "amount": 10.0,
                "unit": "mL",
                "counts_as_fluid": False,
            }
        ]
        day = workbook_bytes_to_day(_save(blends, bad, custom_foods))
        assert len(day.intake_log) == 4
        assert any("telepathy" in w for w in day.warnings), day.warnings

    def test_row_with_no_amount_is_skipped(self, blends, intake_log, custom_foods):
        zeroed = intake_log + [
            {
                "id": 9,
                "time": None,
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 0.0,
                "unit": "mL",
                "counts_as_fluid": True,
            }
        ]
        day = workbook_bytes_to_day(_save(blends, zeroed, custom_foods))
        assert len(day.intake_log) == 4


def test_summary_pluralises_custom_foods_like_its_siblings():
    """ParsedDay.summary is the one line an RD reads right before agreeing
    to REPLACE their day -- every count in it should read like normal
    English. "2 custom food" (no "s") was the only one of the four counts
    that didn't pluralise; the other three already did (2026-08-20 review).
    """
    two_custom = ParsedDay(
        blends={1: {}},
        intake_log=[{}],
        targets={"protein_g": 60.0},
        custom_foods={-1: {"energy_kcal": 100.0}, -2: {"energy_kcal": 200.0}},
    )
    assert two_custom.summary == "1 blend, 1 intake row, 1 target, 2 custom foods"

    one_custom = ParsedDay(custom_foods={-1: {"energy_kcal": 100.0}})
    assert one_custom.summary.endswith("1 custom food")


def test_filename_is_safe_and_readable():
    # "day" became "record" throughout the user-facing wording on
    # 2026-08-16, and the filename is user-facing: it is what an RD sees in
    # their downloads folder months later.
    assert suggested_day_filename("James W, H&N RT wk 5") == "btf-record_James-W-H-N-RT-wk-5.xlsx"
    assert suggested_day_filename("") == "btf-record_record.xlsx"


def test_a_file_from_before_the_sheet_rename_is_refused_not_silently_blanked():
    """Format version 3 renamed the "Day" sheet to "Record" and the reader
    does not accept the old name (author's call 2026-08-16: the app is new
    enough that few such files exist).

    What this pins is that the refusal is LOUD. The Record sheet is read
    with .get(), so without the guard an older file would open looking
    perfectly fine while its label, patient weight and weight unit came
    back empty -- a silent wrong answer in a clinical tool, which is worse
    than a file that plainly will not open.
    """
    import io

    import pandas as pd

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame([{"Field": "Day label", "Value": "James W"}]).to_excel(
            writer, sheet_name=LEGACY_RECORD_SHEET, index=False
        )
        pd.DataFrame([{"Time": "08:00", "Source type": "flush", "Amount": 100.0}]).to_excel(
            writer, sheet_name=INTAKE_SHEET, index=False
        )

    with pytest.raises(DayFileError) as exc:
        workbook_bytes_to_day(buf.getvalue())
    assert LEGACY_RECORD_SHEET in str(exc.value) and RECORD_SHEET in str(exc.value)
