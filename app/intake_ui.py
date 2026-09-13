"""Daily-record entry controls and calculation orchestration."""

from app.session_state import add_intake_row, remove_intake_row
import streamlit as st
from src.calculator import (
    COMMERCIAL_FORMULAS,
    MODULARS,
)
from src.day_io import (
    ROUTE_ORAL,
    ROUTE_TUBE,
)
from app.ui_common import _narrow, render_alert
from src.intake import (
    aggregate_intake,
    intake_row_family,
    resolve_blend_profile,
    sorted_intake_log,
    InvalidBlendError,
    TUBE_FEED_LABEL,
    FOOD_DRINK_LABEL,
)


from app.intake_helpers import (
    _queue_intake_toast,
    _intake_source_options,
    _intake_modular_options,
    _render_add_oral_ui,
    _intake_row_label,
    ROW_LIST_COLLAPSE_THRESHOLD,
)


def render_intake(fn, na, lookup, fg, _tubing_icon):
    _pending_toast = st.session_state.pop("_intake_toast", None)
    if _pending_toast:
        st.toast(_pending_toast, icon="✅")

    st.subheader("Intake Record")
    st.caption("Record tube feeds, water flushes, and food or drink by mouth, all in one place.")

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

    # A blend that an Intake Record row points at but that has no measured
    # volume USED TO CRASH THE WHOLE PAGE (fixed 2026-08-17): aggregate_intake()
    # resolves each referenced blend, resolve_blend_profile() raised
    # InvalidBlendError, and nothing caught it. Reachable in ordinary use --
    # load the example record and clear the volume.
    #
    # Checked up front, by name, rather than caught from the exception: the
    # RD needs to know WHICH blend to go and fix, and the exception message
    # is written for a developer.
    #
    # Totals are deliberately NOT shown while this is true. Skipping the
    # unusable rows and totalling the rest would silently understate the
    # day -- it would look like the patient received less than they did,
    # which is the failure mode this project treats as unacceptable.
    _unusable_blends = []
    for _bid in {
        r.get("source_id") for r in st.session_state.intake_log if r.get("source_type") == "blend"
    }:
        _b = st.session_state.blends.get(_bid)
        if _b is None:
            continue
        try:
            resolve_blend_profile(_b, na, st.session_state.custom_foods)
        except InvalidBlendError:
            _unusable_blends.append(_b["name"] or f"Blend {_bid}")

    # Fix (2026-08-20 review): a formula row can name a commercial formula
    # this app doesn't have in COMMERCIAL_FORMULAS -- a formulas.csv name
    # that changed, or a hand-edited day file. aggregate_intake()
    # (src/intake.py) resolves formula rows via `formulas.get(source_id)`
    # and silently `continue`s past a miss, so the row stays visible in the
    # Intake Record but contributes 0 kcal and 0 mL to every total below --
    # the same silent-undercount failure the no-volume check above already
    # guards against for blends, so it gets the same up-front, name-it,
    # block-the-totals treatment rather than let the RD read a total that
    # quietly dropped a feed they recorded.
    _unknown_formulas = sorted(
        {
            r.get("source_id")
            for r in st.session_state.intake_log
            if r.get("source_type") == "formula" and r.get("source_id") not in COMMERCIAL_FORMULAS
        }
    )

    if _unusable_blends or _unknown_formulas:
        intake_totals = None
        # Author's wording, 2026-08-17. It also happens to demonstrate the
        # house rule (MAINTAINING.md, "Writing copy for the app"): the two
        # facts are impersonal, and only the closing instruction addresses
        # the reader.
        #
        # Names are joined without a serial comma, matching the UK/Canadian
        # style the rest of the copy uses.
        if _unusable_blends:
            _quoted = [f'"{n}"' for n in sorted(_unusable_blends)]
            if len(_quoted) == 1:
                _names, _plural = _quoted[0], False
            else:
                _names, _plural = ", ".join(_quoted[:-1]) + " and " + _quoted[-1], True
            render_alert(
                "warning",
                f"The final volume{'s' if _plural else ''} for {_names} "
                f"{'are' if _plural else 'is'} missing. Without a measured final "
                "volume, the calculations required for the Intake Record below cannot "
                f"be completed. Add the volume{'s' if _plural else ''} on the Feed "
                "Recipes tab under Blend details.",
            )
        if _unknown_formulas:
            # Same construction as the no-volume warning just above, for
            # the same reason: named, impersonal, joined without a serial
            # comma, closing on the one instruction that addresses the
            # reader.
            _fquoted = [f'"{n}"' for n in _unknown_formulas]
            if len(_fquoted) == 1:
                _fnames, _fplural = _fquoted[0], False
            else:
                _fnames, _fplural = ", ".join(_fquoted[:-1]) + " and " + _fquoted[-1], True
            render_alert(
                "warning",
                f"The formula{'s' if _fplural else ''} {_fnames} in the Intake Record "
                f"{'are' if _fplural else 'is'} not recognised by this app, so "
                f"{'their' if _fplural else 'its'} amount cannot be included in the "
                "calculations required for the Intake Record below. Delete the row on "
                "the Daily Intake Record tab and re-add it from the formula list there.",
            )
    else:
        # Always-visible summary line — aggregated NUTRIENT totals, never a
        # raw volume/mass roll-up (750 mL of blend + 45 g of banana isn't a
        # meaningful single number). See FEED_LOG_REWORK.md section 3.4.
        #
        # Computed ONCE here and reused by the daily-totals section further
        # down this tab, which used to call aggregate_intake() a second time
        # with byte-identical arguments -- the whole day aggregated twice on
        # every rerun.
        intake_totals = aggregate_intake(
            st.session_state.intake_log,
            st.session_state.blends,
            na,
            custom_foods=st.session_state.custom_foods,
        )
        _b_kcal = intake_totals.nutrient_totals.get("energy_kcal", 0.0)
        _b_protein = intake_totals.nutrient_totals.get("protein_g", 0.0)
        _b_fluid = intake_totals.fluid_provided_mL
        st.markdown(
            f"**Today: ~{_b_kcal:.0f} kcal | {_b_protein:.0f} g protein | "
            f"{_b_fluid:.0f} mL fluid provided**"
        )

    # --- Add tube feed ---
    # The tubing drawing rather than 💉 (author, 2026-08-27), the same
    # asset and the same base64 data URI the page title uses. A syringe
    # is one way to give a tube feed; the ENFit tubing is the thing
    # itself. Streamlit renders an image in a label at the font's own
    # height, so it sits inline like the emoji it replaces.
    with st.expander(
        f"➕ ![Enteral tubing](data:image/svg+xml;base64,{_tubing_icon}) Add tube feed"
    ):
        tf1, tf2, tf3 = st.columns([1, 2, 1])
        tf_time = tf1.time_input("Time (optional)", value=None, key="tf_time_input")
        _source_options, _source_map = _intake_source_options()
        tf_source_label = tf2.selectbox("Source", _source_options, key="tf_source_select")
        tf_amount = tf3.number_input(
            "Volume (mL)", min_value=0.0, value=0.0, step=10.0, format="%g", key="tf_amount_input"
        )
        if st.button("Add to record below", key="tf_add_btn"):
            if tf_amount > 0:
                tf_source_type, tf_source_id = _source_map[tf_source_label]

                add_intake_row(
                    {
                        "time": tf_time,
                        "source_type": tf_source_type,
                        "source_id": tf_source_id,
                        "food_description": None,
                        "amount": float(tf_amount),
                        "unit": "mL",
                        "counts_as_fluid": tf_source_type == "flush",
                    }
                )
                _queue_intake_toast(f"{tf_source_label}, {tf_amount:.0f} mL")
                st.rerun()
            else:
                render_alert("warning", "Enter a volume greater than 0 mL.")

    # --- Add modulars: protein/fibre/calorie additives given down the
    # tube on their own (author's call, 2026-08-29). Sits between the
    # tube feed and the flushes because that is the order it happens in:
    # the modular is given, then flushed. Its own expander rather than
    # three more entries in the tube-feed Source dropdown because the
    # AMOUNT UNIT DIFFERS PER PRODUCT -- millilitres for a liquid
    # (HiFibre, ProSource NoCarb), grams for a powder (BeneProtein,
    # BanatrAll). A single number field that silently changes what it
    # counts is how someone types 30 meaning millilitres into a field
    # that has become grams.
    with st.expander("➕ 🫙 Add modulars"):
        _mod_options, _mod_map = _intake_modular_options()
        if not _mod_options:
            st.caption("No modulars in this data pack.")
        else:
            md1, md2, md3 = st.columns([1, 2, 1])
            md_time = md1.time_input("Time (optional)", value=None, key="md_time_input")
            md_label = md2.selectbox("Modular", _mod_options, key="md_source_select")
            md_name = _mod_map[md_label]
            md_basis = MODULARS[md_name]["basis"]
            md_amount = md3.number_input(
                f"Amount ({md_basis})",
                min_value=0.0,
                value=0.0,
                step=1.0 if md_basis == "g" else 5.0,
                format="%g",
                key="md_amount_input",
            )
            # The manufacturer's own wording, where the sheet gives it.
            # Shown rather than applied: the sheets disagree (60 mL a
            # scoop in hospital practice, 120 mL a packet on Banatrol's,
            # 30 mL on ProSource's), so the water actually used is
            # entered as a flush by the person who gave it.
            # One list holds both things tubed and things eaten, so the
            # row says which. Defaulting to the tube keeps the common
            # case one click shorter, and the wrong answer here moves a
            # number between the Tube Feed and Food & Drink totals rather
            # than changing what was given.
            md_route_label = st.radio(
                "How was it given?",
                ["Down the tube", "By mouth"],
                horizontal=True,
                key="md_route_radio",
            )
            md_route = ROUTE_TUBE if md_route_label == "Down the tube" else ROUTE_ORAL
            # No directions or explanatory notes here, deliberately
            # (author, 2026-08-29): a food in this app is a name and an
            # amount, and a modular is not special enough to be
            # different. The manufacturers' instructions live in the
            # archived sheets under data/packs/<pack>/formula_sources/.
            if st.button("Add to record below", key="md_add_btn"):
                if md_amount > 0:

                    add_intake_row(
                        {
                            "time": md_time,
                            "source_type": "modular",
                            "source_id": md_name,
                            "food_description": None,
                            "amount": float(md_amount),
                            "unit": md_basis,
                            "counts_as_fluid": md_basis == "mL",
                            "route": md_route,
                        }
                    )
                    _queue_intake_toast(
                        f"{md_name}, {md_amount:g} {md_basis} ({md_route_label.lower()})"
                    )
                    st.rerun()
                else:
                    render_alert("warning", f"Enter an amount greater than 0 {md_basis}.")

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
            ["Single flush", "With feeds (calculated)", "Med flushes (daily)"],
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
            # _narrow(1, 1), not (1, 3): at a quarter of the page this
            # label wrapped onto a second line. The label does not have to
            # fit the width of the input under it (author, 2026-08-21).
            _flush_total = _narrow(1, 1).number_input(
                "Med flushes (mL/day - an approximate figure is fine)",
                min_value=0.0,
                value=100.0,
                step=10.0,
                format="%g",
                key="flush_med_amount",
            )
            _flush_label = "Med flushes"
        if st.button("Add to record below", key="flush_add_btn"):
            if _flush_total > 0:

                add_intake_row(
                    {
                        "time": _flush_time,
                        "source_type": "flush",
                        "source_id": None,
                        "food_description": _flush_label,
                        "amount": float(_flush_total),
                        "unit": "mL",
                        "counts_as_fluid": True,
                    }
                )
                _queue_intake_toast(f"{_flush_label}, {_flush_total:.0f} mL")
                st.rerun()
            else:
                render_alert("warning", "The flush total is 0 mL — nothing to add.")

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
        # Asks src.intake for the rule rather than restating it: this
        # line used to list the tube source_types itself and silently
        # dropped modular rows out of both sections (2026-08-29).
        _tube_rows = [r for r in _ordered_rows if intake_row_family(r) == TUBE_FEED_LABEL]
        _oral_rows = [r for r in _ordered_rows if intake_row_family(r) == FOOD_DRINK_LABEL]

        def _render_intake_row(row: dict, index: int) -> None:
            # Banded rows (Change 1.6, author request 2026-08-15) -- same
            # .st-key-zebrarow/.plainrow CSS hook as the Ingredients list.
            # `index` is a running count across BOTH the Tube Feed and
            # Food & Drink groups below (not restarted per group), so the
            # stripe reads as one continuous 19-row list, matching the
            # "Everything given" framing above the expander.
            _band = "zebrarow" if index % 2 else "plainrow"
            with st.container(key=f"{_band}_intake_{row['id']}"):
                rc1, rc2 = st.columns([6, 1], vertical_alignment="center")
                rc1.write(_intake_row_label(row))
                if rc2.button("❌", key=f"del_intake_{row['id']}"):
                    remove_intake_row(row["id"])
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
            # Modulars are named alongside blends and feeds rather than
            # counted as a category: "BeneProtein x3" is the same kind of
            # fact as "Jevity 1.2 x3" -- a product given repeatedly, which
            # is what this line is for.
            if _r["source_type"] in ("blend", "formula", "modular"):
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

    st.divider()

    return intake_totals, delivery_method
