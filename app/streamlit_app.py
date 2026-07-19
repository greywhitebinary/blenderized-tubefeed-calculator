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

App flow ("start with the blender"):
  1. Build tab -- create/select a blend, search CNF or add a custom food
     from a label, enter grams and measured final volume.
  2. Banner -- patient weight, targets, and the Intake Record (what was
     actually given, tube feed and oral food/drink together).
  3. Results tab (live) -- per-blend densities, daily totals from the
     Intake Record, adequacy, per-source (Tube Feed vs Food & Drink)
     breakdown, formula comparator, dilution what-if, chart note.

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
from src.calculator import label_to_per_100g, COMMERCIAL_FORMULAS
from src.measures import load_measure_lookup, get_measures_for_food
from src.targets import empty_targets
from src.report import (
    generate_adequacy_report,
    generate_clinical_screen,
    generate_comparator_table,
    generate_density_summary,
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
# Session state — Blends (Build tab) + Intake Record (banner), per
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
# banner below — a UX nicety only (e.g. kcal steps by 50, not 1).
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


def render_add_food_ui(
    fn_df: pd.DataFrame,
    na_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    fg_df: pd.DataFrame,
    key_prefix: str,
    add_button_label: str = "Add",
) -> dict | None:
    """Render the CNF-search / custom-food-from-label add-a-food UI.

    Returns a dict {food_code, food_description, grams, unit,
    counts_as_fluid} on the render where the Add button is clicked and the
    entry is valid, else None. `key_prefix` must be unique per call site
    (e.g. "blend_3" vs "oral_dialog") so two simultaneous instances of this
    component never collide on widget keys.
    """
    add_mode = st.radio(
        "Source",
        [
            "Search foods from the Canadian Nutrient File",
            "Enter information on the food label",
        ],
        horizontal=True,
        key=f"{key_prefix}_add_mode",
    )

    result: dict | None = None

    if add_mode == "Search foods from the Canadian Nutrient File":
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
                    st.info("No household measures for this food.")
                    calculated_grams = st.number_input(
                        "Grams", min_value=0.0, value=100.0, step=1.0,
                        key=f"{key_prefix}_grams_nomeasure",
                    )
            else:
                st.info("No foods found. Try another search.")
        else:
            st.caption("Type at least 2 characters to search.")

        if food_code is not None and calculated_grams > 0:
            default_fluid = default_counts_as_fluid(food_desc, sel_group_code)
            if st.button(f"➕ {add_button_label}", key=f"{key_prefix}_add_cnf_btn"):
                result = {
                    "food_code": food_code,
                    "food_description": food_desc,
                    "grams": float(calculated_grams),
                    "unit": "g",
                    "counts_as_fluid": default_fluid,
                }

    else:  # Custom food from label — a Canadian Nutrition Facts lookalike
        st.caption("Enter values exactly as printed on the nutrition facts label.")
        basis_choice = st.radio(
            "Label basis",
            ["per ___ g", "per ___ mL"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"{key_prefix}_basis",
        )
        basis = "g" if basis_choice == "per ___ g" else "mL"

        _registry_map = registry_by_name(DEFAULT_PACK)
        cv: dict[str, float] = {}

        # NFt lookalike styling (visual only). Scoped via a per-key-prefix
        # container key so the two simultaneous instances (blend add form +
        # oral dialog form) don't fight over the same CSS hook.
        box_key = f"{key_prefix}_nft_box"
        st.markdown(
            f"""
            <style>
            .nft-title {{ font-size: 1.9rem; font-weight: 800;
                         letter-spacing: -0.02em; margin-bottom: 0.1rem; }}
            .nft-main {{ font-weight: 700; padding-top: 0.5rem; }}
            .nft-sub {{ font-weight: 400; padding-top: 0.5rem;
                       padding-left: 1.4em; }}
            .nft-cal {{ font-weight: 800; font-size: 1.3rem;
                       padding-top: 0.4rem; }}
            hr.nft-thick {{ border: none; border-top: 6px solid #000;
                            margin: 0.4rem 0; }}
            hr.nft-thin {{ border: none; border-top: 1px solid #000;
                           margin: 0.3rem 0; }}
            .st-key-{box_key} input[type="number"] {{ text-align: right; }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        def _nft_step(d) -> float:
            return 1.0 if d.decimals == 0 else round(10 ** (-d.decimals), d.decimals)

        def _nft_field(text: str, css_class: str, key: str, **kwargs) -> float:
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
                key=f"{key_prefix}_cgrams",
                help=f"Same unit as the label basis above ({basis}) — an "
                     f"mL-basis food's usage can only be entered in mL, by "
                     f"design (no cross-conversion between g and mL).",
            )

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
                        # mL-basis custom foods default to counts-as-fluid=True
                        # — a liquid entered from a label has no CNF moisture
                        # data, so the I&O full-volume convention is the only
                        # fluid signal available for it. Still overridable.
                        "counts_as_fluid": basis == "mL",
                    }

    return result


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="BTF Calculator",
    page_icon="🥣",
    layout="wide",
)

# Tab labels as big as a subheading — Streamlit doesn't expose this as a
# parameter, so it's injected CSS. Verified against Streamlit 1.58's actual
# compiled frontend bundle: each tab button renders as
# `<button data-testid="stTab">` wrapping a
# `[data-testid="stMarkdownContainer"]` div whose `<p>` carries the label.
st.markdown(
    """
    <style>
    button[data-testid="stTab"] [data-testid="stMarkdownContainer"] p,
    button[data-testid="stTab"] p {
        font-size: 1.4rem;
        font-weight: 600;
    }
    button[data-testid="stTab"] {
        padding-top: 0.4rem;
        padding-bottom: 0.4rem;
    }
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

st.title(f"🥣 {recipe_name or 'BTF day'}")
st.caption("For RD use — estimates only")


# ===========================================================================
# Persistent banner — patient weight, targets, and the Intake Record
# summary. Sits above the tabs so it's visible regardless of which tab is
# active. The full Intake Record editor (add tube feed / add food & drink)
# lives here too — see the next commit for the row editor; this commit
# lands the state model and Build tab it depends on.
# ===========================================================================

with st.container(border=True):
    st.subheader("Patient, Targets & Intake Record")

    with st.expander("Targets — set once, referenced throughout", expanded=False):
        st.markdown("**Patient weight (optional)**")
        patient_weight_kg = st.number_input(
            "Weight (kg)",
            min_value=0.0,
            value=0.0,
            step=0.5,
            help="Optional — used only to show kcal/kg, protein g/kg, and "
                 "fluid mL/kg in the Results tab. No target, equation, or "
                 "IBW is computed from it; assessment stays outside this app.",
        )
        st.caption("Blank/0 = not provided. Display only — not a target.")

        st.markdown("**Targets (optional)**")
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
                f"{disp_label} {unit}/day", min_value=0.0, value=0.0, step=step
            )

    st.markdown("**Intake Record**")
    st.caption(
        f"{len(st.session_state.intake_log)} row(s) logged. The row editor "
        "(add tube feed / add food & drink) is being wired up in the next "
        "phase of this rework."
    )


# ===========================================================================
# Build / Results tabs
# ===========================================================================

build_tab, results_tab = st.tabs(["🔨 Build", "📊 Results"])

with build_tab:
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
        help="Read it off the side of the blender jug, or pour into a "
             "measuring cup after blending. Ingredient weights feed the "
             "nutrient math; volume is always this measured number.",
        key=f"vol_{selected_blend_id}",
    )
    selected_blend["measured_volume_mL"] = measured_volume

    # --- Ingredient table ---
    st.subheader("Ingredients")

    if not selected_blend["ingredients"]:
        st.info("Add ingredients above to get started.")
    else:
        st.caption(
            "\"Counts as fluid\" drives the Results tab's Fluid provided "
            "row (full-volume I&O convention) — auto-checked for CNF "
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


with results_tab:
    st.subheader("Per-blend density panel")
    if not selected_blend["ingredients"]:
        st.info("Add ingredients in the Build tab to see this blend's densities.")
    else:
        try:
            profile, fluid_frac = resolve_blend_profile(
                selected_blend, na, st.session_state.custom_foods
            )
        except InvalidBlendError:
            st.warning(
                "This blend has ingredients but no measured volume yet — "
                "enter one in the Build tab to see densities."
            )
        else:
            if selected_blend["measured_volume_mL"] <= 0:
                st.info("Enter a measured final volume in the Build tab to see densities.")
            else:
                d1, d2, d3 = st.columns(3)
                d1.metric("Energy density", f"{profile.kcal_per_mL:.3f}", "kcal/mL")
                d2.metric("Protein density", f"{profile.protein_per_mL:.3f}", "g/mL")
                d3.metric("Measured volume", f"{profile.measured_final_volume_mL:.0f} mL")
                st.caption(
                    f"Free-water fraction: {profile.free_water_fraction:.3f} "
                    "(food moisture / volume)"
                )
                with st.expander("Full density summary"):
                    st.dataframe(
                        generate_density_summary(profile),
                        width="stretch",
                        hide_index=True,
                    )

    st.divider()
    st.info(
        "Daily totals, adequacy, the per-source (Tube Feed vs Food & Drink) "
        "breakdown, and the chart note are computed from the Intake Record "
        "above — full wiring lands in the next phase of this rework, once "
        "the Intake Record row editor is built."
    )


# --- Footer ---
st.divider()
st.caption(
    "For RD use — estimates only. RD clinical judgment is the final authority.  \n"
    "Built on the Canadian Nutrient File (CNF) 2026."
)
