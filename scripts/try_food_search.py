"""Interactive-ish explorer for the three-layer food search ranking.

NOT a CI check -- a debugging aid for "I searched X and didn't like the
ranked list". Runs the real search against the real CNF and prints, for
each result, WHERE it ranked and WHY (the three sort-key tiers from
src/food_search.py::_rows_matching):

    1. [desc] vs [alt]   -- matched in the CNF description, or only in
                            the alternate/lay-name column
    2. exact vs prefix   -- every query word matched a whole word, or at
                            least one was a prefix-only match
    3. head vs (absent)  -- a query word prefixes the description's FIRST
                            word: "Milk, fluid, ..." IS milk, while
                            "Cracker, milk" merely CONTAINS milk
    4. description length (shorter ranks first) breaks remaining ties

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
from src.food_search import build_index, search_foods, tokenize  # noqa: E402

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


def explain(index, query_tokens, frame_row_position):
    """Rebuild the sort key for one row so the ranking is inspectable."""
    desc_words = index.desc_tokens[frame_row_position]
    headword = index.desc_headword[frame_row_position]
    matched_in_desc = True
    exact_words = 0
    for token in query_tokens:
        if token in desc_words:
            exact_words += 1
        elif any(w.startswith(token) for w in desc_words):
            pass
        else:
            matched_in_desc = False
    where = "desc" if matched_in_desc else "alt "
    how = "exact " if exact_words == len(query_tokens) else "prefix"
    head = "head" if any(headword.startswith(t) for t in query_tokens) else "    "
    return f"[{where}|{how}|{head}]"


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
        # Map each returned row back to its position in the index frame so
        # we can show the sort-key tiers. Descriptions are unique in CNF.
        pos_by_desc = {d: i for i, d in enumerate(index.frame["Food_Description_EN"])}
        for rank, (_, row) in enumerate(result.matches.iterrows(), 1):
            desc = row["Food_Description_EN"]
            why = explain(index, tokens, pos_by_desc[desc])
            print(f"   {rank:2}. {why} {desc}")
        print()


if __name__ == "__main__":
    main()
