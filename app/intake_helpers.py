"""Source names and add-food controls shared by the intake editor and reports."""

from app.session_state import add_intake_row
import streamlit as st
from src.calculator import (
    COMMERCIAL_FORMULAS,
    MODULARS,
)
from src.measures import (
    scale_measure_label,
)
from app.add_food import render_add_food_ui
from app.ui_common import _narrow

_FLUSH_LABEL = "Water flush"


ROW_LIST_COLLAPSE_THRESHOLD = 6


def _intake_source_options() -> tuple[list[str], dict[str, tuple[str, object]]]:
    """Build the "Add tube feed" source dropdown: every blend + every
    commercial formula. Water flushes are NOT an option here -- they have
    their own "Add water flush" expander (author feedback 2026-07-20).
    Returns (display_options, {display_option: (source_type, source_id)}).
    """
    options: list[str] = []
    lookup_map: dict[str, tuple[str, object]] = {}
    for bid, blend in st.session_state.blends.items():
        label = f"Blend: {blend['name']}"
        options.append(label)
        lookup_map[label] = ("blend", bid)
    for fname, f in sorted(
        COMMERCIAL_FORMULAS.items(),
        key=lambda kv: (kv[1].get("brand") or "Other", kv[0]),
    ):
        brand = f.get("brand")
        # Feed name first, brand after (same rationale as the comparator
        # multiselect): a clipped dropdown should keep the feed name, not
        # the brand.
        label = f"Formula: {fname}{' – ' + brand if brand else ''}"
        options.append(label)
        lookup_map[label] = ("formula", fname)
    return options, lookup_map


def _intake_modular_options() -> tuple[list[str], dict[str, str]]:
    """Options for the Add modulars picker.

    Returns (display_options, {display_option: modular_name}). Simpler
    than _intake_source_options() because a modular is always one kind of
    thing -- there are no blends to interleave -- but it keeps the same
    "name first, brand after" rule, for the same reason: a clipped
    dropdown should keep the product name.
    """
    options: list[str] = []
    lookup: dict[str, str] = {}
    for name, m in sorted(MODULARS.items(), key=lambda kv: (kv[1].get("brand") or "Other", kv[0])):
        brand = m.get("brand")
        label = f"{name}{' – ' + brand if brand else ''}"
        options.append(label)
        lookup[label] = name
    return options, lookup


def _queue_intake_toast(what: str) -> None:
    """Confirm an Intake Record add, on the NEXT run.

    All three adders append and then st.rerun(), so a toast raised here
    would be thrown away with the run that raised it. Stashing it and
    showing it at the top of the tab is what makes it survive.

    It exists because the row lands BELOW the fold: the author watched a
    first-time reading of this screen where clicking Add appeared to do
    nothing, so the natural move was to click again, and only scrolling
    revealed several identical rows (2026-08-21).
    """
    st.session_state["_intake_toast"] = f"Added to the record below: {what}"


def _feeds_in_record() -> list[str]:
    """The commercial feeds named in the current Intake Record.

    Handed to the report builders so the Source column can name the
    manufacturer whose guide a number could have come from, instead of
    listing both companies on every day. A blend-only record returns
    nothing and the column names neither (2026-08-21).
    """
    return [
        row["source_id"]
        for row in st.session_state.intake_log
        if row.get("source_type") == "formula" and row.get("source_id")
    ]


def _intake_source_name(row: dict) -> str:
    """Resolve the display name for an Intake Record row's source (blend
    name, formula name, flush label, or food description).

    Factored out of _intake_row_label() so the Excel export's "Source"
    column can call this directly instead of re-parsing the formatted
    "{time} — {name} — {amount} {unit}" label on " — ". That split broke
    on any food name that itself contains " — ", including this app's own
    example day, which used to hand-glue "Banana, raw — 1 small" into
    food_description for lack of anywhere else to put "1 small". The real
    household measure now lives in measure_label/measure_grams (Change 3,
    2026-08-15), so food_description is back to being just the food name.
    """
    source_type = row["source_type"]
    if source_type == "blend":
        blend = st.session_state.blends.get(row["source_id"])
        return blend["name"] if blend else "(deleted blend)"
    elif source_type == "formula":
        return row["source_id"]
    elif source_type == "modular":
        # Named, like a formula. Without this branch a modular row fell
        # through to the food_description default and displayed as
        # "(unknown food)" -- it has no food_description to fall back on.
        return row["source_id"]
    elif source_type == "flush":
        return row.get("food_description") or _FLUSH_LABEL
    else:
        return row.get("food_description") or "(unknown food)"


def _intake_row_label(row: dict) -> str:
    """Human-readable one-line summary of an Intake Record row, for the
    row list and (later) the chart note."""
    t = row.get("time")
    t_str = t.strftime("%H:%M") if t else "(no time)"
    name = _intake_source_name(row)
    measure_label = row.get("measure_label")
    measure_grams = row.get("measure_grams")
    # Read-only household-measure form, with the quantity folded into the
    # label the same way the recipe card does it -- "(2 small)", not
    # "(2 × 1 small)" (author, 2026-08-15). Quantity is derived, never
    # stored, so this is always in step with the grams actually recorded.
    if measure_label and measure_grams:
        qty = round(row["amount"] / measure_grams, 2)
        name = f"{name} ({scale_measure_label(measure_label, qty)})"
    return f"{t_str} — {name} — {row['amount']:.0f} {row['unit']}"


def _render_add_oral_ui(fn_df, na_df, lookup_df, fg_df):
    """FEED_LOG_REWORK.md section 3.4: the oral-entry UI. Reuses the same
    search-or-custom-food component as the Feed Recipes tab (section 3.3), plus a
    counts_as_fluid toggle and an optional time. Submitting appends one
    oral row to the Intake Record.

    Implementation note (deviation from the doc's first-choice UI): the
    doc's first choice was an st.dialog for this ("keeps the already-busy
    banner from growing another full search UI inline"), with an inline
    expander explicitly sanctioned as a fallback "if st.dialog proves
    awkward in practice". st.dialog WAS tried first and works correctly
    for real interactive use, but it is incompatible with this project's
    AppTest-driven verification discipline: Streamlit's AppTest harness
    (streamlit/testing/v1) has no dialog-aware handling at all (confirmed
    by inspecting its source — no "dialog" references anywhere), and in
    practice ANY widget rendered inside an open st.dialog becomes an
    orphaned node in AppTest's tracked element tree once the dialog
    closes — real Streamlit's session_state garbage-collects the widget's
    key (expected, since it's no longer being rendered), but AppTest's
    tree still holds a reference to it, and the very next `.run()` call
    (regardless of what triggers it) raises a KeyError trying to
    reserialize that orphaned widget's state. This reproduces with a
    minimal two-widget dialog and is unrelated to this app's own code —
    verified directly (see the handoff report) before making this call.
    Since this repo's established practice is to verify UI behavior with
    AppTest rather than prose claims, and a dialog that poisons every
    subsequent AppTest run is untestable in exactly the way this project
    requires, this uses the sanctioned inline-expander fallback instead.
    """
    oral_time = _narrow(1, 4).time_input("Time (optional)", value=None, key="oral_time_input")
    new_food = render_add_food_ui(
        fn_df,
        na_df,
        lookup_df,
        fg_df,
        key_prefix="oral_add",
        add_button_label="Add to record below",
        add_custom_button_label="Add custom food to record below",
        show_counts_as_fluid_toggle=True,
    )
    if new_food is not None:

        add_intake_row(
            {
                "time": oral_time,
                "source_type": "oral",
                "source_id": new_food["food_code"],
                "food_description": new_food["food_description"],
                "amount": new_food["grams"],
                "unit": new_food["unit"],
                "counts_as_fluid": new_food["counts_as_fluid"],
                # render_add_food_ui()'s dict is re-keyed by hand here
                # (grams -> amount), which means it drops anything not
                # named explicitly -- these two must be listed, not
                # spread (Change 3, 2026-08-15).
                "measure_label": new_food["measure_label"],
                "measure_grams": new_food["measure_grams"],
            }
        )
        _queue_intake_toast(
            f"{new_food['food_description']}, {new_food['grams']:.0f} {new_food['unit']}"
        )
        st.rerun()
