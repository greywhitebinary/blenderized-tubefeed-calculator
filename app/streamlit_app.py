"""
streamlit_app.py — Streamlit UI for the Blenderized Tube Feed Calculator.

Phase 6; reworked per FEED_LOG_REWORK.md (the Intake Record rework) --
read that doc before changing this file. It replaces the old single-
recipe + delivery-schedule model (which silently extrapolated a measured
batch volume against whatever the schedule claimed was given -- see the
doc's section 1 for the bug) with:

  - Blends: a list of recipe formulations (name + ingredients + measured
    volume), managed in the Build tab. A blend is scale-free -- its
    densities (kcal/mL, protein/mL) don't care how many times it was made.
  - Intake Record: one chronological list of rows (blend / formula /
    flush / oral), each contributing exactly what it says it gave, summed
    directly via src.intake.aggregate_intake(). No batch bookkeeping, no
    over-draw flag -- see FEED_LOG_REWORK.md section 6.2 for why that
    concept is removed entirely, not softened.

App flow — three tabs in encounter order:
  1. Nutrition Targets tab -- the patient-side numbers the RD brings
     from their own assessment (kcal/protein/fluid targets, optional
     display-only weight). The app never computes targets.
  2. Feed Recipes tab -- the blend pages: create/select a blend, search
     CNF or add a custom food from a label, enter grams and measured
     final volume; per-blend densities and full nutrient results update
     live with every edit; the dilution what-if, commercial formula
     comparator, and flow-test documentation live here with the blend.
  3. Daily Intake Record tab -- the 24-hour record/plan: one
     chronological list of what was (or will be) given, tube feed
     (blends, formulas, flushes) and oral food/drink together; the
     day-level results (daily totals, adequacy, per-source breakdown,
     chart note, export) sit directly beneath the record they summarize.

Design commitments (from CONTEXT.md section 1):
  - Per-mL is the primary lens, not per-recipe.
  - Final blend volume is a measured input, not computed.
  - Live recipe adjustment is the core interaction.
  - Daily totals are a direct sum over what was actually given -- never
    extrapolated from a batch volume against a schedule (the bug this
    rework fixes).
  - "For RD use, estimates only" -- not a family-facing tool.
"""

import io
import re
import sys
from datetime import time as dtime
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is on sys.path so `src` package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_food_name, load_nutrient_amount, load_food_group
from src.models import Ingredient
from src.calculator import (
    label_to_per_100g,
    compute_nutrient_totals_and_coverage,
    dilute,
    required_daily_volume,
    COMMERCIAL_FORMULAS,
)
from src.measures import load_measure_lookup, get_measures_for_food
from src.targets import empty_targets
from src.report import (
    generate_adequacy_report,
    generate_clinical_screen,
    generate_comparator_table,
    generate_density_summary,
    generate_source_breakdown,
)
from src.nutrients import defs_for_tier, registry_by_name, DEFAULT_PACK
from src.intake import (
    aggregate_intake,
    resolve_blend_profile,
    blend_fluid_fraction,
    sorted_intake_log,
    InvalidBlendError,
    TUBE_FEED_LABEL,
    FOOD_DRINK_LABEL,
    TOTAL_LABEL,
)

# ---------------------------------------------------------------------------
# Thinning liquid presets (per 100 mL) — for the dilution what-if
# ---------------------------------------------------------------------------
# These let the RD see *why* broth thins without nourishing, while milk
# recovers more of the lost kcal density. Oil is excluded — it's a calorie
# booster, not a thinner, and belongs in the ingredient list.
# The canonical source is data/packs/canada/thinning_liquids.csv -- an RD
# can add or update liquids there without touching Python. The hardcoded
# dict below is a fallback used only if the CSV is missing.
_THINNING_CSV = PROJECT_ROOT / "data" / "packs" / "canada" / "thinning_liquids.csv"

_THINNING_FALLBACK: dict[str, dict[str, float]] = {
    "Water": {"kcal": 0.0, "protein_g": 0.0, "water_g": 100.0},
    "Broth (chicken)": {"kcal": 1.5, "protein_g": 0.5, "water_g": 95.0},
    "Apple juice": {"kcal": 46.0, "protein_g": 0.1, "water_g": 88.0},
    "Milk (2%)": {"kcal": 50.0, "protein_g": 3.3, "water_g": 89.0},
}


def _load_thinning_liquids() -> dict[str, dict[str, float]]:
    """Load thinning liquid presets from CSV, falling back to hardcoded dict.

    CSV format: name,kcal_per_100mL,protein_g_per_100mL,water_g_per_100mL
    """
    if not _THINNING_CSV.exists():
        liquids = dict(_THINNING_FALLBACK)
    else:
        df = pd.read_csv(_THINNING_CSV)
        liquids = {}
        for _, row in df.iterrows():
            liquids[row["name"]] = {
                "kcal": float(row["kcal_per_100mL"]),
                "protein_g": float(row["protein_g_per_100mL"]),
                "water_g": float(row["water_g_per_100mL"]),
            }
    # "Custom" is always available (RD enters nutrients manually)
    liquids["Custom"] = {"kcal": 0.0, "protein_g": 0.0, "water_g": 0.0}
    return liquids


THINNING_LIQUIDS: dict[str, dict[str, float]] = _load_thinning_liquids()


# ---------------------------------------------------------------------------
# Cached data loading — avoids re-reading 565k-row CSV on every rerun
# ---------------------------------------------------------------------------

@st.cache_data
def get_food_name():
    return load_food_name()


@st.cache_data
def get_nutrient_amount():
    return load_nutrient_amount()


@st.cache_data
def get_measure_lookup():
    return load_measure_lookup()


@st.cache_data
def get_food_group():
    return load_food_group()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_filename(name: str, fallback: str = "btf") -> str:
    """Strip characters that break filenames/downloads on common filesystems.

    e.g. "chicken/rice" -> "chickenrice"; empty or all-invalid names fall
    back to `fallback` so the download always has a usable name.
    """
    cleaned = re.sub(r'[\\/:*?"<>|]', "", (name or "")).strip()
    return cleaned or fallback


def find_food(fn_df: pd.DataFrame, desc: str) -> int | None:
    """Find the first Food_Code matching a description substring."""
    m = fn_df[fn_df["Food_Description_EN"].str.contains(
        desc, case=False, na=False, regex=False
    )]
    if len(m) == 0:
        return None
    return int(m.iloc[0]["Food_Code"])


# CNF_Food_Group_Code for "Beverages" — see data/packs/canada's
# CNF_Food_Group table (loaded via src.data_loader.load_food_group()).
# Used only to seed the counts-as-fluid checkbox's default; the RD can
# always override per ingredient/row (the toggle IS the policy, this
# default is a starting point, not a rule).
_BEVERAGES_GROUP_CODE = 14


def default_counts_as_fluid(food_desc: str, group_code) -> bool:
    """Starting value for a food's counts-as-fluid checkbox.

    True when the food is in CNF's own Beverages group (14), or its
    description starts with the word "Water" (CNF's four standalone
    water entries: "Water, municipal", "Water, mineral, ...", etc. — a
    plain substring match would also catch "Watermelon" or any of the
    176 CNF foods with "water added" in a soup description, which is why
    this checks for the word at the START of the description, not
    anywhere in it). Always user-toggleable afterward.
    """
    if group_code == _BEVERAGES_GROUP_CODE:
        return True
    if re.match(r"^water\b", (food_desc or "").strip(), re.IGNORECASE):
        return True
    return False


# ---------------------------------------------------------------------------
# Session state — Blends (Build tab) + Intake Record (Intake tab), per
# FEED_LOG_REWORK.md section 3.2.
# ---------------------------------------------------------------------------

def _new_blend(name: str) -> int:
    """Create a new empty blend, select it, and return its id."""
    new_id = st.session_state.next_blend_id
    st.session_state.next_blend_id += 1
    st.session_state.blends[new_id] = {
        "name": name,
        "ingredients": [],
        "measured_volume_mL": 0.0,
    }
    st.session_state.selected_blend_id = new_id
    # The "blend_selector" selectbox widget remembers its OWN prior value
    # across reruns once it's been created (Streamlit ignores a widget's
    # `index=`/`value=` argument once session_state already holds an entry
    # for its key) -- so without this pop, selecting a freshly-created
    # blend here would be silently overwritten back to whatever index the
    # widget last showed, the next time the Build tab renders the
    # selectbox. Popping the key forces it to re-seed from `index=`
    # (computed from selected_blend_id) on the next render instead.
    st.session_state.pop("blend_selector", None)
    return new_id


def init_state():
    """Initialize session_state keys for blends, the Intake Record, and
    custom foods (FEED_LOG_REWORK.md section 3.2).

    - blends: dict id -> {name, ingredients: [...], measured_volume_mL} —
      the list of recipe formulations built in the Build tab.
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


def color_status(val: str) -> str:
    """Color-code adequacy status cells.

    "Above UL" and "Below target" are both concerning (red); "Below UL"
    and "Meeting target" are both fine (green) — a UL is a ceiling, not
    an aim, so "Below UL" reads as "fine" the same way "Meeting target"
    does for an RDA/AI nutrient. See src/report.py::_adequacy_status.

    Text colour is set explicitly alongside each pale background: without
    it, a dark theme renders near-white text on pale pink and the status
    becomes unreadable.
    """
    if val in ("Below target", "Above UL"):
        return "background-color: #ffcccc; color: #1a1a1a"
    elif val == "Above target":
        return "background-color: #ffe0b2; color: #1a1a1a"
    elif val in ("Meeting target", "Below UL"):
        return "background-color: #c8e6c9; color: #1a1a1a"
    return ""


# Per-nutrient step sizes for the custom-target number_inputs in the
# Patient & Targets panel below — a UX nicety only (e.g. kcal steps by 50,
# not 1).
# Nutrients not listed fall back to a step derived from their registry
# `decimals`.
_TARGET_STEP_OVERRIDES: dict[str, float] = {
    "energy_kcal": 50.0,
    "fluid_mL": 100.0,
    "sodium_mg": 100.0,
    "potassium_mg": 100.0,
    "calcium_mg": 50.0,
    "protein_g": 5.0,
    "vitamin_b12_ug": 0.5,
}

# Display formats for those same inputs: macros never need two decimal
# places -- one at most is plenty (author feedback 2026-07-20).
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


# ---------------------------------------------------------------------------
# Reusable "add a food" component (FEED_LOG_REWORK.md section 3.3)
# ---------------------------------------------------------------------------
# The CNF-search-with-food-group-filter and the custom-food NFt-lookalike
# form are the SAME UI whether the food is going into a blend's ingredient
# list or becoming a single Intake Record oral row — only the destination
# differs. This function has no opinion about the destination: it renders
# the search/entry UI and returns a fully-specified food dict when its Add
# button is clicked, letting the caller decide where the food goes. This
# is the UI-layer version of the same "one source of truth for scaling
# logic" discipline behind src/calculator.py's compute_nutrient_totals().


def _note(message: str) -> None:
    """A guidance call-out in Dietitians-of-Canada-style maroon instead of
    st.info's default blue (author theming request 2026-07-20). Used for
    the empty-state "nothing here yet" guidance boxes. Markdown syntax
    won't render inside the raw HTML div -- use <strong>/<br> instead."""
    st.markdown(
        f'<div style="background-color: #f9e8eb; border-left: 4px solid '
        f'#A4243A; padding: 0.6rem 0.9rem; border-radius: 0.25rem; '
        f'color: #3d3d3d;">{message}</div>',
        unsafe_allow_html=True,
    )


def render_add_food_ui(
    fn_df: pd.DataFrame,
    na_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    fg_df: pd.DataFrame,
    key_prefix: str,
    add_button_label: str = "Add",
    show_counts_as_fluid_toggle: bool = False,
) -> dict | None:
    """Render the CNF-search / custom-food-from-label add-a-food UI.

    Returns a dict {food_code, food_description, grams, unit,
    counts_as_fluid} on the render where the Add button is clicked and the
    entry is valid, else None. `key_prefix` must be unique per call site
    (e.g. "blend_3" vs "oral_dialog") so two simultaneous instances of this
    component never collide on widget keys.

    show_counts_as_fluid_toggle: when True, renders an editable
    counts_as_fluid checkbox (seeded with the same auto-default used
    elsewhere -- CNF Beverages group or mL-basis custom food) right before
    the Add button, and the RD's choice (default or overridden) is what
    ends up in the returned dict. The Build tab leaves this False -- a
    blend's ingredient table already lets the RD toggle counts_as_fluid
    after adding; the "Add food/drink" UI passes True, since
    FEED_LOG_REWORK.md section 3.4 calls for the toggle to live right there
    (there's no ingredient table for a single oral row).
    """
    add_mode = st.radio(
        "Source",
        [
            "Search foods from the Canadian Nutrient File",
            "Enter a Nutrition Facts label (custom food)",
        ],
        horizontal=True,
        key=f"{key_prefix}_add_mode",
    )

    result: dict | None = None

    if add_mode == "Search foods from the Canadian Nutrient File":  # else: NFt label form
        # Food-group filter: CNF's own 23 native CNF_Food_Group categories
        # — narrows the search pool *before* the substring search below.
        group_options = ["All"] + sorted(fg_df["CNF_Food_Group_Description_EN"].tolist())
        group_code_by_desc = dict(
            zip(fg_df["CNF_Food_Group_Description_EN"], fg_df["CNF_Food_Group_Code"])
        )
        group_desc_by_code = dict(
            zip(fg_df["CNF_Food_Group_Code"], fg_df["CNF_Food_Group_Description_EN"])
        )

        gc1, gc2 = st.columns([1, 2])
        selected_group = gc1.selectbox("Food group", group_options, key=f"{key_prefix}_group")
        search_term = gc2.text_input(
            "Search foods", "", placeholder="e.g., chicken, rice, oil",
            key=f"{key_prefix}_search",
        )

        food_code: int | None = None
        food_desc: str | None = None
        calculated_grams = 0.0
        sel_group_code = None

        search_pool = fn_df
        if selected_group != "All":
            search_pool = fn_df[fn_df["CNF_Food_Group_Code"] == group_code_by_desc[selected_group]]

        if len(search_term) >= 2:
            matches = search_pool[search_pool["Food_Description_EN"].str.contains(
                search_term, case=False, na=False, regex=False
            )]
            matches = matches.sort_values("Food_Description_EN").head(50)

            if len(matches) > 0:
                food_options = [
                    f"{row['Food_Description_EN']}  [{int(row['Food_Code'])}]"
                    for _, row in matches.iterrows()
                ]
                selected = st.selectbox(
                    f"Found {len(matches)} foods", food_options, key=f"{key_prefix}_food_select"
                )
                idx = food_options.index(selected)
                food_code = int(matches.iloc[idx]["Food_Code"])
                food_desc = str(matches.iloc[idx]["Food_Description_EN"])
                sel_group_code = matches.iloc[idx].get("CNF_Food_Group_Code")
                sel_group_desc = group_desc_by_code.get(sel_group_code)
                if sel_group_desc:
                    st.caption(f"Food group: {sel_group_desc}")

                # Household measure dropdown — same precision-vs-convenience
                # mechanism reused verbatim for oral entries (section 3.3).
                measures = get_measures_for_food(food_code, lookup_df)
                if len(measures) > 0:
                    measure_opts = [
                        f"{r['Measure_Description_and_Unit_EN']}  ({r['grams']:.1f} g)"
                        for _, r in measures.iterrows()
                    ]
                    sel_measure = st.selectbox(
                        "Household measure", measure_opts, key=f"{key_prefix}_measure"
                    )
                    m_idx = measure_opts.index(sel_measure)
                    grams_per = float(measures.iloc[m_idx]["grams"])
                    qty = st.number_input(
                        "Quantity", min_value=0.0, value=1.0, step=0.5, key=f"{key_prefix}_qty"
                    )
                    calculated_grams = grams_per * qty
                    st.caption(f"= **{calculated_grams:.1f} g**")

                    if st.checkbox("Enter grams directly", key=f"{key_prefix}_grams_override"):
                        calculated_grams = st.number_input(
                            "Grams",
                            min_value=0.0,
                            value=round(calculated_grams, 1),
                            step=1.0,
                            key=f"{key_prefix}_grams_direct",
                        )
                else:
                    _note("No household measures for this food.")
                    calculated_grams = st.number_input(
                        "Grams", min_value=0.0, value=100.0, step=1.0,
                        key=f"{key_prefix}_grams_nomeasure",
                    )
            else:
                _note("No foods found. Try another search.")
        else:
            st.caption("Type at least 2 characters to search.")

        if food_code is not None and calculated_grams > 0:
            default_fluid = default_counts_as_fluid(food_desc, sel_group_code)
            if show_counts_as_fluid_toggle:
                final_fluid = st.checkbox(
                    "Counts as fluid", value=default_fluid, key=f"{key_prefix}_fluid_toggle"
                )
            else:
                final_fluid = default_fluid
            if st.button(f"➕ {add_button_label}", key=f"{key_prefix}_add_cnf_btn"):
                result = {
                    "food_code": food_code,
                    "food_description": food_desc,
                    "grams": float(calculated_grams),
                    "unit": "g",
                    "counts_as_fluid": final_fluid,
                }

    else:  # Custom food from label — a Canadian Nutrition Facts lookalike
        st.caption("Enter values exactly as printed on the nutrition facts label.")
        basis_choice = st.radio(
            "Label basis",
            ["Serving size in weight (g)", "Serving size in volume (mL)"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"{key_prefix}_basis",
        )
        basis = "g" if "weight" in basis_choice else "mL"

        _registry_map = registry_by_name(DEFAULT_PACK)
        cv: dict[str, float] = {}

        # NFt lookalike styling (visual only). Scoped via a per-key-prefix
        # container key so the two simultaneous instances (blend add form +
        # oral dialog form) don't fight over the same CSS hook.
        box_key = f"{key_prefix}_nft_box"
        st.markdown(
            f"""
            <style>
            .nft-title {{ font-size: 1.25rem; font-weight: 800;
                         letter-spacing: -0.02em; margin-bottom: 0.05rem; }}
            .nft-main {{ font-weight: 700; padding-top: 0.1rem; }}
            .nft-sub {{ font-weight: 400; padding-top: 0.1rem;
                       padding-left: 1.4em; }}
            .nft-cal {{ font-weight: 800; font-size: 1.05rem;
                       padding-top: 0.1rem; }}
            hr.nft-thick {{ border: none; border-top: 6px solid #000;
                            margin: 0.25rem 0; }}
            hr.nft-thin {{ border: none; border-top: 1px solid #000;
                           margin: 0.15rem 0; }}
            .st-key-{box_key} input[type="number"] {{ text-align: right; }}
            /* Tighten the vertical rhythm inside the NFt box: each
               nutrient row is its own st.columns block, and Streamlit's
               default 1rem vertical gap made the label sprawl far
               beyond the compact print of a real Nutrition Facts table
               (author feedback 2026-07-20). */
            .st-key-{box_key} [data-testid="stVerticalBlock"] {{
                gap: 0.35rem;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        def _nft_step(d) -> float:
            # Real Nutrition Facts tables don't print two decimal places --
            # one at most (author feedback 2026-07-20).
            return 1.0 if d.decimals == 0 else 0.1

        def _nft_field(text: str, css_class: str, key: str, **kwargs) -> float:
            # %g displays the entered value with no forced trailing zeros --
            # real labels don't print two decimal places (author feedback).
            kwargs.setdefault("format", "%g")
            name_col, val_col = st.columns([3, 2])
            with name_col:
                st.markdown(f'<div class="{css_class}">{text}</div>', unsafe_allow_html=True)
            with val_col:
                return st.number_input(
                    text, label_visibility="collapsed", key=key, **kwargs
                )

        label_col, _spacer = st.columns([2, 3])
        with label_col:
            with st.container(border=True, key=box_key):
                st.markdown('<div class="nft-title">Nutrition Facts</div>', unsafe_allow_html=True)
                cname = st.text_input("Food name", "", key=f"{key_prefix}_cname")
                cserving = _nft_field(
                    f"Serving size ({basis})", "nft-main", f"{key_prefix}_cv_serving",
                    min_value=1.0, value=100.0, step=1.0,
                )
                st.markdown('<hr class="nft-thick">', unsafe_allow_html=True)

                label_defs = [d for d in defs_for_tier("label", pack=DEFAULT_PACK) if d.on_label]
                energy_def = next(d for d in label_defs if d.name == "energy_kcal")
                cv[energy_def.name] = _nft_field(
                    f"{energy_def.label} ({energy_def.unit})", "nft-cal", f"{key_prefix}_cv_energy",
                    min_value=0.0, value=0.0, step=1.0,
                )
                st.markdown('<hr class="nft-thin">', unsafe_allow_html=True)

                NFT_MAIN_NAMES = {
                    "fat_g", "carbohydrate_g", "protein_g", "cholesterol_mg",
                    "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg",
                }
                remaining_defs = [d for d in label_defs if d.name != "energy_kcal"]
                for d in remaining_defs:
                    css_class = "nft-main" if d.name in NFT_MAIN_NAMES else "nft-sub"
                    cv[d.name] = _nft_field(
                        f"{d.label} ({d.unit})", css_class, f"{key_prefix}_cv_{d.name}",
                        min_value=0.0, value=0.0, step=_nft_step(d),
                    )
                    if d.name == "sodium_mg":
                        st.markdown('<hr class="nft-thick">', unsafe_allow_html=True)

                st.markdown('<hr class="nft-thick">', unsafe_allow_html=True)
                with st.expander("Optional nutrients on this label?"):
                    st.caption(
                        "Vitamin D, B12, zinc, magnesium, and phosphorus are "
                        "CFIA-optional. Enter them if this label carries them "
                        "so the values reach the BTF micro screen."
                    )
                    clinical_defs = defs_for_tier("clinical", pack=DEFAULT_PACK)
                    for d in clinical_defs:
                        cv[d.name] = _nft_field(
                            f"{d.label} ({d.unit})", "nft-sub", f"{key_prefix}_cv_clin_{d.name}",
                            min_value=0.0, value=0.0, step=_nft_step(d),
                        )

            st.caption(
                "Water/moisture is on no nutrition facts label, so recipes "
                "using custom foods will underestimate the free-water "
                "fraction — the label simply has nowhere to report it."
            )

            st.markdown("**Amount used**")
            cgrams = st.number_input(
                f"Amount used ({basis})",
                min_value=0.0,
                value=100.0,
                step=1.0,
                format="%g",
                key=f"{key_prefix}_cgrams",
                help=f"Same unit as the label basis above ({basis}) — an "
                     f"mL-basis food's usage can only be entered in mL, by "
                     f"design (no cross-conversion between g and mL).",
            )

            # mL-basis custom foods default to counts-as-fluid=True — a
            # liquid entered from a label has no CNF moisture data, so the
            # I&O full-volume convention is the only fluid signal available
            # for it. Still overridable when show_counts_as_fluid_toggle.
            _custom_default_fluid = basis == "mL"
            if show_counts_as_fluid_toggle:
                _custom_final_fluid = st.checkbox(
                    "Counts as fluid", value=_custom_default_fluid,
                    key=f"{key_prefix}_custom_fluid_toggle",
                )
            else:
                _custom_final_fluid = _custom_default_fluid

            if st.button(f"➕ {add_button_label} custom food", key=f"{key_prefix}_add_custom_btn"):
                if not cname:
                    st.warning("Please enter a food name.")
                elif cserving <= 0:
                    st.warning("Serving size must be positive.")
                else:
                    code = st.session_state.next_custom_code
                    st.session_state.next_custom_code -= 1
                    # Only fold in fields the RD actually changed from the
                    # form's 0.0 default — see the zero-coverage-hiding
                    # note this logic has carried since the round-2 pass.
                    st.session_state.custom_foods[code] = {
                        name: label_to_per_100g(val, cserving)
                        for name, val in cv.items()
                        if val > 0
                    }
                    result = {
                        "food_code": code,
                        "food_description": f"{cname} (custom)",
                        "grams": float(cgrams),
                        "unit": basis,
                        "counts_as_fluid": _custom_final_fluid,
                    }

    return result


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="BTF Calculator",
    page_icon="🥕",
    layout="wide",
)

# Tab labels as big as a subheading — Streamlit doesn't expose this as a
# parameter, so it's injected CSS. Verified against Streamlit 1.58's actual
# compiled frontend bundle: each tab button renders as
# `<button data-testid="stTab">` wrapping a
# `[data-testid="stMarkdownContainer"]` div whose `<p>` carries the label.
# The maroon accent itself (selected-tab indicator, radios, sliders) comes
# from .streamlit/config.toml's primaryColor; this block handles what the
# theme can't: label size, bold, spacing, and selected-label colour
# (author theming request 2026-07-20, Dietitians-of-Canada-style maroon).
st.markdown(
    """
    <style>
    /* Base font bump: Streamlit's default body text is 16px, at the
       small end of typical websites (~16-19px). Nearly everything in
       Streamlit is sized in rem, so scaling the root scales the whole
       app proportionally -- tab labels, tables, inputs, captions.
       112.5% (18px) still read small to the author; 125% = 20px
       (author feedback 2026-07-20). Tune this one number to resize the
       whole app. */
    html {
        font-size: 125%;
    }
    /* Trim Streamlit's large default top padding on the main content
       block (it reserves room to clear the top toolbar). The default
       leaves a big empty gap above the first element; 2.5rem keeps a
       little breathing room below the Cloud toolbar without the void.
       Both selectors cover Streamlit version drift in the testid name. */
    .stApp [data-testid="stMainBlockContainer"],
    .stApp .block-container {
        padding-top: 2.5rem !important;
    }
    /* Tab-label sizing, version-resilient. Streamlit's tab DOM attribute
       has drifted across releases (data-baseweb="tab" on older builds,
       data-testid="stTab" on newer) and attribute selectors kept missing
       on the Streamlit Community Cloud runtime while matching the local
       .venv (1.58) -- same code, different rendered DOM. The ARIA
       role="tab" is the one attribute BaseWeb sets on the tab button in
       EVERY version, so lead with it; the data-* selectors stay as extra
       coverage. Target the button plus every plausible text wrapper (p /
       div / span), and use !important -- Streamlit sizes the inner <p> in
       rem itself, which otherwise wins over a plain rule. */
    button[role="tab"],
    button[data-testid="stTab"],
    button[data-baseweb="tab"] {
        padding-top: 0.4rem;
        padding-bottom: 0.4rem;
        margin-right: 1.25rem;
    }
    /* Target ONLY the tab's text <p>, via the version-stable role="tab".
       An earlier pass also matched div/span wrappers with blanket
       !important; on Streamlit 1.60 that compounded into oversized, clunky
       tabs. A single !important on the <p>'s font-size is enough to beat
       Streamlit's own rem sizing without blowing up the layout. */
    button[role="tab"] p,
    button[data-testid="stTab"] p,
    button[data-baseweb="tab"] p {
        font-size: 1.25rem !important;
        font-weight: 700;
    }
    button[role="tab"][aria-selected="true"] p,
    button[data-testid="stTab"][aria-selected="true"] p,
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #A4243A;
    }
    /* Heading scale -- two tiers, author-tuned on the deploy.
       Tier A: page title (h1) sized to match the tab labels (both 1.25rem,
       bold) -- title must be no larger than the tabs. Tier B: section
       headings (h3 = st.subheader, the one consistent section-heading
       style -- bold-markdown pseudo-headings were converted to
       st.subheader so every section heading matches) a clear step down at
       1.05rem. h2 = st.header, currently unused; kept between the tiers.
       High specificity + !important is REQUIRED: on Streamlit 1.60 (the
       Cloud runtime) the framework sizes headings via a CLASS selector,
       which outranks a bare `h1 { ...!important }` (specificity is checked
       before importance), so plain rules applied locally on 1.58 but lost
       on the deploy. Prefixing with the stable stApp / stHeading container
       selectors raises specificity above Streamlit's own rule. */
    .stApp h1,
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stHeadingWithActionElements"] h1 { font-size: 1.5rem !important; }
    .stApp h2,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stHeadingWithActionElements"] h2 { font-size: 1.15rem !important; }
    .stApp h3,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stHeadingWithActionElements"] h3 { font-size: 1.05rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

init_state()

# Load cached CNF data (runs once, then served from cache)
fn = get_food_name()
na = get_nutrient_amount()
lookup = get_measure_lookup()
fg = get_food_group()


# ===========================================================================
# TOP BAR — chrome only: patient/day label, load example. No sidebar.
# ===========================================================================

top_l, top_r = st.columns([4, 1])
with top_l:
    recipe_name = st.text_input("Patient / day label", "My BTF day")
with top_r:
    st.write("")  # vertical spacer so the button aligns with the text input
    load_example_clicked = st.button("📋 Load example day", width="stretch")

if load_example_clicked:
    chicken = find_food(fn, "Chicken, broiler, breast, skinless, boneless, meat, raw")
    rice = find_food(fn, "Grains, rice, white, long-grain, parboiled, cooked")
    oil = find_food(fn, "Vegetable oil, canola")
    water = find_food(fn, "Water, municipal")
    banana = find_food(fn, "Banana, raw")
    if chicken and rice and oil and water and banana:
        # Drop any pre-existing empty starter blend(s) so the example
        # doesn't leave clutter alongside "Morning blend".
        st.session_state.blends = {
            bid: b for bid, b in st.session_state.blends.items() if b["ingredients"]
        }
        example_id = _new_blend("Morning blend")
        st.session_state.next_ingr_id += 4
        st.session_state.blends[example_id]["ingredients"] = [
            {"id": st.session_state.next_ingr_id - 3, "food_code": chicken, "food_description": "Chicken breast", "grams": 200.0, "unit": "g", "counts_as_fluid": False},
            {"id": st.session_state.next_ingr_id - 2, "food_code": rice, "food_description": "Rice, cooked", "grams": 150.0, "unit": "g", "counts_as_fluid": False},
            {"id": st.session_state.next_ingr_id - 1, "food_code": oil, "food_description": "Canola oil", "grams": 15.0, "unit": "g", "counts_as_fluid": False},
            {"id": st.session_state.next_ingr_id, "food_code": water, "food_description": "Water, municipal", "grams": 200.0, "unit": "g", "counts_as_fluid": True},
        ]
        st.session_state.blends[example_id]["measured_volume_mL"] = 550.0

        # Example Intake Record (design doc section 3.2): 300 + 100 mL of
        # the blend, one flush, one oral CNF food via the real
        # household-measure entry ("1 small" banana) — internally
        # consistent, spans both source families.
        banana_measures = get_measures_for_food(banana, lookup)
        small = banana_measures[
            banana_measures["Measure_Description_and_Unit_EN"].str.contains(
                "small", case=False, na=False
            )
        ]
        banana_grams = float(small.iloc[0]["grams"]) if len(small) > 0 else 100.0

        st.session_state.next_intake_id = 4
        st.session_state.intake_log = [
            {"id": 1, "time": dtime(8, 0), "source_type": "blend", "source_id": example_id,
             "food_description": None, "amount": 300.0, "unit": "mL", "counts_as_fluid": False},
            {"id": 2, "time": dtime(12, 0), "source_type": "blend", "source_id": example_id,
             "food_description": None, "amount": 100.0, "unit": "mL", "counts_as_fluid": False},
            {"id": 3, "time": dtime(10, 0), "source_type": "flush", "source_id": None,
             "food_description": None, "amount": 100.0, "unit": "mL", "counts_as_fluid": True},
            {"id": 4, "time": dtime(8, 30), "source_type": "oral", "source_id": banana,
             "food_description": "Banana, raw — 1 small", "amount": banana_grams, "unit": "g",
             "counts_as_fluid": False},
        ]
        st.session_state.custom_foods = {}
        st.session_state.next_custom_code = -1
        st.session_state["load_example"] = True
        st.rerun()
    else:
        st.error("Could not find example foods in CNF.")

st.title(f"🥕🥦🥤 {recipe_name or 'BTF day'} 💉💧🍌")
st.caption("⚠️ Under development — for RD use, estimates only. Double-check all numbers before clinical use.")


# ===========================================================================
# Reusable Intake Record helpers — used by the Intake tab's editor below
# and (once resolved) by the Results tab's chart note.
# ===========================================================================

_FLUSH_LABEL = "Water flush"


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


def _intake_row_label(row: dict) -> str:
    """Human-readable one-line summary of an Intake Record row, for the
    row list and (later) the chart note."""
    t = row.get("time")
    t_str = t.strftime("%H:%M") if t else "(no time)"
    source_type = row["source_type"]
    if source_type == "blend":
        blend = st.session_state.blends.get(row["source_id"])
        name = blend["name"] if blend else "(deleted blend)"
    elif source_type == "formula":
        name = row["source_id"]
    elif source_type == "flush":
        name = row.get("food_description") or _FLUSH_LABEL
    else:
        name = row.get("food_description") or "(unknown food)"
    return f"{t_str} — {name} — {row['amount']:.0f} {row['unit']}"


def _format_tube_feed_bits(rows: list[dict]) -> list[str]:
    """Group tube-feed rows for the chart note (FEED_LOG_REWORK.md
    section 3.5's own example format): consecutive rows against the same
    blend/formula read as "0800 300 mL + 1200 100 mL Morning blend", not
    two disconnected sentences. Flush rows are grouped as
    "flushes N×amount mL" when every flush shares the same amount, else
    listed individually (e.g. one 100 mL + one 150 mL flush).
    """
    bits = []
    blend_formula_rows = [r for r in rows if r["source_type"] in ("blend", "formula")]
    flush_rows = [r for r in rows if r["source_type"] == "flush"]

    seen_keys: list[tuple] = []
    groups: dict[tuple, list[dict]] = {}
    for r in blend_formula_rows:
        key = (r["source_type"], r["source_id"])
        if key not in groups:
            groups[key] = []
            seen_keys.append(key)
        groups[key].append(r)

    for key in seen_keys:
        group_rows = groups[key]
        source_type, source_id = key
        if source_type == "blend":
            name = st.session_state.blends.get(source_id, {}).get("name", "(deleted blend)")
        else:
            name = source_id
        amounts_text = " + ".join(
            f"{(r['time'].strftime('%H%M') if r['time'] else '(no time)')} {r['amount']:.0f} mL"
            for r in group_rows
        )
        bits.append(f"{amounts_text} {name}")

    if flush_rows:
        amounts = {r["amount"] for r in flush_rows}
        if len(amounts) == 1 and len(flush_rows) > 1:
            bits.append(f"flushes {len(flush_rows)}×{flush_rows[0]['amount']:.0f} mL")
        else:
            for r in flush_rows:
                t = r["time"].strftime("%H%M") if r["time"] else "(no time)"
                bits.append(f"{t} {r['amount']:.0f} mL flush")

    return bits


def _format_oral_bits(rows: list[dict]) -> list[str]:
    """Chart-note phrasing for oral rows, e.g. '0830 1 small banana' or
    '1030 125 mL apple juice' (design doc section 3.5's own example)."""
    bits = []
    for r in rows:
        t = r["time"].strftime("%H%M") if r["time"] else "(no time)"
        desc = r.get("food_description") or "(unknown food)"
        bits.append(f"{t} {r['amount']:.0f} {r['unit']} {desc}")
    return bits


def _render_add_oral_ui(fn_df, na_df, lookup_df, fg_df):
    """FEED_LOG_REWORK.md section 3.4: the oral-entry UI. Reuses the same
    search-or-custom-food component as the Build tab (section 3.3), plus a
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
    st.caption("Log a single food or drink the client had by mouth.")
    oral_time = st.time_input("Time (optional)", value=None, key="oral_time_input")
    new_food = render_add_food_ui(
        fn_df, na_df, lookup_df, fg_df,
        key_prefix="oral_add",
        add_button_label="Add",
        show_counts_as_fluid_toggle=True,
    )
    if new_food is not None:
        st.session_state.next_intake_id += 1
        st.session_state.intake_log.append({
            "id": st.session_state.next_intake_id,
            "time": oral_time,
            "source_type": "oral",
            "source_id": new_food["food_code"],
            "food_description": new_food["food_description"],
            "amount": new_food["grams"],
            "unit": new_food["unit"],
            "counts_as_fluid": new_food["counts_as_fluid"],
        })
        st.rerun()


# ===========================================================================
# Three tabs, in encounter order: Nutrition Targets (the patient-side
# numbers the RD brings from their own assessment) → Feed Recipes (the
# blend pages: ingredients, per-blend results, comparator, flow test) →
# Daily Intake Record (the 24-hour record/plan, with the day-level
# results directly beneath the record they summarize).
# ===========================================================================

targets_tab, recipes_tab, record_tab = st.tabs(
    ["Nutrition Targets", "Feed Recipes", "Daily Intake Record"]
)

with targets_tab:
    st.subheader("Patient weight (optional)")
    _w_col, _wu_col = st.columns([3, 1])
    _weight_unit = _wu_col.radio(
        "Unit", ["kg", "lbs"], horizontal=True, key="weight_unit"
    )
    _weight_entered = _w_col.number_input(
        f"Weight ({_weight_unit})",
        min_value=0.0,
        value=0.0,
        step=0.5,
        format="%.1f",
        help="Optional — used only to show kcal/kg, protein g/kg, and "
             "fluid mL/kg in the Daily Intake Record tab. No target, equation, or "
             "IBW is computed from it; assessment stays outside this app.",
    )
    patient_weight_kg = (
        _weight_entered if _weight_unit == "kg" else _weight_entered / 2.20462
    )
    _kg_note = (
        f" = {patient_weight_kg:.1f} kg"
        if _weight_unit == "lbs" and _weight_entered > 0
        else ""
    )
    st.caption(f"Blank/0 = not provided. Display only — not a target.{_kg_note}")

    st.subheader("Targets (optional)")
    st.caption("Blank = no target; enter patient-specific values.")
    targets = empty_targets()
    tc1, tc2 = st.columns(2)
    cols = (tc1, tc2)
    _registry_map = registry_by_name(DEFAULT_PACK)
    for i, nutrient_name in enumerate(empty_targets()):
        col = cols[i % 2]
        if nutrient_name == "fluid_mL":
            disp_label, unit, decimals = "Fluid", "mL", 0
        else:
            d = _registry_map[nutrient_name]
            disp_label, unit, decimals = d.label, d.unit, d.decimals
        step = _TARGET_STEP_OVERRIDES.get(
            nutrient_name, 1.0 if decimals == 0 else round(10 ** (-decimals), decimals)
        )
        targets[nutrient_name] = col.number_input(
            f"{disp_label} {unit}/day", min_value=0.0, value=0.0, step=step,
            format=_TARGET_FORMAT_OVERRIDES.get(
                nutrient_name, f"%.{min(decimals, 1)}f"
            ),
        )


with recipes_tab:
    # --- Blend selector ---
    st.subheader("Blend")
    blend_ids = list(st.session_state.blends.keys())
    if st.session_state.selected_blend_id not in blend_ids:
        st.session_state.selected_blend_id = blend_ids[0] if blend_ids else None
    blend_names = [st.session_state.blends[bid]["name"] or f"Blend {bid}" for bid in blend_ids]
    sel_idx = blend_ids.index(st.session_state.selected_blend_id)

    bsel1, bsel2, bsel3 = st.columns([3, 1, 1])
    chosen_idx = bsel1.selectbox(
        "Select blend",
        options=list(range(len(blend_ids))),
        index=sel_idx,
        format_func=lambda i: blend_names[i],
        key="blend_selector",
    )
    st.session_state.selected_blend_id = blend_ids[chosen_idx]
    selected_blend_id = st.session_state.selected_blend_id
    selected_blend = st.session_state.blends[selected_blend_id]

    if bsel2.button("➕ New blend", width="stretch"):
        _new_blend(f"Blend {len(st.session_state.blends) + 1}")
        st.rerun()
    if bsel3.button("🗑️ Delete blend", width="stretch", disabled=len(blend_ids) <= 1):
        removed_id = selected_blend_id
        del st.session_state.blends[removed_id]
        removed_rows = [
            r for r in st.session_state.intake_log
            if r["source_type"] == "blend" and r["source_id"] == removed_id
        ]
        st.session_state.intake_log = [
            r for r in st.session_state.intake_log
            if not (r["source_type"] == "blend" and r["source_id"] == removed_id)
        ]
        st.session_state.selected_blend_id = next(iter(st.session_state.blends))
        # Same widget-state gotcha as _new_blend() -- force the selectbox
        # to re-seed from `index=` next render instead of clinging to
        # whatever index it last showed (which may now point at a
        # different, surviving blend than intended, or be out of range).
        st.session_state.pop("blend_selector", None)
        if removed_rows:
            st.toast(
                f"Removed {len(removed_rows)} Intake Record row(s) that referenced "
                "the deleted blend."
            )
        st.rerun()

    selected_blend["name"] = st.text_input(
        "Blend name", selected_blend["name"], key=f"blend_name_{selected_blend_id}"
    )

    # Per-blend density mini-summary — orients the RD before they start
    # editing ingredients (design doc section 3.3).
    try:
        if selected_blend["ingredients"]:
            _mini_profile, _mini_fluid_frac = resolve_blend_profile(
                selected_blend, na, st.session_state.custom_foods
            )
            if selected_blend["measured_volume_mL"] > 0:
                st.caption(
                    f"**{_mini_profile.kcal_per_mL:.3f} kcal/mL** · "
                    f"**{_mini_profile.protein_per_mL:.3f} g protein/mL**"
                )
    except InvalidBlendError:
        st.warning(
            "This blend has ingredients but no measured volume yet — "
            "densities can't be computed until you enter one below."
        )

    st.divider()

    # --- Add ingredient (reusable component, section 3.3) ---
    st.subheader(f'Add ingredient to "{selected_blend["name"]}"')
    new_ingredient = render_add_food_ui(
        fn, na, lookup, fg, key_prefix=f"blend_{selected_blend_id}",
        add_button_label="Add to blend",
    )
    if new_ingredient is not None:
        st.session_state.next_ingr_id += 1
        selected_blend["ingredients"].append({
            "id": st.session_state.next_ingr_id, **new_ingredient,
        })
        st.rerun()

    # --- Blend details ---
    st.subheader("Blend details")
    _example_loaded = st.session_state.pop("load_example", False)

    measured_volume = st.number_input(
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
        _note("Add ingredients above to get started.")
    else:
        st.caption(
            "\"Counts as fluid\" drives the Daily Intake Record tab's "
            "Fluid provided row (full-volume I&O convention) — auto-checked for CNF "
            "Beverages and mL-basis custom foods, always your call "
            "otherwise (e.g. soup has no validated rule of thumb)."
        )
        for i, ing in enumerate(selected_blend["ingredients"]):
            unit = ing.get("unit", "g")
            cols = st.columns([4, 2, 2, 1])
            cols[0].write(f"{i + 1}. {ing['food_description']}")
            new_amount = cols[1].number_input(
                f"Amount for {ing['food_description']}",
                value=float(ing["grams"]),
                min_value=0.0,
                step=1.0,
                format="%g",
                key=f"grams_{ing['id']}",
                label_visibility="collapsed",
            )
            cols[1].caption(unit)
            selected_blend["ingredients"][i]["grams"] = new_amount
            new_fluid_flag = cols[2].checkbox(
                "Counts as fluid",
                value=bool(ing.get("counts_as_fluid", False)),
                key=f"fluid_{ing['id']}",
            )
            selected_blend["ingredients"][i]["counts_as_fluid"] = new_fluid_flag
            if cols[3].button("❌", key=f"del_{ing['id']}"):
                selected_blend["ingredients"].pop(i)
                st.rerun()

        total_g = sum(
            ing["grams"] for ing in selected_blend["ingredients"]
            if ing.get("unit", "g") == "g"
        )
        total_mL = sum(
            ing["grams"] for ing in selected_blend["ingredients"]
            if ing.get("unit", "g") == "mL"
        )
        if total_mL > 0:
            st.caption(f"Total ingredient weight: **{total_g:.0f} g** + **{total_mL:.0f} mL**")
        else:
            st.caption(f"Total ingredient weight: **{total_g:.0f} g**")

        _blend_fluid_mL = blend_fluid_fraction(
            selected_blend["ingredients"], selected_blend["measured_volume_mL"]
        ) * selected_blend["measured_volume_mL"]
        if _blend_fluid_mL > 0:
            st.caption(f"Fluid from ingredients (this batch): **{_blend_fluid_mL:.0f} mL**")

        if st.button("🗑️ Clear this blend's ingredients"):
            selected_blend["ingredients"] = []
            st.rerun()


with record_tab:
    st.subheader("Intake Record")
    st.caption(
        "What was actually given — tube feed (blends, formulas, flushes) "
        "and food/drink by mouth, together in one chronological list."
    )

    # Delivery method: a single free-choice field for chart-note wording
    # only (FEED_LOG_REWORK.md section 3.4) — it no longer drives any math.
    delivery_method = st.text_input(
        "Delivery method (chart-note wording only)", "Syringe bolus",
        help="Free text — syringe, gravity, etc. Doesn't affect any "
             "calculation; every row's own amount is what's summed.",
    )

    # Always-visible summary line — aggregated NUTRIENT totals, never a
    # raw volume/mass roll-up (750 mL of blend + 45 g of banana isn't a
    # meaningful single number). See FEED_LOG_REWORK.md section 3.4.
    _banner_totals = aggregate_intake(
        st.session_state.intake_log, st.session_state.blends, na,
        custom_foods=st.session_state.custom_foods,
    )
    _b_kcal = _banner_totals.nutrient_totals.get("energy_kcal", 0.0)
    _b_protein = _banner_totals.nutrient_totals.get("protein_g", 0.0)
    _b_fluid = _banner_totals.fluid_provided_mL
    st.markdown(
        f"**Today: ~{_b_kcal:.0f} kcal | {_b_protein:.0f} g protein | "
        f"{_b_fluid:.0f} mL fluid provided**"
    )

    # --- Add tube feed ---
    with st.expander("➕ 💉 Add tube feed"):
        tf1, tf2, tf3 = st.columns([1, 2, 1])
        tf_time = tf1.time_input("Time (optional)", value=None, key="tf_time_input")
        _source_options, _source_map = _intake_source_options()
        tf_source_label = tf2.selectbox("Source", _source_options, key="tf_source_select")
        tf_amount = tf3.number_input(
            "Volume (mL)", min_value=0.0, value=0.0, step=10.0, key="tf_amount_input"
        )
        if st.button("Add tube feed row", key="tf_add_btn"):
            if tf_amount > 0:
                tf_source_type, tf_source_id = _source_map[tf_source_label]
                st.session_state.next_intake_id += 1
                st.session_state.intake_log.append({
                    "id": st.session_state.next_intake_id,
                    "time": tf_time,
                    "source_type": tf_source_type,
                    "source_id": tf_source_id,
                    "food_description": None,
                    "amount": float(tf_amount),
                    "unit": "mL",
                    "counts_as_fluid": tf_source_type == "flush",
                })
                st.rerun()
            else:
                st.warning("Enter a volume greater than 0 mL.")

    # --- Add water flush: three precisions, one list (author feedback
    # 2026-07-20). A single flush for the precise; a with-feeds
    # calculation for the common "60 mL before and after each feed"
    # pattern; a rough daily figure for med flushes (no meds list --
    # deliberately). All produce ordinary flush rows in the one
    # intake_log, summed the same way as everything else.
    # Sits right after "Add tube feed": flushes are part of the
    # tube-feeding routine (before/after feeds, med flushes down the
    # tube), so they group with the tube-side entry; oral intake is the
    # other route entirely and goes last (author feedback 2026-07-20).
    with st.expander("➕ 💧 Add water flushes"):
        _flush_mode = st.radio(
            "How do you want to count flushes?",
            ["Single flush", "With feeds (calculated)", "Med flushes (daily, rough)"],
            horizontal=True,
            key="flush_mode",
        )
        _flush_label = "Water flush"
        _flush_time = None
        _flush_total = 0.0
        if _flush_mode == "Single flush":
            _sf1, _sf2 = st.columns(2)
            _flush_time = _sf1.time_input(
                "Time (optional)", value=None, key="flush_single_time"
            )
            _flush_total = _sf2.number_input(
                "Volume (mL)", min_value=0.0, value=0.0, step=10.0,
                key="flush_single_amount",
            )
        elif _flush_mode == "With feeds (calculated)":
            _n_feeds = sum(
                1 for r in st.session_state.intake_log
                if r["source_type"] in ("blend", "formula")
            )
            _wf1, _wf2 = st.columns(2)
            _per_flush = _wf1.number_input(
                "mL per flush", min_value=0.0, value=60.0, step=10.0,
                key="flush_per",
            )
            _per_feed = _wf2.number_input(
                "Flushes per feed", min_value=1, value=2, step=1,
                key="flush_per_feed",
            )
            _flush_total = _per_flush * _per_feed * _n_feeds
            _flush_label = "Water flushes with feeds"
            st.caption(
                f"{_n_feeds} tube feed(s) in the record × {_per_feed} flush(es) × "
                f"{_per_flush:.0f} mL = **{_flush_total:.0f} mL**"
            )
        else:
            _flush_total = st.number_input(
                "Med flushes (mL/day — a rough figure is fine)",
                min_value=0.0, value=100.0, step=10.0, key="flush_med_amount",
            )
            _flush_label = "Med flushes"
        if st.button("Add flush row", key="flush_add_btn"):
            if _flush_total > 0:
                st.session_state.next_intake_id += 1
                st.session_state.intake_log.append({
                    "id": st.session_state.next_intake_id,
                    "time": _flush_time,
                    "source_type": "flush",
                    "source_id": None,
                    "food_description": _flush_label,
                    "amount": float(_flush_total),
                    "unit": "mL",
                    "counts_as_fluid": True,
                })
                st.rerun()
            else:
                st.warning("The flush total is 0 mL — nothing to add.")

    # --- Add oral intake (inline expander -- see _render_add_oral_ui()'s
    # docstring for why this is an expander rather than st.dialog).
    # Last of the three adders: the oral route, its own category
    # (author feedback 2026-07-20). ---
    with st.expander("➕ 🍌 Add oral intake (food/drink)"):
        _render_add_oral_ui(fn, na, lookup, fg)

    # --- Row list: grouped by section header, one underlying list
    # (section 6.3 — "Tube Feed" and "Food & Drink" are a DISPLAY
    # grouping, not two separately-maintained logs). Chronological, rows
    # with no time sort last (section 6.1); each row removable.
    if not st.session_state.intake_log:
        st.caption("No intake logged yet.")
    else:
        _ordered_rows = sorted_intake_log(st.session_state.intake_log)
        _tube_rows = [r for r in _ordered_rows if r["source_type"] in ("blend", "formula", "flush")]
        _oral_rows = [r for r in _ordered_rows if r["source_type"] == "oral"]

        def _render_intake_row(row: dict) -> None:
            rc1, rc2 = st.columns([6, 1])
            rc1.write(_intake_row_label(row))
            if rc2.button("❌", key=f"del_intake_{row['id']}"):
                st.session_state.intake_log = [
                    r for r in st.session_state.intake_log if r["id"] != row["id"]
                ]
                st.rerun()

        if _tube_rows:
            st.markdown(f"*{TUBE_FEED_LABEL}*")
            for _row in _tube_rows:
                _render_intake_row(_row)
        if _oral_rows:
            st.markdown(f"*{FOOD_DRINK_LABEL}*")
            for _row in _oral_rows:
                _render_intake_row(_row)


with recipes_tab:
    st.divider()

    # --- Per-blend density panel (EVERY blend, not just selected --
    # densities are still the per-blend lens, design doc section 3.5) ---
    st.subheader("Per-blend density panel")
    _density_rows = []
    for _bid, _blend in st.session_state.blends.items():
        if not _blend["ingredients"]:
            _density_rows.append({
                "Blend": _blend["name"], "kcal/mL": "—", "protein g/mL": "—",
                "Free-water fraction": "—", "Measured volume (mL)": _blend["measured_volume_mL"],
                "Coverage": "—", "Note": "No ingredients yet",
            })
            continue
        try:
            _b_profile, _b_fluid_frac = resolve_blend_profile(
                _blend, na, st.session_state.custom_foods
            )
        except InvalidBlendError:
            _density_rows.append({
                "Blend": _blend["name"], "kcal/mL": "—", "protein g/mL": "—",
                "Free-water fraction": "—", "Measured volume (mL)": 0,
                "Coverage": "—", "Note": "Ingredients but no measured volume",
            })
            continue
        _b_ingredients = [
            Ingredient(i["food_code"], i["food_description"], i["grams"])
            for i in _blend["ingredients"]
        ]
        _, _b_coverage = compute_nutrient_totals_and_coverage(
            _b_ingredients, na, st.session_state.custom_foods
        )
        _n_full = sum(1 for n_sup, n_tot in _b_coverage.values() if n_tot == 0 or n_sup == n_tot)
        _density_rows.append({
            "Blend": _blend["name"],
            "kcal/mL": round(_b_profile.kcal_per_mL, 3),
            "protein g/mL": round(_b_profile.protein_per_mL, 3),
            "Free-water fraction": round(_b_profile.free_water_fraction, 3),
            "Measured volume (mL)": _b_profile.measured_final_volume_mL,
            "Coverage": f"{_n_full}/{len(_b_coverage)} nutrients fully covered",
            "Note": "",
        })
    _density_df = pd.DataFrame(_density_rows)
    # kcal/mL, protein g/mL, and Free-water fraction mix floats with the
    # "—" placeholder for a not-yet-buildable blend — cast to str before
    # display, same convention already used for the adequacy table's
    # Target/% Target columns, so Arrow serialization doesn't have to
    # auto-fix a mixed-type numeric column on every render.
    for _col in ("kcal/mL", "protein g/mL", "Free-water fraction"):
        _density_df[_col] = _density_df[_col].astype(str)
    st.dataframe(_density_df, width="stretch", hide_index=True)

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

    with st.expander(f'Full density summary — "{selected_blend["name"]}"'):
        if _selected_invalid:
            st.warning("This blend has ingredients but no measured volume yet.")
        elif selected_profile is None:
            st.caption("Add ingredients and a measured volume to the blend above.")
        else:
            st.dataframe(
                generate_density_summary(selected_profile), width="stretch", hide_index=True
            )

with record_tab:
    st.divider()

    # --- Daily totals, adequacy, micro screen, per-kg, per-source
    # breakdown -- all computed from the Intake Record via
    # src.intake.aggregate_intake() (design doc section 3.5). ---
    intake_totals = aggregate_intake(
        st.session_state.intake_log, st.session_state.blends, na,
        custom_foods=st.session_state.custom_foods,
    )

    if not st.session_state.intake_log:
        _note("Add rows to the Intake Record above to see daily totals.")
    else:
        # --- Per-source subtotal breakdown (design doc section 3.5) ---
        st.subheader("Per-Source Breakdown")
        st.caption(
            f'"{TUBE_FEED_LABEL}" vs "{FOOD_DRINK_LABEL}" vs "{TOTAL_LABEL}" — combined '
            "numbers, with the split still visible."
        )
        st.dataframe(
            generate_source_breakdown(intake_totals), width="stretch", hide_index=True
        )

        st.subheader("Daily Totals & Adequacy")
        st.caption(
            "A direct sum over the Intake Record (above) — never "
            "extrapolated from a batch volume against a schedule."
        )

        adequacy_df, hidden_main_names = generate_adequacy_report(
            intake_totals.nutrient_totals, targets,
            fluid_provided_mL=intake_totals.fluid_provided_mL,
            nutrient_coverage=intake_totals.nutrient_coverage,
        )
        adequacy_display = adequacy_df.copy()
        adequacy_display["Target"] = adequacy_display["Target"].astype(str)
        adequacy_display["% Target"] = adequacy_display["% Target"].astype(str)
        st.dataframe(
            adequacy_display.style
            # The Styler (needed for status colouring) would otherwise
            # render Daily Total at pandas' default 6-decimal precision;
            # %g shows each value at its registry-rounded precision with
            # no trailing zeros (author feedback 2026-07-20).
            .map(color_status, subset=["Status"])
            .format(lambda v: f"{v:g}", subset=["Daily Total"]),
            width="stretch",
            hide_index=True,
        )
        if hidden_main_names:
            st.caption(
                "Not shown — no data from any ingredient: " + ", ".join(hidden_main_names)
            )

        with st.expander("BTF micro screen — vitamins & minerals not on labels"):
            st.caption(
                "A one-time supplementation screen (ASPEN-style: \"does this "
                "day's intake need a multivitamin?\"), not a daily-tracked panel "
                "like the table above."
            )
            clinical_df, hidden_clinical_names = generate_clinical_screen(
                intake_totals.nutrient_totals, targets,
                nutrient_coverage=intake_totals.nutrient_coverage,
            )
            if len(clinical_df) > 0:
                clinical_display = clinical_df.copy()
                clinical_display["Target"] = clinical_display["Target"].astype(str)
                clinical_display["% Target"] = clinical_display["% Target"].astype(str)
                st.dataframe(
                    clinical_display.style
                    .map(color_status, subset=["Status"])
                    .format(lambda v: f"{v:g}", subset=["Daily Total"]),
                    width="stretch",
                    hide_index=True,
                )
            if hidden_clinical_names:
                st.caption(
                    "Not shown — no data from any ingredient: " + ", ".join(hidden_clinical_names)
                )

        if patient_weight_kg > 0:
            st.markdown(f"**Per-kg (at {patient_weight_kg:.1f} kg)**")
            pk1, pk2, pk3 = st.columns(3)
            pk1.metric(
                "Energy",
                f"{intake_totals.nutrient_totals.get('energy_kcal', 0.0) / patient_weight_kg:.1f}",
                "kcal/kg/day",
            )
            pk2.metric(
                "Protein",
                f"{intake_totals.nutrient_totals.get('protein_g', 0.0) / patient_weight_kg:.2f}",
                "g/kg/day",
            )
            pk3.metric(
                "Fluid provided",
                f"{intake_totals.fluid_provided_mL / patient_weight_kg:.1f}",
                "mL/kg/day",
            )
            st.caption("Display only — no target, equation, or IBW is computed from weight.")

with recipes_tab:
    st.divider()

    # --- Dilution what-if (operates on the selected blend) ---
    st.subheader("Dilution What-If")
    st.caption("If the blend needs thinning, see the density impact before you commit.")

    if selected_profile is None:
        _note(
            "Add ingredients and a measured volume to the blend above "
            "to use the dilution what-if."
        )
    else:
        w1, w2 = st.columns([1, 2])

        with w1:
            liquid_type = st.selectbox("Thinning liquid", list(THINNING_LIQUIDS.keys()))
            added_mL = st.slider("Add liquid (mL)", 0, 500, 0, step=10)

            preset = THINNING_LIQUIDS[liquid_type]
            if liquid_type == "Custom" and added_mL > 0:
                cc1, cc2, cc3 = st.columns(3)
                liq_kcal = cc1.number_input("kcal", min_value=0.0, value=0.0, step=1.0)
                liq_protein = cc2.number_input(
                    "Protein (g)", min_value=0.0, value=0.0, step=0.1
                )
                liq_water = cc3.number_input(
                    "Water (g)", min_value=0.0, value=float(added_mL), step=1.0
                )
            else:
                scale = added_mL / 100.0
                liq_kcal = preset["kcal"] * scale
                liq_protein = preset["protein_g"] * scale
                liq_water = preset["water_g"] * scale
                if added_mL > 0:
                    st.caption(
                        f"Adding {liq_kcal:.0f} kcal, "
                        f"{liq_protein:.1f} g protein, "
                        f"{liq_water:.0f} g water"
                    )

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
                st.dataframe(dil_df, width="stretch", hide_index=True)

                tk = targets.get("energy_kcal", 0.0)
                tp = targets.get("protein_g", 0.0)
                if tk > 0 and tp > 0:
                    ro = required_daily_volume(selected_profile, tk, tp)
                    rd = required_daily_volume(diluted, tk, tp)
                    _note(
                        f"Required daily volume of just this blend to meet "
                        f"{tk:.0f} kcal + {tp:.0f} g protein:<br>"
                        f"<strong>{ro:.0f} mL</strong> → "
                        f"<strong>{rd:.0f} mL</strong> after dilution "
                        f"(+{rd - ro:.0f} mL)"
                    )
            else:
                st.caption("Slide the slider to see the effect of adding thinning liquid.")

    # --- Flow test documentation (pairs with the dilution what-if above:
    # thin the blend, then record whether it flows. Optional for
    # established recipes; handy in one place during recipe development --
    # author feedback 2026-07-20.) ---
    st.subheader("Flow Test")
    st.caption(
        "Documentation only — the tool can't measure viscosity or tube "
        "flow. Optional for established recipes; during recipe development "
        "it pairs with the dilution what-if above."
    )
    ft1, ft2 = st.columns(2)
    flow_test_date = ft1.date_input("Date", value=None)
    flow_test_result = ft2.selectbox("Result", ["Not done", "Passed", "Needs thinning"])
    flow_test_notes = st.text_area(
        "Notes", "", placeholder="e.g., flowed through a 60 mL syringe without resistance"
    )

    # --- Commercial formula comparator (operates on the selected blend,
    # at a manually-chosen comparison volume -- independent of the actual
    # Intake Record, an explicit what-if: "if I gave X mL/day of just this
    # blend, how does it compare to formula Y") ---
    st.subheader("Commercial Formula Comparator")
    if selected_profile is None:
        _note(
            "Add ingredients and a measured volume to the blend above "
            "to use the comparator."
        )
    else:
        compare_volume_mL = st.number_input(
            "Compare at daily volume (mL)",
            min_value=0.0,
            value=max(selected_profile.measured_final_volume_mL, 1200.0),
            step=50.0,
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
                name for name, f in COMMERCIAL_FORMULAS.items()
                if brand_filter == "All" or (f.get("brand") or "Other") == brand_filter
            ),
            key=lambda n: (COMMERCIAL_FORMULAS[n].get("brand") or "Other", n),
        )
        _already_picked = st.session_state.get("comparator_formula_select", [])
        _multiselect_options = formula_pool + [
            n for n in _already_picked if n not in formula_pool
        ]
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
        st.caption(
            "Company narrows the list for scrolling — feeds you already "
            "picked stay selected when you switch companies."
        )
        comparator_df = generate_comparator_table(
            selected_profile, compare_volume_mL, selected_formulas
        )
        st.dataframe(comparator_df, width="stretch", hide_index=True)

with record_tab:
    st.divider()

    # --- Chart note: the Intake Record read aloud chronologically (tube
    # and oral interleaved by time) + totals (design doc section 3.5). ---
    st.subheader("Chart Note")
    st.caption("Copy-paste into your own chart. No patient-identifying fields.")

    if not st.session_state.intake_log:
        st.caption("Add Intake Record rows above to generate a chart note.")
    else:
        _ordered_note_rows = sorted_intake_log(st.session_state.intake_log)
        _tube_note_rows = [r for r in _ordered_note_rows if r["source_type"] in ("blend", "formula", "flush")]
        _oral_note_rows = [r for r in _ordered_note_rows if r["source_type"] == "oral"]

        _note_lines = []
        if _tube_note_rows:
            _note_lines.append(
                f"BTF via {delivery_method}: " + "; ".join(_format_tube_feed_bits(_tube_note_rows)) + "."
            )
        if _oral_note_rows:
            _note_lines.append("Oral: " + "; ".join(_format_oral_bits(_oral_note_rows)) + ".")

        _daily_kcal = intake_totals.nutrient_totals.get("energy_kcal", 0.0)
        _daily_cho = intake_totals.nutrient_totals.get("carbohydrate_g", 0.0)
        _daily_protein = intake_totals.nutrient_totals.get("protein_g", 0.0)
        _daily_fat = intake_totals.nutrient_totals.get("fat_g", 0.0)
        _weight_bit = f" ({_daily_protein / patient_weight_kg:.1f} g/kg)" if patient_weight_kg > 0 else ""
        _note_lines.append(
            f"Provides ~{_daily_kcal:.0f} kcal, {_daily_cho:.0f} g CHO, "
            f"{_daily_protein:.0f} g protein{_weight_bit}, {_daily_fat:.0f} g fat."
        )
        _note_lines.append(f"Fluid provided: {intake_totals.fluid_provided_mL:.0f} mL/day.")
        _note_lines.append(f"Free water (estimated): ~{intake_totals.free_water_mL:.0f} mL/day.")

        if flow_test_result in ("Passed", "Needs thinning"):
            _result_word = "passed" if flow_test_result == "Passed" else "needs thinning"
            _date_bit = f" {flow_test_date.isoformat()}" if flow_test_date else ""
            _notes_bit = f" — {flow_test_notes}" if flow_test_notes else ""
            _note_lines.append(f"Flow test:{_date_bit} {_result_word}{_notes_bit}.")

        _note_text = " ".join(_note_lines)
        st.code(_note_text, language=None)

    # --- Export to Excel ---
    st.subheader("Export")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Field": ["Patient / day label", "Delivery method", "Patient weight (kg)"],
                "Value": [recipe_name, delivery_method, patient_weight_kg],
            }
        ).to_excel(writer, sheet_name="Day", index=False)

        # Intake Record sheet: every row, chronological (design doc
        # section 3.5's export requirement).
        if st.session_state.intake_log:
            _export_rows = []
            for row in sorted_intake_log(st.session_state.intake_log):
                _export_rows.append({
                    "Time": row["time"].strftime("%H:%M") if row["time"] else "",
                    "Section": TUBE_FEED_LABEL if row["source_type"] in ("blend", "formula", "flush") else FOOD_DRINK_LABEL,
                    "Source type": row["source_type"],
                    "Source": _intake_row_label(row).split(" — ")[1],
                    "Amount": row["amount"],
                    "Unit": row["unit"],
                    "Counts as fluid": row["counts_as_fluid"],
                })
            pd.DataFrame(_export_rows).to_excel(writer, sheet_name="Intake Record", index=False)
        else:
            pd.DataFrame(
                {"Time": [], "Section": [], "Source type": [], "Source": [], "Amount": [], "Unit": [], "Counts as fluid": []}
            ).to_excel(writer, sheet_name="Intake Record", index=False)

        # One sheet per blend: ingredient list + measured volume.
        for _bid, _blend in st.session_state.blends.items():
            _sheet_name = sanitize_filename(_blend["name"], fallback=f"Blend {_bid}")[:31]
            if _blend["ingredients"]:
                _ing_df = pd.DataFrame(_blend["ingredients"])[
                    ["food_description", "grams", "unit", "counts_as_fluid"]
                ]
            else:
                _ing_df = pd.DataFrame(
                    {"food_description": [], "grams": [], "unit": [], "counts_as_fluid": []}
                )
            _ing_df.to_excel(writer, sheet_name=_sheet_name, index=False, startrow=1)
            _sheet = writer.sheets[_sheet_name]
            _sheet["A1"] = f"Measured final volume (mL): {_blend['measured_volume_mL']:.0f}"

        # Daily totals sheets, if the Intake Record has anything logged.
        if st.session_state.intake_log:
            generate_adequacy_report(
                intake_totals.nutrient_totals, targets,
                fluid_provided_mL=intake_totals.fluid_provided_mL,
                nutrient_coverage=intake_totals.nutrient_coverage,
            )[0].to_excel(writer, sheet_name="Adequacy", index=False)
            generate_clinical_screen(
                intake_totals.nutrient_totals, targets,
                nutrient_coverage=intake_totals.nutrient_coverage,
            )[0].to_excel(writer, sheet_name="Micro Screen", index=False)
            generate_source_breakdown(intake_totals).to_excel(
                writer, sheet_name="Per-Source Breakdown", index=False
            )

        # Flow test documentation
        pd.DataFrame(
            {
                "Date": [flow_test_date.isoformat() if flow_test_date else ""],
                "Result": [flow_test_result],
                "Notes": [flow_test_notes],
            }
        ).to_excel(writer, sheet_name="Flow Test", index=False)

        # Chart note text
        if st.session_state.intake_log:
            pd.DataFrame({"Chart note": [_note_text]}).to_excel(
                writer, sheet_name="Chart Note", index=False
            )

    st.download_button(
        label="📥 Export to Excel",
        data=output.getvalue(),
        file_name=f"{sanitize_filename(recipe_name)}_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# --- Footer ---
st.divider()
st.caption(
    "⚠️ Under development — for RD use, estimates only. Double-check all numbers before clinical use.  \n"
    "RD clinical judgment is the final authority. Built on the Canadian Nutrient File (CNF) 2026."
)
