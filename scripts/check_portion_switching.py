"""AppTest: switching an ingredient's UNIT must not silently change its AMOUNT.

WHAT THIS GUARDS
----------------
The bug (author, 2026-08-24): the amount box holds a QUANTITY in whatever
measure is chosen ("2 of 1 cup"), but switching the measure used to keep
GRAMS fixed and rewrite the number in the box -- an ingredient at 257.819 g
shown as "1 x 250 ml", switched to "100 ml", silently became "2.5 x 100 ml".
Same 257.819 g, different number on screen.

The author's example: a banana bread entered as 1 loaf, switched to slice,
became 17.27 slices -- still one loaf's weight. The RD asked for one slice.

THE RULE
--------
1. portion -> portion: keep the NUMBER, recompute the WEIGHT.
   1 loaf (1036 g) switched to slice becomes 1 slice (60 g).
2. portion -> g, or g -> portion: keep the WEIGHT, recompute the NUMBER.
   Grams is a weight, not a count, so the number means something different
   on each side of that switch -- carrying it across would be absurd:
     - portion -> g:  1 slice (60 g) becomes 60 in the box, not 1.
     - g -> portion:  60 g becomes 1 slice, not 60 slices.
   This half already worked before the fix; it is pinned here too so the
   portion-to-portion fix cannot flip it by accident.

Uses "Banana, raw" (Food_Code 1704), which CNF gives several household
measures for -- see the "1 x 250 ml mashed" example already named in
streamlit_app.py's own comments, a few lines above the code this file
tests.

Per CONTEXT.md §11, widgets are driven (`.set_value().run()`), never
poked via session_state, once their key already exists. Ingredients here
are appended to session_state directly only ONCE each, before the row has
ever been rendered (so no widget key exists yet for it) -- exactly how a
loaded file or the example day hands the row its starting measure.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.measures import get_measures_for_food, load_measure_lookup  # noqa: E402

BANANA = 1704
lookup = load_measure_lookup()
_measures = {
    str(r["Measure_Description_and_Unit_EN"]): float(r["grams"])
    for _, r in get_measures_for_food(BANANA, lookup).iterrows()
}
MASHED_250ML = "250 ml mashed"
MEDIUM = "1 medium (18cm to 20cm long)"
SMALL = "1 small (15cm to 17.5cm long)"
for label in (MASHED_250ML, MEDIUM, SMALL):
    assert label in _measures, f"CNF measure list for banana changed, missing {label!r}"
GRAMS_PER_MASHED_250ML = _measures[MASHED_250ML]
GRAMS_PER_MEDIUM = _measures[MEDIUM]
GRAMS_PER_SMALL = _measures[SMALL]

at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at.run()
assert not at.exception, at.exception

blend_id = at.session_state.selected_blend_id
assert blend_id is not None, "no starter blend -- app init changed?"
ingredients = at.session_state.blends[blend_id]["ingredients"]

# --- Case 1: portion -> portion (the banana-bread case) --------------------
# Starts as "1 x 250 ml mashed" (237.755 g), exactly the example already
# named in the app's own comments.
ingredients.append(
    {
        "id": 101,
        "food_code": BANANA,
        "food_description": "Banana, raw",
        "grams": GRAMS_PER_MASHED_250ML,
        "unit": "g",
        "counts_as_fluid": False,
        "measure_label": MASHED_250ML,
        "measure_grams": GRAMS_PER_MASHED_250ML,
    }
)
at.run()
assert not at.exception, at.exception

start_box = next(n for n in at.number_input if n.key == f"grams_101_{MASHED_250ML}")
assert start_box.value == 1.0, f"sanity: expected 1 x {MASHED_250ML!r}, got {start_box.value}"

next(s for s in at.selectbox if s.key == "unit_101").set_value(MEDIUM).run()
assert not at.exception, at.exception

switched_box = next(n for n in at.number_input if n.key == f"grams_101_{MEDIUM}")
ing_101 = next(i for i in at.session_state.blends[blend_id]["ingredients"] if i["id"] == 101)
assert switched_box.value == 1.0, (
    f"portion -> portion must keep the NUMBER (banana bread: 1 loaf -> 1 slice, "
    f"not 17.27 slices); got {switched_box.value}"
)
assert ing_101["grams"] == GRAMS_PER_MEDIUM, (
    f"portion -> portion must recompute the WEIGHT from the new portion; "
    f"expected {GRAMS_PER_MEDIUM} g, got {ing_101['grams']}"
)
print(
    f"OK: portion -> portion: 1 x {MASHED_250ML!r} ({GRAMS_PER_MASHED_250ML} g) -> "
    f"{switched_box.value} x {MEDIUM!r} ({ing_101['grams']} g) -- number kept, weight moved"
)

# --- Case 2: portion -> g ----------------------------------------------
# Starts as "2 x 1 medium" (236 g). Switching to plain grams must show
# the WEIGHT (236), never the old count (2).
ingredients.append(
    {
        "id": 102,
        "food_code": BANANA,
        "food_description": "Banana, raw",
        "grams": 2 * GRAMS_PER_MEDIUM,
        "unit": "g",
        "counts_as_fluid": False,
        "measure_label": MEDIUM,
        "measure_grams": GRAMS_PER_MEDIUM,
    }
)
at.run()
assert not at.exception, at.exception

start_box = next(n for n in at.number_input if n.key == f"grams_102_{MEDIUM}")
assert start_box.value == 2.0, f"sanity: expected 2 x {MEDIUM!r}, got {start_box.value}"

next(s for s in at.selectbox if s.key == "unit_102").set_value("g").run()
assert not at.exception, at.exception

grams_box = next(n for n in at.number_input if n.key == "grams_102")
ing_102 = next(i for i in at.session_state.blends[blend_id]["ingredients"] if i["id"] == 102)
assert grams_box.value == 2 * GRAMS_PER_MEDIUM, (
    f"portion -> g must keep the WEIGHT, not the old count; "
    f"expected {2 * GRAMS_PER_MEDIUM} g, got {grams_box.value}"
)
assert ing_102["grams"] == 2 * GRAMS_PER_MEDIUM
print(f"OK: portion -> g: 2 x {MEDIUM!r} -> {grams_box.value} g -- weight kept")

# --- Case 3: g -> portion ----------------------------------------------
# Starts as a plain 100 g, no measure recorded (as a fresh search result,
# or a loaded file's plain-gram row, would look). Switching to a portion
# must show the DERIVED COUNT (100 / 101 = 0.99), never "100 smalls", and
# must leave the 100 g untouched.
ingredients.append(
    {
        "id": 103,
        "food_code": BANANA,
        "food_description": "Banana, raw",
        "grams": 100.0,
        "unit": "g",
        "counts_as_fluid": False,
        "measure_label": None,
        "measure_grams": None,
    }
)
at.run()
assert not at.exception, at.exception

start_box = next(n for n in at.number_input if n.key == "grams_103")
assert start_box.value == 100.0, f"sanity: expected 100 g, got {start_box.value}"

next(s for s in at.selectbox if s.key == "unit_103").set_value(SMALL).run()
assert not at.exception, at.exception

switched_box = next(n for n in at.number_input if n.key == f"grams_103_{SMALL}")
ing_103 = next(i for i in at.session_state.blends[blend_id]["ingredients"] if i["id"] == 103)
expected_qty = round(100.0 / GRAMS_PER_SMALL, 2)
assert switched_box.value == expected_qty, (
    f"g -> portion must derive the COUNT from the unchanged weight; "
    f"expected {expected_qty}, got {switched_box.value}"
)
assert (
    ing_103["grams"] == 100.0
), f"g -> portion must keep the WEIGHT; expected 100.0 g, got {ing_103['grams']}"
print(
    f"OK: g -> portion: 100 g -> {switched_box.value} x {SMALL!r} "
    f"({ing_103['grams']} g) -- weight kept"
)

print("\n=== PORTION SWITCHING APPTEST PASSED ===")
