"""AppTest: switching blends keeps your work, and the dropdown says so.

WHAT THIS GUARDS
----------------
The complaint (author, 2026-08-16): after adding foods to blend 1 and
switching to blend 2, nothing showed whether blend 1 survived, so it was
unclear whether something needed clicking first.

Nothing ever needed clicking -- ingredients write straight into
session_state as they are added -- but the app was silent about it, and a
button then labelled "Save recipe" implied otherwise. The fix was to put
each blend's item count in the selector, so blend 1 visibly still holds its
foods while blend 2 is open.

Two things are pinned here, and the FIRST is the one that matters:

1. Switching away and back does not lose a blend's ingredients. A
   screenshot cannot answer this; it is a state question.
2. The dropdown labels carry live counts, including the singular "1 item"
   and the empty "no items yet".

Label construction is the fragile part and the reason this file exists.
That code has been bitten twice: once by computing labels in format_func,
which Streamlit calls OUTSIDE the script run where st.session_state raises
and took six of the nine CI checks down with it; and once by reading names
off the stored blend rather than the "blend_name_<id>" widget, which made
the dropdown disagree with the name field six lines under it.

NOTE ON AppTest: selectbox.options returns the labels ALREADY FORMATTED,
not the raw option values. Calling format_func on them again yields
"Blend Whole-food blend - 9 items", which looks like an app bug and is not.
set_value() still takes the raw blend id.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

MARKER = "Marker food added to blend 1"


def main() -> None:
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
    at.run()
    assert not at.exception, at.exception

    next(b for b in at.button if "example" in b.label.lower()).click().run()
    assert not at.exception, at.exception

    def selector():
        return next(s for s in at.selectbox if s.key == "blend_selector")

    def labels():
        return list(selector().options)

    blend_ids = list(at.session_state["blends"].keys())
    assert len(blend_ids) >= 2, f"need two blends to switch between, got {blend_ids}"
    blend1, blend2 = blend_ids[0], blend_ids[1]
    print(f"labels on load: {labels()}")

    before = len(at.session_state["blends"][blend1]["ingredients"])
    at.session_state["next_ingr_id"] += 1
    at.session_state["blends"][blend1]["ingredients"].append(
        {
            "id": at.session_state["next_ingr_id"],
            "food_code": 9,
            "food_description": MARKER,
            "grams": 50.0,
            "unit": "g",
            "counts_as_fluid": False,
        }
    )
    at.run()
    assert not at.exception, at.exception
    assert any(
        f"{before + 1} items" in x for x in labels()
    ), f"the count did not follow the new ingredient: {labels()}"
    print(f"after adding:   {labels()}")

    # --- THE COMPLAINT: away, and back again.
    selector().set_value(blend2).run()
    assert not at.exception, at.exception
    assert at.session_state["selected_blend_id"] == blend2, "the selector did not switch"
    # Blend 1's count stays visible while blend 2 is the one being edited.
    # That is the whole point: the reassurance is continuous, not a message
    # shown once.
    assert any(
        f"{before + 1} items" in x for x in labels()
    ), f"blend 1's count vanished while blend 2 was open: {labels()}"
    print(f"while on blend2:{labels()}")

    selector().set_value(blend1).run()
    assert not at.exception, at.exception
    kept = at.session_state["blends"][blend1]["ingredients"]
    assert len(kept) == before + 1, f"blend 1 lost work: expected {before + 1}, got {len(kept)}"
    assert any(i["food_description"] == MARKER for i in kept), "the added food did not survive"
    print(f"back on blend1: {len(kept)} items, the added food survived")

    # --- Counts read correctly at 0 and at 1.
    at.session_state["blends"][blend2]["ingredients"] = []
    at.run()
    assert any(x.endswith("no items yet") for x in labels()), f"empty blend: {labels()}"
    print(f"emptied blend2: {labels()}")

    at.session_state["blends"][blend2]["ingredients"] = [
        {
            "id": 999,
            "food_code": 9,
            "food_description": "Only one",
            "grams": 1.0,
            "unit": "g",
            "counts_as_fluid": False,
        }
    ]
    at.run()
    assert any(x.endswith("· 1 item") for x in labels()), f"singular not handled: {labels()}"
    print(f"one item:       {labels()}")

    # --- The line that states it in words.
    captions = [c.value for c in at.caption if "stay saved while you switch" in c.value]
    assert captions, "the reassurance caption is missing from under the selector"
    print(f"caption:        {captions[0]}")

    print("\n=== BLEND SWITCHING APPTEST PASSED ===")


if __name__ == "__main__":
    main()
