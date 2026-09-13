"""Blend selection, ingredients, measured volume, and flow-test controls."""

from app.session_state import add_ingredient, delete_blend
from html import escape
import streamlit as st
from src.models import Ingredient
from src.calculator import (
    compute_ingredient_breakdown,
)
from src.measures import (
    get_measures_for_food,
    scale_measure_label,
    group_ingredients_for_card,
)
from app.add_food import render_add_food_ui
from app.copy_block import render_copy_block
from app.ui_common import _left_aligned, _narrow, render_alert
from src.report import (
    format_ingredient_breakdown,
    stripe_rows,
)
from src.intake import (
    blend_fluid_fraction,
)


from app.session_state import _new_blend, _next_blend_label, _commit_blend_name


def render_recipe_editor(fn, na, lookup, fg):
    # --- Blend selector ---
    st.subheader("Blend")
    blend_ids = list(st.session_state.blends.keys())
    if st.session_state.selected_blend_id not in blend_ids:
        st.session_state.selected_blend_id = blend_ids[0] if blend_ids else None

    # Read each name off its WIDGET where one exists, not off the stored
    # blend (author, 2026-08-01). The "Blend name" text_input renders
    # BELOW this selectbox, and it owns the value -- `blends[bid]["name"]`
    # is only written after it runs. So on the render where the RD edits a
    # name, this list still holds the PREVIOUS one and the dropdown
    # disagrees with the field six lines under it.
    #
    # The visible symptom was a dropdown reading "Blend 1" above a name
    # field reading "Whole-food blend": clearing the name made the stored
    # value "" (so the label fell back to f"Blend {bid}"), and typing the
    # name back left the fallback on screen for one more render. It looked
    # like two blends, or like the rename hadn't taken.
    #
    # Streamlit fills a widget's session_state entry before the script
    # runs, so the key holds THIS run's text. Falls back to the stored
    # name for blends whose widget hasn't rendered yet (anything not
    # currently selected).
    # Labels are computed ONCE, here, into a plain dict -- format_func must
    # not touch st.session_state. Streamlit calls format_func outside the
    # script run (serialising widget state), where session_state raises
    # "has no attribute" and takes six of the nine CI checks down with it.
    #
    # Each label carries its blend's ITEM COUNT (author, 2026-08-16). The
    # complaint it answers: after adding foods to blend 1 and switching to
    # blend 2, nothing on screen showed that blend 1 still held them, so it
    # was unclear whether something needed clicking before switching. It
    # never did -- ingredients write straight into session_state as they
    # are added -- but the dropdown was silent about it. Counting here in
    # the list every blend is already picked from means the reassurance is
    # continuous and costs no extra control.
    _blend_labels: dict[int, str] = {}
    for _bid in blend_ids:
        _widget_name = st.session_state.get(f"blend_name_{_bid}")
        _stored = st.session_state.blends[_bid]["name"]
        _name = (_widget_name if _widget_name is not None else _stored) or f"Blend {_bid}"
        _count = len(st.session_state.blends[_bid]["ingredients"])
        _blend_labels[_bid] = (
            f"{_name} · {_count} item{'' if _count == 1 else 's'}"
            if _count
            else f"{_name} · no items yet"
        )

    # Options are the BLEND IDS, not positions (author, 2026-08-01).
    #
    # This started as an index list, `range(len(blend_ids))`, which meant
    # that starting the app and pressing "Load example record" sent the
    # browser the same options both times -- [0] before, [0] after -- even
    # though the starter blend (id 0) had been replaced by the example
    # blend (id 1). The server computed the right label; the browser saw a
    # structurally identical widget and kept the one it had already drawn.
    # Result: "Select blend" read "Blend 1" above a "Blend name" field
    # reading "Whole-food blend", which looks like two different blends.
    #
    # Ids make the options genuinely change ([0] -> [1]), so the frontend
    # has to redraw. It also removes the parallel names list this used to
    # index into, which was its own source of drift.
    #
    # AppTest could never reproduce the symptom -- it has no browser to
    # hold a stale label -- so this was found by the author using the
    # deployed app. Worth remembering the next time a UI bug "cannot be
    # reproduced": the test harness renders, it does not paint.
    sel_idx = blend_ids.index(st.session_state.selected_blend_id)

    # vertical_alignment="bottom" so the two buttons line up with the
    # Select blend BOX rather than floating level with its label (author,
    # 2026-08-15) -- same fix as the "Open a saved record" popover above.
    bsel1, bsel2, bsel3 = st.columns([3, 1, 1], vertical_alignment="bottom")
    chosen_id = bsel1.selectbox(
        "Select blend",
        options=blend_ids,
        index=sel_idx,
        format_func=lambda bid: _blend_labels.get(bid, f"Blend {bid}"),
        key="blend_selector",
    )
    st.session_state.selected_blend_id = chosen_id
    selected_blend_id = st.session_state.selected_blend_id
    selected_blend = st.session_state.blends[selected_blend_id]

    # Sits directly under the selector because that is where the doubt
    # lands: switching blends is the moment an RD wonders whether something
    # needed clicking first. Says what to do to KEEP work rather than what
    # would lose it (author, 2026-08-16) -- the tab closing and taking
    # everything with it is intended behaviour on a shared public server,
    # not a gap to apologise for. The second sentence is the only pointer
    # to the Recipe Record section, which sits ~800 lines further down the
    # tab, past the density panel and the Dilution What-If.
    #
    # Written as an INSTRUCTION throughout (author, 2026-08-17), which is
    # what makes the second person correct here: the house rule is
    # impersonal for statements of fact, second person for instructions.
    # As a fact it would read "Blends stay saved while switching between
    # them" -- accurate, but this line exists to reassure someone who
    # thinks they have lost work, and that reports rather than reassures.
    st.caption(
        "Switch between blends freely; nothing is lost. To keep them for "
        "next time, scroll down to save your recipe record."
    )

    if bsel2.button("➕ New blend", width="stretch"):
        _new_blend(_next_blend_label())
        st.rerun()
    if bsel3.button("🗑️ Delete blend", width="stretch", disabled=len(blend_ids) <= 1):
        removed_count = delete_blend(selected_blend_id)
        if removed_count:
            st.toast(
                f"Removed {removed_count} Intake Record row(s) that referenced "
                "the deleted blend."
            )
        st.rerun()

    # Key-driven rather than value-driven: _commit_blend_name() writes the
    # de-duplicated name back into this widget's own state, which Streamlit
    # only permits before the widget exists -- so the value has to come
    # FROM session_state, not from a `value=` argument it would ignore
    # anyway once the key is set. Each blend has its own key, so switching
    # blends still shows the right name.
    _name_key = f"blend_name_{selected_blend_id}"
    if _name_key not in st.session_state:
        st.session_state[_name_key] = selected_blend["name"]
    _name_col = _narrow(1, 1)
    _name_col.text_input(
        "Blend name",
        key=_name_key,
        on_change=_commit_blend_name,
        args=(selected_blend_id,),
    )
    if st.session_state.get("_renamed_blend_note"):
        _name_col.warning(st.session_state.pop("_renamed_blend_note"))

    # The kcal/mL + protein/mL mini-summary that sat here was REMOVED
    # 2026-08-17 (author). Added 2026-07-19 per FEED_LOG_REWORK.md §3.3
    # ("helps orient"), it had since been overtaken: the blend selector
    # above now carries each blend's item count, and the Per-blend density
    # panel a short scroll down shows the same figures for every blend. It
    # was also the only place rendering kcal/mL to three decimals where
    # everything else uses two, so the same blend read 0.720 here and 0.72
    # below.
    #
    # The WARNING it wrapped stays: a blend with ingredients but no measured
    # volume can't produce densities, and this is the only place that says so
    # in the open. The "Full density summary" expander further down carries
    # the same message, but it is collapsed by default.
    #
    # The volume is read off the number_input's OWN state, not off the blend
    # dict (bug fixed 2026-08-17). That widget renders BELOW this line and
    # only writes `selected_blend["measured_volume_mL"]` when it runs, so on
    # the render where an RD types a volume the dict still held the old 0 and
    # this warning stayed on screen until they touched something else --
    # telling them to do the thing they had just done. Streamlit fills a
    # widget's session_state entry before the script runs, so the key holds
    # THIS run's value; the stored volume is the fallback for a blend whose
    # widget has not rendered yet. Same fix as the blend-name selectbox above.
    #
    # Checked directly rather than through resolve_blend_profile(): that
    # raises InvalidBlendError on exactly this condition, so calling it here
    # computed a whole nutrient profile just to learn whether a number was
    # zero.
    _volume_now = st.session_state.get(
        f"vol_{selected_blend_id}", selected_blend["measured_volume_mL"]
    )
    if selected_blend["ingredients"] and float(_volume_now or 0.0) <= 0:
        render_alert(
            "warning",
            "This blend has ingredients but no measured volume yet — "
            "densities can't be computed until you enter one below.",
        )

    st.divider()

    # --- Add ingredient (reusable component, section 3.3) ---
    st.subheader(f'Add ingredient to "{selected_blend["name"]}"')
    # Totals per food ACROSS every row, so a food split over three rows
    # reports the sum rather than whichever row happened to be last.
    _existing_grams: dict[int, float] = {}
    for _ing in selected_blend["ingredients"]:
        _code = _ing.get("food_code")
        if _code is not None:
            _existing_grams[_code] = _existing_grams.get(_code, 0.0) + _ing.get("grams", 0.0)
    new_ingredient = render_add_food_ui(
        fn,
        na,
        lookup,
        fg,
        key_prefix=f"blend_{selected_blend_id}",
        add_button_label="Add to blend",
        # Without this the custom-food button composes to "Add to blend
        # custom food", which it has read as since before the parameter
        # existed. Given, not assembled (2026-08-21 review).
        add_custom_button_label="Add custom food to blend",
        existing_food_codes=_existing_grams,
    )
    if new_ingredient is not None:
        add_ingredient(selected_blend_id, new_ingredient)
        st.rerun()

    # --- Blend details ---
    st.subheader("Blend details")
    st.session_state.pop("load_example", False)

    measured_volume = _narrow(1, 3).number_input(
        "**Measured final volume (mL)**",
        min_value=0.0,
        value=float(selected_blend["measured_volume_mL"]),
        step=10.0,
        format="%g",
        key=f"vol_{selected_blend_id}",
    )
    selected_blend["measured_volume_mL"] = measured_volume
    st.caption(
        "Read it off the side of the blender jug, or pour into a measuring "
        "cup after blending. Ingredient weights feed the nutrient math; "
        "volume is always this measured number."
    )

    # --- Ingredient table ---
    st.subheader("Ingredients")

    if not selected_blend["ingredients"]:
        render_alert("guidance", "Add ingredients above to get started.")
    else:
        # Recipe / Nutrition switcher (Change 1.1, plan
        # you-know-the-line-vectorized-milner.md). Same ingredient list,
        # two readings: a roomy editable recipe for whoever is in the
        # kitchen, or a per-ingredient nutrient pivot for the dietitian --
        # see compute_ingredient_breakdown()'s docstring for why the
        # second one can never disagree with the whole-blend totals
        # shown elsewhere. st.segmented_control ships in 1.58 (verified).
        # required=True keeps a segment always selected -- clicking the
        # already-selected one would otherwise deselect to None.
        # Keyed per blend so switching blends doesn't carry the previous
        # blend's view choice along.
        _view = st.segmented_control(
            "Ingredients view",
            options=["Recipe", "Nutrition"],
            default="Recipe",
            required=True,
            key=f"ingr_view_{selected_blend_id}",
            label_visibility="collapsed",
        )

        if _view == "Recipe":
            st.caption(
                '"Counts as fluid" drives the Daily Intake Record tab\'s '
                "Fluids provided row (full-volume I&O convention) — auto-checked for CNF "
                "Beverages and mL-basis custom foods, and left to the dietitian "
                "otherwise (e.g. soup has no validated rule of thumb)."
            )
            for i, ing in enumerate(selected_blend["ingredients"]):
                unit = ing.get("unit", "g")

                # Banded rows (Change 1.6, author request 2026-08-15) --
                # both the striped and unstriped containers get the SAME
                # padding so rows stay aligned; only the striped one gets a
                # fill colour (see the .st-key-zebrarow/.plainrow CSS
                # above). Grey, not pink -- pink already means "pick from a
                # list" in this row (the unit dropdown), so a pink band
                # would read as a fourth meaningful colour rather than as
                # furniture (see the CSS comment for the full reasoning).
                _band = "zebrarow" if i % 2 else "plainrow"
                with st.container(key=f"{_band}_ingr_{ing['id']}"):
                    # Line 1 -- name + delete (Change 1.2). The name gets
                    # its own full-width line now instead of a 30%-wide
                    # column, so a long CNF description (up to 45 chars,
                    # e.g. "Chicken, feet, boiled") has room to sit on one
                    # line rather than wrapping and changing the row's
                    # height depending on which unit happens to be chosen.
                    # vertical_alignment centres the ❌ against the whole
                    # row. It used to sit at the top right, reading as a
                    # corner mark rather than as this row's control once
                    # the button shrank -- and centring alone did not fix
                    # it, because the button lived on the name line and
                    # so could only centre within that line. Hence
                    # body_col below (author, 2026-08-21).
                    #
                    # body_col spans BOTH the name line and the amount/unit
                    # line below (rather than just the name line), so the
                    # ❌ button in del_col centres against the whole
                    # two-line row instead of only the first line
                    # (author, 2026-08-21).
                    body_col, del_col = st.columns([11, 1], vertical_alignment="center")
                    with body_col:
                        # Not bold: every row would be bold, so it emphasises
                        # nothing and just makes the list heavier to scan
                        # (author, 2026-08-15).
                        #
                        # The backslash escapes the "." so markdown does not
                        # read "4. Chicken, ..." as an ORDERED LIST. It did
                        # once the bold came off (the asterisks had been
                        # hiding it), rendering <ol><li>, which brought a list
                        # indent and narrowed the text -- so names wrapped
                        # early and their second line hung under the text
                        # instead of the number. Visible only when zoomed out,
                        # where "Banana, raw" broke across two lines.
                        st.write(f"{i + 1}\\. {ing['food_description']}")

                        # Line 2 -- amount, unit, computed value, fluid toggle.
                        # Four columns, each with one job, instead of the unit
                        # dropdown sharing a narrow column with the amount box
                        # (the old layout gave the unit dropdown too little
                        # room for CNF's longest labels).
                        amt_col, unit_col, computed_col, fluid_col = st.columns([1, 4, 2, 3])

                        # Which units this row offers comes from the FOOD, via
                        # CNF -- NOT from what happened to be captured when the
                        # row was created (author feedback 2026-08-15). Reading
                        # it off the stored measure_label made the option
                        # appear only on rows added by searching: an identical
                        # banana from the example day, a reloaded file or an
                        # imported recipe offered nothing, so the capability
                        # looked random. CNF knows this banana's measures
                        # either way, so ask CNF. A food with none (chicken
                        # breast has zero) simply offers grams, exactly as
                        # before.
                        #
                        # measure_label/measure_grams still get stored, but
                        # their job changed: they are now the REMEMBERED CHOICE
                        # that seeds this dropdown and prints in the export,
                        # not the gate on whether the RD may switch units at
                        # all.
                        _measures = (
                            get_measures_for_food(int(ing["food_code"]), lookup)
                            if ing.get("food_code") is not None
                            else None
                        )
                        _by_label: dict[str, float] = (
                            {
                                str(r["Measure_Description_and_Unit_EN"]): float(r["grams"])
                                for _, r in _measures.iterrows()
                            }
                            if _measures is not None and len(_measures) > 0
                            else {}
                        )
                        _unit_options = [unit, *_by_label]
                        _remembered = ing.get("measure_label")
                        _default_idx = (
                            _unit_options.index(_remembered) if _remembered in _by_label else 0
                        )

                        chosen_unit = unit_col.selectbox(
                            f"Unit for {ing['food_description']}",
                            _unit_options,
                            index=_default_idx,
                            key=f"unit_{ing['id']}",
                            label_visibility="collapsed",
                        )
                        measure_grams = _by_label.get(chosen_unit)

                        if measure_grams:
                            # Portion-to-portion switch (author, 2026-08-21):
                            # a banana bread entered as 1 loaf, switched to
                            # slice, must read 1 slice -- not 1036 g's worth
                            # of slices (17.27). Grams is a weight and a
                            # portion is a count, so only a PORTION-to-PORTION
                            # switch carries the NUMBER across; g on either
                            # side keeps the WEIGHT instead (that path is
                            # untouched, below and in the else branch).
                            # Detected by comparing this run's chosen_unit
                            # against measure_label/measure_grams as they
                            # stood BEFORE this run -- ing[...] has not been
                            # overwritten yet at this point in the loop, so
                            # it still holds last run's remembered measure.
                            # A falsy old measure_grams (first render of this
                            # row, or a remembered measure that no longer
                            # exists in this food's CNF list) means the OLD
                            # side wasn't a portion, so this skips and the
                            # ordinary weight-preserving path below runs.
                            _old_measure_grams = ing.get("measure_grams")
                            if chosen_unit != _remembered and _old_measure_grams:
                                _old_qty = round(ing["grams"] / _old_measure_grams, 2)
                                selected_blend["ingredients"][i]["grams"] = _old_qty * measure_grams

                            # The box holds the QUANTITY in the chosen measure,
                            # not grams -- "2 of 1 cup", never a pluralised
                            # "2 cups", which breaks on "1 small".
                            #
                            # The widget key carries the chosen unit. Switching
                            # units must re-seed the box from `value=` rather
                            # than have Streamlit hand back the previous unit's
                            # leftover number under a shared key -- that would
                            # silently reinterpret "1 x 250 ml mashed" as
                            # "1 x 1 small" and change the amount. Streamlit
                            # drops state for widgets that stop being
                            # rendered, so the re-seed is reliable (verified).
                            # Still prefixed "grams_", so
                            # _STALE_WIDGET_KEY_PREFIXES already covers it.
                            # Rounded for the BOX only -- an exact ratio reads
                            # "2.3544554455445548", which is noise in a
                            # quantity field. Grams below stay the
                            # authoritative figure and the "=" column prints
                            # them in full, so nothing is lost. The guard must
                            # compare against this same rounded value, or the
                            # rounding itself would look like an edit.
                            derived_qty = round(ing["grams"] / measure_grams, 2)
                            new_qty = amt_col.number_input(
                                f"Amount for {ing['food_description']}",
                                value=derived_qty,
                                min_value=0.0,
                                step=0.5,
                                format="%g",
                                key=f"grams_{ing['id']}_{chosen_unit}",
                                label_visibility="collapsed",
                            )
                            # THE DRIFT GUARD (2026-08-15). This box shows a
                            # ROUNDED quantity -- 300 g / 158 g-per-cup
                            # displays as 1.9 -- so writing it back to grams on
                            # EVERY rerun, including the rerun where the RD
                            # touched nothing, would walk the stored grams down
                            # a little each time (1.9 * 158 = 300.2, which
                            # re-derives to 1.9 again, forever) with nothing on
                            # screen ever showing it. Only write grams back
                            # when the widget's value actually differs from
                            # the derived quantity (float tolerance, not ==);
                            # unchanged means leave the stored grams
                            # byte-for-byte alone.
                            if abs(new_qty - derived_qty) > 1e-6:
                                selected_blend["ingredients"][i]["grams"] = new_qty * measure_grams
                            selected_blend["ingredients"][i]["measure_label"] = chosen_unit
                            selected_blend["ingredients"][i]["measure_grams"] = measure_grams
                            computed_col.markdown(
                                f"= **{selected_blend['ingredients'][i]['grams']:.1f} {unit}**"
                            )
                        else:
                            new_amount = amt_col.number_input(
                                f"Amount for {ing['food_description']}",
                                value=float(ing["grams"]),
                                min_value=0.0,
                                step=1.0,
                                format="%g",
                                key=f"grams_{ing['id']}",
                                label_visibility="collapsed",
                            )
                            selected_blend["ingredients"][i]["grams"] = new_amount
                            # Showing grams is a display choice, so forget the
                            # remembered measure -- the export should print
                            # what the row currently reads, not a unit the RD
                            # moved away from.
                            selected_blend["ingredients"][i]["measure_label"] = None
                            selected_blend["ingredients"][i]["measure_grams"] = None

                        new_fluid_flag = fluid_col.checkbox(
                            "Counts as fluid",
                            value=bool(ing.get("counts_as_fluid", False)),
                            key=f"fluid_{ing['id']}",
                        )
                        selected_blend["ingredients"][i]["counts_as_fluid"] = new_fluid_flag

                    if del_col.button("❌", key=f"del_{ing['id']}"):
                        selected_blend["ingredients"].pop(i)
                        st.rerun()

            # --- Recipe card (Change 1.3): the "hand it to a caregiver"
            # artefact, kept out of the edit rows above so neither job
            # clutters the other. Measure-first, grams in brackets
            # (author's choice); st.code so it gets Streamlit's own copy
            # button, the same idiom the Chart Note (Daily Intake Record
            # tab) already uses.
            #
            # The card COLLAPSES rows that would print identically -- the
            # same food, same unit, same measure -- and sums their grams
            # (author, 2026-08-16). Adding egg twice reads as a mistake on
            # something handed to a caregiver. This is the ONLY place that
            # collapses: the numbered rows above, the export, the
            # Nutrition view and the stored blend all stay row-per-entry,
            # so the card can legitimately show fewer lines than the
            # selector's item count. group_ingredients_for_card() owns the
            # rule, including why "1 large egg" never merges with "75 g".
            #
            # Rendered by render_copy_block since 2026-09-09, so the copy
            # control here is the same one the Chart Note and both of
            # EN-Calc's notes use. It was st.code, for its free copy icon.
            _card_lines = [selected_blend["name"] or f"Blend {selected_blend_id}"]
            for ing in group_ingredients_for_card(selected_blend["ingredients"]):
                _label = ing.get("measure_label")
                _measure_grams = ing.get("measure_grams")
                _unit = ing.get("unit", "g")
                if _label and _measure_grams:
                    # "500 ml Whole milk  (516 g)" -- measure-first, grams
                    # in brackets, with the quantity MULTIPLIED INTO the
                    # label rather than printed in front of it (author,
                    # 2026-08-15). CNF labels carry their own count, so
                    # "2 x 250 ml" and "2 x 1 extra large" both read
                    # awkwardly; folding the number in gives "500 ml" and
                    # "2 extra large". scale_measure_label() owns the rule,
                    # including the two cases where folding would lie --
                    # see its docstring.
                    _qty = round(ing["grams"] / _measure_grams, 2)
                    _amount = scale_measure_label(_label, _qty)
                    _card_lines.append(
                        f"  {_amount} {ing['food_description']}  " f"({ing['grams']:.0f} {_unit})"
                    )
                else:
                    # No household measure recorded for this row -- reads
                    # in grams (or mL), same convention as the "250 mL
                    # water" line in the plan's own example.
                    _card_lines.append(f"  {ing['grams']:.0f} {_unit} {ing['food_description']}")
            # No "Total" line, deliberately (author, 2026-08-15). A total
            # ingredient weight was scaffolding from the original build
            # with no recorded purpose: nothing consumes it, the nutrient
            # maths uses per-ingredient grams and the density maths uses
            # the measured volume. Printed next to "Measured final volume
            # (mL)" it also invited reading grams as millilitres, which is
            # wrong for a blend carrying oil and solids.
            #
            # Collapsed by default (author, 2026-08-15): the card is for
            # the moment you hand the recipe over, not for every edit, so
            # it should not push the rows above it up the page every time.
            with st.expander("📋 Recipe card — copy to hand over"):
                st.session_state["_recipe_card_generated"] = "\n".join(_card_lines)
                render_copy_block(
                    "<br>".join(escape(line) for line in _card_lines),
                    block_id="btf_recipe_card",
                    label="Copy card",
                )

        else:  # _view == "Nutrition" (Change 1.4)
            # compute_ingredient_breakdown() is the SAME merge-and-scale
            # core as compute_nutrient_totals()/calculate_profile(),
            # grouped by ingredient instead of summed away -- see its
            # docstring in src/calculator.py for why this can never
            # disagree with the whole-blend numbers shown elsewhere in
            # this tab, and for how custom (label-entered) foods are
            # folded in even though they never appear in the CNF join.
            _ingr_objs = [
                Ingredient(ing["food_code"], ing["food_description"], ing["grams"])
                for ing in selected_blend["ingredients"]
            ]
            # Per food_code, per-unit totals across every ingredient
            # INSTANCE of that food in this blend -- water added once as
            # itself (mL) and again inside a thinned-blend copy (g) is the
            # real case. compute_ingredient_breakdown() below consolidates
            # those instances into one row per food, so this is built from
            # the blend's own ingredient list (which still carries each
            # instance's own unit) rather than from the breakdown. See
            # format_ingredient_breakdown()'s docstring (src/report.py) for
            # why the merged row can't carry this itself.
            _amounts_by_food_code: dict[int, dict[str, float]] = {}
            for _ing in selected_blend["ingredients"]:
                if _ing.get("food_code") is None:
                    continue
                _code = int(_ing["food_code"])
                _unit = _ing.get("unit", "g")
                _bucket = _amounts_by_food_code.setdefault(_code, {})
                _bucket[_unit] = _bucket.get(_unit, 0.0) + _ing["grams"]
            _breakdown = compute_ingredient_breakdown(_ingr_objs, na, st.session_state.custom_foods)
            _nutrition_display = format_ingredient_breakdown(
                _breakdown, amounts_by_food_code=_amounts_by_food_code
            )
            # Breaks out of the page cap so the nutrient columns can
            # spill sideways (the author's "spill over the way long
            # tables do") instead of truncating.
            with st.container(key="fullbleed_ingr_nutrition"):
                st.dataframe(
                    stripe_rows(_nutrition_display),
                    # stretch + explicit pixel widths, same combination
                    # the Adequacy table uses (see fullbleed_adequacy
                    # above) -- width="content" was tried there and
                    # leaves the table narrow and unable to scroll.
                    width="stretch",
                    hide_index=True,
                    column_config=_left_aligned(
                        _nutrition_display,
                        Ingredient=st.column_config.TextColumn(width=220, alignment="left"),
                        Amount=st.column_config.TextColumn(width=100, alignment="left"),
                    ),
                )

        # "Total ingredient weight" used to print here. Removed 2026-08-15:
        # it dated from the original scaffold with no recorded purpose,
        # nothing downstream consumed it, and sitting a gram figure right
        # under "Measured final volume (mL)" invited reading the two as the
        # same quantity. "Fluid from ingredients" below stays -- that one
        # feeds the Daily Intake Record's fluid accounting.
        _blend_fluid_mL = (
            blend_fluid_fraction(
                selected_blend["ingredients"], selected_blend["measured_volume_mL"]
            )
            * selected_blend["measured_volume_mL"]
        )
        if _blend_fluid_mL > 0:
            st.caption(f"Fluid from ingredients (this batch): **{_blend_fluid_mL:.0f} mL**")

        if st.button("🗑️ Clear this blend's ingredients"):
            selected_blend["ingredients"] = []
            st.rerun()

    # --- Flow test: a property of THIS blend, next to its other
    # properties (author, 2026-08-01) ---
    #
    # It used to sit under the Dilution What-If, from the 2026-07-20
    # reasoning "thin the blend, then record whether it flows". Two
    # things undid that. Collapsing it into an expander left it with no
    # heading of its own, so it read as part of the dilution section
    # rather than as a fact about the recipe. And thinning now produces
    # a SEPARATE blend, so the flow test you record afterwards belongs
    # to that one, not to the blend you were previewing from.
    #
    # Whether a blend pulls through a syringe is true regardless of
    # whether anyone ever thins it, so it belongs with the ingredients
    # and the measured volume.
    # Collapsed, with the RESULT in the label (author, 2026-08-01). The
    # flow test is optional documentation -- most blends never get one --
    # but it took four always-visible widgets on every blend. Putting the
    # result in the expander's own label means the answer ("Passed",
    # "Needs thinning") is readable without opening it, so collapsing
    # hides the form, not the finding.
    #
    # Keyed per blend: switching blends shows that blend's own flow test
    # rather than leaving the previous one on screen describing a recipe
    # it was never about.
    _ft_state = selected_blend.setdefault(
        "flow_test", {"date": None, "result": "Not done", "notes": ""}
    )
    _ft_results = ["Not done", "Passed", "Needs thinning"]
    # Read the label off the WIDGETS' session_state, not off _ft_state.
    # _ft_state is only written at the bottom of this block, after the
    # widgets render, so on the run where the RD changes the dropdown it
    # still holds the previous answer -- the label would say "not
    # recorded" for a test that had just been marked Passed, and stay
    # wrong until some unrelated interaction forced another rerun.
    # Streamlit populates a widget's session_state entry before the script
    # runs, so these keys already hold this run's values. The keys don't
    # exist on the first render of a blend, hence the fallbacks.
    _ft_result_key = f"flow_result_{selected_blend_id}"
    _ft_date_key = f"flow_date_{selected_blend_id}"
    _ft_current = st.session_state.get(_ft_result_key) or _ft_state.get("result") or "Not done"

    # Fix (2026-08-20 review): _ft_current can come straight from a loaded
    # recipe/day file (_ft_state["result"], read by _apply_saved_day() and
    # the recipe importer) -- neither src/recipe_io.py nor src/day_io.py
    # constrains that field, it's free text. list.index() below needs an
    # EXACT match against _ft_results, so a hand-edited file saying
    # "passed" (or with stray whitespace) raised ValueError and took the
    # whole Feed Recipes tab down with it. Resolve case/whitespace-
    # tolerantly instead, and fall back to the safe default -- telling the
    # RD, never crashing -- for a value that still matches nothing.
    _ft_normalized = {r.strip().casefold(): r for r in _ft_results}
    _ft_match = _ft_normalized.get(str(_ft_current).strip().casefold())
    if _ft_match is not None:
        _ft_current = _ft_match
    else:
        render_alert(
            "guidance",
            f"This blend's saved flow-test result, \"{_ft_current}\", isn't "
            'one this app recognises, so it was reset to "Not done".',
        )
        _ft_current = "Not done"

    _ft_shown_date = st.session_state.get(_ft_date_key, _ft_state.get("date"))
    _ft_date_bit = (
        f" ({_ft_shown_date.isoformat()})" if _ft_shown_date and _ft_current != "Not done" else ""
    )
    _ft_label = (
        "🧪 Flow test — not recorded"
        if _ft_current == "Not done"
        else f"🧪 Flow test — {_ft_current}{_ft_date_bit}"
    )
    with st.expander(_ft_label):
        # Reworded 2026-08-17. The previous version called this "the half
        # of the sweet spot the app can't compute" and said it "records
        # what your syringe told you" -- a strained metaphor, an internal
        # glossary term that should never have reached the screen, and a
        # talking syringe. It also said "the tool" and then "the app" for
        # the same thing in one sentence.
        st.caption(
            "Documentation only. Flow through a tube is measured, not "
            "calculated, so a syringe test is recorded here against this "
            "blend, and the chart note can then name the recipe tested."
        )
        ft1, ft2 = st.columns(2)
        flow_test_date = ft1.date_input(
            "Date", value=_ft_state.get("date"), key=f"flow_date_{selected_blend_id}"
        )
        flow_test_result = ft2.selectbox(
            "Result",
            _ft_results,
            index=_ft_results.index(_ft_current),
            key=f"flow_result_{selected_blend_id}",
        )
        flow_test_notes = st.text_area(
            "Notes",
            value=_ft_state.get("notes", ""),
            placeholder="e.g., flowed through a 60 mL syringe without resistance",
            key=f"flow_notes_{selected_blend_id}",
        )
        _ft_state["date"] = flow_test_date
        _ft_state["result"] = flow_test_result
        _ft_state["notes"] = flow_test_notes

    st.divider()

    return selected_blend_id, selected_blend, _ft_state
