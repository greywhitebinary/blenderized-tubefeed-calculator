"""Interactive-ish explorer for the three-layer food search ranking.

NOT a CI check -- a debugging aid for "I searched X and didn't like the
ranked list". Runs the real search against the real CNF and prints, for
each result, WHERE it ranked and WHY (the sort-key tiers from
src/food_search.py::_rows_matching):

    desc / alt    -- matched in the CNF description, or only in the
                     alternate/lay-name column
    exact         -- every query word matched a whole word rather than
                     landing as a prefix
    head          -- a query word prefixes the description's FIRST word:
                     "Milk, fluid, ..." IS milk, "Cracker, milk" merely
                     CONTAINS milk
    typed         -- matched the words AS TYPED, not only after
                     singularising ("greens", not "green")
    inv           -- inverted commodity filing ("Egg, chicken,") above a
                     dish name ("Egg Benedict") sharing that headword
    plain         -- carries no flavour/processing qualifier the query
                     did not ask for

A blank column means the row LOST that tier. The labels are read
positionally off the real sort key returned by `_rows_matching()`, never
recomputed here (2026-08-20): this script used to rebuild the tiers
itself and drifted two generations out of date -- it still described a
"shortest description first" tier eight days after that was replaced by
alphabetical, and it crashed outright once `desc_headword` became a
tuple. A tool that explains the ranking has to read the ranking.

Usage:
    python scripts/try_food_search.py "chicken egg" "egg, chicken" egg
    python scripts/try_food_search.py            # runs a built-in sample batch
    python scripts/try_food_search.py -n 15 egg  # show top 15 per query
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_food_name  # noqa: E402

# _rows_matching is private, and this script is the one caller with a
# reason to reach for it: its whole job is showing what that function
# decided, tier by tier.
from src.food_search import (  # noqa: E402
    _rows_matching,
    build_index,
    search_foods,
    tokenize,
)

SAMPLE_QUERIES = [
    "chicken egg",
    "egg, chicken",
    "egg",
    "rice",
    "beef",
    "milk",
    "peanut butter",
    "yogurt",
    "banana",
    "sweet potato",
]


_TIER_LABELS = ("desc", "exact", "head", "typed", "inv", "plain")


def explain(key_by_position, frame_row_position):
    """Render one row's real sort key as tier labels."""
    key = key_by_position.get(frame_row_position)
    if key is None:
        return "[not scored]"
    # Every tier but the last is 0 for "won" and 1 for "lost"; the last is
    # the description itself, the alphabetical tie-break. If the key ever
    # grows a tier this script doesn't know the name of, show the raw
    # numbers rather than mislabelling them -- silently attaching the
    # wrong name to a tier is how this tool went stale before.
    flags = key[:-1]
    if len(flags) != len(_TIER_LABELS):
        return f"[key {flags}]"
    shown = [label if value == 0 else " " * len(label) for label, value in zip(_TIER_LABELS, flags)]
    return "[" + "|".join(shown) + "]"


def main():
    args = sys.argv[1:]
    limit = 10
    if args[:1] == ["-n"]:
        limit = int(args[1])
        args = args[2:]
    queries = args or SAMPLE_QUERIES

    index = build_index(load_food_name())
    print(f"index: {len(index)} foods\n")

    for query in queries:
        result = search_foods(query, index, limit=limit)
        header = f"== {query!r} -> {result.match_type}"
        if result.interpreted_as:
            header += f" (interpreted as {result.interpreted_as!r})"
        print(header)
        if result.note:
            print(f"   note: {result.note}")
        if result.is_empty:
            print("   (no results)\n")
            continue
        tokens = tokenize(query if result.match_type == "direct" else result.interpreted_as)
        key_by_position = {position: key for key, position in _rows_matching(index, tokens)}
        # Map each returned row back to its position in the index frame so
        # we can show the sort-key tiers. Descriptions are unique in CNF.
        pos_by_desc = {d: i for i, d in enumerate(index.frame["Food_Description_EN"])}
        for rank, (_, row) in enumerate(result.matches.iterrows(), 1):
            desc = row["Food_Description_EN"]
            why = explain(key_by_position, pos_by_desc[desc])
            print(f"   {rank:2}. {why} {desc}")
        print()


if __name__ == "__main__":
    main()
