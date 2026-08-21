"""
test_recipe_io.py — tests for saving a recipe to a spreadsheet and
reading one back (src/recipe_io.py).

Two jobs are being checked here, and they carry different risk:

1. ROUND-TRIP. Save a blend, load it back, get the same recipe. This is
   the "recipe record" case and it must be exact -- if a saved recipe
   reloads with different grams, every number downstream is wrong.

2. TYPED-RECIPE MATCHING. Someone types a recipe in Excel with food names
   but no CNF codes. The rule under test is that the module NEVER
   COMMITS a food without a human looking at it: a description that
   finds candidates comes back with the best one preselected but still
   flagged for confirmation, an unknown name comes back as unmatched,
   and nothing is written to a blend until the RD presses Add. Silently
   picking a food would be the dangerous failure -- nothing errors, the
   RD just gets a plausible wrong number.

Most of this file uses a handful of hand-built food rows standing in for
Food_Name.csv, per the same rule as the rest of the suite -- a test you
can verify by eye beats a test that trusts whatever CNF happens to say.
One class, TestResolvingAgainstRealCNF, is the exception: it loads the
REAL CNF, because it exists to pin the actual regression that motivated
routing resolve_ingredients() through src/food_search.py (2026-08-20)
rather than a literal substring match. It's skipped when the raw CNF
download isn't present, same as tests/test_food_search.py's real-data
guards.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.data_loader import load_food_name

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

    def test_multiple_matches_come_back_ranked_not_committed(self, food_name_df):
        """THE important one. 'chicken, broiler, breast' matches three CNF
        foods with different numbers. The module hands back all three,
        ranked, with the first preselected as a PROPOSAL -- but nothing
        is chosen for the RD, and the row still needs their confirmation
        before it can be used (Change, 2026-08-20: search_foods() replaced
        the old str.contains() match, which is why this is no longer
        AMBIGUOUS -- the search reached these candidates directly, off the
        RD's own words, not via a synonym or a typo guess)."""
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

        assert row.status == MATCH_BY_DESCRIPTION
        assert len(row.candidates) == 3
        # The preselection is candidates[0], not a silent commitment --
        # it's exactly what the confirmation UI shows already selected.
        assert row.food_code == row.candidates[0][0]
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

        assert row.status == MATCH_BY_DESCRIPTION
        assert len(row.candidates) == 3
        assert row.needs_confirmation is True

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

    def test_a_file_the_app_wrote_resolves_entirely_by_code(self, food_name_df):
        """Every row in a file this app wrote carries a food code, so none
        of them should ever reach the search-by-name path -- checked here
        by asking that nothing needs a human's eyes."""
        parsed = ParsedRecipe(
            ingredients=[
                {
                    "food_code": 1704,
                    "food_description": "whatever the file said",
                    "grams": 100.0,
                    "unit": "g",
                    "counts_as_fluid": False,
                },
                {
                    "food_code": 2933,
                    "food_description": "whatever the file said",
                    "grams": 250.0,
                    "unit": "mL",
                    "counts_as_fluid": True,
                },
            ]
        )
        resolved = resolve_ingredients(parsed, food_name_df)

        assert [r.status for r in resolved] == [MATCH_BY_CODE, MATCH_BY_CODE]
        assert all(r.needs_confirmation is False for r in resolved)

    def test_a_nonsense_word_stays_unmatched(self, food_name_df):
        """A search that finds nothing has to say so, not invent a food."""
        parsed = ParsedRecipe(
            ingredients=[
                {"food_code": None, "food_description": "zzqqxxnonsenseword", "grams": 10.0}
            ]
        )
        [row] = resolve_ingredients(parsed, food_name_df)

        assert row.status == UNMATCHED
        assert row.food_code is None
        assert row.candidates == []


CNF_FOOD_NAME = (
    Path(__file__).resolve().parent.parent / "cnf_fcen_all-files-data_2026" / "Food_Name.csv"
)


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
class TestResolvingAgainstRealCNF:
    """The fixture-based tests above prove the mechanics; these pin the
    actual regression that motivated this change (2026-08-20). Before it,
    resolve_ingredients() matched descriptions with `str.contains()`, and
    a straight substring match answered "wild rice" and "greek yogurt"
    with NOTHING, because CNF files them as "Grains, rice, wild, dry" and
    "Yogourt (yogurt), Greek style" -- an RD who typed either into a
    recipe file would have seen the row come back unmatched and trusted
    it. Skipped without the raw CNF download, like
    tests/test_food_search.py's own real-data guards.
    """

    def test_wild_rice_and_greek_yogurt_are_found(self):
        """THE regression. Both used to come back UNMATCHED; search_foods()
        finds 3 and 9 real CNF foods for them respectively."""
        fn_df = load_food_name()
        parsed = ParsedRecipe(
            ingredients=[
                {"food_code": None, "food_description": "wild rice", "grams": 100.0},
                {"food_code": None, "food_description": "greek yogurt", "grams": 100.0},
            ]
        )
        wild_rice, greek_yogurt = resolve_ingredients(parsed, fn_df)

        assert wild_rice.status == MATCH_BY_DESCRIPTION, wild_rice.status
        assert len(wild_rice.candidates) == 3, wild_rice.candidates
        assert "rice" in wild_rice.food_description.lower()

        assert greek_yogurt.status == MATCH_BY_DESCRIPTION, greek_yogurt.status
        assert len(greek_yogurt.candidates) == 9, greek_yogurt.candidates
        assert "yogourt" in greek_yogurt.food_description.lower()

    def test_candidates_are_ranked_and_capped_at_fifty(self):
        """ "chicken" alone matches 344 real CNF foods. The dropdown a
        human has to read caps at search_foods()'s own 50-row default,
        and the row's preselected food_code is the top-ranked candidate,
        not an arbitrary one."""
        fn_df = load_food_name()
        parsed = ParsedRecipe(
            ingredients=[{"food_code": None, "food_description": "chicken", "grams": 50.0}]
        )
        [row] = resolve_ingredients(parsed, fn_df)

        assert len(row.candidates) == 50
        assert row.food_code == row.candidates[0][0]
        assert row.food_description == row.candidates[0][1]

    def test_a_synonym_match_reports_what_it_actually_searched(self):
        """ "courgette" isn't a CNF word -- CNF calls it zucchini, and the
        search only gets there via the curated synonym table. The row has
        to say so: the RD typed one word and is about to be shown a
        different one, and that substitution must never be silent."""
        fn_df = load_food_name()
        parsed = ParsedRecipe(
            ingredients=[{"food_code": None, "food_description": "courgette", "grams": 50.0}]
        )
        [row] = resolve_ingredients(parsed, fn_df)

        assert row.status == AMBIGUOUS
        assert row.interpreted_as == "zucchini"
        assert row.needs_confirmation is True


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

    def test_filename_collapses_runs_of_dashes(self):
        """day_io.py's suggested_day_filename() already solves this; this
        pins recipe_io's copy to the same behaviour (2026-08-20 review).

        A realistic blend name full of punctuation used to keep every
        dash it generated ("James-W--H-N"), and a punctuation-only name
        used to produce a filename of literal dashes instead of falling
        back to the "recipe" placeholder.
        """
        assert suggested_filename("James W, H&N RT wk 5") == "btf-recipe_James-W-H-N-RT-wk-5.xlsx"
        assert suggested_filename("---") == "btf-recipe_recipe.xlsx"

    def test_duplicate_recipe_name_in_a_name_linked_file_is_REFUSED(self):
        """THE important one for name-based linking.

        Two recipes named "Morning" (500 mL and 900 mL) in a file with no
        usable 'Recipe id' column used to load as ONE recipe -- 900 mL,
        both ingredient lists pooled, no warning at all. That is
        indistinguishable from the pooling this module already refuses
        for a missing link column entirely, so it must refuse here too.
        """
        buffer = BytesIO()
        recipe_df = pd.DataFrame(
            [
                {
                    "Recipe name": "Morning",
                    "Measured final volume (mL)": 500.0,
                    "Format version": 2,
                },
                {
                    "Recipe name": "Morning",
                    "Measured final volume (mL)": 900.0,
                    "Format version": 2,
                },
            ]
        )
        ingredients_df = pd.DataFrame(
            [
                {
                    "Recipe name": "Morning",
                    "Food description": "Banana, raw",
                    "CNF food code": 1704,
                    "Amount": 100.0,
                    "Unit": "g",
                }
            ]
        )
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            recipe_df.to_excel(writer, sheet_name=RECIPE_SHEET, index=False)
            ingredients_df.to_excel(writer, sheet_name=INGREDIENTS_SHEET, index=False)

        with pytest.raises(RecipeFileError) as excinfo:
            workbook_bytes_to_recipes(buffer.getvalue())
        message = str(excinfo.value).lower()
        assert "morning" in message
        assert "recipe id" in message

    def test_a_blank_link_cell_is_skipped_not_pooled_into_the_first_recipe(self):
        """THE important one for the blank-cell case.

        An ingredient row with a blank link cell used to fall back to key
        "1" and silently join the FIRST recipe in the file. Verified
        against the reported repro: peanut oil moved from blend B into
        blend A with no warning. It must now be skipped, with a warning
        naming the food, and leave both real recipes untouched.
        """
        entries = [
            (
                TestMultipleRecipes._blend("Blend A", 500.0, [(1704, "Banana, raw", 100.0)]),
                None,
            ),
            (
                TestMultipleRecipes._blend("Blend B", 500.0, [(2933, "Water, municipal", 100.0)]),
                None,
            ),
        ]
        sheets = pd.read_excel(
            BytesIO(recipes_to_workbook_bytes(entries)), sheet_name=None, engine="openpyxl"
        )
        ingredients_df = sheets[INGREDIENTS_SHEET]
        peanut_oil_row = pd.DataFrame(
            [
                {
                    "Recipe id": None,
                    "Recipe name": "",
                    "CNF food code": 451,
                    "Food description": "Peanut oil",
                    "Amount": 14.0,
                    "Unit": "g",
                    "Counts as fluid": "No",
                }
            ]
        )
        sheets[INGREDIENTS_SHEET] = pd.concat([ingredients_df, peanut_oil_row], ignore_index=True)
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=name, index=False)

        recipes = workbook_bytes_to_recipes(buffer.getvalue())

        assert [len(r.ingredients) for r in recipes] == [1, 1]
        assert [i["food_description"] for r in recipes for i in r.ingredients] == [
            "Banana, raw",
            "Water, municipal",
        ]
        all_warnings = recipes[0].row_warnings + recipes[1].row_warnings
        assert any("Peanut oil" in w and "isn't attached to any recipe" in w for w in all_warnings)

    def test_two_recipes_sharing_one_id_is_REFUSED(self):
        """The id case, which the first pass of this guard missed.

        The duplicate check covered names only, so two recipe rows sharing
        a "Recipe id" still merged in silence -- and ids are the format
        this app writes itself, not an exotic hand-built one. Verified
        before the fix: two id-1 recipes loaded as ONE 900 mL blend named
        "Evening", holding both ingredient lists (2026-08-20 second
        review).
        """
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(
                [
                    {"Recipe id": 1, "Recipe name": "Morning", "Measured final volume (mL)": 500.0},
                    {"Recipe id": 1, "Recipe name": "Evening", "Measured final volume (mL)": 900.0},
                ]
            ).to_excel(writer, sheet_name="Recipe", index=False)
            pd.DataFrame(
                [
                    {
                        "Recipe id": 1,
                        "Recipe name": "Morning",
                        "Food description": "Banana, raw",
                        "Amount": 100.0,
                    }
                ]
            ).to_excel(writer, sheet_name="Ingredients", index=False)

        with pytest.raises(RecipeFileError, match="more than one recipe the id 1"):
            workbook_bytes_to_recipes(buffer.getvalue())

    def test_an_ingredients_only_workbook_still_loads_as_one_recipe(self):
        """Guards the blank-link-cell fix against its own first attempt.

        That fix skipped any unlinked ingredient row when `single_key` was
        None -- but `single_key` is None for a workbook with NO Recipe
        sheet at all, where there is exactly one implicit recipe and
        nothing to be ambiguous about. Result: a file that had always
        loaded came back with every row skipped. An unlinked row is only
        ambiguous when there is more than one recipe for it to belong to
        (2026-08-20 second review).
        """
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(
                [
                    {"Recipe name": None, "Food description": "Banana, raw", "Amount": 100.0},
                    {"Recipe name": None, "Food description": "Water, municipal", "Amount": 200.0},
                ]
            ).to_excel(writer, sheet_name="Ingredients", index=False)

        [parsed] = workbook_bytes_to_recipes(buffer.getvalue())

        assert len(parsed.ingredients) == 2
        assert parsed.row_warnings == []

    def test_a_blank_recipe_id_in_a_multi_recipe_file_is_REFUSED(self):
        """THE important one for the blank-id case.

        A blank 'Recipe id' in a multi-recipe file used to fall back to a
        positional key of "1", which collides with a real id of 1 --
        _slot() then silently overwrote one recipe with the other's data,
        and one of the two disappeared from the loaded file entirely.
        """
        buffer = BytesIO()
        recipe_df = pd.DataFrame(
            [
                {
                    "Recipe id": 1,
                    "Recipe name": "Blend A",
                    "Measured final volume (mL)": 500.0,
                    "Format version": 2,
                },
                {
                    "Recipe id": None,
                    "Recipe name": "Blend B",
                    "Measured final volume (mL)": 900.0,
                    "Format version": 2,
                },
            ]
        )
        ingredients_df = pd.DataFrame(
            [
                {
                    "Recipe id": 1,
                    "Recipe name": "Blend A",
                    "Food description": "Banana, raw",
                    "CNF food code": 1704,
                    "Amount": 100.0,
                    "Unit": "g",
                }
            ]
        )
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            recipe_df.to_excel(writer, sheet_name=RECIPE_SHEET, index=False)
            ingredients_df.to_excel(writer, sheet_name=INGREDIENTS_SHEET, index=False)

        with pytest.raises(RecipeFileError) as excinfo:
            workbook_bytes_to_recipes(buffer.getvalue())
        message = str(excinfo.value).lower()
        assert "blend b" in message
        assert "recipe id" in message


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
