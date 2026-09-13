"""Recipe workbook import review and export controls."""

from app.session_state import add_ingredient
import streamlit as st
from src.recipe_io import (
    AMBIGUOUS,
    MATCH_BY_CODE,
    MATCH_BY_DESCRIPTION,
    MATCH_CUSTOM,
    UNMATCHED,
    RecipeFileError,
    recipe_to_workbook_bytes,
    recipes_to_workbook_bytes,
    resolve_ingredients,
    suggested_filename,
    workbook_bytes_to_recipes,
)
from app.add_food import food_search_index
from app.ui_common import render_alert


from app.session_state import _new_blend


def _confirm_recipe_import(entries) -> None:
    """Show uploaded recipes as DRAFTS for the RD to confirm.

    `entries` is a list of (ParsedRecipe, [ResolvedIngredient]) pairs --
    a file may hold several blends since format v2 (see src/recipe_io.py),
    and every one of them is shown before anything is written.

    Nothing here writes to a blend until the confirm button is pressed.
    That is deliberate and matches the rule in CONTEXT.md §11: a file the
    app wrote carries CNF food codes and resolves exactly, but a recipe
    someone typed in Excel carries words, and words are ambiguous --
    "chicken, broiler, breast" is three different CNF foods with three
    different protein figures. Picking one silently would put a plausible
    wrong number into a clinical calculation, so every row that wasn't
    matched by code is shown for a human to settle.

    Every widget key carries the recipe's position as well as the row's.
    Two recipes in one file can hold the same ingredient at the same
    index, and a shared key would make Streamlit treat them as one
    widget -- picking a food for one would silently change the other.
    """

    def _clear() -> None:
        st.session_state.pop("_pending_recipe", None)
        st.session_state.pop("_last_recipe_upload", None)

    st.markdown("---")
    total_rows = sum(len(resolved) for _, resolved in entries)
    if len(entries) > 1:
        st.markdown(f"**Loading {len(entries)} recipes from that file**")
    else:
        st.markdown(f"**Loading recipe: {entries[0][0].name or 'unnamed'}**")

    if total_rows == 0:
        render_alert("guidance", "No usable ingredient rows were found in that file.")
        if st.button("Cancel", key="recipe_import_cancel_empty"):
            _clear()
            st.rerun()
        return

    # needs_confirmation, not "status != MATCH_BY_CODE": MATCH_CUSTOM is
    # also an exact match (the file names both the code and the per-100 g
    # numbers, same as MATCH_BY_CODE names the code) and must not count
    # toward "needs review" (Format v3, 2026-08-20).
    needs_review = sum(1 for _, resolved in entries for r in resolved if r.needs_confirmation)
    if needs_review:
        st.caption(
            f"{needs_review} of {total_rows} rows were matched by name, not by "
            "food code. Check the food and the amount on each one. Nothing is "
            "added until you press Add."
        )
    else:
        st.caption(f"All {total_rows} rows matched by food code. Check them and press Add.")

    # choices_by_recipe[i][j] is the CNF code to use for recipe i's row j,
    # or None to skip that row.
    choices_by_recipe: list[list[int | None]] = []

    for r_index, (parsed, resolved) in enumerate(entries):
        if len(entries) > 1:
            st.markdown(f"**{r_index + 1}. {parsed.name or 'unnamed'}**")

        for warning in parsed.row_warnings:
            render_alert("guidance", warning)

        choices: list[int | None] = []
        for index, row in enumerate(resolved):
            amount_label = f"{row.grams:g} {row.unit}"
            if row.status == MATCH_BY_CODE:
                st.write(f"✅ **{row.food_description}** — {amount_label}")
                choices.append(row.food_code)
            elif row.status == MATCH_CUSTOM:
                st.write(f"✅ **{row.food_description}** — {amount_label} (from the saved label)")
                choices.append(row.food_code)
            elif row.status == UNMATCHED:
                st.write(f'❌ "{row.source_text}" — {amount_label}: no CNF match, will be skipped.')
                choices.append(None)
            elif row.status in (MATCH_BY_DESCRIPTION, AMBIGUOUS):  # found by searching, not code
                heading = f'🔍 "{row.source_text}" — {amount_label}'
                if row.interpreted_as and row.interpreted_as != row.source_text:
                    heading += f', read as "{row.interpreted_as}"'
                st.write(heading)
                picked = st.selectbox(
                    heading,
                    options=[c[0] for c in row.candidates] + [None],
                    format_func=lambda code, _row=row: (
                        "— skip this row —"
                        if code is None
                        else next(d for c, d in _row.candidates if c == code)
                    ),
                    index=0,  # the best-ranked candidate, preselected
                    key=f"recipe_pick_{r_index}_{index}",
                    label_visibility="collapsed",
                )
                choices.append(picked)
            else:
                # Unreachable today -- every status recipe_io defines is
                # handled above. Kept because `choices` is zipped against
                # `resolved` further down: a branch that appended nothing
                # would shift every later row onto the wrong food, which
                # is the one failure this screen exists to prevent. A new
                # status should cost a skipped row, not a silent
                # misalignment (2026-08-20).
                st.write(f'❌ "{row.source_text}" — {amount_label}: will be skipped.')
                choices.append(None)
        choices_by_recipe.append(choices)

    usable = sum(1 for choices in choices_by_recipe for c in choices if c is not None)
    # A recipe whose every row was skipped is not created at all -- an
    # empty blend appearing in the selector would look like the import
    # half-worked.
    blends_to_add = sum(1 for choices in choices_by_recipe if any(c is not None for c in choices))
    if blends_to_add > 1:
        button_label = f"Add as {blends_to_add} new blends ({usable} ingredients)"
    else:
        button_label = f"Add as a new blend ({usable} ingredient{'s' if usable != 1 else ''})"

    c1, c2 = st.columns(2)
    if c1.button(
        button_label,
        disabled=usable == 0,
        key="recipe_import_confirm",
        width="stretch",
    ):
        # A file's negative custom-food codes are file-scoped -- the
        # session may already hold a DIFFERENT food under the same code.
        # Renumber ONCE for the whole file, not per recipe, so two blends
        # in this import that share one custom food land on the same new
        # code rather than being split into two copies. Allocated exactly
        # the way add_food.py hands out a code for a freshly-typed label
        # (author's rule: an imported ingredient must never end up
        # pointing at a pre-existing session custom food, 2026-08-20).
        code_remap: dict[int, int] = {}
        for (_parsed, resolved), choices in zip(entries, choices_by_recipe):
            for row, code in zip(resolved, choices):
                if code is None or row.status != MATCH_CUSTOM or code in code_remap:
                    continue
                new_code = st.session_state.next_custom_code
                st.session_state.next_custom_code -= 1
                st.session_state.custom_foods[new_code] = dict(row.custom_nutrients or {})
                code_remap[code] = new_code

        for (parsed, resolved), choices in zip(entries, choices_by_recipe):
            if not any(c is not None for c in choices):
                continue
            new_id = _new_blend(parsed.name or "Loaded recipe")
            blend = st.session_state.blends[new_id]
            blend["measured_volume_mL"] = parsed.measured_volume_mL
            blend["flow_test"] = {
                "date": parsed.flow_test_date,
                "result": parsed.flow_test_result or "Not done",
                "notes": parsed.flow_test_notes,
            }
            for row, code in zip(resolved, choices):
                if code is None:
                    continue
                # Custom rows use the REMAPPED code, never the file's own
                # -- see code_remap above.
                food_code = code_remap[code] if row.status == MATCH_CUSTOM else int(code)
                add_ingredient(
                    new_id,
                    {
                        "food_code": food_code,
                        "food_description": row.food_description,
                        "grams": row.grams,
                        "unit": row.unit,
                        "counts_as_fluid": row.counts_as_fluid,
                        "measure_label": row.measure_label,
                        "measure_grams": row.measure_grams,
                    },
                )
        _clear()
        st.rerun()

    if c2.button("Cancel", key="recipe_import_cancel", width="stretch"):
        _clear()
        st.rerun()


def render_recipe_record(selected_blend_id, selected_blend, _ft_state, fn):
    # --- Recipe record: save this blend to a file, or load one back ---
    # The calculator computes; this remembers. Everything else in a blend
    # can be recomputed from the ingredient list -- the flow test can't,
    # so a saved recipe is the only place that judgment survives.
    # Files download to the RD's own machine: the deployed app runs on a
    # shared public server with no per-user storage, so there is nowhere
    # safe to keep recipes server-side (and nothing patient-identifying
    # ever leaves the browser this way).
    st.subheader("Recipe Record")
    # Saves EVERY blend that has ingredients, not just the selected one
    # (author, 2026-07-30: the app can hold several BTFs, so the file
    # should too). With one blend this is exactly the old behaviour.
    _savable = [
        (_b, _b.get("flow_test"))
        for _bid, _b in sorted(st.session_state.blends.items())
        if _b["ingredients"]
    ]
    _n_savable = len(_savable)
    st.caption(
        "Save your blends — ingredients, measured volume and flow test — as a "
        "spreadsheet. Re-open it here later, or read it in any spreadsheet program."
        if _n_savable != 1
        else "Save this blend — ingredients, measured volume and flow test — as a "
        "spreadsheet. Re-open it here later, or read it in any spreadsheet program."
    )
    rr1, rr2 = st.columns(2)
    with rr1:
        # "Download", not "Save" (author, 2026-08-16). A button saying
        # Save implies there is unsaved work, which is what made switching
        # blends feel risky when nothing was ever at stake. Same split the
        # Daily Intake Record tab already uses: the SECTION says "Save this
        # record", the BUTTON says "Download".
        #
        # Two gets "both", not "all 2" -- English doesn't take "all" with a
        # pair (author, 2026-08-20). Lifted out of the call because a
        # three-way conditional inline is unreadable.
        if _n_savable <= 1:
            _download_label = "💾 Download recipe"
        elif _n_savable == 2:
            _download_label = "💾 Download both recipes"
        else:
            _download_label = f"💾 Download all {_n_savable} recipes"
        st.download_button(
            _download_label,
            # Falls back to the selected blend purely so the disabled
            # button still has valid bytes to hold.
            data=(
                recipes_to_workbook_bytes(_savable, custom_foods=st.session_state.custom_foods)
                if _savable
                else recipe_to_workbook_bytes(
                    selected_blend, _ft_state, custom_foods=st.session_state.custom_foods
                )
            ),
            file_name=(
                suggested_filename(_savable[0][0].get("name", ""))
                if _n_savable == 1
                else suggested_filename(f"{_n_savable} blends", count=_n_savable)
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=not _savable,
            help=(
                "Add at least one ingredient to a blend first."
                if not _savable
                else (
                    "Downloads to your computer."
                    if _n_savable == 1
                    else (
                        "One file containing both blends that have ingredients."
                        if _n_savable == 2
                        else f"One file containing all {_n_savable} blends that have ingredients."
                    )
                )
            ),
            width="stretch",
        )
    with rr2:
        # In a popover so this reads as a BUTTON beside "Save recipe"
        # rather than a tall drag-and-drop dropzone next to one (author,
        # 2026-08-15) -- the two sat side by side as different kinds of
        # control. Same idiom as "Open a saved record" at the top of the
        # page, which wraps its uploader for exactly this reason.
        with st.popover("📂 Load a recipe", width="stretch"):
            _uploaded = st.file_uploader(
                "Load a recipe",
                type=["xlsx"],
                key=f"recipe_upload_{selected_blend_id}",
                label_visibility="collapsed",
                help="Loads into NEW blends — it never overwrites what you have.",
            )

    if _uploaded is not None and st.session_state.get("_last_recipe_upload") != _uploaded.name:
        try:
            _parsed_list = workbook_bytes_to_recipes(_uploaded.getvalue())
        except RecipeFileError as exc:
            render_alert("guidance", str(exc))
        else:
            st.session_state["_pending_recipe"] = [
                (_p, resolve_ingredients(_p, fn, search_index=food_search_index(fn)))
                for _p in _parsed_list
            ]
            st.session_state["_last_recipe_upload"] = _uploaded.name
            st.rerun()

    _pending = st.session_state.get("_pending_recipe")
    if _pending is not None:
        _confirm_recipe_import(_pending)
