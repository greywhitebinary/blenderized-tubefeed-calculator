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

print("\n=== LABEL PHOTO FILL APPTEST PASSED ===")
