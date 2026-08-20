"""The reusable "add a food" component (FEED_LOG_REWORK.md section 3.3).

The CNF-search-with-food-group-filter and the custom-food NFt-lookalike
form are the SAME UI whether the food is going into a blend's ingredient
list or becoming a single Intake Record oral row -- only the destination
differs. render_add_food_ui() has no opinion about the destination: it
renders the search/entry UI and returns a fully-specified food dict when
its Add button is clicked, letting the caller decide where the food goes.
This is the UI-layer version of the same "one source of truth for scaling
logic" discipline behind src/calculator.py's compute_nutrient_totals().

Split out of streamlit_app.py 2026-08-17. At 570 lines it was the largest
single thing in that file -- bigger than any module in src/ except
calculator.py -- and it already had a clean signature and two call sites.
The label-API rate-limit ledger and the food-search index came with it:
nothing else in the app used them.

Widget keys are all derived from `key_prefix`, which is what lets two
instances (a blend's ingredient list, the oral-intake dialog) coexist
without colliding. The move changed no key and no widget ordering.
"""

from datetime import date as ddate

import pandas as pd
import streamlit as st

from src.food_search import MIN_QUERY_LEN, build_index, search_foods
from src.intake import default_counts_as_fluid
from src.calculator import label_to_per_100g
from src.label_extract import (
    MAX_EXTRACTIONS_PER_DAY,
    MAX_EXTRACTIONS_PER_SESSION,
    LabelExtractionError,
    extract_label,
)
from src.measures import get_measures_for_food
from src.nutrients import DEFAULT_PACK, defs_for_tier, registry_by_name

from app.ui_common import _narrow, _note

# ---------------------------------------------------------------------------
# Label-photo extraction: rate limiting and the API client
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Food-search index
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _food_search_index(group_code: int | None, _fn_df: pd.DataFrame):
    """Pre-tokenised CNF descriptions for the food search box.

    Keyed by food group so the group filter narrows the *index*, not the
    results -- filtering afterwards would let 50 unfiltered hits crowd
    out the ones the RD asked for.

    `cache_resource` rather than `cache_data`: a SearchIndex holds a
    DataFrame plus ~6,000 frozensets and is only ever read, so there is
    nothing to gain from copying it per session. Building one costs
    ~16 ms; a search against it costs 3-10 ms, which is why this can run
    on every keystroke.

    `_fn_df` leads with an underscore so Streamlit excludes it from the
    cache key (it cannot hash a 5,993-row DataFrame cheaply). The key is
    therefore group_code alone -- exactly what it was when this lived in
    streamlit_app.py and read `fn` off the module.
    """
    pool = _fn_df if group_code is None else _fn_df[_fn_df["CNF_Food_Group_Code"] == group_code]
    return build_index(pool)


def food_search_index(fn_df):
    """The unfiltered (all food groups) search index, shared with the search box.

    Just `_food_search_index(None, fn_df)` under a public name -- it hits
    the SAME `cache_resource` entry the search box above already
    populates (group_code=None is "All"), so a caller outside this module
    (the recipe import, streamlit_app.py) gets it for free rather than
    building a second copy in memory (recipe_io.py Change, 2026-08-20).
    """
    return _food_search_index(None, fn_df)


def render_add_food_ui(
    fn_df: pd.DataFrame,
    na_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    fg_df: pd.DataFrame,
    key_prefix: str,
    add_button_label: str = "Add",
    show_counts_as_fluid_toggle: bool = False,
    existing_food_codes: dict[int, float] | None = None,
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

    existing_food_codes: {food_code: grams already present}. When the food
    about to be added is already in that mapping, a note says so before the
    Add button (author, 2026-08-16). It NEVER blocks or merges -- adding a
    food twice is legitimate, and the app deliberately keeps both rows (see
    group_ingredients_for_card() in src/measures.py, which collapses them
    on the recipe card only). This just means an accidental repeat is
    caught where it happens. Only the CNF branch can use it: a custom food
    from a label gets a fresh negative code every time, so there is nothing
    to match on. Left None by the oral-intake dialog, where eating the same
    food twice in a day is an ordinary entry rather than a possible slip.

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
            "Search foods from the 2026 Canadian Nutrient File (CNF)",
            "Enter a Canada Nutrition Facts label (custom food)",
        ],
        horizontal=True,
        key=f"{key_prefix}_add_mode",
    )

    result: dict | None = None

    # This string is the radio OPTION above and this COMPARISON: one pair.
    # Editing either alone silently disables the whole CNF search branch.
    #
    # It also carries the only on-screen expansion of "CNF", which four
    # other captions use bare (the recipe import, the counts-as-fluid note,
    # the water ledger, the Dilution What-If). Dropping the parenthetical
    # leaves those four undefined for a first-time reader.
    if (
        add_mode == "Search foods from the 2026 Canadian Nutrient File (CNF)"
    ):  # else: NFt label form
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
            _search = search_foods(search_term, _food_search_index(_group_code, fn_df), limit=50)
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
            _already_grams = (existing_food_codes or {}).get(food_code)
            if _already_grams:
                st.caption(
                    f"{food_desc} is already in this blend "
                    f"({_already_grams:.0f} g). Adding it again makes a second row."
                )
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
