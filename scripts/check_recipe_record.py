"""AppTest for the recipe record: per-blend flow test + named chart note."""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at.run()
assert not at.exception, at.exception

# Load the example day so there is a blend + an intake log.
next(b for b in at.button if "example" in b.label.lower()).click().run()
assert not at.exception, at.exception

blends = at.session_state["blends"]
print(f"blends after example: {list(blends)}")

# 1. Every blend carries its own flow_test dict.
for bid, b in blends.items():
    assert "flow_test" in b, f"blend {bid} has no flow_test key"
print("OK: flow_test is stored per blend")

# 2. Drive the real widgets (NOT session_state directly -- a widget's
# value= only applies the first time its key is created, per CONTEXT.md
# §11, so writing state behind an existing widget gets overwritten).
first_id = sorted(blends)[0]
next(s for s in at.selectbox if s.key == f"flow_result_{first_id}").set_value("Passed").run()
next(t for t in at.text_area if t.key == f"flow_notes_{first_id}").set_value(
    "flowed through a 60 mL syringe without resistance"
).run()
next(d for d in at.date_input if d.key == f"flow_date_{first_id}").set_value(
    date(2026, 7, 30)
).run()
assert not at.exception, at.exception
assert at.session_state["blends"][first_id]["flow_test"]["result"] == "Passed"
print("OK: widget writes land on the blend's own flow_test")

# 3. The chart note names the blend the flow test belongs to.
note_blocks = [c.value for c in at.code]
note = next((n for n in note_blocks if "Flow test" in n), None)
assert note is not None, f"no chart note containing a flow test; code blocks: {len(note_blocks)}"
blend_name = at.session_state["blends"][first_id]["name"] or f"Blend {first_id}"
assert f"Flow test ({blend_name})" in note, f"blend not named in note:\n{note}"
assert "passed" in note
assert "60 mL syringe" in note
print(f"OK: chart note names the blend -> ...{note[note.index('Flow test'):][:90]}...")

# 4. A blend that was NOT fed today must not appear in the day's note.
unfed_id = at.session_state["next_blend_id"]
at.session_state["blends"][unfed_id] = {
    "name": "Never fed blend",
    "ingredients": [],
    "measured_volume_mL": 0.0,
    "flow_test": {"date": None, "result": "Passed", "notes": "should not appear"},
}
at.run()
assert not at.exception, at.exception
note2 = next(n for n in [c.value for c in at.code] if "Flow test" in n)
assert "Never fed blend" not in note2, "a blend not fed today leaked into the day's chart note"
print("OK: a blend not fed today stays out of the day's chart note")

# 5. Round-trip the REAL example blend through the recipe file: save it,
# read it back, resolve it against real CNF, and confirm every ingredient
# survives with its own code, grams, unit and fluid flag intact.
from src.recipe_io import (  # noqa: E402
    MATCH_BY_CODE,
    recipe_to_workbook_bytes,
    resolve_ingredients,
    workbook_bytes_to_recipe,
)
from src.data_loader import load_food_name  # noqa: E402

real_blend = at.session_state["blends"][first_id]
data = recipe_to_workbook_bytes(real_blend, real_blend["flow_test"])
parsed = workbook_bytes_to_recipe(data)

assert len(parsed.ingredients) == len(
    real_blend["ingredients"]
), f"{len(real_blend['ingredients'])} ingredients in -> {len(parsed.ingredients)} out"
assert parsed.measured_volume_mL == real_blend["measured_volume_mL"]
assert parsed.flow_test_result == "Passed"
assert parsed.flow_test_date == date(2026, 7, 30)

for original, loaded in zip(real_blend["ingredients"], parsed.ingredients):
    assert loaded["food_code"] == original["food_code"], original["food_description"]
    assert loaded["grams"] == original["grams"], original["food_description"]
    assert loaded["unit"] == original["unit"], original["food_description"]
    assert loaded["counts_as_fluid"] == original["counts_as_fluid"], original["food_description"]

resolved = resolve_ingredients(parsed, load_food_name())
assert all(r.status == MATCH_BY_CODE for r in resolved), [
    (r.source_text, r.status) for r in resolved if r.status != MATCH_BY_CODE
]
print(
    f"OK: round-tripped the real example blend -- {len(parsed.ingredients)} ingredients, "
    f"{parsed.measured_volume_mL:g} mL, all matched by code against real CNF"
)

print("\n=== RECIPE RECORD APPTEST PASSED ===")
