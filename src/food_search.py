"""Three-layer food search over the Canadian Nutrient File.

WHY THIS MODULE EXISTS
----------------------
CNF describes foods the way a librarian files them, not the way a
dietitian speaks. Wild rice is filed as "Grains, rice, wild, dry", and
Greek yogurt as "Yogourt, Greek, ...". The app's original search was a
literal substring match (`str.contains(term, regex=False)`), so *both*
of those queries returned nothing at all.

That is worse than it sounds. An RD who types "wild rice", sees no
results, and concludes the food is not in the database has been told
something false -- and their next move is to hand-enter a food that was
already there, with worse data.

It is not a hypothetical failure either. The same substring assumption,
made by a developer rather than a user, produced an estimate that CNF
was missing ~1,600 foods. The real number was about a dozen. That
estimate was the main argument for bolting a second nutrient database
(USDA SR Legacy) onto this app; fixing the search removed the argument,
and the supplement was cancelled on 2026-07-30. See CONTEXT.md S9.

So: the gap was in the search, not in the data. This module is the fix.

THE THREE LAYERS
----------------
1. ALL WORDS, ANY ORDER, matched as prefixes. "wild rice" ->
   "Grains, rice, wild, dry"; "greek yogurt" -> "Yogourt, Greek, ...".
   Prefixes rather than whole words so that search-as-you-type works:
   "chick" finds chickpeas before the RD finishes the word. This layer
   also reads CNF's own `Alternate_Description_EN` column, which carries
   lay and brand terms ("mashed", "hot cocoa", "Cool Whip") for 1,384
   foods and which the old search ignored entirely.

2. TYPO TOLERANCE, per word, against CNF's own vocabulary. "brocolli" ->
   broccoli, "yoghurt" -> yogourt (CNF is bilingual and files some
   entries under the French spelling, so this layer earns its keep even
   for correct English). Uses `difflib` from the standard library.

   Measured at ~1.3 ms against CNF's 2,676 distinct words -- fast enough
   to run on every keystroke, and it adds no dependency. That last part
   is deliberate: this app's public deploy has been broken by dependency
   drift before (CONTEXT.md S11), so a search feature is not worth a new
   package when the standard library is this close.

3. SYNONYMS, curated, from data/packs/<pack>/food_synonyms.csv. Only for
   terms CNF holds under neither spelling: courgette -> zucchini,
   prawns -> shrimp. Deliberately tiny. Layers 1 and 2 do most of the
   work, and a synonym table is the kind of data that rots silently, so
   every row is guarded by a test asserting it still resolves to at
   least one real CNF food (tests/test_food_search.py).

   Two synonyms that seemed obvious were rejected on measurement, which
   is why that test exists: CNF writes "sweet potato" as two words (a
   "sweetpotato" mapping would have found 0 foods instead of 23), and
   "oatmeal" already finds 65 foods where "oats" finds 51 -- the
   "synonym" would have thrown results away.

Layers run in order and stop at the first that finds anything, so an
exact match is never buried underneath a fuzzy one.

RANKING, NOT AUTO-SELECTING
---------------------------
`search_foods()` returns ranked candidates and a note saying how it
interpreted the query. It never picks a food. Callers must show the full
CNF description and let the RD choose. A search that silently selects
the wrong food is more dangerous than one that finds nothing: nothing is
visible to the RD, and wrong is not. This is the same rule the project
applies to AI label extraction (CONTEXT.md S11) -- a typing shortcut is
allowed to be wrong, so it is never allowed to be the last word.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"
DEFAULT_PACK = "canada"
SYNONYMS_CSV_NAME = "food_synonyms.csv"

#: Shortest query we will act on. One character matches most of CNF and
#: tells the RD nothing.
MIN_QUERY_LEN = 2

#: difflib similarity below which a word is not treated as a plausible
#: misspelling.
#:
#: MEASURED, not guessed -- and the measurement mattered. At the 0.75
#: this started on, layer 2 confidently "corrected" words CNF simply
#: does not have: skyr -> Skor (a chocolate bar), maize -> Marie
#: (a biscuit), rocket -> rock (spiny lobster), prawns -> paws. Those
#: are the exact failure this module's docstring warns about, produced
#: by the module itself.
#:
#: Scoring real typos of real CNF words against the words CNF lacks
#: separates them cleanly, with no overlap:
#:
#:   want to correct     brocolli->broccoli 0.875   yoghurt->yogourt 0.857
#:                       chikpeas->chickpeas 0.941  avacado->avocado 0.857
#:                       cinamon->cinnamon 0.933    lentil->lentils  0.923
#:                       (lowest wanted: 0.857)
#:   must NOT correct    maize->marie 0.800   rocket->rock  0.800
#:                       prawns->paws 0.800   skyr->skor    0.750
#:                       mangetout->mango 0.714  paneer->japanese 0.714
#:                       (highest unwanted: 0.800)
#:
#: 0.84 sits in the gap. A word CNF genuinely lacks now falls through to
#: "no results" -- which is honest, and sends the RD to the custom-food
#: form -- instead of quietly offering a candy bar.
FUZZY_CUTOFF = 0.84

#: How many spelling candidates to try per query word.
MAX_FUZZY_PER_WORD = 3

#: Default cap on returned rows. The UI puts these in a dropdown, and a
#: dropdown of 500 foods is not a search result, it is a database.
DEFAULT_LIMIT = 50

# How a result set was arrived at -- carried on SearchResult so the UI
# can explain itself to the RD.
MATCH_DIRECT = "direct"
MATCH_SYNONYM = "synonym"
MATCH_FUZZY = "fuzzy"
MATCH_NONE = "none"

# Words are runs of letters/digits, plus "%" so that "2%" survives as a
# token ("Milk, fluid, 2% M.F." is a real CNF description).
_TOKEN_RE = re.compile(r"[^a-z0-9%]+")

# Noise words that would otherwise force a match. An RD typing "cream of
# mushroom soup" should not fail because CNF omits "of".
_STOPWORDS = frozenset({"and", "or", "of", "with", "in", "the", "a", "an"})


def tokenize(text: str) -> list[str]:
    """Lowercase `text` and split it into searchable words.

    Stopwords are dropped, but only when something else survives -- a
    search for the literal word "and" should still do *something* rather
    than silently match every food in the database.
    """
    if not isinstance(text, str):
        return []
    words = [w for w in _TOKEN_RE.split(text.lower()) if w]
    meaningful = [w for w in words if w not in _STOPWORDS]
    return meaningful or words


@dataclass(frozen=True)
class SearchIndex:
    """Pre-tokenised CNF descriptions, built once and reused per query.

    Built by `build_index()`. Holding this rather than re-tokenising
    5,993 descriptions on every keystroke is the difference between a
    search box that feels instant and one that stutters. The app wraps
    construction in Streamlit's cache; this module stays Streamlit-free
    so it can be tested without a browser.
    """

    frame: pd.DataFrame
    #: Words from Food_Description_EN, one frozenset per row.
    desc_tokens: tuple[frozenset[str], ...]
    #: Words from Alternate_Description_EN, one frozenset per row.
    alt_tokens: tuple[frozenset[str], ...]
    #: Every distinct word CNF uses, for the fuzzy layer to spell against.
    vocabulary: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.frame)


@dataclass(frozen=True)
class SearchResult:
    """Ranked candidates plus an explanation of how we got there."""

    matches: pd.DataFrame
    match_type: str
    #: The query actually searched, when it differs from what was typed.
    interpreted_as: str = ""
    #: UI-ready sentence, or "" when there is nothing worth saying.
    note: str = ""

    def __len__(self) -> int:
        return len(self.matches)

    @property
    def is_empty(self) -> bool:
        return self.matches.empty


def build_index(food_name_df: pd.DataFrame) -> SearchIndex:
    """Tokenise a CNF Food_Name frame once, ready for repeated queries."""
    descriptions = food_name_df["Food_Description_EN"].fillna("")
    if "Alternate_Description_EN" in food_name_df.columns:
        alternates = food_name_df["Alternate_Description_EN"].fillna("")
    else:
        # Older/partial CNF extracts may not carry the column. Degrade to
        # description-only search rather than refusing to start.
        alternates = pd.Series([""] * len(food_name_df), index=food_name_df.index)

    desc_tokens = tuple(frozenset(tokenize(t)) for t in descriptions)
    alt_tokens = tuple(frozenset(tokenize(t)) for t in alternates)

    vocab: set[str] = set()
    for bucket in desc_tokens:
        vocab.update(bucket)
    for bucket in alt_tokens:
        vocab.update(bucket)

    return SearchIndex(
        frame=food_name_df,
        desc_tokens=desc_tokens,
        alt_tokens=alt_tokens,
        vocabulary=tuple(sorted(vocab)),
    )


def _synonyms_csv_path(pack: str = DEFAULT_PACK) -> Path:
    return PACKS_DIR / pack / SYNONYMS_CSV_NAME


@lru_cache(maxsize=8)
def load_synonyms(pack: str = DEFAULT_PACK) -> dict[str, str]:
    """Map a lay/regional term to the CNF words that find it.

    Returns {} when the pack ships no synonym file. Unlike
    `nutrients.load_registry()` -- which raises, because a pack without a
    nutrient registry cannot compute anything -- a missing synonym table
    only costs layer 3. Layers 1 and 2 still work, so refusing to start
    would be a worse failure than degrading.
    """
    path = _synonyms_csv_path(pack)
    if not path.exists():
        return {}

    frame = pd.read_csv(path, encoding="utf-8-sig")
    mapping: dict[str, str] = {}
    for _, row in frame.iterrows():
        term = str(row.get("term", "")).strip().lower()
        cnf_words = str(row.get("cnf_words", "")).strip()
        if term and cnf_words and cnf_words.lower() != "nan":
            mapping[term] = cnf_words
    return mapping


def _rows_matching(index: SearchIndex, query_tokens: list[str]) -> list[tuple[tuple, int]]:
    """Rows where every query word prefixes some word of the food.

    Returns (sort_key, row_position) pairs. The sort key ranks:
      1. description matches above alternate-name-only matches -- an RD
         recognises the CNF description, which is what they will see;
      2. whole-word matches above prefix-only ones, so typing "rice"
         puts rice above "ricelike";
      3. shorter descriptions first, because CNF's terse entries are its
         basic foods and the long ones are heavily-qualified variants.
    """
    scored: list[tuple[tuple, int]] = []

    for position in range(len(index.frame)):
        desc_words = index.desc_tokens[position]
        alt_words = index.alt_tokens[position]

        matched_in_desc = True
        exact_words = 0
        for token in query_tokens:
            if token in desc_words:
                exact_words += 1
                continue
            if any(word.startswith(token) for word in desc_words):
                continue
            # Not in the description -- try the alternate names.
            if token in alt_words or any(word.startswith(token) for word in alt_words):
                matched_in_desc = False
                continue
            break
        else:
            description = index.frame["Food_Description_EN"].iat[position]
            sort_key = (
                0 if matched_in_desc else 1,
                0 if exact_words == len(query_tokens) else 1,
                len(str(description)),
            )
            scored.append((sort_key, position))

    scored.sort(key=lambda pair: pair[0])
    return scored


def _take(index: SearchIndex, scored: list[tuple[tuple, int]], limit: int) -> pd.DataFrame:
    if not scored:
        return index.frame.iloc[[]]
    positions = [position for _, position in scored[:limit]]
    return index.frame.iloc[positions]


def _spell_candidates(index: SearchIndex, token: str) -> list[str]:
    """Plausible CNF spellings of a word the RD typed."""
    if len(token) < 3:
        # Two-character typos are indistinguishable from two-character
        # words. Correcting them produces confident nonsense.
        return []
    return difflib.get_close_matches(
        token, index.vocabulary, n=MAX_FUZZY_PER_WORD, cutoff=FUZZY_CUTOFF
    )


def search_foods(
    query: str,
    index: SearchIndex,
    *,
    pack: str = DEFAULT_PACK,
    limit: int = DEFAULT_LIMIT,
) -> SearchResult:
    """Find CNF foods matching `query`, trying three layers in order.

    Args:
        query:  What the RD typed.
        index:  From `build_index()`, optionally pre-filtered by food
                group (build the index from the filtered frame).
        pack:   Data pack whose synonym table to consult.
        limit:  Maximum rows returned.

    Returns:
        A `SearchResult`. Always ranked, never auto-selected -- see this
        module's docstring for why that distinction is load-bearing.
    """
    empty = index.frame.iloc[[]]
    text = (query or "").strip()
    if len(text) < MIN_QUERY_LEN:
        return SearchResult(empty, MATCH_NONE)

    # --- Layer 1: all words, any order, prefix-matched -----------------
    tokens = tokenize(text)
    if not tokens:
        return SearchResult(empty, MATCH_NONE)

    scored = _rows_matching(index, tokens)
    if scored:
        return SearchResult(_take(index, scored, limit), MATCH_DIRECT)

    # --- Layer 3 before layer 2 ----------------------------------------
    # A curated synonym is a deliberate human statement about this
    # database; a spelling guess is a machine's hunch. When both could
    # fire, the human wins. (The layers are *numbered* by how obvious
    # they are to explain, not by the order they run.)
    synonyms = load_synonyms(pack)
    replacement = synonyms.get(text.lower())
    if replacement is None and len(tokens) == 1:
        replacement = synonyms.get(tokens[0])
    if replacement:
        scored = _rows_matching(index, tokenize(replacement))
        if scored:
            return SearchResult(
                _take(index, scored, limit),
                MATCH_SYNONYM,
                interpreted_as=replacement,
                note=f'CNF calls this "{replacement}" — showing those results.',
            )

    # --- Layer 2: typo tolerance, per word -----------------------------
    # Correct one word at a time and keep the first combination that
    # finds anything, rather than rewriting the whole query at once: a
    # single wrong word shouldn't discard the words the RD got right.
    corrected = list(tokens)
    changed: list[tuple[str, str]] = []
    for position, token in enumerate(tokens):
        for candidate in _spell_candidates(index, token):
            trial = list(corrected)
            trial[position] = candidate
            if _rows_matching(index, trial):
                corrected = trial
                changed.append((token, candidate))
                break

    if changed:
        scored = _rows_matching(index, corrected)
        if scored:
            spelled = " ".join(corrected)
            was = ", ".join(f'"{before}" → "{after}"' for before, after in changed)
            return SearchResult(
                _take(index, scored, limit),
                MATCH_FUZZY,
                interpreted_as=spelled,
                note=f"No exact match — showing results for {was}.",
            )

    return SearchResult(empty, MATCH_NONE)
