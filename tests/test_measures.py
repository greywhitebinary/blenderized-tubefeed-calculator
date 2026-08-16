"""
test_measures.py — tests for src/measures.py.

Covers Change 1.5 (plan you-know-the-line-vectorized-milner.md): the rule
that filters bare gram-weight labels ("125 g", "90 g") out of the
household-measure list, since "g" is already offered separately and means
"type any weight" -- a bare-gram CNF measure is the same choice wearing a
different name, and having both in one dropdown was the confusing part of
the app's "the unit dropdown mixes unlike things" feedback.

is_bare_gram_weight() is tested standalone (no CNF data needed -- it's a
pure string rule). The integration test against the real, loaded
load_measure_lookup() is skipped when the raw CNF download isn't present,
matching test_food_search.py's convention for tests that need real data.
"""

from pathlib import Path

import pytest

from src.measures import is_bare_gram_weight, load_measure_lookup, scale_measure_label

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CNF_MEASURE_NAME = PROJECT_ROOT / "cnf_fcen_all-files-data_2026" / "Measure_Name.csv"


class TestIsBareGramWeight:
    def test_matches_plain_integer_gram_labels(self):
        """The exact shape CNF ships these in -- a number, a space, "g"."""
        assert is_bare_gram_weight("125 g")
        assert is_bare_gram_weight("90 g")
        assert is_bare_gram_weight("55 g")
        assert is_bare_gram_weight("2 g")

    def test_matches_decimal_gram_labels_with_no_space(self):
        """CNF also ships a few with a decimal and no space before "g"."""
        assert is_bare_gram_weight("0.5g")
        assert is_bare_gram_weight("0.6g")

    def test_does_not_match_a_genuine_kitchen_measure(self):
        """Real household measures -- a fraction, a size qualifier, a
        chopped/diced note -- keep at least one non-numeric, non-gram
        word, and must survive the filter."""
        assert not is_bare_gram_weight("1/2 foot")
        assert not is_bare_gram_weight("250 ml chopped or diced")
        assert not is_bare_gram_weight("1 medium (18cm to 20cm long)")
        assert not is_bare_gram_weight("1 cup")

    def test_does_not_match_the_verbose_yield_from_labels(self):
        """The four "yield from ... ear" labels are long (up to 44 chars)
        but genuine measures -- CNF tags them User-defined (Measure_Type
        6) same as any other household measure -- so they must NOT be
        caught by this filter even though they contain a gram-adjacent
        shape nowhere in them."""
        assert not is_bare_gram_weight("yield from 1 large ear (20cm to 23cm long)")
        assert not is_bare_gram_weight("yield from 1 medium ear (17cm to 19cm long)")

    def test_non_string_description_returns_false_not_a_crash(self):
        """A left-joined Measure_Code with no matching Measure_Name row
        comes through as NaN (a float), not a string -- must not raise."""
        assert not is_bare_gram_weight(None)
        assert not is_bare_gram_weight(float("nan"))

    def test_a_unit_other_than_g_is_not_matched(self):
        """Only the "g" unit is the confusing overlap with the plain "g"
        entry mode -- a bare "125 ml" (if CNF ever shipped one) is not
        the same overlap and is out of scope for this rule."""
        assert not is_bare_gram_weight("125 ml")


@pytest.mark.skipif(not CNF_MEASURE_NAME.exists(), reason="raw CNF download not present")
class TestLoadMeasureLookupFiltersRealData:
    def test_no_bare_gram_weight_survives_in_the_real_lookup(self):
        """Change 1.5's actual target: the real CNF Measure_Weight_
        Conversion / Measure_Name join, filtered to household measures
        (Measure_Type=6), must contain zero bare gram-weight labels."""
        lookup = load_measure_lookup()
        bare = lookup["Measure_Description_and_Unit_EN"].apply(is_bare_gram_weight)
        assert not bare.any(), (
            "bare gram-weight labels leaked through: "
            f"{lookup.loc[bare, 'Measure_Description_and_Unit_EN'].tolist()}"
        )

    def test_genuine_measures_are_not_collateral_damage(self):
        """The filter must not be so broad it empties the table -- CNF
        ships far more genuine kitchen measures than bare-gram ones."""
        lookup = load_measure_lookup()
        assert len(lookup) > 1000  # ~1184 real rows minus the 38 filtered


class TestScaleMeasureLabel:
    """scale_measure_label() folds a quantity INTO a CNF measure label so a
    recipe line reads "500 ml" rather than "2 x 250 ml" (author,
    2026-08-15). 98.5% of CNF's household-measure labels open with their
    own count, which is what makes this worth doing.
    """

    def test_quantity_of_one_returns_the_label_untouched(self):
        # CNF labels already carry their own count, so a "1 x" prefix
        # printed "1 1 medium ...".
        assert scale_measure_label("1 medium (18cm to 20cm long)", 1) == (
            "1 medium (18cm to 20cm long)"
        )

    def test_a_leading_volume_is_multiplied_out(self):
        assert scale_measure_label("250 ml", 2) == "500 ml"
        assert scale_measure_label("250 ml mashed", 1.5) == "375 ml mashed"

    def test_a_leading_count_of_one_becomes_the_quantity(self):
        assert scale_measure_label("1 extra large (23cm or longer)", 2) == (
            "2 extra large (23cm or longer)"
        )

    def test_fractional_leaders_are_multiplied_as_fractions(self):
        # 85 CNF labels open with a fraction ("1/2 egg", "1/6 package").
        assert scale_measure_label("1/2 egg", 2) == "1 egg"
        assert scale_measure_label("1/2 egg", 3) == "1.5 egg"

    def test_labels_containing_an_equals_are_never_scaled(self):
        """THE correctness case. "1/2 bagel = 1 food guide serving" doubled
        would read "1 bagel = 1 food guide serving" -- false, since one
        bagel is two servings. Four CNF labels contain "="; all must fall
        back to the multiplier form rather than restate a wrong equation.
        """
        assert scale_measure_label("1/2 bagel = 1 food guide serving", 2) == (
            "2 × 1/2 bagel = 1 food guide serving"
        )
        assert scale_measure_label("1 food guide serving = 75g", 3) == (
            "3 × 1 food guide serving = 75g"
        )

    def test_labels_without_a_leading_count_fall_back_to_the_multiplier(self):
        # 17 CNF labels, e.g. the "yield from ..." ones and ranges.
        assert scale_measure_label("yield from 1 large ear (20cm to 23cm long)", 2) == (
            "2 × yield from 1 large ear (20cm to 23cm long)"
        )
        assert scale_measure_label("8-14 seeds", 2) == "2 × 8-14 seeds"
        # No space after the number -- half-parsing "4.5oz" would be worse
        # than not parsing it.
        assert scale_measure_label("4.5oz cocktail", 2) == "2 × 4.5oz cocktail"

    def test_missing_label_does_not_raise(self):
        assert scale_measure_label(None, 2) == "2"
        assert scale_measure_label("", 2) == "2"
