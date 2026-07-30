"""
test_recipe_io.py — tests for saving a recipe to a spreadsheet and
reading one back (src/recipe_io.py).

Two jobs are being checked here, and they carry different risk:

1. ROUND-TRIP. Save a blend, load it back, get the same recipe. This is
   the "recipe record" case and it must be exact -- if a saved recipe
   reloads with different grams, every number downstream is wrong.

2. TYPED-RECIPE MATCHING. Someone types a recipe in Excel with food names
   but no CNF codes. The rule under test is that the module NEVER guesses:
   an ambiguous name comes back as ambiguous with candidates, an unknown
   name comes back as unmatched, and even a single clean match is flagged
   for a human to confirm. Silently picking a food would be the dangerous
   failure -- nothing errors, the RD just gets a plausible wrong number.

No CNF load here: a handful of hand-built food rows stands in for
Food_Name.csv, per the same rule as the rest of the suite.
"""

from datetime import date

import pandas as pd
import pytest

from src.recipe_io import (
    AMBIGUOUS,
    MATCH_BY_CODE,
    MATCH_BY_DESCRIPTION,
    RECIPE_FORMAT_VERSION,
    UNMATCHED,
    ParsedRecipe,
    RecipeFileError,
    recipe_to_workbook_bytes,
    resolve_ingredients,
    suggested_filename,
    workbook_bytes_to_recipe,
)


@pytest.fixture
def food_name_df():
    """A stand-in for CNF's Food_Name.csv, small enough to reason about.

    Deliberately contains three 'Chicken, broiler, breast...' rows,
    because that is exactly the real-world trap: a human typing "chicken
    breast" cannot be matched to one CNF food without being asked.
    """
    return pd.DataFrame(
        [
            {"Food_Code": 1704, "Food_Description_EN": "Banana, raw"},
            {"Food_Code": 2933, "Food_Description_EN": "Water, municipal"},
            {"Food_Code": 451, "Food_Description_EN": "Vegetable oil, canola"},
            {
                "Food_Code": 7321,
                "Food_Description_EN": "Chicken, broiler, breast, skinless, braised",
            },
            {
                "Food_Code": 842,
                "Food_Description_EN": "Chicken, broiler, breast, meat, roasted",
            },
            {
                "Food_Code": 843,
                "Food_Description_EN": "Chicken, broiler, breast, meat and skin, fried",
            },
        ]
    )


@pytest.fixture
def blend():
    """A small blend in the same shape the app keeps in session state."""
    return {
        "name": "Morning blend",
        "measured_volume_mL": 1000.0,
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
                "food_code": 2933,
                "food_description": "Water, municipal",
                "grams": 250.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Round-trip: the recipe record has to come back unchanged
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_saving_then_loading_returns_the_same_recipe(self, blend):
        """The core promise of the recipe record: save it, reopen it in
        three weeks, get identical numbers."""
        data = recipe_to_workbook_bytes(blend)
        parsed = workbook_bytes_to_recipe(data)

        assert parsed.name == "Morning blend"
        assert parsed.measured_volume_mL == 1000.0
        assert len(parsed.ingredients) == 2
        assert parsed.ingredients[0]["food_code"] == 1704
        assert parsed.ingredients[0]["grams"] == 100.0
        assert parsed.ingredients[0]["unit"] == "g"
        assert parsed.ingredients[0]["counts_as_fluid"] is False
        # The mL/fluid ingredient survives too -- both flags matter to the
        # fluid ledger, so losing either silently changes a patient's
        # recorded fluid intake.
        assert parsed.ingredients[1]["unit"] == "mL"
        assert parsed.ingredients[1]["counts_as_fluid"] is True
        assert parsed.row_warnings == []

    def test_flow_test_travels_with_the_recipe(self, blend):
        """The texture note is the whole point of the record -- 'this one
        flowed' is the knowledge that currently evaporates."""
        flow_test = {
            "date": date(2026, 7, 30),
            "result": "Passed",
            "notes": "flowed through a 60 mL syringe without resistance",
        }
        parsed = workbook_bytes_to_recipe(recipe_to_workbook_bytes(blend, flow_test))

        assert parsed.flow_test_date == date(2026, 7, 30)
        assert parsed.flow_test_result == "Passed"
        assert "60 mL syringe" in parsed.flow_test_notes

    def test_a_recipe_with_no_flow_test_still_saves(self, blend):
        """Flow testing is optional for an established recipe."""
        parsed = workbook_bytes_to_recipe(recipe_to_workbook_bytes(blend))
        assert parsed.flow_test_date is None
        assert parsed.flow_test_result == ""

    def test_format_version_is_written(self, blend):
        """Stamped into every file so a future reader knows what it has."""
        parsed = workbook_bytes_to_recipe(recipe_to_workbook_bytes(blend))
        assert parsed.format_version == RECIPE_FORMAT_VERSION

    def test_filename_is_safe_and_readable(self):
        """An RD's blend name can contain anything; a filename can't."""
        assert suggested_filename("Morning blend") == "btf-recipe_Morning-blend.xlsx"
        assert suggested_filename("J's blend 50/50") == "btf-recipe_J-s-blend-50-50.xlsx"
        assert suggested_filename("") == "btf-recipe_recipe.xlsx"


# ---------------------------------------------------------------------------
# Bad files: fail clearly, and never lose the whole upload over one row
# ---------------------------------------------------------------------------


class TestBadFiles:
    def test_a_non_spreadsheet_raises_a_readable_error(self):
        with pytest.raises(RecipeFileError) as exc:
            workbook_bytes_to_recipe(b"this is not a spreadsheet")
        assert "spreadsheet" in str(exc.value).lower()

    def test_a_workbook_without_an_ingredients_sheet_raises(self):
        buffer = pd.DataFrame([{"Recipe name": "x"}])
        data = _single_sheet_bytes(buffer, "Recipe")
        with pytest.raises(RecipeFileError) as exc:
            workbook_bytes_to_recipe(data)
        assert "Ingredients" in str(exc.value)

    def test_one_unusable_row_is_skipped_not_fatal(self, food_name_df):
        """A mistyped amount costs that line, not the whole recipe."""
        data = _ingredients_only_bytes(
            [
                {"Food description": "Banana, raw", "Amount": 100},
                {"Food description": "Water, municipal", "Amount": "oops"},
                {"Food description": "Vegetable oil, canola", "Amount": 14},
            ]
        )
        parsed = workbook_bytes_to_recipe(data)

        assert len(parsed.ingredients) == 2
        assert len(parsed.row_warnings) == 1
        # The warning names the row and the food, so an RD can find it.
        assert "Water, municipal" in parsed.row_warnings[0]

    def test_blank_rows_are_ignored_silently(self):
        """Excel files are full of trailing blank rows; they aren't errors."""
        data = _ingredients_only_bytes(
            [
                {"Food description": "Banana, raw", "Amount": 100},
                {"Food description": "", "Amount": None},
            ]
        )
        parsed = workbook_bytes_to_recipe(data)
        assert len(parsed.ingredients) == 1
        assert parsed.row_warnings == []


# ---------------------------------------------------------------------------
# Typed recipes: match, but never guess
# ---------------------------------------------------------------------------


class TestResolvingTypedRecipes:
    def test_a_food_code_is_taken_at_its_word(self, food_name_df):
        """A file the app wrote carries codes -- no guessing needed, and
        the description is refreshed from CNF rather than trusted."""
        parsed = ParsedRecipe(
            ingredients=[
                {
                    "food_code": 1704,
                    "food_description": "whatever the file said",
                    "grams": 100.0,
                    "unit": "g",
                    "counts_as_fluid": False,
                }
            ]
        )
        [row] = resolve_ingredients(parsed, food_name_df)

        assert row.status == MATCH_BY_CODE
        assert row.food_code == 1704
        assert row.food_description == "Banana, raw"
        assert row.needs_confirmation is False

    def test_an_ambiguous_description_is_never_guessed(self, food_name_df):
        """THE important one. 'chicken, broiler, breast' matches three CNF
        foods with different numbers. The module must hand back the
        options, not pick one."""
        parsed = ParsedRecipe(
            ingredients=[
                {
                    "food_code": None,
                    "food_description": "Chicken, broiler, breast",
                    "grams": 50.0,
                }
            ]
        )
        [row] = resolve_ingredients(parsed, food_name_df)

        assert row.status == AMBIGUOUS
        assert row.food_code is None  # nothing was chosen
        assert len(row.candidates) == 3
        assert row.needs_confirmation is True

    def test_a_single_description_match_still_asks_for_confirmation(self, food_name_df):
        """One match is not the same as the right match -- a typed recipe
        lands as a draft, per CONTEXT.md §11."""
        parsed = ParsedRecipe(
            ingredients=[{"food_code": None, "food_description": "Banana", "grams": 100.0}]
        )
        [row] = resolve_ingredients(parsed, food_name_df)

        assert row.status == MATCH_BY_DESCRIPTION
        assert row.food_code == 1704
        assert row.needs_confirmation is True

    def test_an_unknown_food_is_reported_not_dropped(self, food_name_df):
        """Silently dropping an ingredient would understate every nutrient
        in the blend -- it has to come back visible."""
        parsed = ParsedRecipe(
            ingredients=[{"food_code": None, "food_description": "Egusi seed", "grams": 30.0}]
        )
        [row] = resolve_ingredients(parsed, food_name_df)

        assert row.status == UNMATCHED
        assert row.food_code is None
        assert row.food_description == "Egusi seed"
        assert row.needs_confirmation is True

    def test_a_code_that_isnt_in_cnf_falls_back_to_the_description(self, food_name_df):
        """A typo'd code shouldn't resolve to nothing silently -- try the
        words instead, then ask."""
        parsed = ParsedRecipe(
            ingredients=[
                {
                    "food_code": 999999,
                    "food_description": "Chicken, broiler, breast",
                    "grams": 50.0,
                }
            ]
        )
        [row] = resolve_ingredients(parsed, food_name_df)

        assert row.status == AMBIGUOUS
        assert len(row.candidates) == 3

    def test_amounts_and_flags_survive_resolution(self, food_name_df):
        """Resolution is about identity only; it must not touch quantities."""
        parsed = ParsedRecipe(
            ingredients=[
                {
                    "food_code": 2933,
                    "food_description": "Water, municipal",
                    "grams": 250.0,
                    "unit": "mL",
                    "counts_as_fluid": True,
                }
            ]
        )
        [row] = resolve_ingredients(parsed, food_name_df)

        assert row.grams == 250.0
        assert row.unit == "mL"
        assert row.counts_as_fluid is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _single_sheet_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buffer.getvalue()


def _ingredients_only_bytes(rows: list[dict]) -> bytes:
    """A hand-built file with only an Ingredients sheet -- what someone
    typing a recipe from scratch in Excel would plausibly produce."""
    return _single_sheet_bytes(pd.DataFrame(rows), "Ingredients")
