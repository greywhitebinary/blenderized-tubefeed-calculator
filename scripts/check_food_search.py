"""AppTest for the three-layer CNF food search in the running app.

The unit tests in tests/test_food_search.py prove the search module is
correct against a hand-built fixture. This proves the app is actually
WIRED to it, against the real 5,993-food CNF -- which is a separate
claim, and the one that broke before: the old search box worked fine as
Python and still returned nothing for "wild rice".

Per CONTEXT.md §11, widgets are driven (`.set_value().run()`), never
poked via session_state -- a widget's `value=` only applies the first
time its key is created, so writing state behind a live widget is
silently discarded.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at.run()
assert not at.exception, at.exception

# The blend tab's add-food component. Its search box key is
# "<key_prefix>_search"; find whichever prefix this build uses rather
# than hardcoding one, so a key_prefix rename doesn't silently skip.
search_boxes = [t for t in at.text_input if t.key and t.key.endswith("_search")]
assert search_boxes, f"no search box found; text_input keys: {[t.key for t in at.text_input]}"
box_key = search_boxes[0].key
print(f"search box: {box_key}")


def search(term):
    """Type `term` into the real search box and return the options offered."""
    next(t for t in at.text_input if t.key == box_key).set_value(term).run()
    assert not at.exception, at.exception
    selects = [s for s in at.selectbox if s.key and s.key.endswith("_food_select")]
    return list(selects[0].options) if selects else []


# --- Layer 1: the exact failure that motivated the rework --------------
# "wild rice" is filed by CNF as "Grains, rice, wild, dry". A substring
# search returns zero results for this, which is how a real food came to
# be counted as missing from the database.
options = search("wild rice")
assert options, "'wild rice' found nothing -- layer 1 is not wired up"
assert any("wild" in o.lower() and "rice" in o.lower() for o in options), options
print(f"OK: 'wild rice' -> {len(options)} results, first: {options[0]}")

options = search("greek yogurt")
assert options, "'greek yogurt' found nothing"
assert any("greek" in o.lower() for o in options), options
print(f"OK: 'greek yogurt' -> {len(options)} results, first: {options[0]}")

# --- Layer 1: CNF's own alternate-names column -------------------------
# "hamburger" appears in Alternate_Description_EN, never in the
# description "Beef, ground, ...". The old search never read that column.
options = search("hamburger")
assert options, "'hamburger' found nothing -- alternate names not searched"
print(f"OK: 'hamburger' -> {len(options)} results, first: {options[0]}")

# --- Layer 2: typo tolerance, and it must announce itself --------------
options = search("brocolli")
assert options, "'brocolli' found nothing -- layer 2 is not wired up"
assert any("broccoli" in o.lower() for o in options), options
captions = [c.value for c in at.caption]
assert any("broccoli" in c for c in captions), (
    "the app corrected the spelling but never told the RD; " f"captions were: {captions}"
)
print(f"OK: 'brocolli' -> {len(options)} results, and the app says so")

# --- Layer 3: curated synonym ------------------------------------------
options = search("courgette")
assert options, "'courgette' found nothing -- layer 3 is not wired up"
assert any("zucchini" in o.lower() for o in options), options
captions = [c.value for c in at.caption]
assert any("zucchini" in c for c in captions), f"synonym not explained; captions: {captions}"
print(f"OK: 'courgette' -> {len(options)} results, first: {options[0]}")

# --- The safety property: no confident nonsense ------------------------
# CNF has no skyr. At a looser fuzzy threshold the search answered this
# with a Skor chocolate bar. Finding nothing is the correct answer, and
# it is what sends the RD to the custom-food form.
options = search("skyr")
assert not options, f"'skyr' should find nothing in CNF, got: {options[:5]}"
print("OK: 'skyr' correctly finds nothing rather than a lookalike")

print("=== FOOD SEARCH APPTEST PASSED ===")
