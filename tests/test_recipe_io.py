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
    MATCH_CUSTOM,
    RECIPE_FORMAT_VERSION,
    UNMATCHED,
    ParsedRecipe,
    RecipeFileError,
    recipe_to_workbook_bytes,
    recipes_to_workbook_bytes,
    resolve_ingredients,
    suggested_filename,
    workbook_bytes_to_recipe,
    workbook_bytes_to_recipes,
)
from io import BytesIO

from src.recipe_io import CUSTOM_FOODS_SHEET, INGREDIENTS_SHEET, RECIPE_SHEET


def _write_v1_workbook(blend) -> bytes:
    """Build a format-v1 file: one recipe, no id/name link columns.

    Written by hand rather than by calling an old version of the writer,
    so the v1 layout stays pinned here even after the writer has moved
    on. This is what every recipe an RD saved before 2026-07-30 looks
    like, and those files have to keep opening.
    """
    recipe_df = pd.DataFrame(
        [
            {
                "Recipe name": blend["name"],
                "Measured final volume (mL)": blend["measured_volume_mL"],
                "Flow test date": "",
                "Flow test result": "",
                "Flow test notes": "",
                "Format version": 1,
            }
        ]
    )
    ingredients_df = pd.DataFrame(
        [
            {
                "CNF food code": i["food_code"],
                "Food description": i["food_description"],
                "Amount": i["grams"],
                "Unit": i["unit"],
                "Counts as fluid": "Yes" if i["counts_as_fluid"] else "No",
            }
            for i in blend["ingredients"]
        ]
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        recipe_df.to_excel(writer, sheet_name=RECIPE_SHEET, index=False)
        ingredients_df.to_excel(writer, sheet_name=INGREDIENTS_SHEET, index=False)
    return buffer.getvalue()


def _strip_link_columns(data: bytes) -> bytes:
    """Remove the columns tying ingredients to recipes.

    Simulates someone deleting them in Excel -- the case where guessing
    would merge two recipes together.
    """
    sheets = pd.read_excel(BytesIO(data), sheet_name=None, engine="openpyxl")
    sheets[INGREDIENTS_SHEET] = sheets[INGREDIENTS_SHEET].drop(
        columns=["Recipe id", "Recipe name"], errors="ignore"
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


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


# ---------------------------------------------------------------------------
# Multi-recipe files (format v2)
#
# The app holds several blends at once, so a file has to as well. The risk
# this class exists to pin is not "does it save" -- it is that two recipes
# in one file could be pooled into one blend, inventing a feed nobody
# wrote, with numbers that look entirely plausible. Same family of failure
# as the batch-extrapolation bug in FEED_LOG_REWORK.md 6.2.
# ---------------------------------------------------------------------------


class TestMultipleRecipes:
    @staticmethod
    def _blend(name, volume, foods):
        return {
            "name": name,
            "measured_volume_mL": volume,
            "ingredients": [
                {
                    "food_code": code,
                    "food_description": desc,
                    "grams": grams,
                    "unit": "g",
                    "counts_as_fluid": False,
                }
                for code, desc, grams in foods
            ],
        }

    def test_three_recipes_round_trip_separately(self):
        entries = [
            (self._blend("Morning blend", 1000.0, [(1704, "Banana, raw", 100.0)]), None),
            (
                self._blend(
                    "Evening blend",
                    800.0,
                    [(1463, "Rolled oats", 80.0), (451, "Canola oil", 14.0)],
                ),
                None,
            ),
            (self._blend("Weekend blend", 950.0, [(113, "Whole milk", 257.0)]), None),
        ]
        recipes = workbook_bytes_to_recipes(recipes_to_workbook_bytes(entries))

        assert [r.name for r in recipes] == [
            "Morning blend",
            "Evening blend",
            "Weekend blend",
        ]
        assert [len(r.ingredients) for r in recipes] == [1, 2, 1]
        assert [r.measured_volume_mL for r in recipes] == [1000.0, 800.0, 950.0]

    def test_two_blends_with_the_same_name_stay_separate(self):
        """Blend names are free text, so two can collide.

        The link is the numeric recipe id precisely for this: matching on
        name would merge these two into one six-ingredient blend that
        never existed.
        """
        entries = [
            (self._blend("Morning blend", 1000.0, [(1704, "Banana, raw", 100.0)]), None),
            (self._blend("Morning blend", 500.0, [(451, "Canola oil", 14.0)]), None),
        ]
        recipes = workbook_bytes_to_recipes(recipes_to_workbook_bytes(entries))

        assert len(recipes) == 2
        assert [r.measured_volume_mL for r in recipes] == [1000.0, 500.0]
        assert [len(r.ingredients) for r in recipes] == [1, 1]

    def test_each_recipe_keeps_its_own_flow_test(self):
        entries = [
            (
                self._blend("Passed one", 1000.0, [(1704, "Banana, raw", 100.0)]),
                {"date": date(2026, 7, 30), "result": "Passed", "notes": "60 mL syringe"},
            ),
            (
                self._blend("Failed one", 800.0, [(451, "Canola oil", 14.0)]),
                {"date": None, "result": "Too thick", "notes": "clogged"},
            ),
        ]
        recipes = workbook_bytes_to_recipes(recipes_to_workbook_bytes(entries))

        assert recipes[0].flow_test_result == "Passed"
        assert recipes[0].flow_test_date == date(2026, 7, 30)
        assert recipes[1].flow_test_result == "Too thick"
        assert recipes[1].flow_test_date is None

    def test_a_v1_single_recipe_file_still_loads(self, blend):
        """Files RDs have already saved must not be orphaned.

        A v1 file has one recipe row and untagged ingredients. That is
        unambiguous, so every ingredient belongs to the one recipe -- no
        guessing involved.
        """
        v1 = _write_v1_workbook(blend)
        recipes = workbook_bytes_to_recipes(v1)

        assert len(recipes) == 1
        assert recipes[0].name == "Morning blend"
        assert len(recipes[0].ingredients) == 2
        assert recipes[0].format_version == 1

    def test_multi_recipe_file_with_no_link_column_is_REFUSED(self):
        """The important one.

        Several recipes and no column saying which ingredient belongs to
        which is not recoverable by guessing. Loading them pooled would
        produce a blend nobody wrote whose kcal/mL looks perfectly
        reasonable, so the module refuses and says what is missing.
        """
        entries = [
            (self._blend("Morning blend", 1000.0, [(1704, "Banana, raw", 100.0)]), None),
            (self._blend("Evening blend", 800.0, [(451, "Canola oil", 14.0)]), None),
        ]
        stripped = _strip_link_columns(recipes_to_workbook_bytes(entries))

        with pytest.raises(RecipeFileError) as excinfo:
            workbook_bytes_to_recipes(stripped)
        assert "which recipe" in str(excinfo.value).lower()

    def test_single_recipe_helper_refuses_a_multi_recipe_file(self):
        """Rather than silently returning the first and losing the rest."""
        entries = [
            (self._blend("A", 1000.0, [(1704, "Banana, raw", 100.0)]), None),
            (self._blend("B", 800.0, [(451, "Canola oil", 14.0)]), None),
        ]
        with pytest.raises(RecipeFileError):
            workbook_bytes_to_recipe(recipes_to_workbook_bytes(entries))

    def test_filename_says_when_a_file_holds_several(self):
        assert suggested_filename("Morning blend") == "btf-recipe_Morning-blend.xlsx"
        assert suggested_filename("3 blends", count=3) == "btf-recipes_3-blends.xlsx"


# ---------------------------------------------------------------------------
# Custom foods (format v3): a food typed in from a Nutrition Facts label
# (app/add_food.py) lives only in session state under a negative code. The
# Custom foods sheet is what stops that data from being silently dropped
# when the recipe reloads -- before this, resolve_ingredients() couldn't
# find the code in CNF, couldn't match the description either, and the
# ingredient came back UNMATCHED and quietly vanished from the blend.
# ---------------------------------------------------------------------------


def _strip_custom_foods_sheet(data: bytes) -> bytes:
    """Simulate a v2 file: written before the Custom foods sheet existed."""
    sheets = pd.read_excel(BytesIO(data), sheet_name=None, engine="openpyxl")
    sheets.pop(CUSTOM_FOODS_SHEET, None)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


class TestCustomFoods:
    @staticmethod
    def _blend_with_custom(name, volume, cnf_foods, custom_ingredients):
        """A blend mixing ordinary CNF ingredients with label-entered ones.

        `cnf_foods` is (code, description, grams) triples; `custom_ingredients`
        is (code, description, grams, unit) quads -- custom foods can be
        entered on an mL basis, which CNF ingredients in this helper never are.
        """
        ingredients = [
            {
                "food_code": code,
                "food_description": desc,
                "grams": grams,
                "unit": "g",
                "counts_as_fluid": False,
            }
            for code, desc, grams in cnf_foods
        ] + [
            {
                "food_code": code,
                "food_description": desc,
                "grams": grams,
                "unit": unit,
                "counts_as_fluid": False,
            }
            for code, desc, grams, unit in custom_ingredients
        ]
        return {"name": name, "measured_volume_mL": volume, "ingredients": ingredients}

    def test_a_custom_food_round_trips_and_resolves_as_match_custom(self, food_name_df):
        """THE bug this sheet exists to fix: a label-entered food used to
        vanish from the reloaded blend, with nothing telling the RD why."""
        blend = self._blend_with_custom(
            "Morning blend",
            1000.0,
            [(1704, "Banana, raw", 100.0)],
            [(-1, "Homemade formula (custom)", 250.0, "mL")],
        )
        session_custom_foods = {-1: {"energy_kcal": 150.0, "protein_g": 5.0}}

        data = recipe_to_workbook_bytes(blend, custom_foods=session_custom_foods)
        parsed = workbook_bytes_to_recipe(data)

        assert parsed.custom_foods == session_custom_foods

        resolved = resolve_ingredients(parsed, food_name_df)
        by_code = {r.food_code: r for r in resolved}
        assert by_code[1704].status == MATCH_BY_CODE

        custom_row = by_code[-1]
        assert custom_row.status == MATCH_CUSTOM
        assert custom_row.food_description == "Homemade formula (custom)"
        assert custom_row.custom_nutrients == {"energy_kcal": 150.0, "protein_g": 5.0}
        # An exact match straight from the file's own data -- nothing for
        # a human to confirm, unlike a description guess.
        assert custom_row.needs_confirmation is False

    def test_only_the_custom_foods_actually_used_are_written(self):
        """The session dict can hold custom foods from OTHER blends
        entirely; a saved file should not carry foods that aren't in it."""
        session_custom_foods = {
            -1: {"energy_kcal": 100.0},
            -2: {"energy_kcal": 200.0},
            -3: {"energy_kcal": 300.0},
        }
        blend = self._blend_with_custom(
            "Morning blend", 1000.0, [], [(-1, "Only this one (custom)", 100.0, "g")]
        )

        data = recipe_to_workbook_bytes(blend, custom_foods=session_custom_foods)
        parsed = workbook_bytes_to_recipe(data)

        assert parsed.custom_foods == {-1: {"energy_kcal": 100.0}}

    def test_a_v2_file_with_no_custom_foods_sheet_still_loads(self, blend):
        """Files RDs already saved must not be orphaned by this change --
        they simply carry no custom foods, exactly as before."""
        v2 = _strip_custom_foods_sheet(recipe_to_workbook_bytes(blend))
        parsed = workbook_bytes_to_recipe(v2)

        assert parsed.custom_foods == {}
        assert len(parsed.ingredients) == 2  # the ordinary CNF ingredients still load

    def test_two_blends_sharing_one_custom_food_share_it_in_the_file_too(self):
        """Multi-recipe files have ONE Custom foods sheet -- codes are
        file-scoped, not recipe-scoped, so both recipes read back the same
        values for the same code."""
        session_custom_foods = {-1: {"energy_kcal": 175.0, "sodium_mg": 80.0}}
        entries = [
            (
                self._blend_with_custom(
                    "Morning blend",
                    1000.0,
                    [],
                    [(-1, "Shared custom food (custom)", 200.0, "g")],
                ),
                None,
            ),
            (
                self._blend_with_custom(
                    "Evening blend",
                    800.0,
                    [],
                    [(-1, "Shared custom food (custom)", 150.0, "g")],
                ),
                None,
            ),
        ]

        data = recipes_to_workbook_bytes(entries, custom_foods=session_custom_foods)
        recipes = workbook_bytes_to_recipes(data)

        assert len(recipes) == 2
        assert recipes[0].custom_foods == session_custom_foods
        assert recipes[1].custom_foods == session_custom_foods
