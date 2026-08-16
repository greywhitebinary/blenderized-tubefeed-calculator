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

from src.measures import is_bare_gram_weight, load_measure_lookup

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
