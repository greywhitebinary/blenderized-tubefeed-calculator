"""
streamlit_app.py — Streamlit UI for the Blenderized Tube Feed Calculator.

Phase 6.

App flow ("start with the blender"):
  1. Recipe builder — search CNF or add custom food from label; enter grams,
     added water, measured final volume.
  2. Delivery input — syringe bolus, pump, or direct mL/day.
  3. Targets (optional) — RD enters known kcal/day, protein g/day, etc.
  4. Results (live) — densities, daily totals, adequacy, formula comparator,
     dilution what-if.

Design commitments (from CONTEXT.md §1):
  - Per-mL is the primary lens, not per-recipe.
  - Final blend volume is a measured input, not computed.
  - The core feature is the water trade-off what-if.
  - "For RD use, estimates only" — not a family-facing tool.
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
from src.models import Ingredient, Recipe, Delivery, DeliveryMethod
from src.calculator import (
    calculate_profile,
    daily_volume_from_delivery,
    dilute,
    required_daily_volume,
    label_to_per_100g,
    COMMERCIAL_FORMULAS,
)
from src.measures import load_measure_lookup, get_measures_for_food
from src.targets import empty_targets
from src.report import (
    generate_adequacy_report,
    generate_clinical_screen,
    generate_formula_comparison,
    generate_density_summary,
)
from src.nutrients import defs_for_tier, registry_by_name, DEFAULT_PACK

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
# always override per ingredient (Part 0 #8 of the round-2 clinical
# feedback plan — the toggle IS the policy, this default is a starting
# point, not a rule).
_BEVERAGES_GROUP_CODE = 14


def default_counts_as_fluid(food_desc: str, group_code) -> bool:
    """Starting value for a CNF ingredient's counts-as-fluid checkbox.

    True when the food is in CNF's own Beverages group (14), or its
    description starts with the word "Water" (CNF's four standalone
    water entries: "Water, municipal", "Water, mineral, ...", etc. — a
    plain substring match would also catch "Watermelon" or any of the
    176 CNF foods with "water added" in a soup description, which is why
    this checks for the word at the START of the description, not
    anywhere in it). Always user-toggleable afterward — see the
    ingredient table's checkbox.
    """
    if group_code == _BEVERAGES_GROUP_CODE:
        return True
    if re.match(r"^water\b", (food_desc or "").strip(), re.IGNORECASE):
        return True
    return False


def init_state():
    """Initialize session_state keys for ingredient list and custom foods."""
    if "ingredients" not in st.session_state:
        st.session_state.ingredients = []
    if "custom_foods" not in st.session_state:
        st.session_state.custom_foods = {}
    if "next_custom_code" not in st.session_state:
        st.session_state.next_custom_code = -1
    if "next_ingr_id" not in st.session_state:
        st.session_state.next_ingr_id = 0


def color_status(val: str) -> str:
    """Color-code adequacy status cells.

    "Above UL" and "Below target" are both concerning (red); "Below UL"
    and "Meeting target" are both fine (green) — a UL is a ceiling, not
    an aim, so "Below UL" reads as "fine" the same way "Meeting target"
    does for an RDA/AI nutrient. See src/report.py::_adequacy_status.

    Text colour is set explicitly alongside each pale background: without
    it, a dark theme renders near-white text on pale pink and the status
    becomes unreadable. This keeps the table legible whether the viewer
    has the native Streamlit theme set to light or dark.
    """
    if val in ("Below target", "Above UL"):
        return "background-color: #ffcccc; color: #1a1a1a"
    elif val == "Above target":
        return "background-color: #ffe0b2; color: #1a1a1a"
    elif val in ("Meeting target", "Below UL"):
        return "background-color: #c8e6c9; color: #1a1a1a"
    return ""


# Per-nutrient step sizes for the custom-target number_inputs in the
# Patient, Delivery & Targets banner below — a UX nicety only (e.g. kcal
# steps by 50, not 1). Nutrients not listed fall back to a step derived
# from their registry `decimals`.
_TARGET_STEP_OVERRIDES: dict[str, float] = {
    "energy_kcal": 50.0,
    "fluid_mL": 100.0,
    "sodium_mg": 100.0,
    "potassium_mg": 100.0,
    "calcium_mg": 50.0,
    "protein_g": 5.0,
    "vitamin_b12_ug": 0.5,
}


def render_schedule_editor(
    state_key: str,
    default_rows: list[dict],
    volume_label: str = "Volume (mL)",
) -> tuple[pd.DataFrame, float]:
    """Render an editable (time, volume) schedule table — used for both the
    syringe bolus schedule and the water-flush schedule (Part 2.5 of the
    round-2 clinical feedback plan: "same schedule-row pattern").

    Uses st.data_editor with num_rows="dynamic" so the RD can add/remove
    rows inline (no manual add/remove-button plumbing needed). The
    DataFrame is persisted in st.session_state[state_key] (a KEY DIFFERENT
    from the widget's own `key=` — never let a widget's key collide with
    the session_state key you also assign into, or Streamlit raises a
    "cannot be modified" warning) so the schedule survives reruns.

    Args:
        state_key:     session_state key to persist the schedule under.
        default_rows:  seed rows, e.g. [{"time": dtime(8, 0), "volume_mL": 300.0}, ...],
                        used only the first time this key is seen.
        volume_label:  column header for the volume column (schedules used
                        for different things — bolus feeds vs. flushes —
                        read better with different labels).

    Returns:
        (edited DataFrame, total of the volume_mL column).
    """
    if state_key not in st.session_state:
        st.session_state[state_key] = pd.DataFrame(default_rows)

    edited = st.data_editor(
        st.session_state[state_key],
        num_rows="dynamic",
        key=f"{state_key}_editor",
        hide_index=True,
        width="stretch",
        column_config={
            "time": st.column_config.TimeColumn("Time", format="HH:mm", required=True),
            "volume_mL": st.column_config.NumberColumn(
                volume_label, min_value=0.0, step=10.0, required=True
            ),
        },
    )
    st.session_state[state_key] = edited
    total = float(edited["volume_mL"].fillna(0.0).sum()) if len(edited) else 0.0
    return edited, total


def format_schedule_for_note(schedule_df: pd.DataFrame) -> str:
    """Render a schedule DataFrame as 'HHMM vol mL, HHMM vol mL, ...' — the
    chart-note format from the round-2 plan's example (Part 3): "0800 300
    mL, 1200 400 mL, ...". Rows with a missing time or volume are skipped
    (a mid-edit blank row from num_rows="dynamic" shouldn't crash the note).
    """
    bits = []
    for _, row in schedule_df.iterrows():
        t, v = row.get("time"), row.get("volume_mL")
        if pd.isna(t) or pd.isna(v):
            continue
        t_str = t.strftime("%H%M") if hasattr(t, "strftime") else str(t)
        bits.append(f"{t_str} {v:.0f} mL")
    return ", ".join(bits)


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="BTF Calculator",
    page_icon="🥣",
    layout="wide",
)

# Tab labels as big as a subheading (Part 0 #10 — Streamlit doesn't expose
# this as a parameter, so it's injected CSS). Verified against Streamlit
# 1.58's actual compiled frontend bundle (grepped the installed
# streamlit/static/static/js/*.js), not the plan's guessed selector: each
# tab button renders as `<button data-testid="stTab">` (a stable,
# Streamlit-owned test id — NOT `data-baseweb="tab"`, which doesn't appear
# as a literal attribute anywhere in the bundle) wrapping a
# `[data-testid="stMarkdownContainer"]` div whose `<p>` carries the label
# text at the framework's small font size (isLabel -> fontSizes.sm). Both
# levels are targeted below so the rule holds even if a future Streamlit
# version drops one wrapper.
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
# TOP BAR — chrome only: recipe name, load example. No sidebar.
#
# There used to be one here. Across two restructuring sessions,
# ingredient search, blend details, delivery, and targets all moved out
# of it (see CONTEXT.md §9) — leaving three sparse fields that didn't
# earn a persistent side rail. Streamlit's sidebar takes a fixed slice of
# horizontal width on every load; keeping it around empty would have
# quietly taken back the width that moving CNF search out of it was
# trying to win in the first place. So it's gone, and everything it held
# lives in this top row instead.
# ===========================================================================

top_l, top_r = st.columns([4, 1])
with top_l:
    recipe_name = st.text_input("Recipe name", "My BTF recipe")
with top_r:
    st.write("")  # vertical spacer so the button aligns with the text input
    load_example_clicked = st.button("📋 Load example recipe", width="stretch")

if load_example_clicked:
    chicken = find_food(fn, "Chicken, broiler, breast, skinless, boneless, meat, raw")
    rice = find_food(fn, "Grains, rice, white, long-grain, parboiled, cooked")
    oil = find_food(fn, "Vegetable oil, canola")
    water = find_food(fn, "Water, municipal")
    if chicken and rice and oil and water:
        st.session_state.next_ingr_id = 4
        st.session_state.ingredients = [
            {"id": 1, "food_code": chicken, "food_description": "Chicken breast", "grams": 200.0, "unit": "g", "counts_as_fluid": False},
            {"id": 2, "food_code": rice, "food_description": "Rice, cooked", "grams": 150.0, "unit": "g", "counts_as_fluid": False},
            {"id": 3, "food_code": oil, "food_description": "Canola oil", "grams": 15.0, "unit": "g", "counts_as_fluid": False},
            # Round-2 clinical feedback (Part 0 #8): the Added-water field
            # is deleted; water is an ordinary CNF ingredient like anything
            # else (CNF has it at 99.9% moisture — nothing is lost), and
            # this is the ingredient that demonstrates the fluids ledger's
            # counts-as-fluid toggle in the example recipe.
            {"id": 4, "food_code": water, "food_description": "Water, municipal", "grams": 200.0, "unit": "g", "counts_as_fluid": True},
        ]
        st.session_state.custom_foods = {}
        st.session_state.next_custom_code = -1
        st.session_state["load_example"] = True
        st.rerun()
    else:
        st.error("Could not find example foods in CNF.")

st.title(f"🥣 {recipe_name or 'BTF Recipe'}")
st.caption("For RD use — estimates only")


# ===========================================================================
# Persistent "Patient, Delivery & Targets" banner — sits above the tabs, so
# it's visible regardless of which tab is active (matches Compleat's
# persistent "1800 Calories" strip). Bundles Delivery together with
# Targets: both are patient-side, set-once, referenced-everywhere inputs,
# and the daily volume the banner's one-line summary always shows comes
# directly from Delivery. See the handoff plan Part 1 for the full
# reasoning behind this placement call.
# ===========================================================================

with st.container(border=True):
    st.subheader("Patient, Delivery & Targets")

    with st.expander("Delivery & targets — set once, referenced throughout", expanded=False):
        # --- Patient weight (optional, DISPLAY ONLY) ---
        # Round-2 clinical feedback, Part 0 #3: no assessment features here
        # beyond this one field. Weight drives per-kg DISPLAY rows in the
        # Results tab (kcal/kg, protein g/kg, fluid mL/kg) — never a
        # target, never an equation, never IBW. Assessment stays out of
        # this app; the RD brings targets, this just divides by a number.
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

        # --- Delivery ---
        # Round-2 clinical feedback, Part 0 #4 / Part 2.5: pump delivery is
        # removed from the UI (AHS: almost never used for BTF) — the PUMP
        # enum stays in src/models.py unused, per Part 4's "don't touch
        # models.py". Syringe bolus becomes an editable schedule (time +
        # volume rows) instead of a single bolus-volume x times/day pair,
        # so the schedule itself can drive the chart note and Excel export.
        # "Direct mL/day" is renamed "Total feed volume per day". Both
        # paths construct Delivery(method=DIRECT, daily_volume_mL=...)
        # under the hood — the schedule is UI/documentation data on top,
        # not a different calculation path (Part 2.5).
        st.markdown("**Delivery**")
        method_label = st.radio(
            "Method",
            ["Syringe bolus (schedule)", "Total feed volume per day"],
            label_visibility="collapsed",
        )

        if method_label == "Syringe bolus (schedule)":
            st.caption(
                "Enter each bolus as a time + volume row. Add/remove rows "
                "with the table's own controls."
            )
            bolus_schedule, daily_vol = render_schedule_editor(
                "bolus_schedule",
                default_rows=[
                    {"time": dtime(8, 0), "volume_mL": 300.0},
                    {"time": dtime(12, 0), "volume_mL": 400.0},
                    {"time": dtime(16, 0), "volume_mL": 400.0},
                    {"time": dtime(20, 0), "volume_mL": 300.0},
                ],
                volume_label="Bolus volume (mL)",
            )
            st.caption(f"Total feed volume: **{daily_vol:.0f} mL/day**")
        else:
            bolus_schedule = pd.DataFrame(columns=["time", "volume_mL"])
            daily_vol = st.number_input(
                "Total feed volume per day (mL)", min_value=0.0, value=1200.0, step=50.0
            )

        delivery = Delivery(method=DeliveryMethod.DIRECT, daily_volume_mL=daily_vol)
        # daily_volume_from_delivery() is a passthrough for DIRECT (kept so
        # the calculator's public entry point is still exercised here,
        # rather than reading delivery.daily_volume_mL directly).
        daily_vol = daily_volume_from_delivery(delivery)

        # --- Water flushes (new — Part 2.5) ---
        # Same schedule-row pattern as the bolus schedule. Total flush
        # volume feeds the fluids ledger (Fluid provided = fluid-from-
        # ingredients + flushes, see the Build tab) and the chart note.
        # No default rows are seeded — flush volume/frequency is a
        # clinical judgment call the RD makes, not a number this app
        # should guess at.
        st.markdown("**Water flushes**")
        st.caption(
            "Optional — syringe water flushes given with the feed. Counted "
            "toward daily fluid provided, separately from the recipe itself."
        )
        flush_schedule, flush_total_mL = render_schedule_editor(
            "flush_schedule", default_rows=[], volume_label="Flush volume (mL)"
        )
        if flush_total_mL > 0:
            st.caption(f"Total flush volume: **{flush_total_mL:.0f} mL/day**")

        # --- Targets (optional) ---
        # Round-2 clinical feedback (Part 0 #2): there is no default-DRI
        # option anymore. "2000 kcal / 75 g protein" as a population
        # default is not defensible for tube-fed patients (protein
        # practice runs 1.0-1.5 g/kg, not the 0.8 g/kg population RDA).
        # Targets always start blank; blank = no adequacy %, daily totals
        # are still shown regardless.
        st.markdown("**Targets (optional)**")
        st.caption("Blank = no target; enter patient-specific values.")
        targets = empty_targets()
        tc1, tc2 = st.columns(2)
        cols = (tc1, tc2)
        # Generated from the registry: iterate every nutrient with
        # offer_target="yes" (data/packs/canada/nutrients.csv — the nine
        # displayed label-tier nutrients, in registry row order), not a
        # hardcoded field list. "fluid_mL" isn't a CNF nutrient (it's the
        # target for the fluids-ledger adequacy row), so it gets a
        # hand-written label/unit; everything else reads its label/unit
        # straight off the registry.
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

    # Always-visible one-line summary, rendered OUTSIDE the expander above so
    # it's visible whether that detail is expanded or collapsed — the "1800
    # Calories" strip is set once, glanced at constantly, rarely touched.
    _summary_bits = [f"Daily volume: {daily_vol:.0f} mL/day"]
    if flush_total_mL > 0:
        _summary_bits.append(f"{flush_total_mL:.0f} mL flushes")
    if patient_weight_kg > 0:
        _summary_bits.append(f"{patient_weight_kg:.1f} kg")
    if targets.get("energy_kcal", 0.0) > 0:
        _summary_bits.append(f"{targets['energy_kcal']:.0f} kcal")
    if targets.get("protein_g", 0.0) > 0:
        _summary_bits.append(f"{targets['protein_g']:.0f} g protein")
    if targets.get("fluid_mL", 0.0) > 0:
        _summary_bits.append(f"{targets['fluid_mL']:.0f} mL fluid")
    st.caption("**" + "  |  ".join(_summary_bits) + "**")


# ===========================================================================
# Build / Results tabs
# ===========================================================================
# Both tabs must always render their shell correctly, even on a fresh/empty
# recipe — that's why the old global `st.stop()` calls (empty ingredients /
# measured_volume <= 0) are gone. `st.stop()` halts the ENTIRE script run,
# which would have broken tab rendering (tabs are still linear script
# execution under the hood): once inside the Build tab, `st.stop()` would
# have prevented the Results tab from ever rendering its own shell. Each
# guard below is now tab-local — it only skips content inside that tab.

build_tab, results_tab = st.tabs(["🔨 Build", "📊 Results"])

with build_tab:
    # --- Add ingredient ---
    st.subheader("Add ingredient")
    add_mode = st.radio(
        "Source",
        [
            "Search foods from the Canadian Nutrient File",
            "Enter information on the food label",
        ],
        horizontal=True,
    )

    if add_mode == "Search foods from the Canadian Nutrient File":
        # Food-group filter: CNF's own 23 native CNF_Food_Group categories
        # (already in Food_Name.csv as CNF_Food_Group_Code) — narrows the
        # search pool *before* the existing substring search below, same
        # regex=False behavior as before, just pre-narrowed by group.
        group_options = ["All"] + sorted(
            fg["CNF_Food_Group_Description_EN"].tolist()
        )
        group_code_by_desc = dict(
            zip(fg["CNF_Food_Group_Description_EN"], fg["CNF_Food_Group_Code"])
        )
        group_desc_by_code = dict(
            zip(fg["CNF_Food_Group_Code"], fg["CNF_Food_Group_Description_EN"])
        )

        gc1, gc2 = st.columns([1, 2])
        selected_group = gc1.selectbox("Food group", group_options)
        search_term = gc2.text_input(
            "Search foods",
            "",
            placeholder="e.g., chicken, rice, oil",
        )

        food_code: int | None = None
        food_desc: str | None = None
        calculated_grams = 0.0

        search_pool = fn
        if selected_group != "All":
            search_pool = fn[
                fn["CNF_Food_Group_Code"] == group_code_by_desc[selected_group]
            ]

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
                    f"Found {len(matches)} foods", food_options
                )
                idx = food_options.index(selected)
                food_code = int(matches.iloc[idx]["Food_Code"])
                food_desc = str(matches.iloc[idx]["Food_Description_EN"])
                # Orientation caption — which CNF group this result belongs
                # to, useful even when "All" is selected.
                _sel_group_code = matches.iloc[idx].get("CNF_Food_Group_Code")
                _sel_group_desc = group_desc_by_code.get(_sel_group_code)
                if _sel_group_desc:
                    st.caption(f"Food group: {_sel_group_desc}")

                # Household measure dropdown
                measures = get_measures_for_food(food_code, lookup)
                if len(measures) > 0:
                    measure_opts = [
                        f"{r['Measure_Description_and_Unit_EN']}  ({r['grams']:.1f} g)"
                        for _, r in measures.iterrows()
                    ]
                    sel_measure = st.selectbox("Household measure", measure_opts)
                    m_idx = measure_opts.index(sel_measure)
                    grams_per = float(measures.iloc[m_idx]["grams"])
                    qty = st.number_input(
                        "Quantity", min_value=0.0, value=1.0, step=0.5
                    )
                    calculated_grams = grams_per * qty
                    st.caption(f"= **{calculated_grams:.1f} g**")

                    if st.checkbox("Enter grams directly"):
                        calculated_grams = st.number_input(
                            "Grams",
                            min_value=0.0,
                            value=round(calculated_grams, 1),
                            step=1.0,
                        )
                else:
                    st.info("No household measures for this food.")
                    calculated_grams = st.number_input(
                        "Grams", min_value=0.0, value=100.0, step=1.0
                    )
            else:
                st.info("No foods found. Try another search.")
        else:
            st.caption("Type at least 2 characters to search.")

        if food_code is not None and calculated_grams > 0:
            _default_fluid = default_counts_as_fluid(food_desc, _sel_group_code)
            if st.button("➕ Add to recipe"):
                st.session_state.next_ingr_id += 1
                st.session_state.ingredients.append({
                    "id": st.session_state.next_ingr_id,
                    "food_code": food_code,
                    "food_description": food_desc,
                    "grams": float(calculated_grams),
                    "unit": "g",
                    "counts_as_fluid": _default_fluid,
                })
                st.rerun()

    else:  # Custom food from label — a Canadian Nutrition Facts lookalike
        # Round-2 clinical feedback, Part 0 #7 / Part 3: the label offers a
        # g-or-mL basis unit that flows through, UNCHANGED, to "Amount used
        # in recipe" below — no cross-conversion, ever (that would require
        # guessing a density). An mL-basis food's usage can only be entered
        # in mL, by construction (same widget, same unit, just placed
        # outside the label box so it reads as a clearly separate step).
        st.caption(
            "Enter values exactly as printed on the nutrition facts label."
        )
        basis_choice = st.radio(
            "Label basis",
            ["per ___ g", "per ___ mL"],
            horizontal=True,
            label_visibility="collapsed",
        )
        basis = "g" if basis_choice == "per ___ g" else "mL"

        _registry_map = registry_by_name(DEFAULT_PACK)
        cv: dict[str, float] = {}

        with st.container(border=True):
            st.markdown("#### Nutrition Facts")
            cname = st.text_input("Food name", "")
            cserving = st.number_input(
                f"Serving size ({basis})", min_value=1.0, value=100.0, step=1.0
            )
            st.divider()

            # CFIA ordering (Calories, then Fat/Sat/Trans, Carbohydrate/
            # Fibre/Sugars, Protein, Cholesterol, Sodium, Potassium,
            # Calcium, Iron) comes for free from data/packs/canada/
            # nutrients.csv's own row order — the registry CSV was
            # reordered to match the label layout the author asked for, so
            # this loop needs no hardcoded nutrient name list in Python;
            # a future country pack orders its own nutrients.csv to match
            # ITS label convention. Energy is rendered first and on its
            # own row (the "Calories" line reads differently from the
            # rest of the panel on a real label). Single column, not a
            # two-column zigzag — a real Nutrition Facts panel IS a single
            # narrow column top-to-bottom, and (Streamlit detail) widgets
            # assigned to st.columns() render column-major, not in loop
            # order, which would scramble this exact sequence apart
            # (Saturated Fat landing far from Fat) — the opposite of
            # "resemble a label as closely as possible."
            label_defs = [d for d in defs_for_tier("label", pack=DEFAULT_PACK) if d.on_label]
            energy_def = next(d for d in label_defs if d.name == "energy_kcal")
            cv[energy_def.name] = st.number_input(
                f"{energy_def.label} ({energy_def.unit})", min_value=0.0, value=0.0, step=1.0
            )
            st.divider()

            remaining_defs = [d for d in label_defs if d.name != "energy_kcal"]
            for d in remaining_defs:
                step = 1.0 if d.decimals == 0 else round(10 ** (-d.decimals), d.decimals)
                cv[d.name] = st.number_input(
                    f"{d.label} ({d.unit})", min_value=0.0, value=0.0, step=step
                )

            with st.expander("Optional nutrients on this label?"):
                st.caption(
                    "Vitamin D, B12, zinc, magnesium, and phosphorus are "
                    "CFIA-optional. Enter them if this label carries them "
                    "so the values reach the BTF micro screen."
                )
                clinical_defs = defs_for_tier("clinical", pack=DEFAULT_PACK)
                for d in clinical_defs:
                    step = 1.0 if d.decimals == 0 else round(10 ** (-d.decimals), d.decimals)
                    cv[d.name] = st.number_input(
                        f"{d.label} ({d.unit})", min_value=0.0, value=0.0, step=step
                    )

        st.caption(
            "Water/moisture is on no nutrition facts label, so recipes using "
            "custom foods will underestimate the free-water fraction — the "
            "label simply has nowhere to report it."
        )

        # Clearly separate from the label box above (Part 0 #7) — same
        # basis unit as the label's serving size, never converted.
        st.markdown("**Amount used in recipe**")
        cgrams = st.number_input(
            f"Amount used ({basis})",
            min_value=0.0,
            value=100.0,
            step=1.0,
            help=f"Same unit as the label basis above ({basis}) — an "
                 f"mL-basis food's usage can only be entered in mL, by "
                 f"design (no cross-conversion between g and mL).",
        )

        if st.button("➕ Add custom food"):
            if not cname:
                st.warning("Please enter a food name.")
            elif cserving <= 0:
                st.warning("Serving size must be positive.")
            else:
                code = st.session_state.next_custom_code
                st.session_state.next_custom_code -= 1
                # Convert label values to per-100-[basis] (same math either
                # way — label_to_per_100g() just divides by serving size
                # and multiplies by 100; it doesn't care whether that 100
                # means grams or mL, since the recipe-usage amount below is
                # scaled by the same basis).
                st.session_state.custom_foods[code] = {
                    name: label_to_per_100g(val, cserving)
                    for name, val in cv.items()
                }
                st.session_state.next_ingr_id += 1
                st.session_state.ingredients.append({
                    "id": st.session_state.next_ingr_id,
                    "food_code": code,
                    "food_description": f"{cname} (custom)",
                    "grams": float(cgrams),
                    "unit": basis,
                    # mL-basis custom foods default to counts-as-fluid=True
                    # (Part 2.4) — a liquid entered from a label (e.g. a
                    # protein shake) has no CNF moisture data, so the I&O
                    # full-volume convention is the only fluid signal
                    # available for it. Still user-toggleable.
                    "counts_as_fluid": basis == "mL",
                })
                st.rerun()

    # --- Blend details ---
    st.subheader("Blend details")
    # Check if example recipe was loaded (flag set by the top-row button
    # above). Must pop before the number_input below renders, so its
    # `value=` argument actually takes effect on this rerun.
    _example_loaded = st.session_state.pop("load_example", False)
    if _example_loaded:
        st.session_state.pop("sb_measured_volume", None)

    # Round-2 clinical feedback (Part 0 #8): the Added-water field is
    # DELETED. All liquids — including plain water — are ordinary
    # ingredients now (see the fluids ledger in the Ingredients section
    # below); nothing is lost, since CNF carries water at 99.9% moisture.
    measured_volume = st.number_input(
        "**Measured final volume (mL)**",
        min_value=0.0,
        value=550.0 if _example_loaded else 0.0,
        step=10.0,
        help="Read it off the side of the blender jug, or pour into a "
             "measuring cup after blending. Ingredient weights feed the "
             "nutrient math; volume is always this measured number.",
        key="sb_measured_volume",
    )

    # --- Ingredient table ---
    st.subheader("Ingredients")
    fluid_from_recipe_mL = 0.0

    if not st.session_state.ingredients:
        st.info("Add ingredients above to get started.")
    else:
        st.caption(
            "\"Counts as fluid\" drives the Results tab's Fluid provided "
            "row (full-volume I&O convention) — auto-checked for CNF "
            "Beverages and mL-basis custom foods, always your call "
            "otherwise (e.g. soup has no validated rule of thumb)."
        )
        # Display each ingredient with editable amount, unit, a
        # counts-as-fluid toggle, and a remove button.
        for i, ing in enumerate(st.session_state.ingredients):
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
            st.session_state.ingredients[i]["grams"] = new_amount
            new_fluid_flag = cols[2].checkbox(
                "Counts as fluid",
                value=bool(ing.get("counts_as_fluid", False)),
                key=f"fluid_{ing['id']}",
            )
            st.session_state.ingredients[i]["counts_as_fluid"] = new_fluid_flag
            if cols[3].button("❌", key=f"del_{ing['id']}"):
                st.session_state.ingredients.pop(i)
                st.rerun()

        # Weight caption: "X g + Y mL" when mL-basis foods are present
        # (Part 0 #7's accepted consequence — no cross-conversion means
        # the two units can't be summed into one number).
        total_g = sum(
            ing["grams"] for ing in st.session_state.ingredients
            if ing.get("unit", "g") == "g"
        )
        total_mL = sum(
            ing["grams"] for ing in st.session_state.ingredients
            if ing.get("unit", "g") == "mL"
        )
        if total_mL > 0:
            st.caption(f"Total ingredient weight: **{total_g:.0f} g** + **{total_mL:.0f} mL**")
        else:
            st.caption(f"Total ingredient weight: **{total_g:.0f} g**")

        # Fluid-from-recipe (Part 2.4): sum of counts-as-fluid ingredient
        # amounts, treating gram-entered liquids as mL 1:1 (the standard
        # clinical approximation already used for free water). Scaled to
        # daily intake + flushes in the Results tab, where daily_vol and
        # measured_volume are both in scope.
        fluid_from_recipe_mL = sum(
            ing["grams"] for ing in st.session_state.ingredients
            if ing.get("counts_as_fluid", False)
        )

        if st.button("🗑️ Clear all ingredients"):
            st.session_state.ingredients = []
            st.session_state.custom_foods = {}
            st.session_state.next_custom_code = -1
            st.rerun()


with results_tab:
    if not st.session_state.ingredients:
        st.info("Add ingredients in the Build tab to see results.")
    elif measured_volume <= 0:
        st.warning("⚠️ Enter a measured final volume in the Build tab to see results.")
    else:
        # --- Build recipe and calculate profile ---
        recipe = Recipe(
            name=recipe_name,
            ingredients=[
                Ingredient(
                    food_code=ing["food_code"],
                    food_description=ing["food_description"],
                    grams=ing["grams"],
                )
                for ing in st.session_state.ingredients
            ],
            # The Added-water field is gone (Part 0 #8) -- water is an
            # ordinary ingredient now. added_water_mL stays 0 here; the
            # model field itself is untouched (Part 4: don't change
            # src/models.py) even though the UI no longer feeds it.
            added_water_mL=0.0,
            measured_final_volume_mL=measured_volume,
        )

        profile = calculate_profile(recipe, na, custom_foods=st.session_state.custom_foods)

        # --- Density panel ---
        st.subheader("Density Panel")
        st.caption("Per-mL is the primary lens — patient tolerates limited mL/day.")

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Energy density", f"{profile.kcal_per_mL:.3f}", "kcal/mL")
        d2.metric("Protein density", f"{profile.protein_per_mL:.3f}", "g/mL")
        d3.metric("Free-water fraction", f"{profile.free_water_fraction:.3f}")
        d4.metric("Measured volume", f"{profile.measured_final_volume_mL:.0f} mL")

        with st.expander("Full density summary"):
            st.dataframe(
                generate_density_summary(profile),
                width="stretch",
                hide_index=True,
            )

        # --- Daily totals + adequacy report ---
        st.subheader("Daily Totals & Adequacy")
        st.caption(f"At **{daily_vol:.0f} mL/day** delivery")

        # NOTE: generate_adequacy_report() now returns (df, hidden_names) --
        # zero-coverage-hiding footnote wiring lands in a later commit
        # (Results-tab rework); this stopgap just keeps the app from
        # crashing now that the Build tab no longer feeds it added_water.
        adequacy_df, _hidden_main_names = generate_adequacy_report(profile, daily_vol, targets)

        # The report uses "—" (string) for missing targets alongside floats,
        # which breaks Arrow serialization in st.dataframe. Convert mixed
        # columns to str.
        adequacy_display = adequacy_df.copy()
        adequacy_display["Target"] = adequacy_display["Target"].astype(str)
        adequacy_display["% Target"] = adequacy_display["% Target"].astype(str)

        st.dataframe(
            adequacy_display.style.map(color_status, subset=["Status"]),
            width="stretch",
            hide_index=True,
        )

        with st.expander("BTF micro screen — vitamins & minerals not on labels"):
            st.caption(
                "A one-time supplementation screen (ASPEN-style: \"does this blend "
                "need a multivitamin?\"), not a daily-tracked panel like the table "
                "above. These nutrients aren't on a Canadian nutrition facts label "
                "(Source column), so a custom food entered from a label always "
                "contributes zero here. CNF coverage is also partial for some of "
                "them — vitamin D is present for only ~88% of foods — so a low "
                "number may reflect missing CNF data rather than missing nutrition."
            )
            clinical_df, _hidden_clinical_names = generate_clinical_screen(profile, daily_vol, targets)
            clinical_display = clinical_df.copy()
            clinical_display["Target"] = clinical_display["Target"].astype(str)
            clinical_display["% Target"] = clinical_display["% Target"].astype(str)
            st.dataframe(
                clinical_display.style.map(color_status, subset=["Status"]),
                width="stretch",
                hide_index=True,
            )

        # --- Dilution what-if ---
        st.subheader("Dilution What-If")
        st.caption("The core feature: see what a thinning decision *costs*.")

        w1, w2 = st.columns([1, 2])

        with w1:
            liquid_type = st.selectbox(
                "Thinning liquid", list(THINNING_LIQUIDS.keys())
            )
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
                diluted = dilute(
                    profile, added_mL, liq_kcal, liq_protein, liq_water
                )

                dil_df = pd.DataFrame(
                    [
                        {
                            "Metric": "Volume (mL)",
                            "Original": profile.measured_final_volume_mL,
                            "After dilution": diluted.measured_final_volume_mL,
                        },
                        {
                            "Metric": "kcal/mL",
                            "Original": round(profile.kcal_per_mL, 3),
                            "After dilution": round(diluted.kcal_per_mL, 3),
                        },
                        {
                            "Metric": "protein g/mL",
                            "Original": round(profile.protein_per_mL, 3),
                            "After dilution": round(diluted.protein_per_mL, 3),
                        },
                        {
                            "Metric": "free water fraction",
                            "Original": round(profile.free_water_fraction, 3),
                            "After dilution": round(diluted.free_water_fraction, 3),
                        },
                    ]
                )
                dil_df["Change"] = dil_df["After dilution"] - dil_df["Original"]
                st.dataframe(dil_df, width="stretch", hide_index=True)

                # Required daily volume to meet targets
                tk = targets.get("energy_kcal", 0.0)
                tp = targets.get("protein_g", 0.0)
                if tk > 0 and tp > 0:
                    ro = required_daily_volume(profile, tk, tp)
                    rd = required_daily_volume(diluted, tk, tp)
                    st.info(
                        f"Required daily volume to meet {tk:.0f} kcal + {tp:.0f} g protein:  \n"
                        f"**{ro:.0f} mL** → **{rd:.0f} mL** after dilution "
                        f"(+{rd - ro:.0f} mL)"
                    )
            else:
                st.caption("Slide the slider to see the effect of adding thinning liquid.")

        # --- Commercial formula comparator ---
        st.subheader("Commercial Formula Comparator")

        f1, f2 = st.columns([1, 3])
        formula_name = f1.selectbox("Formula", list(COMMERCIAL_FORMULAS.keys()))

        if daily_vol > 0:
            f2.dataframe(
                generate_formula_comparison(profile, formula_name, daily_vol),
                width="stretch",
                hide_index=True,
            )
        else:
            f2.info("Set a delivery method in the banner above to see comparison.")

        # --- Export to Excel ---
        st.subheader("Export")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Recipe info sheet
            pd.DataFrame(
                {
                    "Field": [
                        "Recipe name",
                        "Ingredients",
                        "Added water (mL)",
                        "Measured volume (mL)",
                        "Delivery method",
                        "Daily volume (mL)",
                    ],
                    "Value": [
                        recipe.name,
                        len(recipe.ingredients),
                        recipe.added_water_mL,
                        recipe.measured_final_volume_mL,
                        method_label,
                        daily_vol,
                    ],
                }
            ).to_excel(writer, sheet_name="Recipe", index=False)

            # Ingredient list
            if st.session_state.ingredients:
                pd.DataFrame(st.session_state.ingredients)[
                    ["food_description", "grams"]
                ].to_excel(writer, sheet_name="Ingredients", index=False)
            else:
                pd.DataFrame(
                    {"food_description": [], "grams": []}
                ).to_excel(writer, sheet_name="Ingredients", index=False)

            # Density summary
            generate_density_summary(profile).to_excel(
                writer, sheet_name="Density", index=False
            )

            # Adequacy report (tier="label" nutrients + fluid rows)
            generate_adequacy_report(profile, daily_vol, targets)[0].to_excel(
                writer, sheet_name="Adequacy", index=False
            )

            # BTF micro screen (tier="clinical" nutrients — one-time ASPEN-style
            # supplementation screen, not on any Canadian label; see the
            # "BTF micro screen" expander in the app for the full caveat).
            generate_clinical_screen(profile, daily_vol, targets)[0].to_excel(
                writer, sheet_name="Micro Screen", index=False
            )

            # Formula comparison
            generate_formula_comparison(
                profile, formula_name, daily_vol
            ).to_excel(writer, sheet_name="Formula Comparison", index=False)

        st.download_button(
            label="📥 Export to Excel",
            data=output.getvalue(),
            file_name=f"{sanitize_filename(recipe.name)}_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# --- Footer ---
st.divider()
st.caption(
    "For RD use — estimates only. RD clinical judgment is the final authority.  \n"
    "Built on the Canadian Nutrient File (CNF) 2026."
)