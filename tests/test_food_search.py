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

from src import food_search
from src.food_search import (
    find_food,
    MATCH_DIRECT,
    MATCH_FUZZY,
    MATCH_NONE,
    MATCH_SYNONYM,
    build_index,
    load_qualifiers,
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
        # A natural-language DISH name sharing the headword "egg": CNF
        # files commodities inverted ("Egg, chicken, ...") but dishes as
        # spoken, and this one is SHORTER than every real egg entry --
        # the case that motivated the inverted-filing sort tier.
        (13, "Egg Benedict", "", 22),
        # Rows for the flavour/processing-qualifier ranking tier
        # (2026-08-20). "Cracker, milk" gives a CONTAINS-match (no
        # headword) with no qualifier, so it can be pitted against a
        # HEADWORD match that does carry a qualifier -- proving tiers
        # 1-4 still decide the outcome before the qualifier tier does.
        (14, "Yogourt, plain, 2% M.F.", "", 1),
        (15, "Yogourt, flavoured, 2% M.F.", "", 1),
        (16, "Milk, condensed, sweetened, canned", "", 1),
        (17, "Cracker, milk", "", 18),
        # "boiled" is a cooking method, not a listed qualifier -- it must
        # rank the same as an unmarked entry, not sort after it as if it
        # carried an unrequested qualifier.
        (18, "Chicken, breast, boiled, meat only", "", 13),
        (19, "Chicken, breast, skinless, boneless", "", 13),
        # For "a qualifier the RD typed is not penalised": both rows
        # match "sweetened broth" and both carry "sweetened" (requested,
        # so it must not count against either). Row 21 ALSO carries
        # "condensed" (not requested). Chosen so alphabetical order alone
        # -- "condensed..." < "ready..." -- would rank the wrong one
        # first; only the qualifier tier fixes it.
        (20, "Broth, sweetened, ready to serve", "", 1),
        (21, "Broth, sweetened, condensed, canned", "", 1),
        # For the plural-query fix (2026-08-20): CNF's real shape is a
        # plain singular headword ("Carrot, baby, raw") plus a handful of
        # unrelated rows that happen to contain the literal plural word
        # ("carrots"). A query of "carrots" must find the singular food
        # AND rank it above the incidental literal match.
        (22, "Carrot, baby, raw", "", 11),
        (23, "Babyfood, vegetables, jarred, carrots, all stages", "", 20),
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
# _token_forms() -- query-side singular expansion (2026-08-20)
# ---------------------------------------------------------------------------


def test_token_forms_strips_plain_s():
    assert food_search._token_forms("carrots") == ("carrots", "carrot")
    assert food_search._token_forms("eggs") == ("eggs", "egg")
    assert food_search._token_forms("oats") == ("oats", "oat")


def test_token_forms_ies_becomes_y():
    assert food_search._token_forms("strawberries") == ("strawberries", "strawberry")


def test_token_forms_oes_drops_es():
    assert food_search._token_forms("tomatoes") == ("tomatoes", "tomato")


def test_token_forms_double_s_is_not_treated_as_the_plain_s_case():
    # "molasses" still hits the "es" rule (which does not exclude "ss"),
    # producing a harmless nonsense form -- but the plain "s" rule, which
    # DOES exclude "ss", must not also fire and produce "molasse".
    forms = food_search._token_forms("molasses")
    assert forms[0] == "molasses"
    assert "molasse" not in forms


def test_token_forms_never_shorter_than_three_chars():
    # "as" is too short to strip at all; "gas" strips to nothing because
    # the rule requires len > 3 before stripping the plain "s".
    assert food_search._token_forms("as") == ("as",)
    assert food_search._token_forms("gas") == ("gas",)


def test_token_forms_leaves_a_singular_query_alone():
    # No plural-of-a-singular expansion: prefix matching already covers
    # that direction, so _token_forms() has nothing to add.
    assert food_search._token_forms("carrot") == ("carrot",)
    assert food_search._token_forms("rice") == ("rice",)


def test_token_forms_keeps_non_word_tokens_untouched():
    assert food_search._token_forms("2%") == ("2%",)


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


def test_inverted_filing_ranks_above_dish_name_with_same_headword(index):
    """The round-2 complaint (2026-08-07): "egg" led with Egg Benedict.

    With the desc/whole-word/headword tiers all tied, length was the
    only tiebreaker -- and "Egg Benedict" (12 chars) is shorter than
    every real egg entry, because it is a dish name, not a commodity.
    CNF files commodities inverted ("Egg, chicken, ..."), so a comma
    straight after the headword is the signal. An RD who wants the dish
    types the dish name.
    """
    descriptions = _descriptions(search_foods("egg", index))
    assert descriptions.index("Egg, chicken, whole, cooked, poached") < descriptions.index(
        "Egg Benedict"
    )


def test_inverted_tier_does_not_beat_headword_tier(index):
    """An inverted CONTAINS-food still loses to a headword dish match.

    "Bagel, egg" is inverted ("Bagel," ...) but only contains "egg";
    "Egg Benedict" IS headword-egg. The headword tier sits above the
    inverted tier, so the dish still outranks the bagel.
    """
    descriptions = _descriptions(search_foods("egg", index))
    assert descriptions.index("Egg Benedict") < descriptions.index("Bagel, egg")


# ---------------------------------------------------------------------------
# Plural queries, singular CNF (2026-08-20)
# ---------------------------------------------------------------------------


def test_plural_query_finds_the_singular_cnf_entry(index):
    """The bug this fix exists for. CNF files "Carrot, baby, raw" in the
    singular; a literal search for "carrots" alone would never reach it.
    """
    result = search_foods("carrots", index)
    assert result.match_type == MATCH_DIRECT
    assert "Carrot, baby, raw" in _descriptions(result)


def test_plural_query_ranks_the_real_food_above_an_incidental_literal_match(index):
    """Finding the row is only half the fix -- see _rows_matching()'s
    docstring. Without the forms reaching the whole-word and headword
    ranking tiers too, "carrots" finds "Carrot, baby, raw" but still
    ranks the babyfood jar (which contains the literal word "carrots")
    above it.
    """
    descriptions = _descriptions(search_foods("carrots", index))
    assert descriptions.index("Carrot, baby, raw") < descriptions.index(
        "Babyfood, vegetables, jarred, carrots, all stages"
    )


# ---------------------------------------------------------------------------
# Ranking tier 5 -- unrequested flavour/processing qualifiers (2026-08-20)
# ---------------------------------------------------------------------------


def test_plain_food_ranks_above_flavoured_or_sweetened(index):
    """The problem this tier exists to fix.

    Neither "yogurt" nor "milk" asks for a flavour or a processing step,
    so the plain entry should lead -- not whichever qualifier happens to
    sort first alphabetically ("condensed" < "fluid", "flavoured" <
    "plain").
    """
    yogurt = _descriptions(search_foods("yogourt", index))
    assert yogurt.index("Yogourt, plain, 2% M.F.") < yogurt.index("Yogourt, flavoured, 2% M.F.")

    milk = _descriptions(search_foods("milk", index))
    assert milk.index("Milk, fluid, 2% M.F.") < milk.index("Milk, condensed, sweetened, canned")


def test_a_qualifier_the_rd_typed_is_not_penalised(index):
    """Typing the qualifier requests it, so it must not count against a
    food's ranking -- but an EXTRA, untyped qualifier still should.

    Both rows below carry "sweetened", which "sweetened broth" asks for.
    Row 21 also carries "condensed", which the query does not mention.
    Chosen so alphabetical order alone ("condensed..." < "ready...")
    would rank row 21 first -- proving any reordering here comes from
    the qualifier tier, not from the alphabetical fallback.
    """
    descriptions = _descriptions(search_foods("sweetened broth", index))
    assert descriptions.index("Broth, sweetened, ready to serve") < descriptions.index(
        "Broth, sweetened, condensed, canned"
    )


def test_cooking_methods_are_not_treated_as_qualifiers(index):
    """A "boiled" entry must not be demoted below an otherwise-identical
    entry with no qualifier at all.

    Cooking methods are deliberately excluded from
    data/packs/canada/food_qualifiers.csv (see that file and
    `load_qualifiers()`'s docstring). If "boiled" were wrongly treated as
    a qualifier, this entry would sort AFTER "Chicken, breast, skinless,
    boneless" instead of before it (alphabetically "boiled" < "skinless"
    once the qualifier tier ties both at 0).
    """
    result = _descriptions(search_foods("chicken breast", index))
    assert result.index("Chicken, breast, boiled, meat only") < result.index(
        "Chicken, breast, skinless, boneless"
    )


def test_missing_qualifiers_file_is_not_fatal(index):
    """Layers/tiers 1-4 must still work for a pack with no qualifier
    table -- same degrade-safe contract as the missing-synonyms case."""
    assert load_qualifiers("no-such-pack") == {}
    no_pack_index = build_index(index.frame, pack="no-such-pack")
    result = search_foods("milk", no_pack_index, pack="no-such-pack")
    assert result.match_type == MATCH_DIRECT
    assert "Milk, condensed, sweetened, canned" in _descriptions(result)


def test_empty_qualifiers_file_is_not_fatal(index, tmp_path, monkeypatch):
    """A qualifier CSV that exists but has zero bytes must degrade to "no
    qualifiers", not raise -- the same contract as a missing file."""
    pack_dir = tmp_path / "empty-pack"
    pack_dir.mkdir()
    (pack_dir / food_search.QUALIFIERS_CSV_NAME).write_text("")
    monkeypatch.setattr(food_search, "PACKS_DIR", tmp_path)
    food_search.load_qualifiers.cache_clear()
    try:
        assert food_search.load_qualifiers("empty-pack") == {}
        no_pack_index = build_index(index.frame, pack="empty-pack")
        result = search_foods("milk", no_pack_index, pack="empty-pack")
        assert result.match_type == MATCH_DIRECT
        assert "Milk, condensed, sweetened, canned" in _descriptions(result)
    finally:
        food_search.load_qualifiers.cache_clear()


def test_tiers_one_through_four_outrank_the_qualifier_tier(index):
    """A tier-3 HEADWORD match with a qualifier must still beat a
    non-headword CONTAINS match without one.

    "Milk, condensed, sweetened, canned" IS milk (headword match) but
    carries two unrequested qualifiers; "Cracker, milk" merely CONTAINS
    milk (no headword match) and carries none. The headword tier (3)
    sits above the qualifier tier (5), so the real milk must still win.
    """
    milk = _descriptions(search_foods("milk", index))
    assert milk.index("Milk, condensed, sweetened, canned") < milk.index("Cracker, milk")


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

    # A limit big enough to hold every match, so this asserts on the
    # RANKING rather than on what fits the default 50-row page. Since tier
    # 5 became alphabetical (2026-08-15), the contains-matches this test
    # names fall off that page entirely -- a stronger outcome than the
    # test asks for, but one that made the old `next(...)` lookups raise
    # StopIteration instead of proving anything.
    _ALL = 10_000

    milk = _descriptions(search_foods("milk", index, limit=_ALL))
    cracker = next(d for d in milk if d.startswith("Cracker, milk"))
    fluid = next(d for d in milk if d.startswith("Milk, fluid"))
    assert milk.index(fluid) < milk.index(cracker)

    egg = _descriptions(search_foods("egg", index, limit=_ALL))
    bagel = next(d for d in egg if d.startswith("Bagel, egg"))
    chicken_egg = next(d for d in egg if d.startswith("Egg, chicken"))
    assert egg.index(chicken_egg) < egg.index(bagel)
    # And the round-2 complaint: the dish "Egg Benedict" led the list
    # because it is SHORTER than every real egg entry. The inverted
    # tier ("Egg, chicken," is a commodity filing; "Egg Benedict" is a
    # dish name) puts any chicken egg above it now.
    benedict = next(d for d in egg if d.startswith("Egg Benedict"))
    assert egg.index(chicken_egg) < egg.index(benedict)


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
def test_plural_queries_find_and_rank_the_real_singular_food():
    """The plural-query fix (2026-08-20), against the real file.

    Measured before this fix: "carrots" found 7 rows led by a babyfood
    jar; "strawberries" found 1 row (also a babyfood jar); "tomatoes"
    found 5 rows, none of them a plain tomato; "eggs" found 10 rows, none
    of them a plain egg. Layer 2 (typo tolerance) never rescued any of
    these, because it only runs when layer 1 finds nothing, and these
    queries always found *something*.

    Ranking, not just presence, was half the bug -- see
    `_rows_matching()`'s docstring -- so this asserts rank, not just
    membership.
    """
    frame = pd.read_csv(CNF_FOOD_NAME, encoding="utf-8-sig", low_memory=False)
    index = build_index(frame)

    cases = {
        "carrots": "Carrot, baby, raw",
        "strawberries": "Strawberry, frozen, unsweetened",
        "tomatoes": "Tomato, green, raw",
        "eggs": "Egg, chicken, dried, whole",
    }
    for query, expected in cases.items():
        result = search_foods(query, index)
        assert result.match_type == MATCH_DIRECT
        descriptions = _descriptions(result)
        assert expected in descriptions, f"{query!r} did not find {expected!r}"
        assert descriptions.index(expected) < 3, (
            f"{query!r}: {expected!r} ranked #{descriptions.index(expected) + 1}, "
            f"top 3 was {descriptions[:3]}"
        )


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
def test_singular_queries_are_unchanged_by_the_plural_fix():
    """Query-side expansion only ever ADDS candidate forms to try -- see
    `_rows_matching()`'s docstring for why that direction is safe -- so a
    query that already found its answer as a whole singular word must
    return exactly what it returned before this fix.
    """
    frame = pd.read_csv(CNF_FOOD_NAME, encoding="utf-8-sig", low_memory=False)
    index = build_index(frame)

    expected_first_result = {
        "carrot": "Carrot, baby, raw",
        "tomato": "Tomato, green, raw",
        "banana": "Banana, raw",
    }
    for query, expected in expected_first_result.items():
        result = search_foods(query, index)
        assert _descriptions(result)[0] == expected


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
@pytest.mark.parametrize(
    "query,expected_first",
    [("beans", "Beans,"), ("oats", "Cereal, hot, oats"), ("greens", "Beet greens")],
)
def test_a_word_cnf_already_files_as_plural_still_leads_with_that_food(query, expected_first):
    """CNF files some foods under the plural headword itself ("Beans,
    adzuki, ...", "Cereal, hot, oats (oatmeal), ...", "Beet greens,
    ..."). Singularising those queries reaches a far commoner stem --
    "green" and "oat" appear all over CNF -- so the expansion drags in
    mung beans and oat bagels. They are welcome to be in the results;
    they are not welcome at the TOP, which is why the sort key ranks a
    row that matched the words AS TYPED above one that only matched
    after singularising.

    Asserting the first row, not merely a non-empty result: "greens"
    returned 114 rows with the first real leafy green at #74 before that
    tier existed, which is a pass for any weaker assertion and a
    complete failure for an RD (2026-08-20).
    """
    frame = pd.read_csv(CNF_FOOD_NAME, encoding="utf-8-sig", low_memory=False)
    index = build_index(frame)
    result = search_foods(query, index)
    assert result.match_type == MATCH_DIRECT
    assert _descriptions(result)[0].startswith(expected_first)


@pytest.mark.skipif(not CNF_FOOD_NAME.exists(), reason="raw CNF download not present")
def test_a_word_ending_in_double_s_is_not_mangled():
    """ "molasses" ends in "ss", so the plain-s stripping rule in
    `_token_forms()` -- which explicitly excludes "ss" -- must not fire
    on it. It still hits the "es" rule ("molasses" -> "molass"), a
    harmless nonsense form that simply matches nothing; "molasses"
    itself, kept as the first form, still finds the real molasses foods.
    """
    frame = pd.read_csv(CNF_FOOD_NAME, encoding="utf-8-sig", low_memory=False)
    index = build_index(frame)
    result = search_foods("molasses", index)
    assert result.match_type == MATCH_DIRECT
    descriptions = _descriptions(result)
    assert any("molasses" in d.lower() for d in descriptions)


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


class TestFindFood:
    """find_food() is the by-NAME lookup the app uses when it already
    knows the exact CNF description it wants -- the example day's
    ingredients, the water the Dilution What-If adds. Not the RD-facing
    fuzzy search above. Moved out of app/streamlit_app.py 2026-08-17,
    which is the first time it could be tested.

    Hand-built frames, no CNF download needed: the behaviour under test is
    exact-before-substring, which is a pure string rule.
    """

    @staticmethod
    def _frame(*rows):
        return pd.DataFrame([{"Food_Code": c, "Food_Description_EN": d} for c, d in rows])

    def test_exact_match_wins_over_a_substring_match(self):
        """THE BUG THIS PROTECTS (author, 2026-08-15): CNF descriptions
        nest. "Spinach, boiled, drained" is a substring of "New Zealand
        spinach, boiled, drained", so a substring-only lookup resolved the
        example day's spinach to the New Zealand one -- silently, and with
        different nutrients. Note the decoy is listed FIRST, so returning
        the first substring hit would fail this.
        """
        fn = self._frame(
            (1, "New Zealand spinach, boiled, drained"),
            (2, "Spinach, boiled, drained"),
        )
        assert find_food(fn, "Spinach, boiled, drained") == 2

    def test_falls_back_to_the_first_substring_match(self):
        fn = self._frame((1, "Chicken, broiler, breast, braised"))
        assert find_food(fn, "breast") == 1

    def test_matching_ignores_case(self):
        fn = self._frame((7, "Water, municipal"))
        assert find_food(fn, "water, municipal") == 7

    def test_no_match_returns_none_rather_than_raising(self):
        """The Dilution What-If depends on this: it checks for None and
        tells the RD to add the water by hand instead of crashing."""
        assert find_food(self._frame((1, "Banana, raw")), "Sorghum") is None

    def test_a_description_with_regex_characters_is_matched_literally(self):
        """CNF descriptions carry brackets and plus signs. Treating them
        as a pattern would either raise or match the wrong food."""
        fn = self._frame((3, "Yogourt (yogurt), Greek style, 2% M.F."))
        assert find_food(fn, "Yogourt (yogurt), Greek style, 2% M.F.") == 3
