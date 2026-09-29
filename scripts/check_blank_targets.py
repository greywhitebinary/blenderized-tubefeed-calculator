"""AppTest for blank-means-not-entered on the Nutrition targets tab.

Since 2026-09-28 the target and weight fields start empty and can be
cleared back to empty, the same convention ENCalc uses. Everything past
the form still reads 0 as "no target" / "not provided", so this checks
the three places the two meet:

1. A fresh app shows every target and the weight as blank, not 0.
2. Clearing a target the example record set gives a dash for its
   target, % target and difference in the Daily Totals table, instead
   of an error or a 0 target.
3. A saved record reopens with its unset targets and weight blank, and
   its set ones restored.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.day_io import day_to_workbook_bytes, workbook_bytes_to_day  # noqa: E402
from src.report import DIFFERENCE_COLUMN  # noqa: E402
from src.targets import empty_targets  # noqa: E402

APP = str(ROOT / "app" / "streamlit_app.py")


def number_input(at, key):
    return next(n for n in at.number_input if n.key == key)


def daily_totals(at):
    tables = [
        df.value
        for df in at.dataframe
        if hasattr(df.value, "columns") and "Daily Total" in list(df.value.columns)
    ]
    assert tables, "no Daily Totals table rendered"
    return tables[0]


# --- 1. A fresh app starts blank ----------------------------------------
at = AppTest.from_file(APP, default_timeout=180)
at.run()
assert not at.exception, at.exception
for name in empty_targets():
    value = number_input(at, f"target_{name}").value
    assert value is None, f"target_{name} should start blank, got {value!r}"
assert number_input(at, "patient_weight_input").value is None
print("OK: every target and the weight start blank")

# --- 2. Clearing a target leaves nothing to compare against ---------------
next(b for b in at.button if "example" in b.label.lower()).click().run()
assert not at.exception, at.exception
assert number_input(at, "target_energy_kcal").value == 2250.0
assert number_input(at, "target_fat_g").value is None, "unset example targets stay blank"

energy = daily_totals(at).set_index("Nutrient").loc["Energy"]
assert energy[DIFFERENCE_COLUMN] != "—", energy

number_input(at, "target_energy_kcal").set_value(None).run()
assert not at.exception, at.exception
assert number_input(at, "target_energy_kcal").value is None
energy = daily_totals(at).set_index("Nutrient").loc["Energy"]
assert energy["Target"] == "—", energy
assert energy["% Target"] == "—", energy
assert energy[DIFFERENCE_COLUMN] == "—", energy
print("OK: clearing a target gives dashes in Daily Totals")

# --- 3. Save and reopen keeps blank as blank -----------------------------
number_input(at, "patient_weight_input").set_value(None).run()
assert not at.exception, at.exception
saved = day_to_workbook_bytes(
    label="Blank targets check",
    patient_weight=at.session_state["patient_weight_input"],
    weight_unit=at.session_state["weight_unit"],
    targets={name: at.session_state[f"target_{name}"] or 0.0 for name in empty_targets()},
    blends=at.session_state["blends"],
    intake_log=at.session_state["intake_log"],
    custom_foods=at.session_state["custom_foods"],
)
parsed = workbook_bytes_to_day(saved)
assert not parsed.warnings, parsed.warnings
assert "energy_kcal" not in parsed.targets, parsed.targets
assert parsed.targets.get("protein_g") == 100.0, parsed.targets

at2 = AppTest.from_file(APP, default_timeout=180)
at2.run()
at2.session_state["_apply_day"] = parsed
at2.run()
assert not at2.exception, at2.exception
assert number_input(at2, "target_energy_kcal").value is None
assert number_input(at2, "target_protein_g").value == 100.0
assert number_input(at2, "patient_weight_input").value is None
print("OK: a reopened record keeps unset targets and weight blank")
