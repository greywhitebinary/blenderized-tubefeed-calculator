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
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is on sys.path so `src` package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_food_name, load_nutrient_amount
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
from src.targets import default_targets, empty_targets
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


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="BTF Calculator",
    page_icon="🥣",
    layout="wide",
)

init_state()

# Load cached CNF data (runs once, then served from cache)
fn = get_food_name()
na = get_nutrient_amount()
lookup = get_measure_lookup()


# ===========================================================================
# SIDEBAR — Inputs
# ===========================================================================

st.sidebar.title("🥣 BTF Calculator")
st.sidebar.caption("For RD use — estimates only")

# --- Recipe name ---
recipe_name = st.sidebar.text_input("Recipe name", "My BTF recipe")

# --- Load example recipe ---
if st.sidebar.button("📋 Load example recipe"):
    chicken = find_food(fn, "Chicken, broiler, breast, skinless, boneless, meat, raw")
    rice = find_food(fn, "Grains, rice, white, long-grain, parboiled, cooked")
    oil = find_food(fn, "Vegetable oil, canola")
    if chicken and rice and oil:
        st.session_state.next_ingr_id = 3
        st.session_state.ingredients = [
            {"id": 1, "food_code": chicken, "food_description": "Chicken breast", "grams": 200.0},
            {"id": 2, "food_code": rice, "food_description": "Rice, cooked", "grams": 150.0},
            {"id": 3, "food_code": oil, "food_description": "Canola oil", "grams": 15.0},
        ]
        st.session_state.custom_foods = {}
        st.session_state.next_custom_code = -1
        st.session_state["load_example"] = True
        st.rerun()
    else:
        st.sidebar.error("Could not find example foods in CNF.")

# --- Add ingredient ---
with st.sidebar.expander("➕ Add ingredient", expanded=True):
    add_mode = st.radio(
        "Source",
        ["CNF search", "Custom food (label)"],
        horizontal=True,
    )

    if add_mode == "CNF search":
        search_term = st.text_input(
            "Search foods",
            "",
            placeholder="e.g., chicken, rice, oil",
        )

        food_code: int | None = None
        food_desc: str | None = None
        calculated_grams = 0.0

        if len(search_term) >= 2:
            matches = fn[fn["Food_Description_EN"].str.contains(
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
            if st.button("➕ Add to recipe"):
                st.session_state.next_ingr_id += 1
                st.session_state.ingredients.append({
                    "id": st.session_state.next_ingr_id,
                    "food_code": food_code,
                    "food_description": food_desc,
                    "grams": float(calculated_grams),
                })
                st.rerun()

    else:  # Custom food from label
        st.caption("Enter values from the nutrition facts label (per serving).")
        cname = st.text_input("Food name", "")
        cserving = st.number_input(
            "Serving size (g)", min_value=1.0, value=100.0, step=1.0
        )
        cgrams = st.number_input(
            "Grams to use in recipe", min_value=0.0, value=100.0, step=1.0
        )

        # Fields are generated from the registry's tier="label" rows (the
        # nutrients actually printed on a Canadian nutrition facts label) —
        # NOT the full tracked-nutrient list. That's why this form has fat,
        # saturated fat, trans fat, cholesterol, carbohydrate, and sugars
        # (a real Canadian label has them) but no vitamin D, B12, or zinc
        # (no Canadian label carries those — see src/nutrients.py). A future
        # US pack would show vitamin D here instead, with zero code changes.
        with st.expander("Nutrition facts (per serving)"):
            c1, c2 = st.columns(2)
            cv: dict[str, float] = {}
            label_defs = [d for d in defs_for_tier("label", pack=DEFAULT_PACK) if d.on_label]
            for i, d in enumerate(label_defs):
                col = c1 if i % 2 == 0 else c2
                step = 1.0 if d.decimals == 0 else round(10 ** (-d.decimals), d.decimals)
                cv[d.name] = col.number_input(
                    f"{d.label} ({d.unit})", min_value=0.0, value=0.0, step=step
                )
        st.caption(
            "Water/moisture is on no nutrition facts label, so recipes using "
            "custom foods will underestimate the free-water fraction — the "
            "label simply has nowhere to report it."
        )

        if st.button("➕ Add custom food"):
            if not cname:
                st.warning("Please enter a food name.")
            elif cserving <= 0:
                st.warning("Serving size must be positive.")
            else:
                code = st.session_state.next_custom_code
                st.session_state.next_custom_code -= 1
                # Convert label values to per-100g basis
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
                })
                st.rerun()

# --- Blend details ---
st.sidebar.subheader("Blend details")
# Check if example recipe was loaded (flag set by the button above)
_example_loaded = st.session_state.pop("load_example", False)
if _example_loaded:
    st.session_state.pop("sb_added_water", None)
    st.session_state.pop("sb_measured_volume", None)

added_water = st.sidebar.number_input(
    "Added water (mL)",
    min_value=0.0,
    value=200.0 if _example_loaded else 0.0,
    step=10.0,
    key="sb_added_water",
)
measured_volume = st.sidebar.number_input(
    "**Measured final volume (mL)**",
    min_value=0.0,
    value=550.0 if _example_loaded else 0.0,
    step=10.0,
    help="The volume you measured after blending — this is the denominator for all densities.",
    key="sb_measured_volume",
)

# --- Delivery ---
st.sidebar.subheader("Delivery")
method_label = st.sidebar.radio(
    "Method",
    ["Syringe bolus", "Pump", "Direct mL/day"],
    label_visibility="collapsed",
)

if method_label == "Syringe bolus":
    bolus_vol = st.sidebar.number_input(
        "Bolus volume (mL)", min_value=0.0, value=300.0, step=10.0
    )
    times_day = st.sidebar.number_input(
        "Times per day", min_value=0.0, value=4.0, step=1.0
    )
    delivery = Delivery(
        method=DeliveryMethod.SYRINGE_BOLUS,
        bolus_volume_mL=bolus_vol,
        times_per_day=times_day,
    )
elif method_label == "Pump":
    rate = st.sidebar.number_input(
        "Rate (mL/hr)", min_value=0.0, value=100.0, step=10.0
    )
    hours = st.sidebar.number_input(
        "Hours per day", min_value=0.0, value=12.0, step=1.0
    )
    delivery = Delivery(
        method=DeliveryMethod.PUMP,
        rate_mL_per_hr=rate,
        hours_per_day=hours,
    )
else:
    direct_vol = st.sidebar.number_input(
        "Daily volume (mL)", min_value=0.0, value=1200.0, step=50.0
    )
    delivery = Delivery(
        method=DeliveryMethod.DIRECT,
        daily_volume_mL=direct_vol,
    )

daily_vol = daily_volume_from_delivery(delivery)
st.sidebar.caption(f"**Daily volume: {daily_vol:.0f} mL/day**")

# --- Targets (optional) ---
st.sidebar.subheader("Targets (optional)")
use_defaults = st.sidebar.checkbox(
    "Use default DRI adult targets", value=True
)

# Per-nutrient step sizes for the custom-target number_inputs below —
# a UX nicety only (e.g. kcal steps by 50, not 1). Nutrients not listed
# fall back to a step derived from their registry `decimals`.
_TARGET_STEP_OVERRIDES: dict[str, float] = {
    "energy_kcal": 50.0,
    "fluid_mL": 100.0,
    "sodium_mg": 100.0,
    "potassium_mg": 100.0,
    "calcium_mg": 50.0,
    "protein_g": 5.0,
    "vitamin_b12_ug": 0.5,
}

if use_defaults:
    targets = default_targets()
else:
    targets = empty_targets()
    st.sidebar.caption("Enter patient-specific targets (0 = no target):")
    tc1, tc2 = st.sidebar.columns(2)
    cols = (tc1, tc2)
    # Generated from the registry: iterate every nutrient that HAS a
    # target in data/packs/canada/targets.csv (default_targets()' keys,
    # in CSV row order), not a hardcoded field list. "fluid_mL" isn't a
    # CNF nutrient (it's the target for the derived Free water row), so
    # it gets a hand-written label/unit; everything else reads its
    # label/unit straight off the registry.
    _registry_map = registry_by_name(DEFAULT_PACK)
    for i, nutrient_name in enumerate(default_targets()):
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


# ===========================================================================
# MAIN AREA — Ingredient table + Results
# ===========================================================================

st.title(f"🥣 {recipe_name or 'BTF Recipe'}")

# --- Ingredient table ---
st.subheader("Ingredients")

if not st.session_state.ingredients:
    st.info("👈 Add ingredients using the sidebar to get started.")
    st.stop()

# Display each ingredient with editable grams and a remove button
for i, ing in enumerate(st.session_state.ingredients):
    cols = st.columns([5, 2, 1])
    cols[0].write(f"{i + 1}. {ing['food_description']}")
    new_grams = cols[1].number_input(
        f"Grams for {ing['food_description']}",
        value=float(ing["grams"]),
        min_value=0.0,
        step=1.0,
        key=f"grams_{ing['id']}",
        label_visibility="collapsed",
    )
    st.session_state.ingredients[i]["grams"] = new_grams
    if cols[2].button("❌", key=f"del_{ing['id']}"):
        st.session_state.ingredients.pop(i)
        st.rerun()

total_grams = sum(ing["grams"] for ing in st.session_state.ingredients)
st.caption(f"Total ingredient weight: **{total_grams:.0f} g** + {added_water:.0f} mL water")

if st.button("🗑️ Clear all ingredients"):
    st.session_state.ingredients = []
    st.session_state.custom_foods = {}
    st.session_state.next_custom_code = -1
    st.rerun()

# --- Build recipe and calculate profile ---
if measured_volume <= 0:
    st.warning("⚠️ Enter a measured final volume in the sidebar to see results.")
    st.stop()

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
    added_water_mL=added_water,
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

adequacy_df = generate_adequacy_report(profile, daily_vol, targets)

# The report uses "—" (string) for missing targets alongside floats, which
# breaks Arrow serialization in st.dataframe. Convert mixed columns to str.
adequacy_display = adequacy_df.copy()
adequacy_display["Target"] = adequacy_display["Target"].astype(str)
adequacy_display["% Target"] = adequacy_display["% Target"].astype(str)


def color_status(val: str) -> str:
    """Color-code adequacy status cells.

    "Above UL" and "Below target" are both concerning (red); "Below UL"
    and "Meeting target" are both fine (green) — a UL is a ceiling, not
    an aim, so "Below UL" reads as "fine" the same way "Meeting target"
    does for an RDA/AI nutrient. See src/report.py::_adequacy_status.
    """
    if val in ("Below target", "Above UL"):
        return "background-color: #ffcccc"
    elif val == "Above target":
        return "background-color: #ffe0b2"
    elif val in ("Meeting target", "Below UL"):
        return "background-color: #c8e6c9"
    return ""


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
    clinical_df = generate_clinical_screen(profile, daily_vol, targets)
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
    f2.info("Set a delivery method in the sidebar to see comparison.")

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

    # Adequacy report (tier="label" nutrients + Free water)
    generate_adequacy_report(profile, daily_vol, targets).to_excel(
        writer, sheet_name="Adequacy", index=False
    )

    # BTF micro screen (tier="clinical" nutrients — one-time ASPEN-style
    # supplementation screen, not on any Canadian label; see the
    # "BTF micro screen" expander in the app for the full caveat).
    generate_clinical_screen(profile, daily_vol, targets).to_excel(
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