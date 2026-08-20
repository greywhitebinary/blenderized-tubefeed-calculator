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
QUALIFIERS_CSV_NAME = "food_qualifiers.csv"

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

    Does NOT normalise singular/plural -- "carrots" and "carrot" tokenize
    to themselves, unchanged. That normalisation happens separately and
    only on the query side, in `_token_forms()` inside `_rows_matching()`
    (2026-08-20): CNF descriptions are tokenized here exactly as CNF
    wrote them, and only the RD's query is ever expanded to more forms.
    See `_rows_matching()`'s docstring for why.
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
    #: The headword WORDS of each description -- normally just the first
    #: word, since CNF files foods headword-first ("Milk, fluid, ..."),
    #: which is how the ranking tells "this food IS what you typed" apart
    #: from "this food CONTAINS what you typed" ("Cracker, milk").
    #:
    #: A tuple, not one string, because CNF spells a headword's alternate
    #: name in brackets straight after it -- "Yogourt (yogurt), Greek
    #: style", "Doughnut (donut), ...", "Rutabaga (swede), ...". Both
    #: words are the headword as far as a searcher is concerned, and CNF
    #: prints the bracket precisely because it knows people type the
    #: other one. Crediting only the first meant "yogurt" never scored a
    #: headword match on a single real yogurt (CNF's own spelling is
    #: "Yogourt"), so the ranking fell through to length and answered
    #: with frozen-yogurt desserts and yogurt-covered candies -- 64
    #: entries affected, the largest such pair in the file (author,
    #: 2026-08-15). Empty tuple for an untokenisable description.
    desc_headword: tuple[tuple[str, ...], ...]
    #: True when the description opens with "<headword>," -- CNF's
    #: inverted commodity filing ("Egg, chicken, whole, cooked, ..."),
    #: as opposed to a natural-language dish name ("Egg Benedict",
    #: "Eggnog"). Both can share a headword, and length alone cannot
    #: tell them apart: "Egg Benedict" is SHORTER than any real egg
    #: entry. Among headword matches, inverted filings rank first.
    desc_inverted: tuple[bool, ...]
    #: Every distinct word CNF uses, for the fuzzy layer to spell against.
    vocabulary: tuple[str, ...]
    #: Which qualifiers (from data/packs/<pack>/food_qualifiers.csv) each
    #: description carries, by name -- one frozenset per row. Computed
    #: ONCE here rather than re-scanning the description string on every
    #: query: build_index() runs once, search_foods() runs on every
    #: keystroke, so the cost belongs here (author, 2026-08-20).
    desc_qualifiers: tuple[frozenset[str], ...]
    #: The qualifier vocabulary itself -- qualifier name -> the set of
    #: description words that signal it ("sugar added" -> {"sugar",
    #: "added"}). Carried alongside desc_qualifiers so the ranking tier
    #: can tell whether the RD's query already asked for a qualifier it
    #: finds, without re-reading the CSV per query.
    qualifier_words: dict[str, frozenset[str]]

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


# CNF's "Headword (alternate spelling)" convention, e.g. "Yogourt
# (yogurt), Greek style" or "Doughnut (donut), plain". Only matched at the
# very start of a description, and only when the bracket holds a single
# word: a multi-word bracket is a description, not an alias ("Leeks (bulb
# and lower-leaf portion)"), and crediting those as headwords would let
# "portion" rank a leek above whatever the RD actually meant.
_HEADWORD_ALIAS = re.compile(r"^\s*([A-Za-z][A-Za-z\-]*)\s*\(\s*([A-Za-z][A-Za-z\-]*)\s*\)")


def _headwords(raw_description: str, words: list[str]) -> tuple[str, ...]:
    """The word(s) a searcher would consider this food's headword."""
    if not words:
        return ()
    match = _HEADWORD_ALIAS.match(str(raw_description))
    if match:
        alias = match.group(2).lower()
        if alias != words[0]:
            return (words[0], alias)
    return (words[0],)


def build_index(food_name_df: pd.DataFrame, *, pack: str = DEFAULT_PACK) -> SearchIndex:
    """Tokenise a CNF Food_Name frame once, ready for repeated queries."""
    descriptions = food_name_df["Food_Description_EN"].fillna("")
    if "Alternate_Description_EN" in food_name_df.columns:
        alternates = food_name_df["Alternate_Description_EN"].fillna("")
    else:
        # Older/partial CNF extracts may not carry the column. Degrade to
        # description-only search rather than refusing to start.
        alternates = pd.Series([""] * len(food_name_df), index=food_name_df.index)

    desc_words = [tokenize(t) for t in descriptions]
    desc_tokens = tuple(frozenset(words) for words in desc_words)
    desc_headword = tuple(_headwords(raw, words) for raw, words in zip(descriptions, desc_words))
    desc_inverted = tuple(
        bool(words) and str(raw).lower().startswith(words[0] + ",")
        for raw, words in zip(descriptions, desc_words)
    )
    alt_tokens = tuple(frozenset(tokenize(t)) for t in alternates)

    vocab: set[str] = set()
    for bucket in desc_tokens:
        vocab.update(bucket)
    for bucket in alt_tokens:
        vocab.update(bucket)

    qualifier_words = load_qualifiers(pack)
    desc_qualifiers = tuple(
        frozenset(name for name, words in qualifier_words.items() if words <= words_present)
        for words_present in desc_tokens
    )

    return SearchIndex(
        frame=food_name_df,
        desc_tokens=desc_tokens,
        alt_tokens=alt_tokens,
        desc_headword=desc_headword,
        desc_inverted=desc_inverted,
        vocabulary=tuple(sorted(vocab)),
        desc_qualifiers=desc_qualifiers,
        qualifier_words=qualifier_words,
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

    # Same reasoning as load_qualifiers(): this file is hand-edited, so an
    # unreadable one degrades to "no synonyms" rather than stopping the
    # search from starting at all (2026-08-20).
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, OSError:
        return {}
    mapping: dict[str, str] = {}
    for _, row in frame.iterrows():
        term = str(row.get("term", "")).strip().lower()
        cnf_words = str(row.get("cnf_words", "")).strip()
        if term and cnf_words and cnf_words.lower() != "nan":
            mapping[term] = cnf_words
    return mapping


def _qualifiers_csv_path(pack: str = DEFAULT_PACK) -> Path:
    return PACKS_DIR / pack / QUALIFIERS_CSV_NAME


@lru_cache(maxsize=8)
def load_qualifiers(pack: str = DEFAULT_PACK) -> dict[str, frozenset[str]]:
    """Map a flavour/processing qualifier to the description words that
    signal it ("sugar added" -> {"sugar", "added"}).

    Feeds the ranking tier in `_rows_matching()` that pushes a food with
    an unrequested qualifier (flavoured, sweetened, powdered, ...) below
    the plain version of the same food. Data, not code, per the same
    reasoning as `load_synonyms()`: the vocabulary is a clinical
    judgement call, and a dietitian should be able to edit it without
    touching Python.

    Deliberately excludes cooking methods (boiled, roasted, fried, raw,
    steamed, ...). Demoting them would push RAW foods to the top of every
    result, and raw meat is not what a blenderized feed wants ranked
    first for a query like "chicken" -- that is a clinical judgement by
    the author, not an oversight (2026-08-20).

    Returns {} when the pack ships no qualifier file, and also when the
    file exists but is empty -- same degrade-safe contract as
    `load_synonyms()`: a missing or unusable qualifier table only costs
    this one ranking tier, never the search itself.
    """
    path = _qualifiers_csv_path(pack)
    if not path.exists():
        return {}

    try:
        frame = pd.read_csv(path, encoding="utf-8-sig")
    # Empty file, a stray comma in a note, a bad encoding, an unreadable
    # file: this table is meant to be edited by a dietitian, not a
    # programmer, so a typo in it must cost this one ranking tier and
    # nothing else. Before this, a note containing a comma raised
    # ParserError out of build_index() and took the entire search down
    # with it -- the app's most-used control, felled by punctuation
    # (2026-08-20).
    except pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, OSError:
        return {}

    mapping: dict[str, frozenset[str]] = {}
    for _, row in frame.iterrows():
        qualifier = str(row.get("qualifier", "")).strip().lower()
        if not qualifier or qualifier == "nan":
            continue
        words = frozenset(tokenize(qualifier))
        if words:
            mapping[qualifier] = words
    return mapping


def _token_forms(token: str) -> tuple[str, ...]:
    """The word as typed, plus conservative singular candidates.

    Query-side only -- see `_rows_matching()`'s docstring for why. Rules,
    cheapest-and-most-specific first so e.g. "berries" hits the "ies"
    rule rather than the plain "s" one:

      ies -> y     ("strawberries" -> "strawberry"), len > 4
      oes -> ""    ("tomatoes" -> "tomato"), len > 4
      es  -> ""    ("dishes" -> "dish"; "leaves" -> "leav", which is not
                    a word but matches nothing, which is harmless), len > 3
      s   -> ""    ("carrots" -> "carrot", "eggs" -> "egg"), but not
                    words ending "ss" ("molasses" must stay "molasses")
                    or short enough that stripping leaves under 3 chars

    Deliberately does not go the other way (singular query -> plural
    form): prefix matching already finds "carrots" from a typed
    "carrot", so generating a plural here would just be redundant work
    on every keystroke.
    """
    candidates = []
    if token.endswith("ies") and len(token) > 4:
        candidates.append(token[:-3] + "y")
    elif token.endswith("oes") and len(token) > 4:
        candidates.append(token[:-2])
    elif token.endswith("es") and len(token) > 3:
        candidates.append(token[:-2])
    elif token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        candidates.append(token[:-1])

    ordered = [token]
    seen = {token}
    for form in candidates:
        if len(form) >= 3 and form not in seen:
            seen.add(form)
            ordered.append(form)
    return tuple(ordered)


def _has_unrequested_qualifier(index: SearchIndex, position: int, query_tokens: list[str]) -> bool:
    """Does this row carry a flavour/processing qualifier the RD did not type?

    A qualifier counts as REQUESTED when every one of its words is
    matched by a query token using the same rule the rest of this module
    uses for query words: equal, or a prefix of, the word. So a query of
    "flavoured yogurt" requests "flavoured" and does not penalise it.
    """
    for name in index.desc_qualifiers[position]:
        words = index.qualifier_words.get(name)
        if not words:
            continue
        requested = all(
            any(token == word or word.startswith(token) for token in query_tokens) for word in words
        )
        if not requested:
            return True
    return False


def _rows_matching(index: SearchIndex, query_tokens: list[str]) -> list[tuple[tuple, int]]:
    """Rows where every query word -- or a conservative singular form of
    it -- prefixes some word of the food.

    PLURAL QUERIES, SINGULAR CNF (2026-08-20). CNF files most whole foods
    in the singular ("Carrot, baby, raw", "Strawberry, frozen,
    unsweetened", "Tomato, green, raw"), but prefix matching only reaches
    from a singular query TO a plural entry ("carrot" is a prefix of
    "carrots"), never the other way. A plural query typed the way an RD
    actually types -- "carrots", "strawberries", "tomatoes" -- searched
    only for the literal word "carrots" and so found the handful of CNF
    rows that happen to contain it verbatim (babyfood jars, mixed
    vegetables) while the 23 real carrot entries stayed invisible.
    Measured on the real file before this fix: "carrot" found 23 rows
    led by "Carrot, baby, raw", "carrots" found 7 led by "Babyfood,
    vegetables, jarred, carrots"; "strawberry" found 32, "strawberries"
    found 1 ("Babyfood, fruit, jarred, apple and berries..."); "tomato"
    found 50, "tomatoes" found 5, none of them a plain tomato; "eggs"
    found 10, none of them a plain egg. Layer 2 (typo tolerance) never
    rescued this, because it only runs when layer 1 finds NOTHING, and
    "carrots" was never nothing.

    The fix is QUERY-SIDE ONLY: each query token is expanded, here, to a
    small set of forms via `_token_forms()` -- the word as typed plus
    cheap singular candidates ("carrots" -> ("carrots", "carrot")) -- and
    a token counts as matched when ANY of its forms matches. The index
    built by `build_index()`, `tokenize()`'s output, and what counts as a
    match against a DESCRIPTION word are all untouched. That asymmetry is
    deliberate, not an oversight: expanding the query can only ever find
    MORE rows than before, never fewer, so this cannot regress an
    existing singular search. Expanding the index instead -- stemming
    every CNF word at build time -- would touch the same three tiers
    below AND the vocabulary the fuzzy layer spells against, for a much
    larger surface to get wrong. A generated form that happens not to be
    a real English word (the "es" rule turns "leaves" into "leav") is
    harmless by the same logic: it simply matches no CNF word, exactly
    like a query word that was never in the file.

    Returns (sort_key, row_position) pairs. The sort key ranks:
      1. description matches above alternate-name-only matches -- an RD
         recognises the CNF description, which is what they will see;
      2. whole-word matches above prefix-only ones, so typing "rice"
         puts rice above "ricelike". A form matching a description word
         EXACTLY counts as exact here, not just the token as typed --
         otherwise a plural query such as "carrots" would win tier 1 via
         its singular form but lose this tier's whole-word credit, and
         rank behind foods it should rank above;
      3. foods whose HEADWORD (first word) a query word prefixes above
         foods that merely contain the word -- CNF files foods
         headword-first, so "Milk, fluid, ..." IS milk while "Cracker,
         milk" CONTAINS milk. Without this tier, tier 4 alone answered
         "egg" with "Bagel, egg" and "milk" with "Cracker, milk", which
         is the complaint that motivated it. This tier sits BELOW tier 2
         deliberately: a prefix-only headword ("Eggplant, raw" for
         "egg") must not outrank a real whole-word match deeper in the
         description ("Roll, dinner, egg"). This check also considers
         every form of every token (2026-08-20): without it, "carrots"
         found "Carrot, baby, raw" via tier 1 but still ranked babyfood
         jars above it, because the headword check saw only the literal
         "carrots" and "carrot" never appears as a headword;
      4. rows that matched every word AS TYPED above rows that only
         matched after singularising (2026-08-20). Singularising reaches
         a commoner stem than the RD typed -- "greens" also searches
         "green", which is scattered across CNF as an adjective ("green
         gram", "green or yellow", "Tomato, green"), and "oats" also
         searches "oat", which finds bagels and bread. Those foods
         deserve to be IN the results; they do not deserve the top of
         them. Measured when this tier was missing: "greens" returned
         114 rows whose first real leafy green ("Beet greens, boiled")
         sat at #74, past the 50-row page, so an RD typing "greens" saw
         no greens at all.

         It sits BELOW the headword tier on purpose. Above it, "carrots"
         would rank the babyfood jars that contain the literal word
         "carrots" over "Carrot, baby, raw" -- undoing the very fix the
         forms expansion exists for. Below it, the headword decides the
         plural case and this tier decides only what the headword tier
         left tied, which is exactly the "greens" case;
      5. CNF's inverted commodity filing ("Egg, chicken, ...") above
         natural-language dish names ("Egg Benedict", "Eggnog"). Both
         can share a headword, and tier 7 alone cannot tell them apart
         -- "Egg Benedict" is SHORTER than every real egg entry, which
         is how it ranked #1 for "egg" until this tier existed
         (2026-08-07 RD feedback, round 2). An RD looking for a dish
         types the dish ("chicken a la king"); a bare commodity word
         means the commodity;
      6. a food with no UNREQUESTED flavour/processing qualifier above one
         that has one -- "chicken" answered with "Chicken, broiler, back,
         meat and skin, batter dipped, fried" and "milk" with "Milk,
         condensed, sweetened, canned", both alphabetically ahead of the
         plain food an RD actually meant. Qualifiers come from
         data/packs/<pack>/food_qualifiers.csv (flavoured, sweetened,
         powder, condensed, ...) and are precomputed per row in
         `build_index()`, not scanned here.

         "Unrequested" is the load-bearing word: if the query itself asks
         for the qualifier -- "flavoured yogurt", "strawberry yogurt" --
         that food is not penalised. An RD who wants a flavoured food
         types the flavour.

         This tier is safe to add here, and only here, because
         `_rows_matching()` has already thrown away every row that fails
         to match all of `query_tokens` by the time this runs -- see the
         `for ... else` below. The tier can only reorder foods that ALL
         equally satisfied the RD's query; it can never hide or bury a
         food the RD asked for by name.

         Deliberately excludes cooking methods (boiled, braised, roasted,
         raw, steamed, ...) -- see `load_qualifiers()`'s docstring.
         Demoting them would rank raw meat above cooked for "chicken",
         which is backwards for a blenderized-feed tool (author,
         2026-08-20).
      7. alphabetically, as a stable last resort.

         This used to be "shortest description first", on the theory that
         CNF's terse entries are its basic foods. Measured against the
         file, that theory is wrong often enough to matter: it answered
         "chicken" with "Chicken, feet, boiled" (21 chars) ahead of
         "Chicken, broiler, breast, skinless, boneless, meat, braised"
         (59), and "milk" with "Milk, dry whole" ahead of every fluid
         milk. Short and basic are not the same thing. Alphabetical
         decides nothing about relevance -- tiers 1-6 have already done
         that -- it just stops length from pretending to (author,
         2026-08-15).

         Note what tiers 1-7 still cannot do (2026-08-20): nothing in a
         CNF description says breast is wanted more often than back, and
         nothing marks a plain sweet potato as more wanted than sweet
         potato LEAVES -- "sweet potato" still answers with the leaves
         first, because neither food carries an unrequested qualifier or
         differs on any tier above. Both need a curated preferred-foods
         list, the same shape as data/packs/<pack>/food_synonyms.csv.
    """
    # Each query token expanded to itself plus conservative singular
    # forms, computed ONCE for the whole query -- not per row -- because
    # this function's caller runs it on every keystroke against every
    # CNF row. See `_token_forms()`.
    token_forms = [_token_forms(token) for token in query_tokens]

    scored: list[tuple[tuple, int]] = []

    for position in range(len(index.frame)):
        desc_words = index.desc_tokens[position]
        alt_words = index.alt_tokens[position]

        matched_in_desc = True
        exact_words = 0
        for forms in token_forms:
            if any(form in desc_words for form in forms):
                exact_words += 1
                continue
            if any(word.startswith(form) for form in forms for word in desc_words):
                continue
            # Not in the description -- try the alternate names.
            if any(form in alt_words for form in forms) or any(
                word.startswith(form) for form in forms for word in alt_words
            ):
                matched_in_desc = False
                continue
            break
        else:
            description = index.frame["Food_Description_EN"].iat[position]
            headword = index.desc_headword[position]
            # Asked only of rows that already matched -- a few hundred at
            # most, against 5,993 scanned -- because this runs on every
            # keystroke. Skipped entirely for a token singularising left
            # alone: with one form, "as typed" is the only way the row
            # could have matched at all (2026-08-20).
            matched_as_typed = all(
                len(forms) == 1
                or forms[0] in desc_words
                or any(word.startswith(forms[0]) for word in desc_words)
                or forms[0] in alt_words
                or any(word.startswith(forms[0]) for word in alt_words)
                for forms in token_forms
            )
            sort_key = (
                0 if matched_in_desc else 1,
                0 if exact_words == len(query_tokens) else 1,
                (
                    0
                    if any(
                        h.startswith(form)
                        for h in headword
                        for forms in token_forms
                        for form in forms
                    )
                    else 1
                ),
                0 if matched_as_typed else 1,
                0 if index.desc_inverted[position] else 1,
                1 if _has_unrequested_qualifier(index, position, query_tokens) else 0,
                str(description).lower(),
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


def find_food(fn_df: pd.DataFrame, desc: str) -> int | None:
    """Find a Food_Code by description: an exact match if there is one,
    otherwise the first substring match.

    NOT the RD-facing search above -- this is the by-name lookup the app
    uses when IT already knows the exact CNF description it wants (the
    example day's ingredients, the water the Dilution What-If adds).
    Moved here from app/streamlit_app.py 2026-08-17; it needs no Streamlit
    and so can be tested.

    The exact pass matters because CNF descriptions nest. "Spinach,
    boiled, drained" is a substring of "New Zealand spinach, boiled,
    drained", so substring-only resolved the example day's spinach to the
    New Zealand one -- silently, and with different nutrients (author,
    2026-08-15). Every caller names a full CNF description, so preferring
    an exact hit costs nothing and removes a whole class of
    wrong-food-looks-right bug.
    """
    descriptions = fn_df["Food_Description_EN"]
    exact = fn_df[descriptions.str.casefold() == desc.casefold()]
    if len(exact):
        return int(exact.iloc[0]["Food_Code"])
    m = fn_df[descriptions.str.contains(desc, case=False, na=False, regex=False)]
    if len(m) == 0:
        return None
    return int(m.iloc[0]["Food_Code"])
