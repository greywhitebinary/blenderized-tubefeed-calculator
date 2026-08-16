"""
streamlit_app.py — Streamlit UI for the Blenderized Tube Feed Calculator.

Phase 6; reworked per FEED_LOG_REWORK.md (the Intake Record rework) --
read that doc before changing this file. It replaces the old single-
recipe + delivery-schedule model (which silently extrapolated a measured
batch volume against whatever the schedule claimed was given -- see the
doc's section 1 for the bug) with:

  - Blends: a list of recipe formulations (name + ingredients + measured
    volume), managed in the Feed Recipes tab. A blend is scale-free -- its
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
  - Estimates to inform clinical judgment, never to replace it. Built for
    dietitians and the teams supporting blenderized tube feeding; families
    and patients are welcome to use it, but it gives no individual advice
    and creates no professional relationship (author, 2026-08-01 -- this
    used to read "not a family-facing tool", which excluded the people
    doing this at home rather than telling them where their questions
    belong).
"""

import copy
import re
import sys
from datetime import date as ddate
from datetime import time as dtime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Ensure project root is on sys.path so `src` package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_food_name, load_nutrient_amount, load_food_group
from src.models import Ingredient
from src.calculator import (
    label_to_per_100g,
    compute_nutrient_totals_and_coverage,
    compute_ingredient_breakdown,
    dilute,
    required_daily_volume,
    COMMERCIAL_FORMULAS,
)
from src.measures import load_measure_lookup, get_measures_for_food, scale_measure_label
from src.food_search import MIN_QUERY_LEN, build_index, search_foods
from src.label_extract import (
    MAX_EXTRACTIONS_PER_DAY,
    MAX_EXTRACTIONS_PER_SESSION,
    LabelExtractionError,
    extract_label,
)
from src.day_io import (
    DayFileError,
    day_to_workbook_bytes,
    suggested_day_filename,
    workbook_bytes_to_day,
)
from src.recipe_io import (
    AMBIGUOUS,
    MATCH_BY_CODE,
    UNMATCHED,
    RecipeFileError,
    recipe_to_workbook_bytes,
    recipes_to_workbook_bytes,
    resolve_ingredients,
    suggested_filename,
    workbook_bytes_to_recipes,
)
from src.targets import empty_targets
from src.report import (
    generate_adequacy_report,
    generate_clinical_screen,
    generate_comparator_table,
    EDITING_MARKER,
    generate_density_summary,
    generate_source_breakdown,
    generate_water_ledger,
    format_ingredient_breakdown,
)
from src.nutrients import defs_for_tier, registry_by_name, DEFAULT_PACK
from src.intake import (
    aggregate_intake,
    resolve_blend_profile,
    blend_fluid_fraction,
    sorted_intake_log,
    unique_blend_name,
    InvalidBlendError,
    TUBE_FEED_LABEL,
    FOOD_DRINK_LABEL,
    TOTAL_LABEL,
    WATER_FLUSH_LABEL,
)

# ---------------------------------------------------------------------------
# Thinning liquid presets (per 100 mL) — for the dilution what-if
# ---------------------------------------------------------------------------
# NARROWED TO NON-NUTRITIVE LIQUIDS ONLY (author, 2026-07-30).
#
# dilute() models exactly three things from an added liquid: kcal,
# protein and water. For plain water that is the COMPLETE picture, so the
# preview is exact. For broth, juice or milk it is not: their sodium,
# potassium, calcium and the rest silently stay at the pre-dilution
# total, so the panel understates what the liquid actually brought --
# thinning with broth would show sodium DENSITY falling while real broth
# adds a sodium load.
#
# The fix is not to teach dilute() about every nutrient. Adding 200 mL of
# broth to a blend IS a recipe change, and the recipe editor already
# handles it correctly through the full CNF row -- every nutrient, not
# three. For anything nutritive the editor gives a BETTER answer than
# this preview, so offering the preview at all was offering the worse of
# two tools. The rule an RD can hold in their head: thinning with water
# is a preview, thinning with anything nutritive is a recipe edit.
#
# The CSV stays the canonical, RD-editable source (add "Sterile water" or
# "Distilled water" and it appears automatically); the app simply filters
# to entries that contribute no kcal and no protein.
_THINNING_CSV_NAME = "thinning_liquids.csv"

# Fallback used only if a pack's CSV is missing. Water only, matching the
# non-nutritive filter in _load_thinning_liquids().
_THINNING_FALLBACK: dict[str, dict[str, float]] = {
    "Water": {"kcal": 0.0, "protein_g": 0.0, "water_g": 100.0},
}


def _thinning_csv_path(pack: str = DEFAULT_PACK) -> Path:
    """Where a pack keeps its thinning-liquid presets.

    Pack-aware since 2026-07-30 -- this was the last loader still reading
    from a hardcoded `canada` path (CONTEXT.md §9). Inert until a second
    pack exists, but it no longer silently serves Canadian reference data
    to a non-Canadian pack.
    """
    return PROJECT_ROOT / "data" / "packs" / pack / _THINNING_CSV_NAME


def _load_thinning_liquids(pack: str = DEFAULT_PACK) -> dict[str, dict[str, float]]:
    """Load thinning liquid presets from a pack's CSV, falling back to a
    hardcoded dict if the file is missing.

    Returns ONLY non-nutritive liquids (no kcal, no protein) -- see the
    module-level note above for why. Nutritive thinners belong in the
    recipe, where every nutrient is computed rather than three.

    CSV format: name,kcal_per_100mL,protein_g_per_100mL,water_g_per_100mL
    """
    csv_path = _thinning_csv_path(pack)
    if not csv_path.exists():
        liquids = dict(_THINNING_FALLBACK)
    else:
        df = pd.read_csv(csv_path)
        liquids = {}
        for _, row in df.iterrows():
            liquids[row["name"]] = {
                "kcal": float(row["kcal_per_100mL"]),
                "protein_g": float(row["protein_g_per_100mL"]),
                "water_g": float(row["water_g_per_100mL"]),
            }
    # Keep only non-nutritive liquids. A liquid carrying kcal or protein
    # also carries sodium, potassium and the rest -- none of which
    # dilute() models -- so previewing it here would be less accurate
    # than simply adding it to the recipe. The "Custom" free-entry option
    # was removed for the same reason: hand-entering kcal and protein is
    # precisely the nutritive case that belongs in the ingredient list.
    return {
        name: vals
        for name, vals in liquids.items()
        if vals["kcal"] == 0.0 and vals["protein_g"] == 0.0
    }


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


def find_food(fn_df: pd.DataFrame, desc: str) -> int | None:
    """Find a Food_Code by description: an exact match if there is one,
    otherwise the first substring match.

    The exact pass matters because CNF descriptions nest. "Spinach,
    boiled, drained" is a substring of "New Zealand spinach, boiled,
    drained", so substring-only resolved the example day's spinach to the
    New Zealand one -- silently, and with different nutrients (author,
    2026-08-15). Every caller here names a full CNF description, so
    preferring an exact hit costs nothing and removes a whole class of
    wrong-food-looks-right bug.
    """
    descriptions = fn_df["Food_Description_EN"]
    exact = fn_df[descriptions.str.casefold() == desc.casefold()]
    if len(exact):
        return int(exact.iloc[0]["Food_Code"])
    m = fn_df[descriptions.str.contains(desc, case=False, na=False, regex=False)]
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
# Session state — Blends (Feed Recipes tab) + Intake Record (Daily Intake
# Record tab), per FEED_LOG_REWORK.md section 3.2.
# ---------------------------------------------------------------------------


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
        _note("No usable ingredient rows were found in that file.")
        if st.button("Cancel", key="recipe_import_cancel_empty"):
            _clear()
            st.rerun()
        return

    needs_review = sum(1 for _, resolved in entries for r in resolved if r.status != MATCH_BY_CODE)
    if needs_review:
        st.caption(
            f"{needs_review} of {total_rows} rows need you to confirm which "
            "CNF food is meant. Nothing is added until you press Add."
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
            _note(warning)

        choices: list[int | None] = []
        for index, row in enumerate(resolved):
            amount_label = f"{row.grams:g} {row.unit}"
            if row.status == MATCH_BY_CODE:
                st.write(f"✅ **{row.food_description}** — {amount_label}")
                choices.append(row.food_code)
            elif row.status == AMBIGUOUS:
                picked = st.selectbox(
                    f'"{row.source_text}" — {amount_label}: which food?',
                    options=[None] + [c[0] for c in row.candidates],
                    format_func=lambda code, _row=row: (
                        "— choose one —"
                        if code is None
                        else next(d for c, d in _row.candidates if c == code)
                    ),
                    key=f"recipe_pick_{r_index}_{index}",
                )
                choices.append(picked)
            elif row.status == UNMATCHED:
                st.write(f'❌ "{row.source_text}" — {amount_label}: no CNF match, will be skipped.')
                choices.append(None)
            else:  # matched on description — likely right, still confirm
                keep = st.checkbox(
                    f'"{row.source_text}" → **{row.food_description}** — {amount_label}',
                    value=True,
                    key=f"recipe_keep_{r_index}_{index}",
                )
                choices.append(row.food_code if keep else None)
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
                st.session_state.next_ingr_id += 1
                blend["ingredients"].append(
                    {
                        "id": st.session_state.next_ingr_id,
                        "food_code": int(code),
                        "food_description": row.food_description,
                        "grams": row.grams,
                        "unit": row.unit,
                        "counts_as_fluid": row.counts_as_fluid,
                        "measure_label": row.measure_label,
                        "measure_grams": row.measure_grams,
                    }
                )
        _clear()
        st.rerun()

    if c2.button("Cancel", key="recipe_import_cancel", width="stretch"):
        _clear()
        st.rerun()


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
        f"#A4243A; padding: 0.6rem 0.9rem; border-radius: 0.25rem; "
        f'color: #3d3d3d;">{message}</div>',
        unsafe_allow_html=True,
    )


def _narrow(left: int = 1, right: int = 2):
    """Column pair with an empty spacer -- keeps a short field from running
    the full page width. Streamlit stacks columns on a narrow viewport, so
    on a phone the field goes back to full width by itself."""
    col, _spacer = st.columns([left, right])
    return col


@st.cache_resource(show_spinner=False)
def _label_call_ledger() -> dict:
    """A call counter SHARED by every visitor to this app instance.

    `cache_resource` hands the same object to every session in the
    process, which is the only cross-session state a Streamlit app gets
    without a database. That makes this a real (if crude) global
    throttle: the per-session limit alone is defeated by opening a new
    tab, and this is not.

    Its limits are honest ones. It resets when the app restarts, and if
    Cloud ever runs more than one process each gets its own counter. It
    reduces how often the spend limit on the API key gets tested; it is
    not what protects the author's card. That is the console limit.
    """
    return {"date": None, "count": 0}


def _label_calls_remaining() -> tuple[int, int]:
    """(remaining this session, remaining today) — never below zero."""
    ledger = _label_call_ledger()
    today = ddate.today()
    if ledger["date"] != today:
        ledger["date"], ledger["count"] = today, 0
    session_used = st.session_state.get("_label_calls_used", 0)
    return (
        max(0, MAX_EXTRACTIONS_PER_SESSION - session_used),
        max(0, MAX_EXTRACTIONS_PER_DAY - ledger["count"]),
    )


def _label_record_call() -> None:
    st.session_state["_label_calls_used"] = st.session_state.get("_label_calls_used", 0) + 1
    _label_call_ledger()["count"] += 1


def _label_api_client():
    """The Anthropic client, or None when no key is configured.

    The key is read HERE and nowhere else, straight out of Streamlit's
    secrets. Streamlit executes server-side, so a secret read in this
    process is never sent to the browser -- unlike a key in front-end
    JavaScript, which anyone can read from devtools. It is never logged,
    never rendered, and never put in an error message.

    Returning None rather than raising keeps the app fully usable with no
    key at all: the photo control simply doesn't appear, and the RD types
    the label in by hand exactly as before.
    """
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:  # noqa: BLE001 - no secrets file at all, locally
        return None
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic(api_key=api_key)


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
    counts_as_fluid, measure_label, measure_grams} on the render where the
    Add button is clicked and the entry is valid, else None. measure_label
    is the raw CNF household-measure description ("1 cup") and
    measure_grams is grams-per-ONE-of-that-measure; both are None for a
    custom food from a label, or a CNF food with no household measures.
    `key_prefix` must be unique per call site
    (e.g. "blend_3" vs "oral_dialog") so two simultaneous instances of this
    component never collide on widget keys.

    show_counts_as_fluid_toggle: when True, renders an editable
    counts_as_fluid checkbox (seeded with the same auto-default used
    elsewhere -- CNF Beverages group or mL-basis custom food) right before
    the Add button, and the RD's choice (default or overridden) is what
    ends up in the returned dict. The Feed Recipes tab leaves this False -- a
    blend's ingredient table already lets the RD toggle counts_as_fluid
    after adding; the "Add food/drink" UI passes True, since
    FEED_LOG_REWORK.md section 3.4 calls for the toggle to live right there
    (there's no ingredient table for a single oral row).
    """
    add_mode = st.radio(
        "Source",
        [
            "Search foods from the Canadian Nutrient File",
            "Enter a Canada Nutrition Facts label (custom food)",
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

        # The search row gets its own card: after adding a food the RD scrolls
        # back up to type the next one, and a flat stack of identical rows gives
        # the eye nothing to aim at (author feedback 2026-08-14).
        with st.container(border=True):
            gc1, gc2 = st.columns([1, 2])
            selected_group = gc1.selectbox("Food group", group_options, key=f"{key_prefix}_group")
            search_term = gc2.text_input(
                "Search foods",
                "",
                placeholder="e.g., chicken, rice, oil",
                key=f"{key_prefix}_search",
            )

        food_code: int | None = None
        food_desc: str | None = None
        calculated_grams = 0.0
        sel_group_code = None
        # Household measure, carried through to the returned dict (Change
        # 1, 2026-08-15) so grams stays the thing calculated with while the
        # RD can keep reading/editing in cups. None when no measure was
        # picked (no CNF measures for this food).
        measure_label: str | None = None
        measure_grams: float | None = None

        # Three-layer search (src/food_search.py): all words in any order,
        # then a curated synonym, then per-word typo tolerance. It replaced
        # a literal substring match that returned NOTHING for "wild rice"
        # or "greek yogurt", because CNF files those as "Grains, rice,
        # wild, dry" and "Yogourt (yogurt), Greek style...". An RD who
        # searches, sees nothing, and hand-enters a food that was already
        # in CNF gets worse data than the database could have given her.
        _group_code = None if selected_group == "All" else group_code_by_desc[selected_group]

        if len(search_term) >= MIN_QUERY_LEN:
            _search = search_foods(search_term, _food_search_index(_group_code), limit=50)
            # Deliberately NOT re-sorted alphabetically: search_foods()
            # returns them ranked (description matches before
            # alternate-name matches, whole words before prefixes,
            # shorter CNF descriptions -- its basic foods -- first).
            matches = _search.matches

            # Say so whenever the query was reinterpreted. The RD has to
            # be able to see that "brocolli" became broccoli, or that a
            # synonym fired -- a substitution is allowed to be wrong only
            # because it is never silent (CONTEXT.md §11, same rule as AI
            # label extraction).
            if _search.note:
                st.caption(f"🔎 {_search.note}")

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
                    # Measure and quantity on one line, with a spacer so neither runs the
                    # full width -- a household measure is a short phrase and a quantity is
                    # usually "1" (author feedback 2026-08-14).
                    mc1, mc2, _spacer = st.columns([3, 1, 2])
                    sel_measure = mc1.selectbox(
                        "Household measure", measure_opts, key=f"{key_prefix}_measure"
                    )
                    m_idx = measure_opts.index(sel_measure)
                    grams_per = float(measures.iloc[m_idx]["grams"])
                    # The raw CNF string, not measure_opts' "  (158.0 g)"
                    # suffix -- that suffix is a dropdown affordance, not
                    # part of the label an RD or caregiver should read back.
                    measure_label = str(measures.iloc[m_idx]["Measure_Description_and_Unit_EN"])
                    measure_grams = grams_per
                    qty = mc2.number_input(
                        "Quantity",
                        min_value=0.0,
                        value=1.0,
                        step=0.5,
                        format="%g",
                        key=f"{key_prefix}_qty",
                    )
                    calculated_grams = grams_per * qty
                    mc2.caption(f"= **{calculated_grams:.1f} g**")

                    if st.checkbox("Enter grams directly", key=f"{key_prefix}_grams_override"):
                        calculated_grams = _narrow().number_input(
                            "Grams",
                            min_value=0.0,
                            value=round(calculated_grams, 1),
                            step=1.0,
                            format="%g",
                            key=f"{key_prefix}_grams_direct",
                        )
                else:
                    _note("No household measures for this food.")
                    calculated_grams = _narrow().number_input(
                        "Grams",
                        min_value=0.0,
                        value=100.0,
                        step=1.0,
                        format="%g",
                        key=f"{key_prefix}_grams_nomeasure",
                    )
            else:
                # Nothing found is an honest answer, and after three
                # layers it usually means CNF really doesn't have it --
                # so point at the way out rather than just saying no.
                _note(
                    "No foods found. Try fewer words, or switch to "
                    "<strong>Enter a Canada Nutrition Facts label</strong> above to add "
                    "this food yourself."
                )
        else:
            st.caption(f"Type at least {MIN_QUERY_LEN} characters to search.")

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
                    "measure_label": measure_label,
                    "measure_grams": measure_grams,
                }

    else:  # Custom food from label — a Canadian Nutrition Facts lookalike
        st.caption("Enter values exactly as printed on the Nutrition Facts table.")

        # Wipe the form after a custom food was added on the previous run.
        #
        # Without this the fields keep the food just added, so a second
        # label inherits the first one's numbers for every field the RD
        # doesn't happen to overwrite -- add Ensure, then Boost, and
        # Boost silently carries Ensure's sodium. Nothing on screen would
        # show it.
        #
        # Deleting the keys (rather than setting them to 0) lets each
        # widget fall back to its own `value=` default. Like the photo
        # drafts, it must happen before those widgets are instantiated,
        # which is why the Add handler at the bottom only sets a flag.
        if st.session_state.pop(f"{key_prefix}_clear_form", False):
            for _stale in (
                f"{key_prefix}_cname",
                f"{key_prefix}_cv_serving",
                f"{key_prefix}_cv_energy",
                f"{key_prefix}_label_photo",
                f"{key_prefix}_photo_result",
                f"{key_prefix}_label_photo_seen",
            ):
                st.session_state.pop(_stale, None)
            for _d in defs_for_tier("label", pack=DEFAULT_PACK):
                st.session_state.pop(f"{key_prefix}_cv_{_d.name}", None)
            for _d in defs_for_tier("clinical", pack=DEFAULT_PACK):
                st.session_state.pop(f"{key_prefix}_cv_clin_{_d.name}", None)

        # Apply anything a label photo staged on the previous run. This has
        # to happen BEFORE the first widget below is instantiated -- see the
        # staging comment in the photo handler, and CONTEXT.md §11.
        _pending_photo_key = f"{key_prefix}_photo_pending"
        _pending_photo = st.session_state.pop(_pending_photo_key, None)
        if _pending_photo is not None:
            if _pending_photo.food_name:
                st.session_state[f"{key_prefix}_cname"] = _pending_photo.food_name
            if _pending_photo.serving_amount and _pending_photo.serving_amount > 0:
                st.session_state[f"{key_prefix}_cv_serving"] = float(_pending_photo.serving_amount)
            if _pending_photo.serving_unit in ("g", "mL"):
                st.session_state[f"{key_prefix}_basis"] = (
                    "Serving size in weight (g)"
                    if _pending_photo.serving_unit == "g"
                    else "Serving size in volume (mL)"
                )
            for _n, _v in _pending_photo.values.items():
                # Energy's widget key is _cv_energy, not _cv_energy_kcal --
                # it predates the others.
                _wkey = (
                    f"{key_prefix}_cv_energy" if _n == "energy_kcal" else f"{key_prefix}_cv_{_n}"
                )
                st.session_state[_wkey] = float(_v)
            # Derived here, from the same staged object, so one event
            # leaves one piece of state. The handler below used to set
            # this separately, which meant the drafts and the message
            # explaining them could get out of step.
            st.session_state[f"{key_prefix}_photo_result"] = {
                "found": _pending_photo.found_count,
                "missing": list(_pending_photo.missing),
                "notes": _pending_photo.notes,
            }

        # Rendered here, NOT inside the photo uploader above. It describes
        # values already sitting in the form, so it must not vanish just
        # because the API client is unavailable -- and gating it on the
        # client made the whole thing untestable without a key, which is
        # how CI found it.
        _result = st.session_state.get(f"{key_prefix}_photo_result")
        if _result:
            _reg = registry_by_name(DEFAULT_PACK)
            _missing_labels = [_reg[_m].label for _m in _result["missing"] if _m in _reg]
            st.success(
                f"Filled in {_result['found']} values from your photo. "
                "**Check every one against the label before adding it.**"
            )
            if _missing_labels:
                # Named, not silently left at 0: an absent line and a
                # printed zero are different facts, and only the RD
                # holding the label can tell which this is.
                st.caption(
                    "Not found on that label, so left alone: "
                    + ", ".join(_missing_labels)
                    + ". If the label really shows 0, enter 0 yourself."
                )
            if _result["notes"]:
                st.caption(f"Note from the reader: {_result['notes']}")

        basis_choice = st.radio(
            "Label basis",
            ["Serving size in weight (g)", "Serving size in volume (mL)"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"{key_prefix}_basis",
        )
        basis = "g" if "weight" in basis_choice else "mL"

        # --- Label photo -> draft values (paid API) ------------------------
        # Placed ABOVE the Nutrition Facts box on purpose. Filling the form
        # means writing the number_inputs' session_state keys, and that only
        # works BEFORE those widgets are instantiated this run (§11). So this
        # block writes the keys and immediately reruns; the box below then
        # renders holding the drafts.
        #
        # The extraction NEVER writes to a blend. It fills the same form the
        # RD would have typed into, and the RD confirms every value against
        # the label in their hand before pressing Add. That is the rule from
        # CONTEXT.md §11, and this form doubles as the verification UI.
        _photo_client = _label_api_client()
        if _photo_client is not None:
            _session_left, _day_left = _label_calls_remaining()
            with st.expander("📷 Read the values from a photo instead of typing"):
                st.caption(
                    "Reads the table and fills the form below for you to check. "
                    f"**{_session_left} left this session**, "
                    f"{_day_left} left today across everyone. "
                    "Every value stays editable and nothing is saved until you press Add."
                )
                if _session_left <= 0 or _day_left <= 0:
                    _note(
                        "Photo reading has reached its limit for now — please type "
                        "the values in below."
                    )
                else:
                    _photo = st.file_uploader(
                        "Photo of the Nutrition Facts table",
                        type=["jpg", "jpeg", "png", "webp"],
                        key=f"{key_prefix}_label_photo",
                        help="Photograph the table on the package, straight on and close.",
                    )
                    _seen_key = f"{key_prefix}_label_photo_seen"
                    if _photo is not None and st.session_state.get(_seen_key) != _photo.name:
                        st.session_state[_seen_key] = _photo.name
                        with st.spinner("Reading the label…"):
                            try:
                                _read = extract_label(
                                    _photo.getvalue(),
                                    _photo.type or "",
                                    client=_photo_client,
                                    pack=DEFAULT_PACK,
                                )
                            except LabelExtractionError as _exc:
                                _note(str(_exc))
                            else:
                                _label_record_call()
                                # STAGE the drafts; do not write widget keys
                                # here. This handler runs below the "Label
                                # basis" radio, and writing a widget's
                                # session_state after that widget exists in
                                # the same run raises StreamlitAPIException
                                # (§11). Staging + rerun means the values are
                                # applied at the TOP of the next run, above
                                # every widget in this component -- which
                                # stays correct even if this block moves.
                                st.session_state[_pending_photo_key] = _read
                                st.rerun()

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
                return st.number_input(text, label_visibility="collapsed", key=key, **kwargs)

        label_col, _spacer = st.columns([2, 3])
        with label_col:
            with st.container(border=True, key=box_key):
                # NOT "Canada Nutrition Facts". This heading is part of the
                # visual replica of the printed table, and a real Canadian
                # package prints exactly "Nutrition Facts / Valeur
                # nutritive". Relabelling it would make the lookalike wrong
                # in the one place it is meant to be literal -- the RD holds
                # the real label beside this box and compares.
                st.markdown('<div class="nft-title">Nutrition Facts</div>', unsafe_allow_html=True)
                cname = st.text_input("Food name", "", key=f"{key_prefix}_cname")
                cserving = _nft_field(
                    f"Serving size ({basis})",
                    "nft-main",
                    f"{key_prefix}_cv_serving",
                    min_value=1.0,
                    value=100.0,
                    step=1.0,
                )
                st.markdown('<hr class="nft-thick">', unsafe_allow_html=True)

                label_defs = [d for d in defs_for_tier("label", pack=DEFAULT_PACK) if d.on_label]
                energy_def = next(d for d in label_defs if d.name == "energy_kcal")
                cv[energy_def.name] = _nft_field(
                    f"{energy_def.label} ({energy_def.unit})",
                    "nft-cal",
                    f"{key_prefix}_cv_energy",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                )
                st.markdown('<hr class="nft-thin">', unsafe_allow_html=True)

                NFT_MAIN_NAMES = {
                    "fat_g",
                    "carbohydrate_g",
                    "protein_g",
                    "cholesterol_mg",
                    "sodium_mg",
                    "potassium_mg",
                    "calcium_mg",
                    "iron_mg",
                }
                remaining_defs = [d for d in label_defs if d.name != "energy_kcal"]
                for d in remaining_defs:
                    css_class = "nft-main" if d.name in NFT_MAIN_NAMES else "nft-sub"
                    cv[d.name] = _nft_field(
                        f"{d.label} ({d.unit})",
                        css_class,
                        f"{key_prefix}_cv_{d.name}",
                        min_value=0.0,
                        value=0.0,
                        step=_nft_step(d),
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
                            f"{d.label} ({d.unit})",
                            "nft-sub",
                            f"{key_prefix}_cv_clin_{d.name}",
                            min_value=0.0,
                            value=0.0,
                            step=_nft_step(d),
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
                    "Counts as fluid",
                    value=_custom_default_fluid,
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
                        # No CNF household measure exists for a food typed
                        # from a label -- always grams (or mL) only.
                        "measure_label": None,
                        "measure_grams": None,
                    }
                    # Only a flag: every field above has already been
                    # instantiated this run, so clearing them here would
                    # raise StreamlitAPIException (§11). The caller reruns
                    # after adding, and the block at the top of this
                    # branch does the wiping.
                    st.session_state[f"{key_prefix}_clear_form"] = True

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
       leaves a big empty gap above the first element; this keeps a
       little breathing room below the Cloud toolbar without the void.
       Both selectors cover Streamlit version drift in the testid name.

       3.75rem matches the height of Streamlit's fixed header, which
       page content scrolls under -- anything less clips the first
       element. Tune this one number. */
    .stApp [data-testid="stMainBlockContainer"],
    .stApp .block-container {
        padding-top: 3.75rem !important;
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

    /* Desktop page width (author feedback 2026-08-14). layout="wide" removes
       Streamlit's width limit entirely, which is right for the report tables
       and wrong for everything else: on a large monitor a number box holding
       "1.0" ran the full screen and caption paragraphs ran past a readable
       line length. Cap the column here; the few tables that genuinely need
       the whole screen break out of it below.

       60rem, not 1200px, so this scales with the font-size knob at the top of
       this block instead of fighting it. Tune this one number. It has no
       effect on a phone, where the viewport is already narrower than the cap.

       LEFT-justified, not centred (author feedback 2026-08-14). Streamlit
       centres the block with margin:auto, which put the capped reading column
       in the middle of the screen while a full-width table was centred on the
       VIEWPORT -- so the wide tables started further left than every heading
       above them and read as misaligned rather than wide. One shared left
       edge for everything is what makes the mixed widths look deliberate. */
    .stApp [data-testid="stMainBlockContainer"],
    .stApp .block-container {
        max-width: 60rem;
        margin-left: 0 !important;
        margin-right: auto !important;
    }

    /* Break-out for tables too wide to read inside the cap. Any
       st.container(key="fullbleed_*") keeps the shared left edge and simply
       extends to the right -- no negative margins, which is what made the
       first attempt straddle the page.

       Only above 64rem: below that the viewport is already narrower than the
       cap, so there is nothing to break out of and the table should just be
       the width of the phone. The 8rem keeps the right edge clear of the
       viewport even at the widest block-container padding, so the PAGE never
       gets a horizontal scrollbar of its own. */
    @media (min-width: 64rem) {
        [class*="st-key-fullbleed"] {
            width: calc(100vw - 8rem);
            max-width: calc(100vw - 8rem);
        }
    }

    /* Type-vs-pick convention (author feedback 2026-08-14). Every box carried
       the same pale-pink secondaryBackgroundColor, so a search line and the
       dropdown under it were indistinguishable and there was no landmark to
       scroll back to. Typed fields get a white fill and a maroon outline;
       dropdowns, radios and checkboxes keep the flat pink, untouched. Fill and
       outline are two separate cues, so this survives colour-blindness.

       Every input type needs the SAME two-part treatment: paint the fill and
       the outline on the outer rounded element, then force the inner ones
       transparent. Miss the second half and the inner <input> keeps painting
       Streamlit's pink straight over the white (which is what sent the
       Search foods box back to pink); do the second half with white instead
       of transparent and the square inner element clips the outer's rounded
       corners. stTextInputRootElement / stTextAreaRootElement are Streamlit's
       own handles for the outer element -- more precise than the BaseWeb
       attribute, which is kept alongside as a fallback.

       2px is the number to tune if the outline reads loud. */
    [data-testid="stTextInputRootElement"],
    [data-testid="stTextAreaRootElement"],
    [data-testid="stTextInput"] [data-baseweb="input"],
    [data-testid="stTextArea"] textarea {
        background-color: #ffffff !important;
        border: 2px solid #A4243A !important;
    }
    [data-testid="stTextInput"] [data-baseweb="base-input"],
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] [data-baseweb="base-input"] {
        background-color: transparent !important;
    }
    /* Number inputs are built differently and MUST be targeted by their
       container. Streamlit hands BaseWeb a Root override zeroing all four
       border-radii AND all four border widths, then puts the radius, the
       border and `overflow: hidden` on stNumberInputContainer instead. An
       earlier pass styled [data-baseweb="input"] here, which drew a square
       2px box inside a rounded clipping parent -- so every +/- box rendered
       with its corners visibly cut off while text inputs looked fine. The
       step buttons keep Streamlit's pale pink on purpose: white where you
       type, pink where you click is the same convention as the dropdowns. */
    [data-testid="stNumberInputContainer"] {
        background-color: #ffffff !important;
        border: 2px solid #A4243A !important;
    }
    /* Every nested wrapper, by attribute AND by structure. The pink sits on
       one of BaseWeb's inner divs and which one has moved between releases;
       naming only [data-baseweb="input"] left it painting over the white, so
       the Nutrition Targets tab -- which is nothing BUT number inputs -- still
       looked entirely pink. The step buttons are <button> elements, so these
       div selectors leave their pale pink alone, which is what we want. */
    [data-testid="stNumberInputContainer"] [data-baseweb="input"],
    [data-testid="stNumberInputContainer"] [data-baseweb="base-input"],
    [data-testid="stNumberInputContainer"] > div,
    [data-testid="stNumberInputContainer"] > div > div,
    [data-testid="stNumberInputField"] {
        background-color: transparent !important;
    }
    /* Streamlit signals keyboard focus by turning the border maroon -- now the
       resting state, so focus would be invisible. Restore it as a soft ring.
       The number input carries focus as a `.focused` class on its container
       as well as :focus-within, so match both. */
    [data-testid="stTextInputRootElement"]:focus-within,
    [data-testid="stTextAreaRootElement"]:focus-within,
    [data-testid="stTextArea"] textarea:focus,
    [data-testid="stNumberInputContainer"]:focus-within,
    [data-testid="stNumberInputContainer"].focused {
        box-shadow: 0 0 0 3px rgba(164, 36, 58, 0.25) !important;
    }

    /* Mobile tab strip (author feedback 2026-08-14). The desktop sizing above
       is deliberate and unchanged; below 640px those same 1.25rem bold labels
       are oversized for the screen. The strip still scrolls -- that is fine and
       the labels stay full length -- the text just should not shout. Tune the
       1rem. */
    @media (max-width: 640px) {
        button[role="tab"] p,
        button[data-testid="stTab"] p,
        button[data-baseweb="tab"] p {
            font-size: 1rem !important;
        }
        button[role="tab"],
        button[data-testid="stTab"],
        button[data-baseweb="tab"] {
            margin-right: 0.75rem;
        }
    }

    /* Tab scroll arrows: make them read as a control. Streamlit's own styling
       is a ~2rem button with a 60%-faded grey chevron over a gradient that
       only turns opaque 40% of the way across, so tab text bleeds under the
       arrow. Use the app's maroon, widen to a thumb-sized target, enlarge the
       chevron, and bring the gradient opaque at 25% so the icon always sits on
       solid ground. #fff is Streamlit's default light background -- no
       backgroundColor is set in .streamlit/config.toml, and the app already
       hardcodes light-theme colours elsewhere (see _note). */
    [data-testid="stTabsScrollLeft"],
    [data-testid="stTabsScrollRight"] {
        color: #A4243A !important;
        width: 2.75rem !important;
    }
    [data-testid="stTabsScrollLeft"] svg,
    [data-testid="stTabsScrollRight"] svg {
        width: 1.5rem !important;
        height: 1.5rem !important;
    }
    [data-testid="stTabsScrollRight"] {
        background-image: linear-gradient(to right, rgba(255, 255, 255, 0), #ffffff 25%) !important;
    }
    [data-testid="stTabsScrollLeft"] {
        background-image: linear-gradient(to left, rgba(255, 255, 255, 0), #ffffff 25%) !important;
    }

    /* Table toolbar: search, download CSV, fullscreen, column visibility
       (author feedback 2026-08-14). Streamlit ships these at opacity:0 and
       reveals them only on :hover -- which means that on a phone, where there
       is no hover at all, four useful controls are completely undiscoverable.
       Park them permanently at 55% and go solid on interaction.

       top is pinned to one value for both states because Streamlit animates
       it from -1rem to -2.65rem on hover; with the toolbar always visible
       that became a visible jump.

       These are two DIFFERENT quantities, not one knob -- setting them equal
       (the first attempt) left far too much white space above every table.
       `top` is fixed by the toolbar's own height, or it overlaps the table it
       sits above. `margin-top` only has to cover the SHORTFALL between that
       height and the gap Streamlit already leaves after a caption, so it is
       the smaller number. If the toolbar ends up touching the caption, raise
       margin-top in 0.2rem steps and leave top alone. */
    [data-testid="stElementToolbar"] {
        opacity: 0.55 !important;
        top: -1.7rem !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    [data-testid="stElementToolbar"]:hover,
    [data-testid="stElementToolbar"]:focus-within {
        opacity: 1 !important;
    }
    [data-testid="stDataFrame"] {
        margin-top: 0.5rem;
    }

    /* Zebra banding (Change 1.6, author request 2026-08-15): Excel-style
       alternating row tints for the two hand-built lists this app has --
       the Ingredients rows (Feed Recipes tab) and the "Everything given"
       intake list (Daily Intake Record tab, 19 rows on the example day).
       Neither is an actual <table>, so this is CSS over the
       st.container(key=...) -> .st-key-<key> hook already used for the
       full-bleed tables above, with the row id folded into the key so
       every row gets its own selector.

       Both classes get the SAME padding, so striped and unstriped rows
       stay aligned -- only zebrarow gets a fill colour. */
    [class*="st-key-zebrarow"],
    [class*="st-key-plainrow"] {
        padding: 0.35rem 0.5rem;
        border-radius: 0.35rem;
    }
    /* Pull the ingredient row's two lines together. Streamlit's default
       20px vertical gap between the name line and the amount/unit line
       left them reading as two separate things rather than one ingredient
       (author, 2026-08-15).

       The selector has NO descendant part on purpose: st.container()
       renders the keyed class ON the stVerticalBlock itself, so
       `.st-key-x [data-testid="stVerticalBlock"]` matches only the nested
       blocks inside the columns and leaves the 20px gap that actually
       separates the two lines untouched (measured, after that first
       attempt did nothing). */
    [class*="st-key-zebrarow_ingr"],
    [class*="st-key-plainrow_ingr"] {
        gap: 0.15rem;
    }
    [class*="st-key-zebrarow"] {
        /* #f8f9fb is not a new colour -- it's the grey Streamlit already
           paints behind the report tables' header rows (sampled off a
           rendered screenshot; body rows are #ffffff, grid lines #e4e5e8).
           Reusing it means the app has one grey doing all of its neutral
           work, in the hand-built lists and the tables alike.

           Grey, not pink, deliberately: in this app maroon and pale pink
           already carry meaning (maroon outline = "type here", pale pink
           = "pick from a list"). An Ingredients row already holds white
           outlined boxes and a pink unit dropdown -- a fourth pink tone
           behind them would put four shades of pink in one row and the
           band would compete with colour that means something. Grey sits
           outside that vocabulary and can only read as furniture.

           Deliberately subtle (about 3% off white -- 2-5% is the usual
           range for banding-as-furniture). If it disappears on the
           deploy, #f4f4f6 is the same idea a shade stronger. */
        background-color: #f8f9fb;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_state()


# Widget-key prefixes for keys that are scoped to a blend/ingredient/intake
# row id (e.g. "vol_{blend_id}", "grams_{ing_id}", "del_intake_{id}") or to
# one of the per-blend/per-row widget components ("blend_{id}_*" from the
# add-food UI, "oral_add_*" from its own instance of the same UI). These
# ids get reassigned when a day is loaded from a file -- blend ids come
# from the file, ingredient ids restart at 1 -- so they collide with keys
# the CURRENT session already holds for the SAME ids. _apply_saved_day()
# below pops all of them before writing the loaded day into session_state,
# so every such widget re-seeds from the loaded value instead of returning
# a stale one from before the load. MUST stay in sync with the widget
# `key=`/`key_prefix=` call sites -- add a prefix here whenever a new
# per-id (or per-component-instance) widget key is introduced.
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

    Replaces rather than merges. Opening a saved day means "go back to
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
    st.session_state["patient_weight_input"] = float(parsed.patient_weight or 0.0)
    st.session_state["weight_unit"] = (
        parsed.weight_unit if parsed.weight_unit in ("kg", "lbs") else "kg"
    )
    for _name in empty_targets():
        st.session_state[f"target_{_name}"] = float(parsed.targets.get(_name, 0.0))


_staged_day = st.session_state.pop("_apply_day", None)
if _staged_day is not None:
    _apply_saved_day(_staged_day)

# Load cached CNF data (runs once, then served from cache)
fn = get_food_name()
na = get_nutrient_amount()
lookup = get_measure_lookup()
fg = get_food_group()


@st.cache_resource(show_spinner=False)
def _food_search_index(group_code: int | None):
    """Pre-tokenised CNF descriptions for the food search box.

    Keyed by food group so the group filter narrows the *index*, not the
    results -- filtering afterwards would let 50 unfiltered hits crowd
    out the ones the RD asked for.

    `cache_resource` rather than `cache_data`: a SearchIndex holds a
    DataFrame plus ~6,000 frozensets and is only ever read, so there is
    nothing to gain from copying it per session. Building one costs
    ~16 ms; a search against it costs 3-10 ms, which is why this can run
    on every keystroke.
    """
    pool = fn if group_code is None else fn[fn["CNF_Food_Group_Code"] == group_code]
    return build_index(pool)


# ===========================================================================
# TOP BAR — onboarding row (demo, example), then patient/day label and
# "Open a saved day". No sidebar.
# ===========================================================================


# components.html, not st.video(): st.video handles YouTube URLs only, so
# a Vimeo one renders an empty player. The <style> line is load-bearing --
# without a real height on html/body the iframe's height:100% collapses to
# the browser default 300x150.
@st.dialog("How this works", width="medium")
def _show_demo_video() -> None:
    components.html(
        "<style>html,body{margin:0;height:100%;overflow:hidden}</style>"
        '<iframe src="https://player.vimeo.com/video/1216832087'
        '?badge=0&autopause=0&player_id=0&app_id=58479" '
        'style="width:100%;height:100%;border:0;display:block;" '
        'allow="autoplay; fullscreen; picture-in-picture" '
        'title="BTF Tool Demonstration"></iframe>',
        height=430,
    )
    # Fallback: a blocked iframe fails silently as an empty box.
    st.caption("Trouble playing? [Watch it on Vimeo](https://vimeo.com/1216832087) — 3 minutes.")


# Onboarding pair: both are for someone who has never seen the tool.
# "Open a saved day" stays top right as the returning-user action.
with st.container(horizontal=True):
    _demo_clicked = st.button("▶️ How this works — a 3-minute demo")
    load_example_clicked = st.button("📋 Load example day")
if _demo_clicked:
    _show_demo_video()

# vertical_alignment="bottom" aligns the popover with the text input
# exactly; the old st.write("") spacer only guessed at the label height.
top_l, top_r = st.columns([4, 1], vertical_alignment="bottom")
with top_r:
    with st.popover("📂 Open a saved day", width="stretch"):
        # In a popover so the top bar keeps its shape -- the UI is pinned
        # (CONTEXT.md §9), and a file uploader is a tall control.
        _day_file = st.file_uploader(
            "Open a saved day",
            type=["xlsx"],
            key="day_upload",
            label_visibility="collapsed",
            help="A day file saved from this app. Recipes load from the Feed Recipes tab.",
        )

if _day_file is not None and st.session_state.get("_last_day_upload") != _day_file.name:
    try:
        st.session_state["_pending_day"] = workbook_bytes_to_day(_day_file.getvalue())
    except DayFileError as _exc:
        _note(str(_exc))
    else:
        st.session_state["_last_day_upload"] = _day_file.name
        st.rerun()

# Confirm before replacing. Opening a saved day overwrites the blends,
# the intake record and the targets currently on screen, and an RD who
# has been working for ten minutes should get to say no.
_pending_day = st.session_state.get("_pending_day")
if _pending_day is not None:
    st.warning(
        f"**Open this saved day?** {_pending_day.summary}. "
        "This replaces the blends, intake record and targets currently on screen."
    )
    for _w in _pending_day.warnings:
        _note(_w)
    _dc1, _dc2, _dc3 = st.columns([1, 1, 3])
    if _dc1.button("Open it", key="day_open_confirm", width="stretch"):
        st.session_state["_apply_day"] = _pending_day
        st.session_state.pop("_pending_day", None)
        st.rerun()
    if _dc2.button("Cancel", key="day_open_cancel", width="stretch"):
        st.session_state.pop("_pending_day", None)
        st.session_state.pop("_last_day_upload", None)
        st.rerun()

# NOTE: the button-click handler below is deliberately placed BEFORE the
# "Patient / day label" text_input is instantiated (even though that input
# renders visually to the LEFT of the button -- `with top_l:`/`with top_r:`
# only control layout POSITION, not script execution order). This lets the
# handler preset st.session_state["recipe_name_input"] before that widget's
# key is ever created this run -- setting a keyed widget's session_state
# entry AFTER it has already been instantiated in the same script run
# raises StreamlitAPIException (the §11 widget-state gotcha); setting it
# before instantiation is exactly how a "Load example" button is supposed
# to preset a widget it doesn't itself own.
if load_example_clicked:
    # Synthetic case: James W, H&N RT wk 5, syringe bolus day. Real CNF
    # foods only -- see the ingredient table in the task/CONTEXT.md S9
    # 2026-07-23 entry for the sourcing rationale behind each pick
    # (COOKED variants preferred where the case calls for them; "Carrot,
    # boiled, drained" and "...with salt" both match the search substring,
    # so this relies on find_food()'s first-match convention resolving to
    # the unsalted row -- verified against CNF, not assumed).
    milk = find_food(fn, "Milk, fluid, whole, pasteurized, homogenized, 3.25% M.F.")
    yogurt = find_food(fn, "Yogourt (yogurt), Greek style, 2% M.F., plain")
    oats = find_food(fn, "Cereal, hot, oats (oatmeal), large flakes, prepared, Rogers")
    chicken = find_food(fn, "Chicken, broiler, breast, skinless, boneless, meat, braised")
    banana = find_food(fn, "Banana, raw")
    avocado = find_food(fn, "Avocado, raw, all commercial varieties")
    carrot = find_food(fn, "Carrot, boiled, drained")
    oil = find_food(fn, "Vegetable oil, canola")
    water = find_food(fn, "Water, municipal")
    # A SECOND blend, vegan, so the example demonstrates what one blend
    # cannot (author, 2026-08-15): that a day can hold several recipes,
    # that they can be compared against each other and against a
    # commercial formula, that "Save all N recipes" has something to
    # save, and that the Intake Record draws on whichever blend was
    # actually fed -- here the first, leaving this one on the shelf.
    soy = find_food(fn, "Plant-based beverage, soy beverage, all flavours, low fat, fortified")
    tofu = find_food(fn, "Tofu, regular, firm or extra firm")
    lentils = find_food(fn, "Lentils, mature seeds, boiled")
    peanut = find_food(fn, "Peanut butter, natural")
    spinach = find_food(fn, "Spinach, boiled, drained")
    _example_foods = [milk, yogurt, oats, chicken, banana, avocado, carrot, oil, water]
    _vegan_foods = [soy, tofu, lentils, peanut, spinach]
    if all(f is not None for f in _example_foods):
        # Drop any pre-existing empty starter blend(s) so the example
        # doesn't leave clutter alongside "Whole-food blend".
        st.session_state.blends = {
            bid: b for bid, b in st.session_state.blends.items() if b["ingredients"]
        }
        example_id = _new_blend("Whole-food blend")
        st.session_state.next_ingr_id += 9
        _base_id = st.session_state.next_ingr_id - 8

        # Descriptions come from CNF itself, not hand-written friendly
        # names (author, 2026-08-15). The example is meant to look like a
        # blend the RD built by searching, and searching yields CNF's own
        # wording -- "Cereal, hot, oats (oatmeal), large flakes, prepared,
        # Rogers", not "Rolled oats, cooked". Hand-written short names made
        # the example look like it came from somewhere other than the
        # database the app actually uses, and hid how long real CNF
        # descriptions get.
        def _cnf_name(code: int, fallback: str) -> str:
            _row = fn[fn["Food_Code"] == code]
            return str(_row.iloc[0]["Food_Description_EN"]) if len(_row) else fallback

        # Each row names the CNF household measure the RD would have
        # picked when searching, and its grams are that measure's own
        # weight -- so the example is a blend somebody actually built,
        # not one typed in grams (author, 2026-08-15). Weights come from
        # the lookup at runtime rather than being hard-coded, so they
        # cannot drift from CNF.
        #
        # Chicken deliberately has NO measure: CNF offers it only as
        # "1 piece" (181 g) and "1 food guide serving = 75g", neither of
        # which is the 50 g this case wants, so grams is what an RD would
        # really type. The example is more honest for showing both kinds
        # of row.
        def _measure_grams(code: int, label: str, fallback: float) -> float:
            _m = get_measures_for_food(code, lookup)
            _hit = _m[_m["Measure_Description_and_Unit_EN"] == label]
            return float(_hit.iloc[0]["grams"]) if len(_hit) else fallback

        # (code, fallback name, measure label or None, fallback grams, counts_as_fluid)
        _example_spec = [
            (milk, "Whole milk 3.25% M.F.", "250 ml", 257.0, True),
            (yogurt, "Greek yogurt, plain, 2%", "100 ml", 100.0, False),
            (oats, "Rolled oats, cooked", "100 ml", 100.0, False),
            (chicken, "Chicken breast, cooked (skinless)", None, 50.0, False),
            (banana, "Banana, raw", "1 small (15cm to 17.5cm long)", 100.0, False),
            (avocado, "Avocado, raw", "100 ml slices", 50.0, False),
            (carrot, "Carrots, cooked (boiled, drained)", "125 ml slices", 75.0, False),
            (oil, "Canola oil", "15 ml", 14.0, False),
            (water, "Water, municipal", "250 ml", 250.0, True),
        ]
        _example_ingredients = []
        for _offset, (_code, _fallback, _label, _fallback_g, _fluid) in enumerate(_example_spec):
            _grams = _measure_grams(_code, _label, _fallback_g) if _label else _fallback_g
            _example_ingredients.append(
                {
                    "id": _base_id + _offset,
                    "food_code": _code,
                    "food_description": _cnf_name(_code, _fallback),
                    "grams": _grams,
                    "unit": "g",
                    "counts_as_fluid": _fluid,
                    "measure_label": _label,
                    "measure_grams": _grams if _label else None,
                }
            )
        st.session_state.blends[example_id]["ingredients"] = _example_ingredients
        st.session_state.blends[example_id]["measured_volume_mL"] = 1000.0

        # --- Second blend: vegan, built the same way ---------------------
        # Deliberately NOT fed in the Intake Record below. A day usually
        # holds more recipes than were used, and seeing one blend sitting
        # unfed is how that reads on screen.
        if all(f is not None for f in _vegan_foods):
            vegan_id = _new_blend("Vegan blend")
            _vegan_spec = [
                (soy, "Soy beverage, fortified", "250 ml", 257.0, True),
                (tofu, "Tofu, firm", "125 ml", 133.0, False),
                (lentils, "Lentils, boiled", "125 ml", 105.0, False),
                (peanut, "Peanut butter, natural", "30 ml", 31.5, False),
                (banana, "Banana, raw", "1 medium (18cm to 20cm long)", 118.0, False),
                (spinach, "Spinach, boiled, drained", "125 ml", 95.0, False),
                (oil, "Canola oil", "15 ml", 14.0, False),
                (water, "Water, municipal", "250 ml", 250.0, True),
            ]
            _vegan_ingredients = []
            for _code, _fallback, _label, _fallback_g, _fluid in _vegan_spec:
                st.session_state.next_ingr_id += 1
                _grams = _measure_grams(_code, _label, _fallback_g)
                _vegan_ingredients.append(
                    {
                        "id": st.session_state.next_ingr_id,
                        "food_code": _code,
                        "food_description": _cnf_name(_code, _fallback),
                        "grams": _grams,
                        "unit": "g",
                        "counts_as_fluid": _fluid,
                        "measure_label": _label,
                        "measure_grams": _grams,
                    }
                )
            st.session_state.blends[vegan_id]["ingredients"] = _vegan_ingredients
            st.session_state.blends[vegan_id]["measured_volume_mL"] = 1000.0

            # _new_blend() selects whatever it just made, which would open
            # the example on the vegan blend. Land on the one the day
            # actually fed instead -- the Intake Record below is all
            # "Whole-food blend", so opening anywhere else reads as though
            # the numbers on screen belong to the recipe in front of you
            # when they do not.
            st.session_state.selected_blend_id = example_id
            st.session_state.pop("blend_selector", None)

        # Example Intake Record -- a full bolus day (design doc section
        # 3.2): the WHOLE "Whole-food blend" batch across 4 bolus feeds
        # (4 x 250 mL = 1000 mL, the full measured_volume_mL -- no
        # over-draw/batch-mismatch bookkeeping, just what was actually
        # given), 3 cartons of Resource 2.0 (237 mL each), 11 water-flush
        # rows (before/after several feeds + free-water sips) summing to
        # exactly 1032 mL so fluid lands at 507 (blend fluid ingredients)
        # + 711 (formula, full-volume I&O) + 1032 (flush) = 2250 mL, and
        # one oral CNF food via the real household-measure entry ("1
        # small" banana) for QOL -- spans every source_type.
        banana_measures = get_measures_for_food(banana, lookup)
        small = banana_measures[
            banana_measures["Measure_Description_and_Unit_EN"].str.contains(
                "small", case=False, na=False
            )
        ]
        banana_grams = float(small.iloc[0]["grams"]) if len(small) > 0 else 100.0
        # The real measure_label/measure_grams now carry "1 small" instead
        # of it being hand-glued onto food_description below (Change 3,
        # 2026-08-15) -- that glue is what broke the Excel export's " — "
        # split on this very row (see _intake_source_name()'s docstring).
        banana_measure_label = (
            str(small.iloc[0]["Measure_Description_and_Unit_EN"]) if len(small) > 0 else None
        )
        banana_measure_grams = banana_grams if len(small) > 0 else None

        _rows = [
            # Tube feed -- blend (full batch across 4 bolus feeds)
            {
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(12, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(17, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(21, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            # Tube feed -- Resource 2.0, 3 cartons
            {
                "time": dtime(10, 0),
                "source_type": "formula",
                "source_id": "Resource 2.0",
                "food_description": None,
                "amount": 237.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(14, 0),
                "source_type": "formula",
                "source_id": "Resource 2.0",
                "food_description": None,
                "amount": 237.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(20, 0),
                "source_type": "formula",
                "source_id": "Resource 2.0",
                "food_description": None,
                "amount": 237.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            # Tube feed -- water flushes: before/after several feeds + free-water sips
            {
                "time": dtime(7, 45),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(8, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(9, 0),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 244.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(10, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(12, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(14, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(15, 30),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 274.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(17, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(19, 0),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 274.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(20, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(21, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            # Food & drink -- oral, small banana for QOL
            {
                "time": dtime(8, 30),
                "source_type": "oral",
                "source_id": banana,
                "food_description": "Banana, raw",
                "amount": banana_grams,
                "unit": "g",
                "counts_as_fluid": False,
                "measure_label": banana_measure_label,
                "measure_grams": banana_measure_grams,
            },
        ]
        st.session_state.next_intake_id = len(_rows) + 1
        st.session_state.intake_log = [{"id": i + 1, **row} for i, row in enumerate(_rows)]
        st.session_state.custom_foods = {}
        st.session_state.next_custom_code = -1
        st.session_state["load_example"] = True

        # Presets set here, BEFORE the widgets they belong to are
        # instantiated further down in this same script run (the §11
        # widget-state gotcha: this is the one and only window in which
        # `st.session_state[key] = ...` for an already-existing widget key
        # is legal).
        #
        # These figures are spoken in the demo video -- keep them in step
        # with it. Other targets are zeroed because "Load example day"
        # warns that it replaces the targets on screen.
        st.session_state["patient_weight_input"] = 165.0
        st.session_state["weight_unit"] = "lbs"
        for _tname in empty_targets():
            st.session_state[f"target_{_tname}"] = 0.0
        st.session_state["target_energy_kcal"] = 2250.0
        st.session_state["target_protein_g"] = 100.0
        st.session_state["target_fluid_mL"] = 2250.0

        st.session_state["recipe_name_input"] = "Example — James W (H&N RT wk 5)"
        st.session_state["delivery_method_input"] = "BTF using 24Fr PEG tube via syringe bolus"
        st.rerun()
    else:
        st.error("Could not find example foods in CNF.")

with top_l:
    # Seed the default only the very first time this key ever exists,
    # rather than passing value= on every run -- passing BOTH a hardcoded
    # value= and relying on the Load Example handler's session_state
    # preset triggers Streamlit's (harmless but noisy) "created with a
    # default value but also had its value set via Session State" warning.
    if "recipe_name_input" not in st.session_state:
        st.session_state["recipe_name_input"] = "My BTF day"
    recipe_name = _narrow(1, 1).text_input("Patient / day label", key="recipe_name_input")

st.title(f"🥕🥦🥤 {recipe_name or 'BTF day'} 💉💧🍌")
st.caption(
    "⚠️ Under development. Estimates to inform clinical judgment, not to replace it. "
    "Check the numbers before you act on them."
)


# ===========================================================================
# Reusable Intake Record helpers — used by the Daily Intake Record tab's
# editor below and (once resolved) by that same tab's chart note.
# ===========================================================================

_FLUSH_LABEL = "Water flush"

# Above this many Intake Record rows, the row list starts collapsed so the
# day's totals stay near the top of the tab. Six is roughly a day that
# still fits on screen alongside its results: four feeds plus a couple of
# flushes. Tune this one number to change the behaviour.
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
    st.caption("Log a single food or drink the client had by mouth.")
    oral_time = _narrow(1, 4).time_input("Time (optional)", value=None, key="oral_time_input")
    new_food = render_add_food_ui(
        fn_df,
        na_df,
        lookup_df,
        fg_df,
        key_prefix="oral_add",
        add_button_label="Add",
        show_counts_as_fluid_toggle=True,
    )
    if new_food is not None:
        st.session_state.next_intake_id += 1
        st.session_state.intake_log.append(
            {
                "id": st.session_state.next_intake_id,
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


with recipes_tab:
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
    _blend_labels: dict[int, str] = {}
    for _bid in blend_ids:
        _widget_name = st.session_state.get(f"blend_name_{_bid}")
        _stored = st.session_state.blends[_bid]["name"]
        _blend_labels[_bid] = (_widget_name if _widget_name is not None else _stored) or (
            f"Blend {_bid}"
        )

    # Options are the BLEND IDS, not positions (author, 2026-08-01).
    #
    # This started as an index list, `range(len(blend_ids))`, which meant
    # that starting the app and pressing "Load example day" sent the
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
    # 2026-08-15) -- same fix as the "Open a saved day" popover above.
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

    if bsel2.button("➕ New blend", width="stretch"):
        _new_blend(_next_blend_label())
        st.rerun()
    if bsel3.button("🗑️ Delete blend", width="stretch", disabled=len(blend_ids) <= 1):
        removed_id = selected_blend_id
        del st.session_state.blends[removed_id]
        removed_rows = [
            r
            for r in st.session_state.intake_log
            if r["source_type"] == "blend" and r["source_id"] == removed_id
        ]
        st.session_state.intake_log = [
            r
            for r in st.session_state.intake_log
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
        fn,
        na,
        lookup,
        fg,
        key_prefix=f"blend_{selected_blend_id}",
        add_button_label="Add to blend",
    )
    if new_ingredient is not None:
        st.session_state.next_ingr_id += 1
        selected_blend["ingredients"].append(
            {
                "id": st.session_state.next_ingr_id,
                **new_ingredient,
            }
        )
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
        _note("Add ingredients above to get started.")
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
                "Beverages and mL-basis custom foods, always your call "
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
                    name_col, del_col = st.columns([11, 1])
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
                    name_col.write(f"{i + 1}\\. {ing['food_description']}")
                    if del_col.button("❌", key=f"del_{ing['id']}"):
                        selected_blend["ingredients"].pop(i)
                        st.rerun()

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

            # --- Recipe card (Change 1.3): the "hand it to a caregiver"
            # artefact, kept out of the edit rows above so neither job
            # clutters the other. Measure-first, grams in brackets
            # (author's choice); st.code so it gets Streamlit's own copy
            # button, the same idiom the Chart Note (Daily Intake Record
            # tab) already uses.
            _card_lines = [selected_blend["name"] or f"Blend {selected_blend_id}"]
            for ing in selected_blend["ingredients"]:
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
                st.code("\n".join(_card_lines), language=None)

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
            _units_by_food_code = {
                int(ing["food_code"]): ing.get("unit", "g")
                for ing in selected_blend["ingredients"]
                if ing.get("food_code") is not None
            }
            _breakdown = compute_ingredient_breakdown(_ingr_objs, na, st.session_state.custom_foods)
            _nutrition_display = format_ingredient_breakdown(
                _breakdown, units_by_food_code=_units_by_food_code
            )
            # Breaks out of the page cap so the nutrient columns can
            # spill sideways (the author's "spill over the way long
            # tables do") instead of truncating.
            with st.container(key="fullbleed_ingr_nutrition"):
                st.dataframe(
                    _nutrition_display,
                    # stretch + explicit pixel widths, same combination
                    # the Adequacy table uses (see fullbleed_adequacy
                    # above) -- width="content" was tried there and
                    # leaves the table narrow and unable to scroll.
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Ingredient": st.column_config.TextColumn(width=220),
                        "Amount": st.column_config.TextColumn(width=100),
                    },
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
        st.caption(
            "Documentation only — the tool can't measure viscosity or tube "
            "flow. This is the half of the sweet spot the app can't compute: "
            "it records what your syringe told you, and it belongs to this "
            "blend, so the chart note can say which recipe it refers to."
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


with record_tab:
    st.subheader("Intake Record")
    st.caption(
        "What was actually given — tube feed (blends, formulas, flushes) "
        "and food/drink by mouth, together in one chronological list."
    )

    # Delivery method: a single free-choice field for chart-note wording
    # only (FEED_LOG_REWORK.md section 3.4) — it no longer drives any math.
    # Seed the default only the very first time this key ever exists (see
    # the same comment by "recipe_name_input" above) -- avoids the
    # Session-State-vs-value= warning when Load Example presets this key.
    # Seeded EMPTY, not "Syringe bolus": the placeholder only shows in an
    # empty field, and a greyed example teaches the format without anyone
    # having to load the example day first. This line is the chart note's
    # opening line verbatim, so it needs to show the whole shape.
    if "delivery_method_input" not in st.session_state:
        st.session_state["delivery_method_input"] = ""
    delivery_method = _narrow(1, 1).text_input(
        "Delivery method (chart-note wording only)",
        placeholder="Eg: BTF using [feeding tube type, include tube diameter if known], "
        "via [feeding method]",
        help="Free text — this becomes the first line of the chart note. "
        "Doesn't affect any calculation; every row's own amount is what's summed.",
        key="delivery_method_input",
    )

    # Always-visible summary line — aggregated NUTRIENT totals, never a
    # raw volume/mass roll-up (750 mL of blend + 45 g of banana isn't a
    # meaningful single number). See FEED_LOG_REWORK.md section 3.4.
    _banner_totals = aggregate_intake(
        st.session_state.intake_log,
        st.session_state.blends,
        na,
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
            "Volume (mL)", min_value=0.0, value=0.0, step=10.0, format="%g", key="tf_amount_input"
        )
        if st.button("Add tube feed row", key="tf_add_btn"):
            if tf_amount > 0:
                tf_source_type, tf_source_id = _source_map[tf_source_label]
                st.session_state.next_intake_id += 1
                st.session_state.intake_log.append(
                    {
                        "id": st.session_state.next_intake_id,
                        "time": tf_time,
                        "source_type": tf_source_type,
                        "source_id": tf_source_id,
                        "food_description": None,
                        "amount": float(tf_amount),
                        "unit": "mL",
                        "counts_as_fluid": tf_source_type == "flush",
                    }
                )
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
            _flush_time = _sf1.time_input("Time (optional)", value=None, key="flush_single_time")
            _flush_total = _sf2.number_input(
                "Volume (mL)",
                min_value=0.0,
                value=0.0,
                step=10.0,
                format="%g",
                key="flush_single_amount",
            )
        elif _flush_mode == "With feeds (calculated)":
            _n_feeds = sum(
                1 for r in st.session_state.intake_log if r["source_type"] in ("blend", "formula")
            )
            _wf1, _wf2 = st.columns(2)
            _per_flush = _wf1.number_input(
                "mL per flush",
                min_value=0.0,
                value=60.0,
                step=10.0,
                format="%g",
                key="flush_per",
            )
            _per_feed = _wf2.number_input(
                "Flushes per feed",
                min_value=1,
                value=2,
                step=1,
                key="flush_per_feed",
            )
            _flush_total = _per_flush * _per_feed * _n_feeds
            _flush_label = "Water flushes with feeds"
            st.caption(
                f"{_n_feeds} tube feed(s) in the record × {_per_feed} flush(es) × "
                f"{_per_flush:.0f} mL = **{_flush_total:.0f} mL**"
            )
        else:
            _flush_total = _narrow(1, 3).number_input(
                "Med flushes (mL/day — a rough figure is fine)",
                min_value=0.0,
                value=100.0,
                step=10.0,
                format="%g",
                key="flush_med_amount",
            )
            _flush_label = "Med flushes"
        if st.button("Add flush row", key="flush_add_btn"):
            if _flush_total > 0:
                st.session_state.next_intake_id += 1
                st.session_state.intake_log.append(
                    {
                        "id": st.session_state.next_intake_id,
                        "time": _flush_time,
                        "source_type": "flush",
                        "source_id": None,
                        "food_description": _flush_label,
                        "amount": float(_flush_total),
                        "unit": "mL",
                        "counts_as_fluid": True,
                    }
                )
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

        def _render_intake_row(row: dict, index: int) -> None:
            # Banded rows (Change 1.6, author request 2026-08-15) -- same
            # .st-key-zebrarow/.plainrow CSS hook as the Ingredients list.
            # `index` is a running count across BOTH the Tube Feed and
            # Food & Drink groups below (not restarted per group), so the
            # stripe reads as one continuous 19-row list, matching the
            # "Everything given" framing above the expander.
            _band = "zebrarow" if index % 2 else "plainrow"
            with st.container(key=f"{_band}_intake_{row['id']}"):
                rc1, rc2 = st.columns([6, 1])
                rc1.write(_intake_row_label(row))
                if rc2.button("❌", key=f"del_intake_{row['id']}"):
                    st.session_state.intake_log = [
                        r for r in st.session_state.intake_log if r["id"] != row["id"]
                    ]
                    st.rerun()

        # Collapsed once the day gets long (author, 2026-08-01). A real
        # day is mostly flushes -- the example day is 19 rows, 11 of them
        # water and 8 of those an identical 30 mL -- and every row is a
        # full-width line with its own delete button. That pushed the
        # day's actual OUTPUT (per-source breakdown, adequacy, chart
        # note) roughly a screen and a half down the page, so the numbers
        # the RD came for sat below a wall of "30 mL flush".
        #
        # Collapsing, not paginating or summarising: the rows still have
        # to be individually deletable (grouping "8 x 30 mL" into one
        # line would take that away), and they are still ONE list under a
        # display grouping, exactly as before -- section 6.3 is untouched.
        # Short days stay open so a new user sees rows appear as they add
        # them; the collapse only kicks in once scrolling was going to be
        # the problem anyway.
        # Names the DISTINCT things given, with how many times each was
        # given -- not a row count per source_type (author, 2026-08-01).
        # The first version of this line read "4 blend feeds, 3 formulas"
        # for a day that had ONE blend given four times and ONE product
        # given three times. That reads as four different blends, which is
        # the kind of number an RD notices first and stops trusting the
        # rest of the page over.
        #
        # Flushes are named but NOT counted: eleven of them is noise in a
        # summary line, and "did I flush" is the question, not "how many
        # times". They're still individually listed and deletable inside.
        # Oral rows are counted as ONE category, not named individually
        # (author, 2026-08-01). A blend and a commercial feed are each a
        # thing you gave repeatedly, so naming them earns its space; the
        # food and drink side is "did they eat anything, how much", and
        # listing every banana crowds the line without answering it. The
        # category name matches the section header the rows sit under
        # inside, so the label and the list use one vocabulary.
        _n_rows = len(_ordered_rows)
        _times_given: dict[tuple, int] = {}
        _order: list[tuple] = []
        for _r in _ordered_rows:
            if _r["source_type"] in ("blend", "formula"):
                _key = (_r["source_type"], _r["source_id"])
                if _key not in _times_given:
                    _times_given[_key] = 0
                    _order.append(_key)
                _times_given[_key] += 1

        _parts: list[str] = []
        for _key in _order:
            _stype, _sid = _key
            if _stype == "blend":
                _nm = st.session_state.blends.get(_sid, {}).get("name") or f"Blend {_sid}"
            else:
                _nm = str(_sid)
            _n = _times_given[_key]
            _parts.append(f"{_nm} ×{_n}" if _n > 1 else _nm)

        # A day drawing on many feeds would otherwise run the label off
        # the edge of the expander.
        if len(_parts) > 3:
            _parts = _parts[:3] + [f"+{len(_parts) - 3} more"]

        if any(_r["source_type"] == "flush" for _r in _ordered_rows):
            _parts.append("water flushes")
        _n_oral = sum(1 for _r in _ordered_rows if _r["source_type"] == "oral")
        if _n_oral:
            _parts.append(f"{FOOD_DRINK_LABEL} ×{_n_oral}")

        _summary = f"📋 Everything given ({_n_rows} row{'' if _n_rows == 1 else 's'})"
        if _parts:
            _summary += " — " + ", ".join(_parts)

        with st.expander(_summary, expanded=_n_rows <= ROW_LIST_COLLAPSE_THRESHOLD):
            _row_idx = 0
            if _tube_rows:
                st.markdown(f"*{TUBE_FEED_LABEL}*")
                for _row in _tube_rows:
                    _render_intake_row(_row, _row_idx)
                    _row_idx += 1
            if _oral_rows:
                st.markdown(f"*{FOOD_DRINK_LABEL}*")
                for _row in _oral_rows:
                    _render_intake_row(_row, _row_idx)
                    _row_idx += 1


with recipes_tab:
    st.divider()

    # --- Per-blend density panel (EVERY blend, not just selected --
    # densities are still the per-blend lens, design doc section 3.5) ---
    st.subheader("Per-blend density panel")
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
        _n_full = sum(1 for n_sup, n_tot in _b_coverage.values() if n_tot == 0 or n_sup == n_tot)
        _density_rows.append(
            {
                "Blend": _blend["name"],
                "kcal/mL": round(_b_profile.kcal_per_mL, 2),
                "protein g/mL": round(_b_profile.protein_per_mL, 3),
                "Free-water fraction": round(_b_profile.free_water_fraction, 3),
                "Measured volume (mL)": round(_b_profile.measured_final_volume_mL),
                "Coverage": f"{_n_full}/{len(_b_coverage)} nutrients fully covered",
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
                generate_density_summary(selected_profile), width="content", hide_index=True
            )

with record_tab:
    st.divider()

    # --- Daily totals, adequacy, micro screen, per-kg, per-source
    # breakdown -- all computed from the Intake Record via
    # src.intake.aggregate_intake() (design doc section 3.5). ---
    intake_totals = aggregate_intake(
        st.session_state.intake_log,
        st.session_state.blends,
        na,
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
        with st.container(key="fullbleed_source_breakdown"):
            st.dataframe(generate_source_breakdown(intake_totals), width="stretch", hide_index=True)

        # --- Water ledger: every source on its own line (author, 2026-07-30) ---
        _water_ledger = generate_water_ledger(intake_totals.water_sources)
        if not _water_ledger.empty:
            st.subheader("Where the Water Came From")
            st.caption(
                "Free water is water that arrived as part of something fed — "
                "including tap water blended into a recipe, since in the recipe "
                "it *is* the recipe. Water flushes are water given as water, so "
                "they sit on their own and add on top."
            )
            st.dataframe(_water_ledger, width="content", hide_index=True)

        st.subheader("Daily Totals & Adequacy")
        st.caption(
            "A direct sum over the Intake Record (above) — never "
            "extrapolated from a batch volume against a schedule."
        )

        adequacy_df, hidden_main_names = generate_adequacy_report(
            intake_totals.nutrient_totals,
            targets,
            fluid_provided_mL=intake_totals.fluid_provided_mL,
            nutrient_coverage=intake_totals.nutrient_coverage,
            patient_weight_kg=patient_weight_kg if patient_weight_kg > 0 else None,
        )
        adequacy_display = adequacy_df.copy()
        adequacy_display["Target"] = adequacy_display["Target"].astype(str)
        adequacy_display["% Target"] = adequacy_display["% Target"].astype(str)
        # Mixed floats and "—" in one column, same convention as Target /
        # % Target above -- cast so Arrow isn't fixing a mixed-type column
        # on every render.
        if "Per kg" in adequacy_display.columns:
            adequacy_display["Per kg"] = adequacy_display["Per kg"].astype(str)
        # Provenance (Source / Coverage) moves to its own expander below
        # (author feedback 2026-08-14). Nine columns competed for width here
        # and the text ones lost -- Source in particular truncated on exactly
        # the rows whose provenance is least obvious. It is still one click
        # away, and generate_adequacy_report() still RETURNS all nine, so the
        # Excel export below is untouched.
        _PROVENANCE_COLS = ["Source", "Coverage"]
        _main_cols = [c for c in adequacy_display.columns if c not in _PROVENANCE_COLS]
        # Breaks out of the page cap: it is the table the RD reads most, so a
        # hidden column costs more here than anywhere else.
        with st.container(key="fullbleed_adequacy"):
            st.dataframe(
                adequacy_display[_main_cols].style
                # Daily Total / Target / % Target arrive from report.py
                # already formatted as text at each nutrient's own registry
                # precision (see _fmt there), which is what stops Energy's
                # 0 dp being dragged to "2204.0" by Protein's 1 dp sharing
                # the column. The Styler only colours Status now.
                .map(color_status, subset=["Status"]),
                # stretch + explicit pixel widths is the only combination
                # that both guarantees the long cells fit and still scrolls.
                # width="content" was tried and is wrong here: it leaves the
                # columns at their measured size without filling the
                # container, so the table renders narrow with dead space to
                # its right and can never scroll. The named buckets are no
                # help either -- small/medium/large are the raw pixel
                # constants 75/200/400, and medium clipped both columns.
                #
                # Sized for the longest value each column carries, both on
                # the free-water row: "Free water from foods and feeds" (31
                # chars) and "Informational — see Fluids provided" (35).
                # These are PIXELS and the cell font is rem-based, so if the
                # root font-size knob at the top of the style block ever
                # changes, bump these to match.
                width="stretch",
                hide_index=True,
                column_config={
                    "Nutrient": st.column_config.TextColumn(width=320),
                    "Status": st.column_config.TextColumn(width=360),
                },
            )
        st.caption(
            "Free water counts moisture from CNF foods plus formula-declared "
            "free water. Water flushes are counted under Fluids provided, not "
            "here. Foods entered from a label contribute none, because no "
            "label carries moisture."
        )
        with st.expander("Where these numbers came from"):
            st.dataframe(
                adequacy_display[["Nutrient", *_PROVENANCE_COLS]],
                # Widths measured off a rendered screenshot, not guessed:
                # Source's longest value ("Full volume of counts-as-fluid
                # ingredients (I&O convention) + flushes", 69 chars) draws
                # about 500px. An earlier 680 here overflowed the expander
                # and pushed the Coverage column out of view entirely, so
                # these are sized to leave Coverage its share.
                width="stretch",
                hide_index=True,
                column_config={
                    "Nutrient": st.column_config.TextColumn(width=270),
                    "Source": st.column_config.TextColumn(width=520),
                },
            )
        if hidden_main_names:
            st.caption("Not shown — no data from any ingredient: " + ", ".join(hidden_main_names))

        with st.expander("BTF micro screen — vitamins & minerals not on labels"):
            st.caption(
                'A one-time supplementation screen (ASPEN-style: "does this '
                "day's intake need a multivitamin?\"), not a daily-tracked panel "
                "like the table above."
            )
            clinical_df, hidden_clinical_names = generate_clinical_screen(
                intake_totals.nutrient_totals,
                targets,
                nutrient_coverage=intake_totals.nutrient_coverage,
            )
            if len(clinical_df) > 0:
                clinical_display = clinical_df.copy()
                clinical_display["Target"] = clinical_display["Target"].astype(str)
                clinical_display["% Target"] = clinical_display["% Target"].astype(str)
                st.dataframe(
                    clinical_display.style.map(color_status, subset=["Status"]),
                    width="stretch",
                    hide_index=True,
                )
            if hidden_clinical_names:
                st.caption(
                    "Not shown — no data from any ingredient: " + ", ".join(hidden_clinical_names)
                )

        # Per-kg used to be three st.metric tiles below this table (author,
        # 2026-08-01). Metrics are the app's loudest display element, which
        # gave kcal/kg, protein g/kg and fluid mL/kg more visual weight than
        # the adequacy table they were derived from. They are now a "Per kg"
        # column inside that table, between Unit and Target, so they read as
        # another way of looking at the same daily totals rather than a
        # separate, more important finding.

# At this many eligible blends OR MORE, the comparator's blend rows switch
# from "everyone automatically" to an explicit st.multiselect (defaulting to
# all of them) -- same idiom as the formula multiselect just below it.
# Nothing persists in this app (no accounts), so a session rarely holds many
# blends, and an always-on picker would be a control most users never need
# (author, you-know-the-line-vectorized-milner.md, 2026-08-15; confirmed as
# "at 4, not above 4" 2026-08-16).
COMPARATOR_BLEND_PICKER_THRESHOLD = 4

with recipes_tab:
    st.divider()

    # --- Dilution what-if (operates on the selected blend) ---
    st.subheader("Dilution What-If")
    st.caption(
        "**What would thinning this blend with water cost you?** Move the "
        "slider to see the density drop before you commit to anything.  \n"
        "This is a calculation, not a change: the blend above is untouched "
        "until you save the thinned version as its own blend, which you can "
        "do at the bottom of this section.  \n"
        "Thinning with broth, juice or milk isn't a dilution, it's a recipe "
        "change — add it as an ingredient instead, where every nutrient is "
        "counted rather than just calories and protein."
    )

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

            # Presets are non-nutritive by construction (see
            # _load_thinning_liquids), so kcal and protein are always 0
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
                st.dataframe(dil_df, width="content", hide_index=True)

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
                    _note(
                        "Couldn't find a plain water entry in CNF, so this can't "
                        "be saved automatically. Add the water as an ingredient "
                        "yourself and re-measure the volume."
                    )
                elif st.button(
                    f"➕ Save as a new blend with {added_mL:.0f} mL {liquid_type.lower()}",
                    key=f"dilute_commit_{selected_blend_id}",
                    width="stretch",
                    help="Your original blend is left untouched.",
                ):
                    _src_name = _src_label
                    # Name says WHAT it was thinned with, not just how much
                    # (author, 2026-08-01): "(thinned +150 mL)" left the RD
                    # to remember whether that was water, broth or juice --
                    # and a recipe name is exactly the place that shouldn't
                    # need remembering, since it is what the chart note, the
                    # blend selector and the saved file all carry.
                    _new_id = _new_blend(
                        f"{_src_name} (thinned with {added_mL:.0f} mL {liquid_type.lower()})"
                    )
                    _copy = st.session_state.blends[_new_id]
                    for _ing in selected_blend["ingredients"]:
                        st.session_state.next_ingr_id += 1
                        _copy["ingredients"].append({**_ing, "id": st.session_state.next_ingr_id})
                    st.session_state.next_ingr_id += 1
                    _copy["ingredients"].append(
                        {
                            "id": st.session_state.next_ingr_id,
                            "food_code": _water_code,
                            "food_description": f"{liquid_type} (added to thin)",
                            "grams": float(added_mL),
                            "unit": "mL",
                            "counts_as_fluid": True,
                            # A raw mL amount from the dilution slider, not
                            # a CNF household measure -- no label to carry.
                            "measure_label": None,
                            "measure_grams": None,
                        }
                    )
                    _copy["measured_volume_mL"] = _new_volume_mL
                    st.toast(
                        f'Created "{_copy["name"]}" and switched to it. Volume '
                        f"set to {_new_volume_mL:.0f} mL — re-measure if you blend "
                        "it again. Next: record its flow test."
                    )
                    st.rerun()
            else:
                st.caption(
                    "Move the slider to see what thinning would do to the "
                    "density. Nothing changes until you choose to save it."
                )

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
        "spreadsheet you keep. Re-open it here later, or edit it in Excel."
        if _n_savable != 1
        else "Save this blend — ingredients, measured volume and flow test — as a "
        "spreadsheet you keep. Re-open it here later, or edit it in Excel."
    )
    rr1, rr2 = st.columns(2)
    with rr1:
        st.download_button(
            "💾 Save recipe" if _n_savable <= 1 else f"💾 Save all {_n_savable} recipes",
            # Falls back to the selected blend purely so the disabled
            # button still has valid bytes to hold.
            data=(
                recipes_to_workbook_bytes(_savable)
                if _savable
                else recipe_to_workbook_bytes(selected_blend, _ft_state)
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
                    else f"One file containing all {_n_savable} blends that have ingredients."
                )
            ),
            width="stretch",
        )
    with rr2:
        # In a popover so this reads as a BUTTON beside "Save recipe"
        # rather than a tall drag-and-drop dropzone next to one (author,
        # 2026-08-15) -- the two sat side by side as different kinds of
        # control. Same idiom as "Open a saved day" at the top of the
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
            _note(str(exc))
        else:
            st.session_state["_pending_recipe"] = [
                (_p, resolve_ingredients(_p, fn)) for _p in _parsed_list
            ]
            st.session_state["_last_recipe_upload"] = _uploaded.name
            st.rerun()

    _pending = st.session_state.get("_pending_recipe")
    if _pending is not None:
        _confirm_recipe_import(_pending)

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
        _note("Add ingredients and a measured volume to the blend above " "to use the comparator.")
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
        st.caption(
            "Company narrows the list for scrolling — feeds you already "
            "picked stay selected when you switch companies."
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
            _other_blends.append((_cblend["name"], _cprofile))

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
            # Options are POSITIONS, not names, so the picker keeps working
            # even if two blends somehow share a name; format_func puts the
            # name back on screen.
            _kept = st.multiselect(
                "Also compare these blends",
                list(range(len(_other_blends))),
                default=list(range(len(_other_blends))),
                format_func=lambda i: _other_blends[i][0],
                key="comparator_blend_select",
            )
            _other_blends = [_other_blends[i] for i in _kept]

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
        st.dataframe(comparator_df, width="stretch", hide_index=True)
        # The marker is meaningless without this sentence, so the caption
        # is not decoration here -- it is the legend. "at the top of this
        # tab" rather than "above" because the comparator sits a long way
        # down, past Ingredients, the density panel, the Dilution What-If
        # and the Recipe Record, so "above" points at most of the page
        # (author, 2026-08-16).
        st.caption(
            f"{EDITING_MARKER} marks the blend being edited, chosen at the "
            "top of this tab. Rows are compared at one daily volume; "
            "differences between rows are in the feeds themselves and not "
            "in the amounts given."
        )

with record_tab:
    st.divider()

    # --- Chart note: the delivery-method line, then totals by category
    # (author, 2026-08-10). The chronological timeline it used to open
    # with is gone -- the Intake Record above IS that list, and repeating
    # it as prose made the note too long to paste into an EHR. ---
    st.subheader("Chart Note")
    st.caption("Copy-paste into your own chart. No patient-identifying fields.")

    if not st.session_state.intake_log:
        st.caption("Add Intake Record rows above to generate a chart note.")
    else:
        _ordered_note_rows = sorted_intake_log(st.session_state.intake_log)
        _tube_note_rows = [
            r for r in _ordered_note_rows if r["source_type"] in ("blend", "formula", "flush")
        ]
        _oral_note_rows = [r for r in _ordered_note_rows if r["source_type"] == "oral"]

        # --- The three summary lines, in the author's charting format
        # (2026-08-09): feed regimen, oral intake, total -- each one
        # Energy/Protein/CHO/Fat/Fluids in that order, and the feed line
        # showing its fluid split.
        #
        # "Fluids" is counted per line the way the clinic counts it, not
        # by one rule: feed = free water + flushes (so the bracket adds
        # up), oral = only rows ticked "counts as fluid", because nobody
        # charts the water in a banana. Total is the two added.
        _tube_sub = intake_totals.subtotals.get(TUBE_FEED_LABEL, {}).get("nutrient_totals", {})
        _oral_family = intake_totals.subtotals.get(FOOD_DRINK_LABEL, {})
        _oral_sub = _oral_family.get("nutrient_totals", {})
        _flush_mL = intake_totals.water_sources.get(WATER_FLUSH_LABEL, 0.0)

        def _macro_bits(totals: dict, fluid_mL: float) -> str:
            return (
                f"Energy {totals.get('energy_kcal', 0.0):.0f}kcal, "
                f"Protein {totals.get('protein_g', 0.0):.0f}g, "
                f"CHO {totals.get('carbohydrate_g', 0.0):.0f}g, "
                f"Fat {totals.get('fat_g', 0.0):.0f}g, "
                f"Fluids {fluid_mL:.0f}ml"
            )

        _tube_free_water = _tube_sub.get("water_g", 0.0)
        _tube_fluid = _tube_free_water + _flush_mL
        _oral_fluid = _oral_family.get("fluid_provided_mL", 0.0)

        # The delivery-method field is the opening line verbatim, so a
        # blank one drops the line rather than emitting a bare full stop.
        _water_split = (
            f" ({_tube_free_water:.0f}ml from free water "
            f"+ {_flush_mL:.0f}ml from water flushes)"
        )
        _total_line = "Total daily intake: " + _macro_bits(
            intake_totals.nutrient_totals, _tube_fluid + _oral_fluid
        )

        _summary_lines = []
        if delivery_method.strip():
            _summary_lines.append(delivery_method.strip().rstrip(".") + ".")
        if _tube_note_rows and _oral_note_rows:
            _summary_lines.append(
                "Feed regimen: " + _macro_bits(_tube_sub, _tube_fluid) + _water_split + "."
            )
            _summary_lines.append("Oral intake: " + _macro_bits(_oral_sub, _oral_fluid) + ".")
            _summary_lines.append(_total_line + ".")
        else:
            # One category only, so the category line and the total would
            # be the same numbers twice. Keep the total: every note then
            # ends on the same label whatever the day held, which is what
            # someone scanning back through a series of them looks for.
            # The water split rides along when there is tube feed to split.
            _summary_lines.append(_total_line + (_water_split if _tube_note_rows else "") + ".")

        # The flow-test line was dropped here too (author, 2026-08-10) --
        # it is still shown in the Feed Recipes tab and saved to the
        # workbook, it just isn't part of the pasted note.
        _note_text = "\n".join(_summary_lines)
        st.code(_note_text, language=None)

    # --- One file: the day you can reopen, and the report you can file ---
    #
    # This used to be two download buttons (author, 2026-08-01). The split
    # asked the RD to know, at download time, whether they were filing this
    # or coming back to it tomorrow -- and it is usually both. Worse, the
    # failure was asymmetric: saving only the report meant the day could
    # never be reloaded and the work was gone, while nobody is harmed by a
    # file carrying extra sheets. One file, both jobs.
    #
    # The per-blend "BTF <name>" sheets and the standalone "Flow Test"
    # sheet are gone with it, as duplicates rather than losses: the
    # reloadable half already carries every ingredient on the Ingredients
    # sheet (tagged with its blend, so Excel can sort or filter by recipe)
    # and every flow test as columns on the Blends sheet. Two views of the
    # same rows in one workbook is how they drift apart.
    st.subheader("Save this day")

    _report_sheets: dict[str, pd.DataFrame] = {}
    if st.session_state.intake_log:
        _report_sheets["Adequacy"] = generate_adequacy_report(
            intake_totals.nutrient_totals,
            targets,
            fluid_provided_mL=intake_totals.fluid_provided_mL,
            nutrient_coverage=intake_totals.nutrient_coverage,
            patient_weight_kg=patient_weight_kg if patient_weight_kg > 0 else None,
        )[0]
        _report_sheets["Micro Screen"] = generate_clinical_screen(
            intake_totals.nutrient_totals,
            targets,
            nutrient_coverage=intake_totals.nutrient_coverage,
        )[0]
        _report_sheets["Per-Source Breakdown"] = generate_source_breakdown(intake_totals)

    _wl = generate_water_ledger(intake_totals.water_sources)
    if not _wl.empty:
        _report_sheets["Water Sources"] = _wl
    if st.session_state.intake_log:
        _report_sheets["Chart Note"] = pd.DataFrame({"Chart note": [_note_text]})

    # Chronological, and each row tagged with the readable source name so
    # the Intake sheet is legible to a person as well as reloadable by the
    # app (day_io writes it to a "Source" column and ignores it on load).
    _intake_for_file = [
        {**row, "_source_name": _intake_source_name(row)}
        for row in sorted_intake_log(st.session_state.intake_log)
    ]

    st.download_button(
        label="💾 Download this day (.xlsx)",
        data=day_to_workbook_bytes(
            label=recipe_name,
            patient_weight=st.session_state.get("patient_weight_input", 0.0),
            weight_unit=st.session_state.get("weight_unit", "kg"),
            targets=targets,
            blends=st.session_state.blends,
            intake_log=_intake_for_file,
            custom_foods=st.session_state.custom_foods,
            delivery_method=delivery_method,
            extra_sheets=_report_sheets,
        ),
        file_name=suggested_day_filename(recipe_name),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="One spreadsheet that does both jobs: reopen it here later, or " "file it as it is.",
        width="stretch",
    )
    st.caption(
        "One file, two uses. Re-upload it with “Open a saved day” at the top "
        "of the page to carry on where you left off, or file it as it is — the "
        "first tabs hold what you entered (blends, ingredients, intake record, "
        "targets, custom foods) and the rest hold the worked-out numbers "
        "(adequacy, micro screen, per-source breakdown, water sources, chart "
        "note). It downloads to your computer, and it holds whatever you typed "
        "in the patient/day label."
    )


# --- Footer ---
#
# The second line is the one that matters now the app is public (author,
# 2026-08-01). The author is a registered dietitian, and a regulated
# professional publishing a clinical tool needs the "not YOUR dietitian"
# distinction stated where users actually are -- which is here, in the
# app, not only in the README that most of them will never open.
#
# The contact line (author, 2026-08-09) is here for that same reason --
# the README has a whole "Get in touch" section the app had no trace of.
# Deliberately NO email address: it is already public in the README, but
# a mailto in a footer on a public app is a scraper magnet, and both of
# these routes have a human gate in front of them.
#
# Contact sits AFTER "ask their own physician" on purpose: the limit is
# read before the invitation to write.
st.divider()
st.caption(
    "- ⚠️ **Under development.** A calculator for dietitians and the teams supporting "
    "blenderized tube feeding, and anyone is welcome to use it. It is built to inform "
    "clinical judgment, not to replace it. Please use with caution and check numbers "
    "before acting on them.\n"
    "- Using this tool creates no dietitian–client or other professional relationship, and "
    "it is no substitute for professional medical advice, diagnosis or treatment. For "
    "anything about a specific person's care, ask their own physician, registered "
    "dietitian or qualified health provider, and never delay that advice because of "
    "something calculated here.\n"
    "- Built on the Canadian Nutrient File (CNF) 2026.\n"
    "- Issues or feedback? Please [open an issue at GitHub]"
    "(https://github.com/greywhitebinary/blenderized-tubefeed-calculator/issues), or "
    "[find me on LinkedIn](https://www.linkedin.com/in/hui-jun-gail-chew/)."
)
