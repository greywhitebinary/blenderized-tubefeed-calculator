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

# 2b. A hand-edited flow-test cell must never crash the Feed Recipes tab
# (2026-08-20 review, fix 2). Neither src/recipe_io.py nor src/day_io.py
# constrains flow_test["result"] -- it is free text off a loaded file --
# and the widget used to do `_ft_results.index(_ft_current)` on it
# directly, which raised ValueError for anything not an exact match.
#
# Case/whitespace-tolerant match: "passed" (lowercase, stray whitespace)
# must resolve to "Passed" with no crash and no reset. Only the SELECTED
# blend's flow-test expander renders, and its widget is only ever
# instantiated once selected -- so the free-text value is written into
# the blend's OWN flow_test dict (exactly where a loaded file's value
# would land) BEFORE the blend is ever selected, reproducing how this
# actually happens: a blend rendering for the first time this session
# with an odd value already sitting in flow_test["result"].
second_id = sorted(blends)[1]
at.session_state["blends"][second_id]["flow_test"]["result"] = "  passed  "
next(s for s in at.selectbox if s.key == "blend_selector").set_value(second_id).run()
assert not at.exception, at.exception
assert (
    next(s for s in at.selectbox if s.key == f"flow_result_{second_id}").value == "Passed"
), "a lowercase/whitespace 'passed' from a file should resolve to 'Passed'"
print("OK: 'passed' (lowercase, whitespace) resolves to 'Passed' without crashing")

# A value that matches nothing must fall back to the safe default and
# tell the RD, rather than crash. A THIRD, never-before-selected blend --
# second_id's flow_result widget now already exists this session, and
# mutating an existing widget's backing value other than by driving the
# widget itself is not a real scenario (that is the same §11 rule the app
# code documents throughout streamlit_app.py).
third_id = at.session_state["next_blend_id"]
at.session_state["blends"][third_id] = {
    "name": "Third blend",
    "ingredients": [],
    "measured_volume_mL": 0.0,
    "flow_test": {"date": None, "result": "Excellent flow", "notes": ""},
}
at.session_state["next_blend_id"] = third_id + 1
# A plain rerun first, so the selector's own .options picks up the new
# blend before set_value() validates against it.
at.run()
assert not at.exception, at.exception
next(s for s in at.selectbox if s.key == "blend_selector").set_value(third_id).run()
assert not at.exception, at.exception
assert (
    next(s for s in at.selectbox if s.key == f"flow_result_{third_id}").value == "Not done"
), "an unrecognised saved value must fall back to 'Not done', never crash"
notes = " ".join(n.value for n in at.markdown if n.value)
assert "Excellent flow" in notes and "Not done" in notes, (
    "the RD is not told which unrecognised value was reset -- " f"notes seen: {notes[:400]}"
)
print(
    "OK: an unrecognised saved value ('Excellent flow') resets to 'Not done' and is named on screen"
)

# Back to first_id -- the sections below assume it is selected.
next(s for s in at.selectbox if s.key == "blend_selector").set_value(first_id).run()
assert not at.exception, at.exception

# 3. The flow test is NOT in the chart note (2026-08-10). The note is the
# delivery-method line plus totals by category, nothing else. Attribution
# to the right recipe is still guarded -- by the per-blend widgets above
# and by the recipe-file round-trip in section 5.
note_blocks = [c.value for c in at.code]
assert note_blocks, "no chart note rendered"
assert all(
    "Flow test" not in (n or "") for n in note_blocks
), f"flow test is back in the chart note:\n{note_blocks}"
print("OK: chart note carries no flow test")

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
note2 = "\n".join(c.value or "" for c in at.code)
assert "Never fed blend" not in note2, "a blend not fed today leaked into the day's chart note"
print("OK: a blend not fed today stays out of the day's chart note")

# 5. Round-trip the REAL example blend through the recipe file: save it,
# read it back, resolve it against real CNF, and confirm every ingredient
# survives with its own code, grams, unit and fluid flag intact.
from src.recipe_io import (
    recipes_to_workbook_bytes,
    workbook_bytes_to_recipes,  # noqa: E402
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

# --- 6. A file holding SEVERAL blends, straight out of the app ---------
# The app can hold several BTFs at once, so its export has to as well
# (author, 2026-07-30). The risk being pinned here is not "does it save"
# -- it is that two recipes could be pooled into one blend on the way
# back in, inventing a feed nobody wrote whose kcal/mL looks plausible.
second_id = _new_second_blend = at.session_state["next_blend_id"]
at.session_state["blends"][second_id] = {
    "name": "Evening blend",
    "ingredients": [
        dict(real_blend["ingredients"][0], id=901),
        dict(real_blend["ingredients"][1], id=902),
    ],
    "measured_volume_mL": 640.0,
    "flow_test": {"date": None, "result": "Too thick", "notes": "clogged the 14 Fr"},
}
at.session_state["next_blend_id"] = second_id + 1
at.run()
assert not at.exception, at.exception

savable = [
    (b, b.get("flow_test"))
    for _bid, b in sorted(at.session_state["blends"].items())
    if b["ingredients"]
]
# The example day itself now ships TWO blends (Whole-food + Vegan), and
# this script adds a third. Derive the count rather than pinning it, so
# the check is "every blend with ingredients round-trips" -- which is what
# it is actually for -- instead of a number that changes with the example.
assert len(savable) == 3, f"expected 3 savable blends, got {len(savable)}"

multi = recipes_to_workbook_bytes(savable)
recipes = workbook_bytes_to_recipes(multi)
assert len(recipes) == len(savable), f"{len(savable)} blends saved -> {len(recipes)} read back"

by_name = {r.name: r for r in recipes}
assert set(by_name) == {"Whole-food blend", "Vegan blend", "Evening blend"}, list(by_name)
assert len(by_name["Whole-food blend"].ingredients) == len(real_blend["ingredients"])
assert len(by_name["Evening blend"].ingredients) == 2
assert by_name["Evening blend"].measured_volume_mL == 640.0

# Each blend keeps its OWN flow test -- the mixed case (one dated, one
# not) is where a blank date used to come back as pandas NaT.
assert by_name["Whole-food blend"].flow_test_result == "Passed"
assert by_name["Whole-food blend"].flow_test_date == date(2026, 7, 30)
assert by_name["Evening blend"].flow_test_result == "Too thick"
assert by_name["Evening blend"].flow_test_date is None, by_name["Evening blend"].flow_test_date

# Every ingredient of both blends still resolves against real CNF.
fn_df = load_food_name()
for name, recipe in by_name.items():
    statuses = [r.status for r in resolve_ingredients(recipe, fn_df)]
    assert all(s == MATCH_BY_CODE for s in statuses), (name, statuses)

print(
    f"OK: {len(savable)} blends -> one file -> {len(recipes)} blends back "
    f"({len(by_name['Whole-food blend'].ingredients)} + "
    f"{len(by_name['Evening blend'].ingredients)} ingredients), "
    "each with its own flow test, all matched by code"
)

# A v1 file (single recipe, no link columns) must still open.
v1 = recipe_to_workbook_bytes(real_blend, {"date": None, "result": "Passed", "notes": ""})
assert len(workbook_bytes_to_recipes(v1)) == 1
print("OK: a single-recipe file still reads as exactly one recipe")

# --- 7. Custom-food import through the REAL upload/confirm UI, and the
# code-collision case specifically (Format v3, 2026-08-20). A file's
# negative custom-food codes are file-scoped: the session may already
# hold a DIFFERENT food under the same code. Confirming an imported
# recipe must renumber the file's code onto a fresh one -- an imported
# ingredient must never end up silently pointing at whatever the session
# happened to already have at that code.
at.session_state["custom_foods"] = {-1: {"energy_kcal": 999.0}}
at.session_state["next_custom_code"] = -2
at.run()
assert not at.exception, at.exception

custom_blend = {
    "name": "Imported blend",
    "measured_volume_mL": 500.0,
    "ingredients": [
        {
            "food_code": -1,
            "food_description": "Homemade formula (custom)",
            "grams": 250.0,
            "unit": "mL",
            "counts_as_fluid": True,
        }
    ],
}
custom_data = recipe_to_workbook_bytes(
    custom_blend, custom_foods={-1: {"energy_kcal": 111.0, "protein_g": 5.0}}
)

uploader = next(f for f in at.file_uploader if f.label == "Load a recipe")
uploader.set_value(
    (
        "imported.xlsx",
        custom_data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
).run()
assert not at.exception, at.exception

confirm_btn = next(b for b in at.button if b.key == "recipe_import_confirm")
assert not confirm_btn.disabled, "the custom-food row should need no confirmation to be usable"
confirm_btn.click().run()
assert not at.exception, at.exception

# The pre-existing session food at -1 must be untouched...
assert at.session_state["custom_foods"][-1] == {
    "energy_kcal": 999.0
}, "importing a colliding custom code corrupted the session's existing food"
# ...and the imported ingredient must have landed on a NEW code, with its
# own values copied in under that code.
imported_blend_id = max(at.session_state["blends"])
imported = at.session_state["blends"][imported_blend_id]
assert imported["name"] == "Imported blend"
[imported_ingredient] = imported["ingredients"]
new_code = imported_ingredient["food_code"]
assert new_code != -1, "imported ingredient still points at the pre-existing session code"
assert at.session_state["custom_foods"][new_code] == {
    "energy_kcal": 111.0,
    "protein_g": 5.0,
}
print(
    f"OK: colliding custom code -1 remapped to {new_code} on import; "
    "the pre-existing session food at -1 was untouched"
)

# --- 8. "Load example record" must not corrupt a label-entered custom
# food that survives it (2026-08-20 review, fix 1). The handler used to
# wipe custom_foods unconditionally and rewind next_custom_code to -1,
# even though the blend filter it runs right after (streamlit_app.py,
# "Load example record" handler) only drops EMPTY blends -- a blend
# already carrying a label-entered (negative-code) food survives that
# filter. Wiping custom_foods then blanked the surviving blend's
# nutrients, and rewinding the counter to -1 handed that same vacated
# code straight back out to the next label typed, so the surviving blend
# would go on to silently pull a DIFFERENT food's numbers.
#
# Fresh app instance so this isn't tangled up with the custom-food state
# section 7 already built. Drives the REAL "add custom food" UI (same
# flow as check_label_photo_fill.py) rather than writing to
# session_state directly, so the code allocation is exercised exactly as
# an RD triggers it.
at3 = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at3.run()
assert not at3.exception, at3.exception


def _add_food_prefix(app) -> str:
    # Re-derived every time rather than cached: the add-food component's
    # key_prefix is f"blend_{selected_blend_id}", so it changes whenever
    # the selected blend changes (as "Load example record" does).
    prefixes = {
        t.key.rsplit("_search", 1)[0] for t in app.text_input if t.key and t.key.endswith("_search")
    }
    assert prefixes, [t.key for t in app.text_input]
    return sorted(prefixes)[0]


def _type_label_food(app, prefix: str, name: str, energy: float, protein: float, amount: float):
    mode = next(r for r in app.radio if r.key and r.key.endswith("_add_mode"))
    label_option = next(o for o in mode.options if "abel" in o)
    mode.set_value(label_option).run()
    assert not app.exception, app.exception
    next(x for x in app.text_input if x.key == f"{prefix}_cname").set_value(name).run()
    next(n for n in app.number_input if n.key == f"{prefix}_cv_serving").set_value(amount).run()
    next(n for n in app.number_input if n.key == f"{prefix}_cv_energy").set_value(energy).run()
    next(n for n in app.number_input if n.key == f"{prefix}_cv_protein_g").set_value(protein).run()
    next(n for n in app.number_input if n.key == f"{prefix}_cgrams").set_value(amount).run()
    assert not app.exception, app.exception
    blend_id = app.session_state["selected_blend_id"]
    before = len(app.session_state["blends"][blend_id]["ingredients"])
    next(b for b in app.button if b.key == f"{prefix}_add_custom_btn").click().run()
    assert not app.exception, app.exception
    after_ingredients = app.session_state["blends"][blend_id]["ingredients"]
    assert len(after_ingredients) == before + 1, "the label-entered food was not added"
    return after_ingredients[-1]["food_code"]


seeded_blend_id = at3.session_state["selected_blend_id"]
# amount == serving size (100.0), so the per-100g value stored in
# custom_foods equals the entered label figure exactly -- easier to
# assert on directly than working through label_to_per_100g's scaling.
seeded_code = _type_label_food(
    at3, _add_food_prefix(at3), "Homemade formula, from label", 300.0, 12.0, 100.0
)
assert seeded_code < 0, f"expected a custom (negative) food code, got {seeded_code}"
assert at3.session_state["custom_foods"][seeded_code]["energy_kcal"] == 300.0
print(f"OK: label-entered food seeded at custom code {seeded_code}")

next(b for b in at3.button if "example" in b.label.lower()).click().run()
assert not at3.exception, at3.exception

assert seeded_blend_id in at3.session_state["blends"], "the surviving blend was dropped"
surviving = at3.session_state["blends"][seeded_blend_id]["ingredients"]
assert any(
    i["food_code"] == seeded_code for i in surviving
), "the surviving blend no longer references its label-entered food"
assert at3.session_state["custom_foods"].get(seeded_code, {}).get("energy_kcal") == 300.0, (
    "the surviving blend's custom food lost its nutrients -- custom_foods "
    f"now holds {at3.session_state['custom_foods']}"
)
print(f"OK: surviving blend's custom food (code {seeded_code}) kept its nutrients")

# The counter must not have been handed back to -1 while seeded_code is
# still in use -- that is the silent-collision half of the bug.
assert at3.session_state["next_custom_code"] < seeded_code, (
    f"next_custom_code ({at3.session_state['next_custom_code']}) can still "
    f"collide with the still-referenced code {seeded_code}"
)
print(f"OK: next_custom_code moved to {at3.session_state['next_custom_code']}, past {seeded_code}")

# A SECOND label food, typed after "Load example record", must not be
# handed seeded_code (or any other code still in custom_foods).
new_code = _type_label_food(
    at3, _add_food_prefix(at3), "Second label-entered food", 150.0, 5.0, 100.0
)
assert new_code != seeded_code, "the newly typed food was handed the still-in-use code"
assert (
    at3.session_state["custom_foods"][seeded_code]["energy_kcal"] == 300.0
), "adding the second label food corrupted the first one's nutrients"
print(f"OK: the newly typed food got code {new_code}, not the still-referenced {seeded_code}")

print("\n=== RECIPE RECORD APPTEST PASSED ===")
