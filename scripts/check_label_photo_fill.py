"""AppTest for a label photo filling the Nutrition Facts form.

No API key and no API call. The extraction result is staged directly
into session state, which is precisely the handover this test exists to
check: the photo handler stages an ExtractedLabel and reruns, and the
form applies it on the next run.

WHY THIS EXISTS. The first working extraction crashed the app:

    StreamlitAPIException: st.session_state.blend_0_basis cannot be
    modified after the widget with key blend_0_basis is instantiated

The handler sits below the "Label basis" radio, so writing that widget's
state was illegal -- the §11 gotcha, in a file that documents the §11
gotcha. Reordering alone would have fixed it and stayed fragile, so the
drafts are now applied at the top of the component, above every widget.
This test pins that, and it would have caught the crash without spending
a cent or needing a photo.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.label_extract import ExtractedLabel  # noqa: E402

at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
at.run()
assert not at.exception, at.exception

# The blend tab's add-food component. Find its prefix rather than
# hardcoding "blend_0", so a rename fails loudly here instead of silently
# skipping the test.
prefixes = {
    t.key.rsplit("_search", 1)[0] for t in at.text_input if t.key and t.key.endswith("_search")
}
assert prefixes, [t.key for t in at.text_input]
prefix = sorted(prefixes)[0]
print(f"add-food component prefix: {prefix}")

# Switch to the Nutrition Facts entry mode so the form exists.
mode = next(r for r in at.radio if r.key and r.key.endswith("_add_mode"))
label_option = next(o for o in mode.options if "abel" in o)
mode.set_value(label_option).run()
assert not at.exception, at.exception

# A label with a deliberate mix: values present, a printed zero, and two
# nutrients with no line at all.
staged = ExtractedLabel(
    food_name="Ensure Plus Vanilla",
    serving_amount=235.0,
    serving_unit="mL",
    values={
        "energy_kcal": 350.0,
        "protein_g": 13.0,
        "trans_fat_g": 0.0,
        "sodium_mg": 240.0,
    },
    missing=["fibre_g", "potassium_mg"],
    notes="",
)
at.session_state[f"{prefix}_photo_pending"] = staged
at.run()
assert not at.exception, at.exception
print("OK: applying staged drafts does not raise StreamlitAPIException")


def value_of(key):
    return next(n for n in at.number_input if n.key == key).value


assert at.session_state[f"{prefix}_cname"] == "Ensure Plus Vanilla"
assert value_of(f"{prefix}_cv_serving") == 235.0
print("OK: name and serving size filled -- 235.0 mL")

# The basis radio is the widget that caused the crash. It must have
# flipped to volume, because the label says mL.
basis = next(r for r in at.radio if r.key == f"{prefix}_basis")
assert "volume" in basis.value, basis.value
print(f"OK: basis switched to {basis.value!r} from the label's unit")

assert value_of(f"{prefix}_cv_energy") == 350.0
assert value_of(f"{prefix}_cv_protein_g") == 13.0
assert value_of(f"{prefix}_cv_sodium_mg") == 240.0
print("OK: energy, protein and sodium filled from the label")

# A printed "Trans 0 g" is a measurement and must be filled in as 0.
assert value_of(f"{prefix}_cv_trans_fat_g") == 0.0
print("OK: a printed 0 was filled in as a real value")

# Nutrients with NO line on the label are left alone at the form's own
# default. The RD is told which ones, and decides. This is the whole
# never-fabricate rule, checked at the UI rather than in the parser.
assert value_of(f"{prefix}_cv_fibre_g") == 0.0
assert value_of(f"{prefix}_cv_potassium_mg") == 0.0
captions = " ".join(c.value for c in at.caption)
assert "Fibre" in captions and "Potassium" in captions, captions
assert "left alone" in captions, captions
print("OK: missing nutrients are named on screen rather than passed off as 0")

# The staging key must be consumed, or the drafts would reapply on every
# rerun and stamp over anything the RD corrects.
assert f"{prefix}_photo_pending" not in at.session_state
print("OK: staged drafts are consumed once, so RD edits are not overwritten")

# --- A SECOND label must not inherit the first one's numbers ----------
# The form used to keep everything after a food was added, so adding
# Ensure and then Boost gave Boost whatever Ensure had in any field the
# RD didn't overwrite -- silently, with nothing on screen to show it.
serving = next(n for n in at.number_input if n.key == f"{prefix}_cv_serving")
serving.set_value(235.0).run()
name_box = next(x for x in at.text_input if x.key == f"{prefix}_cname")
name_box.set_value("Ensure Plus Vanilla").run()
grams = next(n for n in at.number_input if n.key == f"{prefix}_cgrams")
grams.set_value(235.0).run()
assert not at.exception, at.exception

before = len(at.session_state["blends"][at.session_state["selected_blend_id"]]["ingredients"])
next(b for b in at.button if b.key == f"{prefix}_add_custom_btn").click().run()
assert not at.exception, at.exception
after = len(at.session_state["blends"][at.session_state["selected_blend_id"]]["ingredients"])
assert after == before + 1, f"custom food was not added ({before} -> {after})"
print(f"OK: custom food added to the blend ({before} -> {after} ingredients)")

# Read the rendered widget, not session_state: AppTest's proxy has no
# .get(), and the widget is what the RD actually sees anyway.
name_now = next(x for x in at.text_input if x.key == f"{prefix}_cname").value
assert (
    not name_now
), f"the food name survived the add ({name_now!r}) -- the next label would inherit it"
for stale_key, label in (
    (f"{prefix}_cv_energy", "energy"),
    (f"{prefix}_cv_sodium_mg", "sodium"),
    (f"{prefix}_cv_protein_g", "protein"),
):
    assert value_of(stale_key) == 0.0, f"{label} survived the add: {value_of(stale_key)}"
print("OK: the form is blank again, so a second label starts from zero")

captions = " ".join(c.value for c in at.caption)
assert "left alone" not in captions, "the previous photo's summary is still on screen"
print("OK: the previous photo's summary is cleared too")

print("\n=== LABEL PHOTO FILL APPTEST PASSED ===")
