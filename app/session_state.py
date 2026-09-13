"""Working-day state and blend lifecycle operations."""

import copy
import streamlit as st
from src.targets import empty_targets
from src.intake import (
    unique_blend_name,
)


def _next_blend_label() -> str:
    """The default name for a brand-new blend: "Blend N" for the LOWEST N
    not already in use.

    Counting the blends instead ("Blend {len + 1}") repeats a name as soon
    as one is deleted: with Blend 1/2/3, deleting Blend 2 leaves a count of
    2, so the next one is another "Blend 3". Taking the lowest free number
    keeps the name clean rather than leaning on unique_blend_name() to turn
    it into "Blend 3 (2)".
    """
    taken = {b["name"] for b in st.session_state.blends.values()}
    n = 1
    while f"Blend {n}" in taken:
        n += 1
    return f"Blend {n}"


def _commit_blend_name(blend_id: int) -> None:
    """on_change for the Blend name box: keep the typed name unique.

    Runs as a CALLBACK rather than inline after the widget, because
    Streamlit refuses to let session_state["blend_name_<id>"] be written
    once that widget has been instantiated in the same run -- and the box
    itself has to show the corrected name, or the RD sees one name in the
    field and a different one in every table. A callback fires before the
    rerun that redraws the widget, so the write is allowed there.

    Clearing the box entirely falls back to the next free "Blend N": an
    empty name is not something the app can show in a table, and two empty
    names would repeat, which is the whole thing being prevented.
    """
    key = f"blend_name_{blend_id}"
    wanted = st.session_state[key].strip() or _next_blend_label()
    taken = [b["name"] for bid, b in st.session_state.blends.items() if bid != blend_id]
    unique = unique_blend_name(wanted, taken)
    st.session_state[key] = unique
    st.session_state.blends[blend_id]["name"] = unique
    # Read and cleared where the box is drawn, so the explanation appears
    # once, right under the field that changed, and not again afterwards.
    st.session_state["_renamed_blend_note"] = (
        None
        if unique == wanted
        else (
            f"Another blend is already called {wanted}, so this one is now "
            f"{unique}. Rename either one to tell them apart."
        )
    )


def _new_blend(name: str) -> int:
    """Create a new empty blend, select it, and return its id.

    `name` is de-duplicated against the existing blends here rather than by
    each caller, because this is the ONLY way a blend is ever created --
    the starter blend, the New blend button, an imported recipe file, the
    example day, a thinned copy. Any future path gets the guarantee for
    free (src.intake.unique_blend_name explains why names must be unique).
    """
    name = unique_blend_name(name, [b["name"] for b in st.session_state.blends.values()])
    new_id = st.session_state.next_blend_id
    st.session_state.next_blend_id += 1
    st.session_state.blends[new_id] = {
        "name": name,
        "ingredients": [],
        "measured_volume_mL": 0.0,
        # The flow test belongs to THIS blend, not to the page. It is the
        # one thing in a recipe the app can never recompute -- kcal/mL and
        # protein/mL regenerate from the ingredient list any time, but
        # whether the blend actually pulled through a 60 mL syringe lives
        # only in the RD's hands. Storing it per blend is what lets the
        # chart note say WHICH recipe passed (2026-07-30).
        "flow_test": {"date": None, "result": "Not done", "notes": ""},
    }
    st.session_state.selected_blend_id = new_id
    # The "blend_selector" selectbox widget remembers its OWN prior value
    # across reruns once it's been created (Streamlit ignores a widget's
    # `index=`/`value=` argument once session_state already holds an entry
    # for its key) -- so without this pop, selecting a freshly-created
    # blend here would be silently overwritten back to whatever index the
    # widget last showed, the next time the Feed Recipes tab renders the
    # selectbox. Popping the key forces it to re-seed from `index=`
    # (computed from selected_blend_id) on the next render instead.
    st.session_state.pop("blend_selector", None)
    return new_id


def init_state():
    """Initialize session_state keys for blends, the Intake Record, and
    custom foods (FEED_LOG_REWORK.md section 3.2).

    - blends: dict id -> {name, ingredients: [...], measured_volume_mL} —
      the list of recipe formulations built in the Feed Recipes tab.
    - intake_log: list of row dicts (see src/intake.py's module docstring
      for the exact shape) — the single source of truth for everything
      the client actually received, tube feed and oral together.
    - custom_foods: stays global across blends AND oral entries (negative
      codes are unique everywhere a food can be entered).
    """
    if "blends" not in st.session_state:
        st.session_state.blends = {}
    if "next_blend_id" not in st.session_state:
        st.session_state.next_blend_id = 0
    if "selected_blend_id" not in st.session_state:
        st.session_state.selected_blend_id = None
    if "custom_foods" not in st.session_state:
        st.session_state.custom_foods = {}
    if "next_custom_code" not in st.session_state:
        st.session_state.next_custom_code = -1
    if "next_ingr_id" not in st.session_state:
        st.session_state.next_ingr_id = 0
    if "intake_log" not in st.session_state:
        st.session_state.intake_log = []
    if "next_intake_id" not in st.session_state:
        st.session_state.next_intake_id = 0
    # Always have at least one blend selected — an empty starter blend,
    # never a population default recipe.
    if not st.session_state.blends:
        _new_blend("Blend 1")


_STALE_WIDGET_KEY_PREFIXES = (
    "blend_",  # blend_selector, blend_name_{id}, blend_{id}_* (add-food UI)
    "vol_",  # vol_{blend_id} -- measured volume number_input
    "grams_",  # grams_{ing_id}[_measure] -- ingredient amount number_input
    "unit_",  # unit_{ing_id} -- ingredient g/household-measure toggle
    "fluid_",  # fluid_{ing_id} -- ingredient counts-as-fluid checkbox
    "del_",  # del_{ing_id}, del_intake_{id} -- row delete buttons
    "flow_date_",  # flow_date_{blend_id} -- flow-test date_input
    "flow_result_",  # flow_result_{blend_id} -- flow-test result selectbox
    "flow_notes_",  # flow_notes_{blend_id} -- flow-test notes text_input
    "recipe_upload_",  # recipe_upload_{blend_id} -- per-blend recipe file_uploader
    "oral_add_",  # oral_add_* -- the "Add food/drink" component's own keys
    "tf_",  # tf_time_input, tf_source_select, tf_amount_input, tf_add_btn
    "flush_",  # flush_mode, flush_single_time/amount, flush_per*, flush_med_amount, flush_add_btn
)


def _apply_saved_day(parsed) -> None:
    """Replace the whole working day with one read from a file.

    Runs HERE, at the top of the script, and not where the file is
    uploaded: it writes session_state keys that widgets own
    ("recipe_name_input", "patient_weight_input", every "target_*"), and
    setting those AFTER their widget has been instantiated in the same
    run raises StreamlitAPIException -- the §11 widget-state gotcha. So
    the upload handler stages the parsed day and reruns; this applies it
    before any widget exists.

    Replaces rather than merges. Opening a saved record means "go back to
    that day"; merging two days would produce an intake record that never
    happened. Recipes are the opposite and load alongside what you have.
    """
    # Pop every stale per-blend/per-ingredient/per-row widget key BEFORE
    # writing the loaded day into session_state. Without this, a loaded
    # blend/ingredient id that happens to match one from the CURRENT
    # session (e.g. blend id 1, ingredient id 1 -- ids restart low both
    # times) would leave that widget's number_input/checkbox holding its
    # old session value; the code that reads it back a few lines below
    # this run (e.g. `selected_blend["measured_volume_mL"] = ...`) then
    # writes that stale value straight back into the freshly loaded blend,
    # silently discarding the file's numbers with no error. Safe to do
    # here, and only here: _apply_saved_day() runs before any widget is
    # instantiated this run, so popping can't raise the §11
    # StreamlitAPIException that setting an existing widget key would.
    for _key in list(st.session_state.keys()):
        if _key.startswith(_STALE_WIDGET_KEY_PREFIXES):
            st.session_state.pop(_key, None)

    # Deep-copy rather than alias `parsed`'s collections. The app mutates
    # session_state.blends / intake_log / custom_foods in place (grams
    # edits, volume edits, deletes, ...); handing it the ParsedDay's own
    # nested dicts/lists would let those in-place edits silently change
    # `parsed` itself out from under anything still holding a reference
    # to it (e.g. a regression test asserting against the file's values).
    st.session_state.blends = copy.deepcopy(parsed.blends) or {}
    st.session_state.intake_log = copy.deepcopy(parsed.intake_log)
    st.session_state.custom_foods = copy.deepcopy(parsed.custom_foods)

    # Rebuild the id counters from what was actually loaded, so newly
    # added rows can't collide with loaded ones.
    st.session_state.next_blend_id = (max(parsed.blends) + 1) if parsed.blends else 0
    st.session_state.next_intake_id = len(parsed.intake_log)
    st.session_state.next_ingr_id = max(
        (ing["id"] for b in parsed.blends.values() for ing in b["ingredients"]),
        default=0,
    )
    # Custom food codes count DOWN from -1, so the next free one is below
    # the lowest already in use.
    st.session_state.next_custom_code = min(parsed.custom_foods) - 1 if parsed.custom_foods else -1

    # A day saved with no blends would leave the blend selector with
    # nothing to select; init_state()'s "always at least one" rule applies
    # here too.
    if not st.session_state.blends:
        _new_blend("Blend 1")
    st.session_state.selected_blend_id = min(st.session_state.blends)

    st.session_state["recipe_name_input"] = parsed.label
    st.session_state["delivery_method_input"] = parsed.delivery_method
    st.session_state["patient_weight_input"] = float(parsed.patient_weight or 0.0)
    st.session_state["weight_unit"] = (
        parsed.weight_unit if parsed.weight_unit in ("kg", "lbs") else "kg"
    )
    for _name in empty_targets():
        st.session_state[f"target_{_name}"] = float(parsed.targets.get(_name, 0.0))


def add_intake_row(row: dict) -> int:
    """Append one event and allocate its id from the working day's counter."""
    st.session_state.next_intake_id += 1
    row_id = st.session_state.next_intake_id
    st.session_state.intake_log.append({**row, "id": row_id})
    return row_id


def remove_intake_row(row_id: int) -> None:
    """Remove only the selected event, retaining the order of the others."""
    st.session_state.intake_log = [
        row for row in st.session_state.intake_log if row["id"] != row_id
    ]


def add_ingredient(blend_id: int, ingredient: dict) -> int:
    """Copy an ingredient into a blend with a fresh id for its controls."""
    st.session_state.next_ingr_id += 1
    ingredient_id = st.session_state.next_ingr_id
    st.session_state.blends[blend_id]["ingredients"].append({**ingredient, "id": ingredient_id})
    return ingredient_id


def delete_blend(blend_id: int) -> int:
    """Delete a blend and its linked intake events; return the removed event count.

    The caller keeps the existing guard against deleting the last blend.
    Selecting the remaining blend and clearing the selector happen together.
    """
    del st.session_state.blends[blend_id]
    before = len(st.session_state.intake_log)
    st.session_state.intake_log = [
        row
        for row in st.session_state.intake_log
        if not (row["source_type"] == "blend" and row["source_id"] == blend_id)
    ]
    st.session_state.selected_blend_id = next(iter(st.session_state.blends))
    st.session_state.pop("blend_selector", None)
    return before - len(st.session_state.intake_log)
