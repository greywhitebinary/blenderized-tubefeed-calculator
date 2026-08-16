"""AppTest for saving and reopening a whole day.

The unit tests prove the file layer round-trips. This proves the APP
does: that the day the user is looking at is the day that gets written,
and that reopening it restores the widgets too -- the targets and the
patient label live in Streamlit widget state, which is exactly the thing
that silently doesn't get set if you write it at the wrong moment
(CONTEXT.md §11).

Uses the real example day, so the numbers are a real 9-ingredient blend
against real CNF rather than a fixture.
"""

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.day_io import (  # noqa: E402
    day_to_workbook_bytes,
    workbook_bytes_to_day,
)

at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at.run()
assert not at.exception, at.exception

# --- Build a real day -------------------------------------------------
next(b for b in at.button if "example" in b.label.lower()).click().run()
assert not at.exception, at.exception

# Set a patient label and two targets through the real widgets, so this
# tests what an RD would actually have on screen.
next(t for t in at.text_input if t.key == "recipe_name_input").set_value(
    "James W, H&N RT wk 5"
).run()
next(n for n in at.number_input if n.key == "target_energy_kcal").set_value(2000.0).run()
next(n for n in at.number_input if n.key == "target_protein_g").set_value(95.0).run()
next(n for n in at.number_input if n.key == "patient_weight_input").set_value(62.5).run()
assert not at.exception, at.exception

blends_before = at.session_state["blends"]
log_before = at.session_state["intake_log"]
label_before = at.session_state["recipe_name_input"]
print(
    f"day on screen: {len(blends_before)} blend(s), {len(log_before)} intake rows, label {label_before!r}"
)
assert len(log_before) > 10, "example day should have a full intake record"

# --- Save it ----------------------------------------------------------
saved = day_to_workbook_bytes(
    label=label_before,
    patient_weight=at.session_state["patient_weight_input"],
    weight_unit=at.session_state["weight_unit"],
    targets={
        "energy_kcal": at.session_state["target_energy_kcal"],
        "protein_g": at.session_state["target_protein_g"],
    },
    blends=blends_before,
    intake_log=log_before,
    custom_foods=at.session_state["custom_foods"],
)
parsed = workbook_bytes_to_day(saved)
assert not parsed.warnings, parsed.warnings
print(f"saved and re-read: {parsed.summary}")

# --- Wipe the session, then reopen the day ----------------------------
# A fresh app is the honest test: reopening a day has to work in the
# browser someone opens tomorrow, not just in the session that saved it.
at2 = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at2.run()
assert not at2.exception, at2.exception
assert at2.session_state["intake_log"] == [], "a fresh app should start empty"

at2.session_state["_apply_day"] = parsed
at2.run()
assert not at2.exception, at2.exception

# --- Everything must be back ------------------------------------------
assert len(at2.session_state["blends"]) == len(blends_before), at2.session_state["blends"]
assert len(at2.session_state["intake_log"]) == len(log_before), len(at2.session_state["intake_log"])

restored_blend = at2.session_state["blends"][min(at2.session_state["blends"])]
original_blend = blends_before[min(blends_before)]
assert restored_blend["name"] == original_blend["name"]
assert restored_blend["measured_volume_mL"] == original_blend["measured_volume_mL"]
assert len(restored_blend["ingredients"]) == len(original_blend["ingredients"])
for before, after in zip(original_blend["ingredients"], restored_blend["ingredients"]):
    assert after["food_code"] == before["food_code"], before["food_description"]
    assert after["grams"] == before["grams"], before["food_description"]
    assert after["unit"] == before["unit"], before["food_description"]
    assert after["counts_as_fluid"] == before["counts_as_fluid"], before["food_description"]
print(
    f"OK: blend restored -- {len(restored_blend['ingredients'])} ingredients, every code/gram/unit/fluid flag"
)

# Every source type survives, not just blends.
types_before = sorted({r["source_type"] for r in log_before})
types_after = sorted({r["source_type"] for r in at2.session_state["intake_log"]})
assert types_before == types_after, (types_before, types_after)
print(f"OK: intake record restored -- {len(log_before)} rows covering {', '.join(types_after)}")

# The widget-backed values are the ones that silently fail to apply if
# they're written after their widget exists. Check them through the
# rendered widgets, not just session_state.
assert at2.session_state["recipe_name_input"] == label_before
assert next(n for n in at2.number_input if n.key == "target_energy_kcal").value == 2000.0
assert next(n for n in at2.number_input if n.key == "target_protein_g").value == 95.0
assert next(n for n in at2.number_input if n.key == "patient_weight_input").value == 62.5
print("OK: label, weight and targets restored into the real widgets")

# The restored day must actually compute. A day that loads but shows no
# totals would look fine in session_state and be useless on screen.
totals_tables = [
    df.value
    for df in at2.dataframe
    if hasattr(df.value, "columns") and "Daily Total" in list(df.value.columns)
]
assert totals_tables, "restored day rendered no daily totals table"
energy = totals_tables[0][totals_tables[0]["Nutrient"] == "Energy"]
assert not energy.empty and float(energy.iloc[0]["Daily Total"]) > 0, energy
print(f"OK: restored day still computes -- energy {float(energy.iloc[0]['Daily Total']):,.0f} kcal")

print("\n=== DAY SAVE/LOAD APPTEST PASSED ===")

# --- Same-session reopen: the bug the fresh-session test above cannot see ---
#
# The section above passes precisely because at2 is a BRAND NEW AppTest --
# no widget with key "vol_{bid}" or "grams_{ing_id}" has ever been created
# in that session, so there's nothing stale for the loaded values to
# collide with. That's exactly why the real bug (opening a saved day
# mid-session silently keeps the OLD on-screen numbers instead of the
# file's) went unnoticed: it only shows up when the same session that
# built/saved the day is still open and its per-blend/per-ingredient
# widgets already hold values under the same ids the reopened file uses.
at3 = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at3.run()
assert not at3.exception, at3.exception

next(b for b in at3.button if "example" in b.label.lower()).click().run()
assert not at3.exception, at3.exception

bid = min(at3.session_state["blends"])

# Target an ingredient shown in GRAMS, not one shown in a household
# measure. An ingredient carrying a measure_label renders its amount box
# under "grams_{id}_{unit}" (the unit is in the key so switching units
# re-seeds the box); only a grams-mode row uses the plain "grams_{id}"
# this test drives. The example day now gives most of its ingredients a
# CNF measure, so ask for the grams-mode one rather than assuming index 0.
_ings = at3.session_state["blends"][bid]["ingredients"]
ing_idx = next(i for i, ing in enumerate(_ings) if not ing.get("measure_label"))
ing_id = _ings[ing_idx]["id"]

# What the example day actually put on screen, read from the app rather
# than hard-coded. This used to pin a literal 257.0; the example's weights
# now come from CNF at runtime, and pinning one meant this check broke the
# moment the example changed without testing anything more than it does.
in_session_grams0 = float(_ings[ing_idx]["grams"])

# Save the day exactly as it stands right now (1000 mL, and whatever the
# example's first ingredient weighs) BEFORE touching any widget.
saved3 = day_to_workbook_bytes(
    label=at3.session_state["recipe_name_input"],
    patient_weight=at3.session_state["patient_weight_input"],
    weight_unit=at3.session_state["weight_unit"],
    targets={
        "energy_kcal": at3.session_state["target_energy_kcal"],
        "protein_g": at3.session_state["target_protein_g"],
    },
    blends=at3.session_state["blends"],
    intake_log=at3.session_state["intake_log"],
    custom_foods=at3.session_state["custom_foods"],
)
parsed3 = workbook_bytes_to_day(saved3)
assert not parsed3.warnings, parsed3.warnings

# Snapshot the FILE's values with a deep copy right now, before anything
# else touches `parsed3`. Without the deepcopy this assertion is vacuous:
# _apply_saved_day() (once fixed) hands session_state.blends a COPY of
# parsed3.blends, but the app then mutates whatever it was handed in
# place -- so a plain alias here would silently change out from under this
# very assertion and "pass" even with the old aliasing bug back in place.
# This is a real trap; it fooled the author of this test once.
expected_volume = copy.deepcopy(parsed3.blends[bid]["measured_volume_mL"])
expected_grams0 = copy.deepcopy(parsed3.blends[bid]["ingredients"][ing_idx]["grams"])
assert expected_volume == 1000.0, expected_volume
# The file must carry what was on screen -- and it must not be the 11.0
# this test is about to type in, or the round-trip assertion below would
# pass vacuously.
assert expected_grams0 == in_session_grams0, (expected_grams0, in_session_grams0)
assert expected_grams0 != 11.0, expected_grams0

# Now edit the SAME blend/ingredient through the real on-screen widgets,
# to values that do NOT appear anywhere in the saved file.
next(n for n in at3.number_input if n.key == f"vol_{bid}").set_value(400.0).run()
next(n for n in at3.number_input if n.key == f"grams_{ing_id}").set_value(11.0).run()
assert not at3.exception, at3.exception
assert at3.session_state["blends"][bid]["measured_volume_mL"] == 400.0
assert at3.session_state["blends"][bid]["ingredients"][ing_idx]["grams"] == 11.0

# Reopen the saved day -- in this SAME session, where "vol_{bid}" and
# "grams_{ing_id}" already hold the edited 400/11 values above.
at3.session_state["_apply_day"] = parsed3
at3.run()
assert not at3.exception, at3.exception

restored_volume = at3.session_state["blends"][bid]["measured_volume_mL"]
restored_grams0 = at3.session_state["blends"][bid]["ingredients"][ing_idx]["grams"]
assert (
    restored_volume == expected_volume
), f"expected the file's volume {expected_volume}, got stale on-screen value {restored_volume}"
assert (
    restored_grams0 == expected_grams0
), f"expected the file's grams {expected_grams0}, got stale on-screen value {restored_grams0}"
print(
    f"OK: same-session reopen restored the file's numbers "
    f"(volume {restored_volume:.0f} mL, ingredient[0] {restored_grams0:.0f} g) "
    "instead of the stale on-screen 400/11"
)

print("\n=== SAME-SESSION REOPEN PASSED ===")
