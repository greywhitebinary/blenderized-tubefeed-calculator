"""Optional targets and display-only patient weight."""

import streamlit as st
from src.targets import empty_targets
from src.nutrients import (
    registry_by_name,
    DEFAULT_PACK,
)

_TARGET_STEP_OVERRIDES: dict[str, float] = {
    "energy_kcal": 50.0,
    "fluid_mL": 100.0,
    "sodium_mg": 100.0,
    "potassium_mg": 100.0,
    "calcium_mg": 50.0,
    "protein_g": 5.0,
    "vitamin_b12_ug": 0.5,
}


_TARGET_FORMAT_OVERRIDES: dict[str, str] = {
    "energy_kcal": "%.0f",
    "fluid_mL": "%.0f",
    "protein_g": "%.1f",
    "fat_g": "%.1f",
    "carbohydrate_g": "%.1f",
    "fibre_g": "%.1f",
    "iron_mg": "%.1f",
    "sodium_mg": "%.0f",
    "potassium_mg": "%.0f",
    "calcium_mg": "%.0f",
}


def render_targets():
    st.subheader("Patient weight (optional)")
    _w_col, _wu_col = st.columns([3, 1])
    _weight_unit = _wu_col.radio("Unit", ["kg", "lbs"], horizontal=True, key="weight_unit")
    # Seed the default only the very first time this key ever exists (see
    # the same comment by "recipe_name_input" above) -- avoids the
    # Session-State-vs-value= warning when Load Example presets this key.
    if "patient_weight_input" not in st.session_state:
        st.session_state["patient_weight_input"] = 0.0
    _weight_entered = _w_col.number_input(
        f"Weight ({_weight_unit})",
        min_value=0.0,
        step=0.5,
        format="%.1f",
        help="Optional — used only to show kcal/kg, protein g/kg, and "
        "fluid mL/kg in the Daily Intake Record tab. No target, equation, or "
        "IBW is computed from it; assessment stays outside this app.",
        key="patient_weight_input",
    )
    patient_weight_kg = _weight_entered if _weight_unit == "kg" else _weight_entered / 2.20462

    # The kg conversion gets its own bold line directly under the input
    # (author, 2026-08-08). It used to be tacked onto the end of the
    # static caption below as " = 99.8 kg", where it opened on a bare
    # equals sign and sat at the end of a sentence about something else,
    # which is where a number goes to be missed. It is a live value and
    # the caption is fixed guidance, so they are separate lines now.
    if _weight_unit == "lbs" and _weight_entered > 0:
        # Sized explicitly rather than with st.caption: this page sets
        # `html { font-size: 125% }`, so Streamlit's own caption size
        # lands bigger here than it does anywhere else, and it still
        # competed with the number it is annotating. 0.75rem reads as a
        # sub-line of the input. The negative top margin closes
        # Streamlit's default block gap so it sits ON the field rather
        # than floating between the field and the guidance below it.
        #
        # Full-strength text colour, NOT the dimmed grey the explanatory
        # captions use: this is a value the RD reads, not guidance about
        # how to use the form. Small and bold, but not faded. Inheriting
        # the colour also keeps it correct if the theme ever changes.
        _w_col.markdown(
            f"<div style='font-size:0.75rem; line-height:1.1; "
            f"margin-top:-0.75rem;'><strong>{patient_weight_kg:.1f} kg</strong></div>",
            unsafe_allow_html=True,
        )

    # "0", not "blank": this is a number_input seeded to 0.0 with
    # min_value=0.0, so an empty box is not a state the RD can reach --
    # clearing it snaps back to 0. Saying "blank" described something the
    # form cannot do (author feedback 2026-07-30).
    st.caption("0 = not provided. Display only — not a target.")

    st.subheader("Targets (optional)")
    st.caption("0 = no target; enter patient-specific values.")
    targets = empty_targets()
    tc1, tc2 = st.columns(2)
    cols = (tc1, tc2)
    _registry_map = registry_by_name(DEFAULT_PACK)

    # Clinical entry order, not registry order (author, 2026-08-08).
    # The registry is ordered like a Nutrition Facts table, which is how
    # a LABEL is laid out, not how a dietitian sets targets. These five
    # are what gets decided first, so they come first; anything not named
    # here keeps its registry order underneath.
    _TARGET_ORDER = ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g", "fluid_mL")
    _ordered_target_names = [n for n in _TARGET_ORDER if n in targets] + [
        n for n in targets if n not in _TARGET_ORDER
    ]

    for i, nutrient_name in enumerate(_ordered_target_names):
        col = cols[i % 2]
        if nutrient_name == "fluid_mL":
            # "Water", not "Fluid", on the target side: this is the water
            # you decide to give. The report's "Fluids provided" row is the
            # separate I&O total of everything that counted as fluid.
            disp_label, unit, decimals = "Water", "mL", 0
        else:
            d = _registry_map[nutrient_name]
            disp_label, unit, decimals = d.label, d.unit, d.decimals
        step = _TARGET_STEP_OVERRIDES.get(
            nutrient_name, 1.0 if decimals == 0 else round(10 ** (-decimals), decimals)
        )
        _target_key = f"target_{nutrient_name}"
        # Seed the default only the very first time this key ever exists
        # (see the same comment by "recipe_name_input" above) -- avoids
        # the Session-State-vs-value= warning when Load Example presets
        # energy/protein/fluid here.
        if _target_key not in st.session_state:
            st.session_state[_target_key] = 0.0
        targets[nutrient_name] = col.number_input(
            f"{disp_label} {unit}/day",
            min_value=0.0,
            step=step,
            format=_TARGET_FORMAT_OVERRIDES.get(nutrient_name, f"%.{min(decimals, 1)}f"),
            key=_target_key,
        )
    return targets, patient_weight_kg
