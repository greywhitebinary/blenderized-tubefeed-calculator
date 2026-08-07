"""
test_food_search.py — tests for the three-layer CNF food search
(src/food_search.py).

Most of this file uses a small hand-built stand-in for Food_Name.csv,
per the same rule as the rest of the suite (see conftest.py): a test you
can verify by eye beats a test that trusts whatever CNF happens to say.

Two classes of test here are different, though, and worth understanding
before changing anything:

1. THE ANTI-NONSENSE TESTS. Layer 2 (typo tolerance) is the part of this
   module that can hurt someone. A search that finds nothing is a small
   annoyance -- the RD uses the custom-food form. A search that
   confidently returns the WRONG food is a wrong number in a patient's
   daily total, and it is invisible, because the RD sees a plausible
   result and no warning. During development, at a looser threshold,
   this module really did answer "skyr" with a Skor chocolate bar and
   "maize" with a Marie biscuit. The tests below pin the tuning that
   stopped that.

2. THE SYNONYM GUARD (test_every_synonym_resolves). This one loads the
   REAL CNF and the REAL synonym table on purpose. A synonym table is
   data that rots silently: someone edits a row, the term stops
   resolving, and nothing anywhere fails -- the search just quietly gets
   worse. Two rows in the shipped table were already wrong when written
   and this guard is what caught them ("peppers sweet" doesn't match
   CNF's singular "Pepper, sweet"). It is skipped if the raw CNF
   download isn't present, so a fresh clone without the data can still
   run the suite.
"""

from pathlib import Path

import pandas as pd
import pytest

from src.food_search import (
    MATCH_DIRECT,
    MATCH_FUZZY,
    MATCH_NONE,
    MATCH_SYNONYM,
    build_index,
    load_synonyms,
    search_foods,
    tokenize,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CNF_FOOD_NAME = PROJECT_ROOT / "cnf_fcen_all-files-data_2026" / "Food_Name.csv"


@pytest.fixture
def food_name_df() -> pd.DataFrame:
    """A stand-in for CNF's Food_Name.csv.

    Descriptions are written in CNF's real style -- inverted and
    comma-prefixed ("Grains, rice, wild, dry", not "wild rice") -- because
    that inversion is the entire reason this module exists. A fixture
    with friendly names would test nothing.
    """
    rows = [
        (1, "Grains, rice, wild, dry", "", 20),
        (2, "Grains, rice, white, long grain, cooked", "", 20),
        (3, "Yogourt (yogurt), Greek style, 2% M.F., plain", "yoghurt", 1),
        (4, "Broccoli, raw", "", 11),
        (5, "Beef, ground, lean, raw", "hamburger, mince", 13),
        (6, "Zucchini, raw", "", 11),
        (7, "Potatoes, mashed, prepared", "mash, mashed", 11),
        (8, "Milk, fluid, 2% M.F.", "", 1),
        (9, "Chickpeas (garbanzo beans), mature seeds, cooked", "", 16),
        (10, "Bagel, egg", "", 18),
        (11, "Egg, chicken, whole, cooked, poached", "", 3),
        (12, "Eggplant, raw", "", 11),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Food_Code",
            "Food_Description_EN",
            "Alternate_Description_EN",
            "CNF_Food_Group_Code",
        ],
    )


@pytest.fixture
def index(food_name_df):
    return build_index(food_name_df)


def _descriptions(result) -> list[str]:
    return result.matches["Food_Description_EN"].tolist()


# ---------------------------------------------------------------------------
# tokenize()
# ---------------------------------------------------------------------------


def test_tokenize_splits_on_cnf_punctuation():
    assert tokenize("Grains, rice, wild, dry") == ["grains", "rice", "wild", "dry"]


def test_tokenize_keeps_percentages():
    # "2%" is a real and meaningful token in CNF ("Milk, fluid, 2% M.F.").
    assert "2%" in tokenize("Milk, fluid, 2% M.F.")


def test_tokenize_drops_stopwords():
    assert tokenize("cream of mushroom") == ["cream", "mushroom"]


def test_tokenize_keeps_stopwords_when_nothing_else_survives():
    # Searching the literal word "and" should do something, not match
    # every food in the database via an empty token list.
    assert tokenize("and") == ["and"]


# ---------------------------------------------------------------------------
# Layer 1 -- all words, any order
# ---------------------------------------------------------------------------


def test_wild_rice_is_found_despite_cnf_word_order(index):
    """The bug this whole module exists to fix.

    A literal substring search for "wild rice" returns nothing, because
    CNF files it as "Grains, rice, wild, dry". That false negative is
    what produced the (wrong) conclusion that CNF was missing ~1,600
    foods -- see CONTEXT.md S9, 2026-07-30.
    """
    result = search_foods("wild rice", index)
    assert result.match_type == MATCH_DIRECT
    assert "Grains, rice, wild, dry" in _descriptions(result)


def test_word_order_does_not_matter(index):
    assert _descriptions(search_foods("rice wild", index)) == _descriptions(
        search_foods("wild rice", index)
    )


def test_partial_words_match_as_prefixes(index):
    # Search-as-you-type: results appear before the word is finished.
    assert "Chickpeas (garbanzo beans), mature seeds, cooked" in _descriptions(
        search_foods("chickp", index)
    )


def test_alternate_descriptions_are_searched(index):
    """CNF's Alternate_Description_EN carries the lay words RDs type.

    "hamburger" appears nowhere in the description "Beef, ground, lean,
    raw" -- only in the alternate-names column, which the old substring
    search never looked at.
    """
    result = search_foods("hamburger", index)
    assert result.match_type == MATCH_DIRECT
    assert "Beef, ground, lean, raw" in _descriptions(result)


def test_description_matches_rank_above_alternate_only_matches(index):
    """An RD recognises the CNF description, so those come first."""
    result = search_foods("mashed", index)
    assert _descriptions(result)[0] == "Potatoes, mashed, prepared"


def test_all_query_words_must_match(index):
    # "rice" matches; "helicopter" does not; so the row does not match.
    assert search_foods("wild rice helicopter", index).match_type == MATCH_NONE


def test_query_below_minimum_length_returns_nothing(index):
    result = search_foods("r", index)
    assert result.match_type == MATCH_NONE
    assert result.is_empty


def test_limit_is_respected(index):
    assert len(search_foods("grains", index, limit=1)) == 1


def test_headword_match_ranks_above_contains_match(index):
    """The complaint that added the third sort tier (2026-08-07).

    "egg" used to rank "Bagel, egg" above actual eggs, and "milk"
    ranked "Cracker, milk" above fluid milk, because once the desc/alt
    and whole-word tiers tied, description length was the only
    tiebreaker. CNF files foods headword-first, so a query word that
    prefixes the description's FIRST word means this food IS the thing
    typed; a word deeper in the description is an ingredient of it.
    """
    descriptions = _descriptions(search_foods("egg", index))
    assert descriptions.index("Egg, chicken, whole, cooked, poached") < descriptions.index(
        "Bagel, egg"
    )


def test_headword_tier_does_not_beat_whole_word_tier(index):
    """A prefix-only headword must not outrank a real whole-word match.

    For "egg", "Eggplant, raw" matches only because "eggplant" starts
    with "egg"; "Bagel, egg" contains the actual word. The headword
    tier sits BELOW the whole-word tier precisely so the bagel stays
    the better answer to "egg".
    """
    descriptions = _descriptions(search_foods("egg", index))
    assert descriptions.index("Bagel, egg") < descriptions.index("Eggplant, raw")


# ---------------------------------------------------------------------------
# Layer 2 -- typo tolerance
# ---------------------------------------------------------------------------


def test_misspelling_is_corrected(index):
    result = search_foods("brocolli", index)
    assert result.match_type == MATCH_FUZZY
    assert "Broccoli, raw" in _descriptions(result)


def test_fuzzy_result_says_what_it_did(index):
    """The RD must be able to see that a substitution happened.

    This is the whole safety story for layer 2: the correction is
    allowed to be wrong precisely because it is never silent.
    """
    result = search_foods("brocolli", index)
    assert result.interpreted_as == "broccoli"
    assert "broccoli" in result.note
    assert result.note


def test_only_the_misspelled_word_is_replaced(index):
    """A single wrong word must not discard the words the RD got right."""
    result = search_foods("wilde rice", index)
    assert result.match_type == MATCH_FUZZY
    assert "Grains, rice, wild, dry" in _descriptions(result)


def test_exact_match_is_never_downgraded_to_fuzzy(index):
    """Layers stop at the first that finds anything."""
    assert search_foods("broccoli", index).match_type == MATCH_DIRECT


@pytest.mark.parametrize("query", ["skyr", "paneer", "mangetout"])
def test_words_cnf_lacks_return_nothing_rather_than_nonsense(index, query):
    """The most important test in this file.

    At a looser fuzzy threshold this module answered "skyr" with a Skor
    chocolate bar, "maize" with a Marie biscuit and "prawns" with animal
    crackers. Finding nothing is honest and sends the RD to the
    custom-food form. Finding the wrong food puts a wrong number in a
    patient's daily total with no warning attached.

    If this test fails, FUZZY_CUTOFF has been lowered. Read the
    measurement table beside it in src/food_search.py before changing it.
    """
    assert search_foods(query, index).match_type == MATCH_NONE


def test_two_character_words_are_never_spell_corrected(index):
    # A two-character typo is indistinguishable from a two-character word.
    assert search_foods("zz", index).is_empty


# ---------------------------------------------------------------------------
# Layer 3 -- synonyms
# ---------------------------------------------------------------------------


def test_synonym_maps_a_regional_term(index):
    result = search_foods("courgette", index)
    assert result.match_type == MATCH_SYNONYM
    assert "Zucchini, raw" in _descriptions(result)


def test_synonym_result_says_what_it_did(index):
    result = search_foods("courgette", index)
    assert result.interpreted_as == "zucchini"
    assert "zucchini" in result.note


def test_synonym_beats_spell_correction(index):
    """A curated human statement outranks a machine's spelling hunch."""
    assert search_foods("courgette", index).match_type == MATCH_SYNONYM


def test_missing_synonym_file_is_not_fatal(index):
    """Layers 1 and 2 must still work for a pack with no synonym table.

    Deliberately unlike nutrients.load_registry(), which raises: a pack
    without a nutrient registry cannot compute anything, but a pack
    without synonyms merely searches slightly worse.
    """
    assert load_synonyms("no-such-pack") == {}
    assert search_foods("wild rice", index, pack="no-such-pack").match_type == MATCH_DIRECT


# ---------------------------------------------------------------------------
# The synonym guard -- real CNF, real table
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
def test_every_synonym_resolves():
    """Every shipped synonym must still find at least one real CNF food.

    This is a guard against silent data rot, and it has already earned
    its place twice: "peppers sweet" failed because CNF writes the
    singular "Pepper, sweet", and two synonyms proposed from memory
    ("sweetpotato", "oats") were dropped after measurement showed they
    found FEWER foods than typing the term plainly.

    If you add a row to food_synonyms.csv and this fails, the mapping
    points at words CNF does not use. Fix the mapping -- do not relax
    this test.
    """
    frame = pd.read_csv(CNF_FOOD_NAME, encoding="utf-8-sig", low_memory=False)
    index = build_index(frame)

    failures = []
    for term in load_synonyms():
        result = search_foods(term, index)
        if result.match_type != MATCH_SYNONYM or result.is_empty:
            failures.append(f"{term!r} -> {result.match_type}, {len(result)} matches")

    assert not failures, "synonyms that no longer resolve:\n  " + "\n  ".join(failures)


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
def test_real_cnf_basic_foods_rank_above_contains_foods():
    """The headword tier, against the real CNF.

    The fixture versions above prove the mechanism; this one proves it
    against the actual descriptions an RD complained about (2026-08-07):
    searching "egg" offered bagels before eggs and "milk" offered a
    cracker before milk. Skipped without the raw CNF download, like the
    other real-data guards.
    """
    frame = pd.read_csv(CNF_FOOD_NAME, encoding="utf-8-sig", low_memory=False)
    index = build_index(frame)

    milk = _descriptions(search_foods("milk", index))
    cracker = next(d for d in milk if d.startswith("Cracker, milk"))
    fluid = next(d for d in milk if d.startswith("Milk, fluid"))
    assert milk.index(fluid) < milk.index(cracker)

    egg = _descriptions(search_foods("egg", index))
    bagel = next(d for d in egg if d.startswith("Bagel, egg"))
    chicken_egg = next(d for d in egg if d.startswith("Egg, chicken"))
    assert egg.index(chicken_egg) < egg.index(bagel)


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
def test_synonyms_never_shadow_a_working_plain_search():
    """A synonym must not override a search that already worked.

    The bar is layer 1 specifically, not "finds anything". Overriding a
    *fuzzy* result is often the whole point of a synonym: without its
    row, "bicarbonate of soda" spell-corrects to "carbonated soda" and
    returns club soda and cream soda -- a soft drink where the RD asked
    for a leavening agent. That is exactly the silent-wrong-answer case
    layer 3 exists to intercept, so a term resolving via fuzzy is a
    reason to KEEP its synonym, not to delete it.

    But if a term already resolves directly, the plain search handled it
    and the row is just one more thing to maintain and get wrong --
    which is how "aubergine", "soy milk" and "powdered sugar" were kept
    out of the shipped table.
    """
    frame = pd.read_csv(CNF_FOOD_NAME, encoding="utf-8-sig", low_memory=False)
    index = build_index(frame)

    unnecessary = []
    for term in load_synonyms():
        without = search_foods(term, index, pack="no-such-pack")
        if without.match_type == MATCH_DIRECT:
            unnecessary.append(f"{term!r} already resolves directly, without the synonym")

    assert not unnecessary, "synonyms that aren't needed:\n  " + "\n  ".join(unnecessary)
