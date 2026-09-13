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

from pathlib import Path
import sys
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_food_name, load_nutrient_amount, load_food_group
from src.measures import load_measure_lookup
from app.session_state import init_state, _apply_saved_day
from app.record_header import render_record_header
from app.targets_ui import render_targets
from app.recipes_ui import render_recipes
from app.intake_ui import render_intake
from app.intake_results import render_intake_results


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


st.set_page_config(
    page_title="BTF Calculator",
    page_icon="🥕",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def _stylesheet() -> str:
    """The app's stylesheet, read from app/styles.css.

    Lifted out of this module 2026-08-16: 313 lines of CSS inside a Python
    string got no syntax highlighting and its diffs read as Python. Cached
    so it is read from disk once per session rather than on every rerun.

    WHAT IT IS FOR. The maroon accent itself (selected-tab indicator,
    radios, sliders) comes from .streamlit/config.toml's primaryColor; this
    stylesheet handles what the theme can't -- label size, bold, spacing,
    and selected-label colour (author theming request 2026-07-20,
    Dietitians-of-Canada-style maroon). Tab labels as big as a subheading
    are the clearest example: Streamlit exposes no parameter for it, so it
    has to be injected. requirements.txt pins Streamlit exactly, and
    scripts/check_css_hooks.py checks the selectors against that build.

    Small widget-specific style blocks remain beside their components in
    add_food.py and record_header.py.
    """
    return (PROJECT_ROOT / "app" / "styles.css").read_text()


st.markdown(f"<style>{_stylesheet()}</style>", unsafe_allow_html=True)
init_state()
_staged_day = st.session_state.pop("_apply_day", None)
if _staged_day is not None:
    _apply_saved_day(_staged_day)

fn = get_food_name()
na = get_nutrient_amount()
lookup = get_measure_lookup()
fg = get_food_group()
recipe_name, tubing_icon = render_record_header(fn, lookup)

targets_tab, recipes_tab, record_tab = st.tabs(
    ["Nutrition targets", "Feed recipes", "Daily intake record"]
)
with targets_tab:
    targets, patient_weight_kg = render_targets()
with recipes_tab:
    render_recipes(fn, na, lookup, fg, targets)
with record_tab:
    intake_totals, delivery_method = render_intake(fn, na, lookup, fg, tubing_icon)
    render_intake_results(intake_totals, targets, patient_weight_kg, recipe_name, delivery_method)

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
#
# The publication is NOT named here. It was, briefly, but the footer is
# fourth of four blocks of boilerplate and the link was buried under three
# paragraphs of disclaimer; it now leads the page note instead (author,
# 2026-08-19). Naming it in both places put it twice on one page.
#
st.divider()
# Set smaller than the page note above it (author, 2026-08-19), giving
# three deliberate steps: body text, then the orientation note at
# 0.75rem, then this at 0.7rem. Boilerplate is conventionally set below
# body size, and this block is long -- four bullets, one of them a dense
# attribution paragraph. See st-key-pagefooter in app/styles.css.
with st.container(key="pagefooter"):
    st.caption(
        "- ⚠️ **Review calculations before clinical use.**\n"
        "- **Related tool:** [ENCalc](https://encalc.feedformflow.ca) — adult inpatient enteral nutrition calculator.\n"
        "- **Display tip:** Adjust Zoom in your browser menu, or use `Ctrl +/−` on Windows and `⌘ +/−` on Mac. You can also pinch on touchscreens and trackpads.\n"
        "- Issues or feedback? Please [open an issue at GitHub]"
        "(https://github.com/greywhitebinary/blenderized-tubefeed-calculator/issues), or "
        "[find me on LinkedIn](https://www.linkedin.com/in/hui-jun-gail-chew/).",
    )
    with st.expander("About this calculator", expanded=False):
        st.caption(
            "BTFCalc is designed for dietitians and teams supporting blenderized tube "
            "feeding. It supports, but does not replace, clinical judgement.\n\n"
            "This tool does not create a dietitian–client or other professional "
            "relationship and is not a substitute for professional medical advice, "
            "diagnosis, or treatment. For advice about an individual's care, consult "
            "their physician, registered dietitian, or other qualified health "
            "professional. Do not delay seeking that advice because of a result from "
            "this calculator.\n\n"
            "Food values come from the Canadian Nutrient File, Health Canada, 2026, "
            "used under Health Canada's copyright guidelines. This is not an official "
            "version and is not affiliated with or endorsed by Health Canada. "
            "Commercial formula values come from manufacturers' Canadian product "
            "information."
        )
