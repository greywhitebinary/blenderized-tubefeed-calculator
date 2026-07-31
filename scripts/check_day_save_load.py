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
