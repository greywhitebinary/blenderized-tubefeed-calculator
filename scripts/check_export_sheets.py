"""AppTest: near-identically named blends must both survive the download,
and the app must refuse to let their names collide in the first place.

WHAT THIS GUARDS
----------------
The original bug: the download wrote one sheet per blend, named
f"BTF {blend_name}"[:31], with no dedupe. openpyxl accepts a duplicate
sheet title silently and the second write overwrote the first, so two
blends with the same name produced ONE sheet and one blend's ingredients
vanished with no error. Reachable without renaming anything --
_new_blend() re-issued "Blend 3" after the middle of three blends is
deleted -- and reachable by truncation, since two names differing past
the 31st character collide.

WHAT CHANGED (2026-08-01)
-------------------------
The two downloads became one file, and the per-blend sheets went with
them: ingredients now live on a single "Ingredients" sheet, tagged with
"Blend id" and "Blend name". That makes a *sheet-name* collision
impossible by construction.

WHAT CHANGED (2026-08-16)
-------------------------
Blend names can no longer repeat at all: src.intake.unique_blend_name()
turns a second "Duplicate Blend" into "Duplicate Blend (2)", enforced in
_new_blend() and in the Blend name box's on_change. So this check can no
longer BUILD two identically named blends, and its first job is now to
prove that -- through the real widget, which is the only way to catch the
rename failing to reach either the box or the stored blend.

The underlying risk has NOT gone away, so neither has the rest of this
check. Two blends the RD can barely tell apart must still be
distinguishable in the file, each keeping its own ingredients and its own
flow test. The link is the numeric blend id, not the name, for the same
reason recipe_io refuses to pool unlabelled rows: silently merging two
recipes is the failure this project treats as unacceptable.
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

DUPLICATE_NAME = "Duplicate Blend"
# What the app must turn a second DUPLICATE_NAME into.
DEDUPED_NAME = f"{DUPLICATE_NAME} (2)"
MARKER = "Marker ingredient for the second blend"

# AppTest has no accessor for download_button payloads, so capture them as
# the app writes them.
#
# BOTH call paths have to be patched, and the reason is easy to trip over:
# `streamlit.download_button` is a BOUND method, captured off the root
# DeltaGenerator at import time. Patching the class alone therefore
# intercepts `some_column.download_button(...)` but NOT `st.download_button
# (...)`, which is what this app now uses. Patching the module alone would
# miss the container form. Patch both and stay honest either way.
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
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=180)
    at.run()
    assert not at.exception, at.exception

    next(b for b in at.button if "example" in b.label.lower()).click().run()
    assert not at.exception, at.exception

    # Rename through the real widget: the blend-name text_input owns the
    # value, so writing session_state directly is silently overwritten on
    # the next run and the two blends never actually collide.
    first_id = at.session_state["selected_blend_id"]
    next(t for t in at.text_input if t.key == f"blend_name_{first_id}").set_value(
        DUPLICATE_NAME
    ).run()

    next(b for b in at.button if "New blend" in b.label).click().run()
    second_id = at.session_state["selected_blend_id"]
    assert second_id != first_id, "New blend did not create a second blend"
    # Ask for the SAME name as the first blend. The app must refuse the
    # collision and hand back the numbered variant instead.
    next(t for t in at.text_input if t.key == f"blend_name_{second_id}").set_value(
        DUPLICATE_NAME
    ).run()
    assert not at.exception, at.exception

    names = [b["name"] for b in at.session_state["blends"].values()]
    assert names.count(DUPLICATE_NAME) == 1, f"the duplicate name was allowed to repeat: {names}"
    assert (
        at.session_state["blends"][second_id]["name"] == DEDUPED_NAME
    ), f"expected the stored name to become {DEDUPED_NAME!r}, got {names}"
    # The box itself has to show the corrected name too, or the RD reads
    # one name in the field and a different one in every table.
    shown = next(t for t in at.text_input if t.key == f"blend_name_{second_id}").value
    assert shown == DEDUPED_NAME, f"the name box still shows {shown!r}, not {DEDUPED_NAME!r}"
    print(f"OK: the second {DUPLICATE_NAME!r} became {DEDUPED_NAME!r}, in the box and in state")

    # Give the second blend an ingredient and a flow test of its own, so
    # "both kept theirs" is a claim with something behind it.
    #
    # The flow test goes through its WIDGET, not session_state: the
    # selectbox owns that value and writes it back on every run, so a
    # direct assignment is silently reverted and this check would pass
    # against a file where nothing was ever set. Same trap as the blend
    # names above. It is reachable because the second blend is the
    # selected one, and the widget renders inside the (collapsed)
    # flow-test expander.
    next(s for s in at.selectbox if s.key == f"flow_result_{second_id}").set_value(
        "Needs thinning"
    ).run()
    assert not at.exception, at.exception
    assert (
        at.session_state["blends"][second_id]["flow_test"]["result"] == "Needs thinning"
    ), "setting the flow test through its widget did not stick"

    at.session_state["next_ingr_id"] += 1
    at.session_state["blends"][second_id]["ingredients"].append(
        {
            "id": at.session_state["next_ingr_id"],
            "food_code": 9,
            "food_description": MARKER,
            "grams": 42.0,
            "unit": "g",
            "counts_as_fluid": False,
        }
    )
    at.run()
    assert not at.exception, at.exception

    assert _captured, "no download payload captured"
    payload = _captured[-1]
    sheets = pd.read_excel(io.BytesIO(payload), sheet_name=None, engine="openpyxl")
    for required in ("Blends", "Ingredients"):
        assert required in sheets, f"no {required!r} sheet — have {list(sheets)}"

    blends_df = sheets["Blends"]
    same_named = blends_df[blends_df["Blend name"].isin([DUPLICATE_NAME, DEDUPED_NAME])]
    assert len(same_named) == 2, f"expected 2 rows for {DUPLICATE_NAME!r}, got {len(same_named)}"
    assert same_named["Blend id"].nunique() == 2, "the two blends share a Blend id"
    print(f"OK: both blends kept their own row, ids {sorted(same_named['Blend id'].tolist())}")

    results = sorted(str(r) for r in same_named["Flow test result"].fillna(""))
    assert "Needs thinning" in results, f"a flow test was lost — {results}"
    print(f"OK: flow tests stayed separate — {results}")

    ing_df = sheets["Ingredients"]
    per_blend = ing_df.groupby("Blend id").size()
    for blend_id in same_named["Blend id"]:
        assert blend_id in per_blend.index, f"blend {blend_id} has no ingredients in the file"
    assert MARKER in set(ing_df["Food description"]), "the second blend's ingredient vanished"
    print(f"OK: ingredients kept per blend — {({int(k): int(v) for k, v in per_blend.items()})}")

    # The report half must be there too -- that is the point of merging the
    # two downloads into one file.
    for report_sheet in ("Adequacy", "Per-Source Breakdown", "Chart Note"):
        assert report_sheet in sheets, f"no {report_sheet!r} sheet — have {list(sheets)}"
    print("OK: the report sheets ride along in the same file")

    # And it still reloads.
    parsed = workbook_bytes_to_day(payload)
    assert len(parsed.blends) == len(at.session_state["blends"]), parsed.blends
    assert parsed.intake_log, "reloaded day has no intake rows"
    print(f"OK: the same file reloads — {parsed.summary}")

    print("\n=== EXPORT SHEET APPTEST PASSED ===")


if __name__ == "__main__":
    main()
