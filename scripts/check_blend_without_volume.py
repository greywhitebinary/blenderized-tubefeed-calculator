"""AppTest: a blend with no measured volume must not take the app down.

WHAT THIS GUARDS
----------------
The bug (found 2026-08-17, present since the Intake Record rework): clearing
a blend's measured final volume while the Intake Record holds rows that
reference that blend CRASHED THE WHOLE PAGE. aggregate_intake() resolves
every referenced blend, resolve_blend_profile() raised InvalidBlendError,
and nothing caught it. Reachable in ordinary use: load the example record,
clear the volume.

Three properties are pinned here, and the third is the one most likely to
be lost by a well-meaning "just skip the bad rows" fix:

1. The page survives, and says WHICH blend needs a volume. Naming it
   matters: the RD has to know where to go, and the exception's own message
   is written for a developer.

2. The download still works. The report sheets (Adequacy, Chart Note,
   Per-Source Breakdown, Water Sources) need totals and are omitted, but the
   RELOADABLE half never needed them -- so an RD is never unable to save
   their work because one number is missing.

3. Totals are NOT shown while a referenced blend is unusable. Skipping the
   unusable rows and totalling the rest would silently understate the day:
   it would look like the patient received less than they did. That is the
   failure mode this project treats as unacceptable, and it is worse than
   the crash it would replace, because nothing on screen would look wrong.

Also covers the smaller bug fixed alongside it: the "no measured volume
yet" warning used to lag one render, because it read the blend dict while
the volume number_input writes to that dict further down the same script
run -- so typing a volume left the warning up, telling the RD to do the
thing they had just done.
"""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit  # noqa: E402
from streamlit.delta_generator import DeltaGenerator  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.day_io import workbook_bytes_to_day  # noqa: E402

# AppTest has no accessor for download_button payloads, so capture them as
# the app writes them. Both call paths need patching -- see
# check_export_sheets.py's note on why the bound method is not enough.
_captured: list[bytes] = []
_real_method = DeltaGenerator.download_button
_real_module_fn = streamlit.download_button


def _record(kwargs) -> None:
    data = kwargs.get("data")
    if isinstance(data, (bytes, bytearray)):
        _captured.append(bytes(data))


def _spy_method(self, *args, **kwargs):
    _record(kwargs)
    return _real_method(self, *args, **kwargs)


def _spy_module(*args, **kwargs):
    _record(kwargs)
    return _real_module_fn(*args, **kwargs)


DeltaGenerator.download_button = _spy_method
streamlit.download_button = _spy_module


def main() -> None:
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=240)
    at.run()
    assert not at.exception, at.exception

    next(b for b in at.button if "example" in b.label.lower()).click().run()
    assert not at.exception, at.exception

    blend_id = at.session_state["selected_blend_id"]
    blend_name = at.session_state["blends"][blend_id]["name"]
    assert any(
        r.get("source_type") == "blend" and r.get("source_id") == blend_id
        for r in at.session_state["intake_log"]
    ), "the example record should reference the selected blend -- otherwise this proves nothing"

    # --- Clear the volume through the WIDGET, never session_state behind it.
    next(n for n in at.number_input if n.key == f"vol_{blend_id}").set_value(0.0).run()
    assert not at.exception, f"clearing a referenced blend's volume crashed the app: {at.exception}"
    print("OK: the page survived")

    warnings = [w.value for w in at.warning if "can't be worked out" in w.value]
    assert warnings, f"no warning explaining why totals are missing; warnings were {at.warning}"
    assert blend_name in warnings[0], f"the warning does not name the blend: {warnings[0]!r}"
    print(f"OK: it names the blend -- {warnings[0][:72]}...")

    # --- Property 3: no totals while a referenced blend is unusable.
    banner = [m.value for m in at.markdown if m.value.startswith("**Today:")]
    assert not banner, f"totals shown despite an unusable blend -- they would understate: {banner}"
    print("OK: no totals shown (understating the day is worse than showing none)")

    # --- Property 2: the work is still downloadable.
    assert _captured, "no download payload captured -- the RD cannot save their work"
    sheets = pd.read_excel(io.BytesIO(_captured[-1]), sheet_name=None, engine="openpyxl")
    for required in ("Record", "Blends", "Ingredients", "Intake"):
        assert (
            required in sheets
        ), f"the reloadable half lost its {required!r} sheet: {list(sheets)}"
    for computed in ("Adequacy", "Chart Note", "Per-Source Breakdown"):
        assert computed not in sheets, f"{computed!r} was written without totals to build it from"
    parsed = workbook_bytes_to_day(_captured[-1])
    assert parsed.blends and parsed.intake_log, "the saved file does not reload"
    print(f"OK: still downloadable and reloadable -- {parsed.summary}")

    # --- The warning clears on the SAME run the volume is typed.
    stale = [w.value for w in at.warning if "no measured volume yet" in w.value]
    assert stale, "the per-blend volume warning is missing while the volume is 0"
    next(n for n in at.number_input if n.key == f"vol_{blend_id}").set_value(1000.0).run()
    assert not at.exception, at.exception
    assert not [
        w for w in at.warning if "no measured volume yet" in w.value
    ], "the volume warning lagged a render -- it should clear as soon as a volume is entered"
    banner = [m.value for m in at.markdown if m.value.startswith("**Today:")]
    assert banner, "totals did not come back after a volume was entered"
    print(f"OK: warning cleared and totals returned -- {banner[0]}")

    print("\n=== BLEND WITHOUT VOLUME APPTEST PASSED ===")


if __name__ == "__main__":
    main()
