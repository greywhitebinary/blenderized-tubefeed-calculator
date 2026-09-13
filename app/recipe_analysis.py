"""Density, dilution, and commercial-formula comparison panels."""

from app.session_state import add_ingredient
import pandas as pd
import streamlit as st
from src.models import Ingredient
from src.calculator import (
    compute_nutrient_totals_and_coverage,
    dilute,
    required_daily_volume,
    COMMERCIAL_FORMULAS,
)
from src.food_search import find_food
from app.ui_common import _left_aligned, _narrow, render_alert
from src.report import (
    generate_comparator_table,
    EDITING_MARKER,
    generate_density_summary,
    stripe_rows,
)
from src.nutrients import (
    load_thinning_liquids,
)
from src.intake import (
    resolve_blend_profile,
    thinned_blend_name,
    InvalidBlendError,
)


from app.session_state import _new_blend

THINNING_LIQUIDS: dict[str, dict[str, float]] = load_thinning_liquids()


COMPARATOR_BLEND_PICKER_THRESHOLD = 4


def render_density(selected_blend, na):
    # --- Blend nutrient density (EVERY blend, not just selected --
    # densities are still the per-blend lens, design doc section 3.5) ---
    st.subheader("Blend nutrient density")
    _density_rows = []
    for _bid, _blend in st.session_state.blends.items():
        if not _blend["ingredients"]:
            _density_rows.append(
                {
                    "Blend": _blend["name"],
                    "kcal/mL": "—",
                    "protein g/mL": "—",
                    "Free-water fraction": "—",
                    "Measured volume (mL)": _blend["measured_volume_mL"],
                    "Coverage": "—",
                    "Note": "No ingredients yet",
                }
            )
            continue
        try:
            _b_profile, _b_fluid_frac = resolve_blend_profile(
                _blend, na, st.session_state.custom_foods
            )
        except InvalidBlendError:
            _density_rows.append(
                {
                    "Blend": _blend["name"],
                    "kcal/mL": "—",
                    "protein g/mL": "—",
                    "Free-water fraction": "—",
                    "Measured volume (mL)": 0,
                    "Coverage": "—",
                    "Note": "Ingredients but no measured volume",
                }
            )
            continue
        _b_ingredients = [
            Ingredient(i["food_code"], i["food_description"], i["grams"])
            for i in _blend["ingredients"]
        ]
        _, _b_coverage = compute_nutrient_totals_and_coverage(
            _b_ingredients, na, st.session_state.custom_foods
        )
        # Counts the EXCEPTION, not the norm (author, 2026-08-21): the
        # nutrients an RD would act on are the incomplete ones, and
        # "24/35 nutrients fully covered" made a reader work out the
        # useful number by subtraction. "Fully" was carrying the load in
        # that phrasing too -- a nutrient is complete only when EVERY
        # ingredient supplied a value, and "covered" alone sounds
        # absolute already.
        _n_missing = sum(1 for n_sup, n_tot in _b_coverage.values() if n_tot > 0 and n_sup < n_tot)
        _density_rows.append(
            {
                "Blend": _blend["name"],
                "kcal/mL": round(_b_profile.kcal_per_mL, 2),
                "protein g/mL": round(_b_profile.protein_per_mL, 3),
                "Free-water fraction": round(_b_profile.free_water_fraction, 3),
                "Measured volume (mL)": round(_b_profile.measured_final_volume_mL),
                "Coverage": (
                    # "no nutrients missing data", not "all nutrients
                    # complete": complete reads as nutritionally complete,
                    # which is a claim about the blend rather than about
                    # the database (author, 2026-08-21). Phrased to
                    # parallel the other reading in this same cell.
                    "no nutrients missing data"
                    if _n_missing == 0
                    else f"{_n_missing} of {len(_b_coverage)} nutrients missing data"
                ),
                "Note": "",
            }
        )
    _density_df = pd.DataFrame(_density_rows)
    # kcal/mL, protein g/mL, and Free-water fraction mix floats with the
    # "—" placeholder for a not-yet-buildable blend — cast to str before
    # display, same convention already used for the adequacy table's
    # Target/% Target columns, so Arrow serialization doesn't have to
    # auto-fix a mixed-type numeric column on every render.
    for _col in ("kcal/mL", "protein g/mL", "Free-water fraction"):
        _density_df[_col] = _density_df[_col].astype(str)
    st.dataframe(
        stripe_rows(_density_df),
        width="stretch",
        hide_index=True,
        column_config=_left_aligned(_density_df),
    )

    # Resolve the SELECTED blend's profile once -- reused by the density
    # detail expander, comparator, and dilution what-if below.
    selected_profile = None
    selected_fluid_frac = 0.0
    _selected_invalid = False
    if selected_blend["ingredients"]:
        try:
            selected_profile, selected_fluid_frac = resolve_blend_profile(
                selected_blend, na, st.session_state.custom_foods
            )
            if selected_blend["measured_volume_mL"] <= 0:
                selected_profile = None
        except InvalidBlendError:
            _selected_invalid = True

    # Bold name, no quotes, and it says where to change it: this panel
    # sits well below the "Select blend" control, so an RD reading it can
    # be a long way from the thing that chose it (author, 2026-08-21).
    with st.expander(
        f"Full density summary for **{selected_blend['name']}** "
        "(selected at the top of this tab)"
    ):
        if _selected_invalid:
            render_alert("warning", "This blend has ingredients but no measured volume yet.")
        elif selected_profile is None:
            st.caption("Add ingredients and a measured volume to the blend above.")
        else:
            st.dataframe(
                stripe_rows(_density_panel := generate_density_summary(selected_profile)),
                width="content",
                hide_index=True,
                column_config=_left_aligned(_density_panel),
            )

    st.divider()

    return selected_profile, selected_fluid_frac


def render_dilution(
    selected_blend_id, selected_blend, selected_profile, selected_fluid_frac, fn, targets
):
    # --- Dilution what-if (operates on the selected blend) ---
    st.subheader("Dilution What-If")
    # Was "What would thinning this blend with water cost you?" until
    # 2026-08-17. Two problems, both the author's: it addressed the reader
    # in what is a statement of fact, and "cost" reads as MONEY in a
    # country with public healthcare, when the thing being spent is
    # density. Say the effect plainly instead.
    st.caption(
        "**What does thinning this blend with water do to its density?** "
        "Move the slider to see the drop before you commit to anything.  \n"
        "This is a calculation, not a change: the blend above is untouched "
        "until the thinned version is saved as its own blend, at the bottom "
        "of this section.  \n"
        "Thinning with broth, juice or milk isn't a dilution, it's a recipe "
        "change — add it as an ingredient instead, where every nutrient is "
        "counted rather than just calories and protein."
    )

    if selected_profile is None:
        render_alert(
            "guidance",
            "Add ingredients and a measured volume to the blend above "
            "to use the dilution what-if.",
        )
    else:
        w1, w2 = st.columns([1, 2])

        with w1:
            liquid_type = st.selectbox("Thinning liquid", list(THINNING_LIQUIDS.keys()))
            added_mL = st.slider("Add liquid (mL)", 0, 500, 0, step=10)

            # Presets are non-nutritive by construction (see
            # src.nutrients.load_thinning_liquids), so kcal and protein are 0
            # here and only the water term does any work. The old
            # "Custom" branch -- hand-entering kcal and protein for the
            # added liquid -- was removed 2026-07-30: that is exactly the
            # nutritive case, and the recipe editor computes it properly.
            preset = THINNING_LIQUIDS[liquid_type]
            scale = added_mL / 100.0
            liq_kcal = preset["kcal"] * scale
            liq_protein = preset["protein_g"] * scale
            liq_water = preset["water_g"] * scale
            if added_mL > 0:
                st.caption(f"Adding {liq_water:.0f} g water — no calories, no protein.")

        with w2:
            if added_mL > 0:
                diluted = dilute(selected_profile, added_mL, liq_kcal, liq_protein, liq_water)

                dil_df = pd.DataFrame(
                    [
                        {
                            "Metric": "Volume (mL)",
                            "Original": selected_profile.measured_final_volume_mL,
                            "After dilution": diluted.measured_final_volume_mL,
                        },
                        {
                            "Metric": "kcal/mL",
                            "Original": round(selected_profile.kcal_per_mL, 3),
                            "After dilution": round(diluted.kcal_per_mL, 3),
                        },
                        {
                            "Metric": "protein g/mL",
                            "Original": round(selected_profile.protein_per_mL, 3),
                            "After dilution": round(diluted.protein_per_mL, 3),
                        },
                        {
                            "Metric": "free water fraction",
                            "Original": round(selected_profile.free_water_fraction, 3),
                            "After dilution": round(diluted.free_water_fraction, 3),
                        },
                    ]
                )
                dil_df["Change"] = dil_df["After dilution"] - dil_df["Original"]
                st.dataframe(
                    stripe_rows(dil_df),
                    width="content",
                    hide_index=True,
                    column_config=_left_aligned(dil_df),
                )

                tk = targets.get("energy_kcal", 0.0)
                tp = targets.get("protein_g", 0.0)
                if tk > 0 and tp > 0:
                    ro = required_daily_volume(selected_profile, tk, tp)
                    rd = required_daily_volume(diluted, tk, tp)
                    render_alert(
                        "guidance",
                        f"Required daily volume of just this blend to meet "
                        f"{tk:.0f} kcal + {tp:.0f} g protein:<br>"
                        f"<strong>{ro:.0f} mL</strong> → "
                        f"<strong>{rd:.0f} mL</strong> after dilution "
                        f"(+{rd - ro:.0f} mL)",
                        allow_html=True,
                    )

                # --- Commit the preview into a real, documentable blend ---
                # Without this the what-if is a dead end: it models a change
                # to the jug and writes nothing, so an RD who acts on it is
                # left with an app describing a recipe that no longer
                # exists (author, 2026-08-01). Every downstream number --
                # daily totals, adequacy %, per-kg, chart note, export --
                # then silently uses the un-thinned density.
                #
                # A COPY, not an edit in place: the thick original is
                # itself a finding worth keeping ("this needed thinning"),
                # and each blend carries its own flow test, so the pair
                # documents the before and after.
                #
                # Measured volume is CARRIED FORWARD as original + added
                # (author's challenge, 2026-08-01). It used to be left
                # blank, on the "volume is measured, not computed" rule
                # (CONTEXT.md §1) -- but that rule earns its keep for a
                # different case. It exists because INGREDIENT WEIGHTS
                # don't predict blended volume: whipping raw food into a
                # slurry traps air and packs particles unpredictably.
                # Adding a known volume of water to a blend whose volume
                # was ALREADY measured is not that. Water is miscible and
                # roughly additive, so the estimate is out by a percent or
                # two on a figure the app already calls an estimate --
                # while blocking every density on the new blend until the
                # RD re-measures was a heavy toll for arithmetic they can
                # do in their head.
                #
                # The caveat that survives: RE-BLENDING can change trapped
                # air, so the guidance says what the number assumes and
                # invites a correction rather than presenting it as
                # measured.
                _new_volume_mL = selected_blend["measured_volume_mL"] + added_mL
                _water_code = find_food(fn, "Water, municipal")
                _src_label = selected_blend["name"] or f"Blend {selected_blend_id}"
                st.markdown("**Going to actually thin it?**")
                st.caption(
                    f"Saving turns the preview dilution into a blend of its own. "
                    f'Clicking the "Save as a new blend with {added_mL:.0f} mL '
                    f'{liquid_type.lower()}" button will:  \n'
                    f'1. Copy every ingredient of **"{_src_label}"** and add the '
                    f"{added_mL:.0f} mL of {liquid_type.lower()} as one more "
                    f"ingredient;  \n"
                    f"2. Add it to **Select blend** at the top of this tab and "
                    f"switch you to it;  \n"
                    f"3. Set its **Measured final volume** to "
                    f"**{_new_volume_mL:.0f} mL** — this blend's "
                    f"{selected_blend['measured_volume_mL']:.0f} mL plus the "
                    f"{added_mL:.0f} mL of {liquid_type.lower()}. Re-measure and "
                    f"correct it if you blend it again, since that can change how "
                    f"much air is trapped;  \n"
                    f"4. Give it its own **🧪 Flow test**, under its ingredient "
                    f"list, so you can record whether the thinned version actually "
                    f"pulls through the tube."
                )
                if _water_code is None:
                    render_alert(
                        "guidance",
                        "Couldn't find a plain water entry in CNF, so this can't "
                        "be saved automatically. Add the water as an ingredient "
                        "yourself and re-measure the volume.",
                    )
                elif st.button(
                    f"➕ Save as a new blend with {added_mL:.0f} mL {liquid_type.lower()}",
                    key=f"dilute_commit_{selected_blend_id}",
                    width="stretch",
                    help="Your original blend is left untouched.",
                ):
                    _src_name = _src_label
                    # Just "(thinned)" (author, 2026-08-16). This used to
                    # spell the dilution out -- "(thinned with 150 mL
                    # water)", 2026-08-01, so the RD would not have to
                    # remember which liquid it was -- but there is only one
                    # liquid to remember (THINNING_LIQUIDS is water-only by
                    # construction), and at ~70 characters it crowded the
                    # blend selector. The amount is already recorded where
                    # it cannot go stale: as an ingredient of the copy and
                    # in the copy's measured volume. A name that repeats
                    # the ingredient list is a name that can disagree with
                    # it after an edit.
                    #
                    # Repeated thinning numbers itself through
                    # unique_blend_name() inside _new_blend(), so this stays
                    # one naming scheme rather than two: (thinned),
                    # (thinned) (2), (thinned) (3).
                    _new_id = _new_blend(thinned_blend_name(_src_name))
                    _copy = st.session_state.blends[_new_id]
                    for _ing in selected_blend["ingredients"]:
                        add_ingredient(_new_id, _ing)
                    add_ingredient(
                        _new_id,
                        {
                            "food_code": _water_code,
                            "food_description": f"{liquid_type} (added to thin)",
                            "grams": float(added_mL),
                            "unit": "mL",
                            "counts_as_fluid": True,
                            # A raw mL amount from the dilution slider, not
                            # a CNF household measure -- no label to carry.
                            "measure_label": None,
                            "measure_grams": None,
                        },
                    )
                    _copy["measured_volume_mL"] = _new_volume_mL
                    st.toast(
                        f'Created "{_copy["name"]}" and switched to it. Volume '
                        f"set to {_new_volume_mL:.0f} mL — re-measure if you blend "
                        "it again. Next: record its flow test."
                    )
                    st.rerun()


def render_comparator(selected_blend_id, selected_blend, selected_profile, na):
    # --- Comparator (operates on the selected blend plus the RD's other
    # blends, at a manually-chosen comparison volume -- independent of the
    # actual Intake Record, an explicit what-if: "if I gave X mL/day of
    # just this blend, how does it compare to my vegan one, or to formula
    # Y") ---
    #
    # Heading renamed from "Commercial Formula Comparator" (author,
    # 2026-08-16): once the RD's own blends became rows, and the FIRST
    # rows, a heading naming only formulas described the part that is no
    # longer the point.
    st.subheader("Compare Blends and Formulas")
    if selected_profile is None:
        render_alert(
            "guidance",
            "Add ingredients and a measured volume to the blend above " "to use the comparator.",
        )
    else:
        compare_volume_mL = _narrow(1, 3).number_input(
            "Compare at daily volume (mL)",
            min_value=0.0,
            value=max(selected_profile.measured_final_volume_mL, 1200.0),
            step=50.0,
            format="%g",
            help="An independent what-if volume for this comparison only -- "
            "it doesn't need to match the Intake Record (Daily Intake Record tab).",
        )
        # Company filter (restored round 3, refined round 4): picking a
        # company narrows the SCROLL LIST only. Selections from other
        # companies stay selected when you switch, because the multiselect's
        # options are the narrowed pool UNION whatever is already selected
        # (Streamlit silently drops selected values that aren't in
        # options -- this keeps Nepro + Isosource side by side without
        # ever scrolling the full 33).
        _comparator_brands = sorted(
            {f.get("brand") or "Other" for f in COMMERCIAL_FORMULAS.values()}
        )
        brand_filter = st.radio(
            "Company",
            ["All"] + _comparator_brands,
            horizontal=True,
            key="comparator_brand_filter",
        )
        formula_pool = sorted(
            (
                name
                for name, f in COMMERCIAL_FORMULAS.items()
                if brand_filter == "All" or (f.get("brand") or "Other") == brand_filter
            ),
            key=lambda n: (COMMERCIAL_FORMULAS[n].get("brand") or "Other", n),
        )
        _already_picked = st.session_state.get("comparator_formula_select", [])
        _multiselect_options = formula_pool + [n for n in _already_picked if n not in formula_pool]
        selected_formulas = st.multiselect(
            "Compare against (up to 4)",
            _multiselect_options,
            max_selections=4,
            # Feed name FIRST, brand after: multiselect chips clip from the end,
            # and the brand ("Nestlé Health Science") is the useless-to-clip-to
            # part -- leading with the feed name keeps it readable when truncated.
            format_func=lambda n: f"{n} — {COMMERCIAL_FORMULAS[n].get('brand') or 'Other'}",
            key="comparator_formula_select",
        )

        # Which of the RD's OWN blends join the table (Change 3,
        # you-know-the-line-vectorized-milner.md, 2026-08-15): every blend
        # with ingredients. A blend with ingredients but no measured volume
        # yet raises InvalidBlendError from resolve_blend_profile()
        # (src/intake.py); that blend is SKIPPED here, same as the density
        # table above, rather than crashing this whole tab.
        _other_blends = []
        for _cbid, _cblend in st.session_state.blends.items():
            if _cbid == selected_blend_id or not _cblend["ingredients"]:
                continue
            try:
                _cprofile, _ = resolve_blend_profile(_cblend, na, st.session_state.custom_foods)
            except InvalidBlendError:
                continue
            _other_blends.append((_cbid, _cblend["name"], _cprofile))

        # The picker offers only the OTHER blends: the one being edited is
        # what this whole section is about, so it always stays row 0
        # (author, 2026-08-16). That is also what keeps report.py's
        # "(open above)" label honest -- report.py marks whichever row
        # comes first, so a picker able to drop row 0 would slide the next
        # blend into its place and label a blend the RD is NOT editing.
        #
        # At the threshold or above, ask which to include (defaulting to
        # all) instead of showing every one -- see the module-level comment
        # on COMPARATOR_BLEND_PICKER_THRESHOLD for why it is off below that.
        if len(_other_blends) + 1 >= COMPARATOR_BLEND_PICKER_THRESHOLD:
            # Fix (2026-08-20 review): this used to key the multiselect's
            # persistent widget state by LIST POSITION, but _other_blends is
            # rebuilt fresh every run as "every blend except whichever one
            # is selected above" -- switching the selected blend, adding a
            # blend, or deleting one all reshuffle those positions, so a
            # remembered position-2 pick could silently point at a
            # completely different recipe next run with no error or notice.
            # A blend's id is stable for its whole session (see
            # next_blend_id), so keying by id instead means a remembered
            # pick either still names the same recipe, or -- if that blend
            # is gone -- gets dropped from the restored selection the same
            # way multiselect already silently drops a stale value from
            # `options` (see the company-filter comment above this block).
            _blend_names_by_id = {_bid: _name for _bid, _name, _ in _other_blends}
            _kept_ids = st.multiselect(
                "Also compare these blends",
                list(_blend_names_by_id),
                default=list(_blend_names_by_id),
                format_func=lambda bid: _blend_names_by_id[bid],
                key="comparator_blend_select",
            )
            _kept_id_set = set(_kept_ids)
            _other_blends = [
                (_name, _profile) for _bid, _name, _profile in _other_blends if _bid in _kept_id_set
            ]
        else:
            _other_blends = [(_name, _profile) for _bid, _name, _profile in _other_blends]

        comparator_df = generate_comparator_table(
            [(selected_blend["name"], selected_profile)] + _other_blends,
            compare_volume_mL,
            selected_formulas,
        )
        # NOT a fullbleed break-out (author, 2026-08-16). The break-out
        # exists for tables that genuinely cannot be read inside the 60rem
        # cap -- Adequacy, with its long nutrient names and nine columns.
        # This one is a name and six short numbers, so stretching it to
        # the viewport spread those numbers across the whole screen and
        # made a small table look like the biggest thing on the page.
        st.dataframe(
            stripe_rows(comparator_df),
            width="stretch",
            hide_index=True,
            column_config=_left_aligned(comparator_df),
        )
        # The marker is meaningless without this sentence, so the caption
        # is not decoration here -- it is the legend. "at the top of this
        # tab" rather than "above" because the comparator sits a long way
        # down, past Ingredients, the density panel, the Dilution What-If
        # and the Recipe Record, so "above" points at most of the page
        # (author, 2026-08-16).
        st.caption(
            f"{EDITING_MARKER} marks the blend being edited, selected at "
            "the top of this tab. Rows are compared at one daily volume; "
            "differences between rows are in the feeds themselves and not "
            "in the amounts given."
        )
