"""Daily totals, chart note, and saved-day report rendering."""

from src.chart_note import build_chart_note
from html import escape
import pandas as pd
import streamlit as st
from src.day_io import (
    day_to_workbook_bytes,
    suggested_day_filename,
)
from app.copy_block import render_copy_block
from app.ui_common import _left_aligned, render_alert
from src.report import (
    generate_adequacy_report,
    generate_clinical_screen,
    generate_source_breakdown,
    generate_water_ledger,
    color_status,
    stripe_rows,
)
from src.intake import (
    sorted_intake_log,
)


from app.intake_helpers import _feeds_in_record, _intake_source_name


def render_intake_results(intake_totals, targets, patient_weight_kg, recipe_name, delivery_method):
    # --- Daily totals, adequacy, micro screen, per-kg, per-source
    # breakdown -- all computed from the Intake Record via
    # src.intake.aggregate_intake() (design doc section 3.5). ---
    #
    # `intake_totals` comes from the banner block above: computed once per
    # rerun, and None when a blend in the record has no measured volume
    # or the record names a formula this app doesn't know (2026-08-20)
    # (the warning there names it). Everything below needs real totals, so
    # it is all skipped in that case rather than shown half-filled.
    if intake_totals is None:
        pass
    elif not st.session_state.intake_log:
        render_alert("guidance", "Add rows to the Intake Record above to see daily totals.")
    else:
        # --- Per-source subtotal breakdown (design doc section 3.5) ---
        st.subheader("Per-Source Breakdown")
        with st.container(key="fullbleed_source_breakdown"):
            st.dataframe(
                stripe_rows(_source_breakdown := generate_source_breakdown(intake_totals)),
                width="stretch",
                hide_index=True,
                column_config=_left_aligned(_source_breakdown),
            )

        # --- Water ledger: every source on its own line (author, 2026-07-30) ---
        _water_ledger = generate_water_ledger(intake_totals.water_sources)
        if not _water_ledger.empty:
            st.subheader("Where the Water Came From")
            st.caption(
                "Free water is water contained within a feed, including water "
                "added to a blend recipe. Water flushes are entered separately "
                "and added to total fluids."
            )
            st.dataframe(
                stripe_rows(_water_ledger),
                width="content",
                hide_index=True,
                column_config=_left_aligned(_water_ledger),
            )

        st.subheader("Daily Totals & Adequacy")
        st.caption("The total fluid from everything entered in the Daily Intake Record above.")

        adequacy_df, hidden_main_names = generate_adequacy_report(
            intake_totals.nutrient_totals,
            targets,
            fluid_provided_mL=intake_totals.fluid_provided_mL,
            nutrient_coverage=intake_totals.nutrient_coverage,
            patient_weight_kg=patient_weight_kg if patient_weight_kg > 0 else None,
            feed_names=_feeds_in_record(),
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
                stripe_rows(adequacy_display[_main_cols])
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
                column_config=_left_aligned(
                    adequacy_display[_main_cols],
                    Nutrient=st.column_config.TextColumn(width=320, alignment="left"),
                    Status=st.column_config.TextColumn(width=360, alignment="left"),
                ),
            )
        st.caption(
            "Free water includes moisture from CNF foods and manufacturer-declared "
            "free water in formulas. Water flushes are included under Fluids "
            "provided instead. Foods entered from a nutrition label contribute no "
            "free water as nutrition labels do not report moisture."
        )
        with st.expander("Where these numbers came from"):
            st.dataframe(
                stripe_rows(adequacy_display[["Nutrient", *_PROVENANCE_COLS]]),
                # Widths measured off a rendered screenshot, not guessed:
                # Source's longest value ("Full volume of counts-as-fluid
                # ingredients (I&O convention) + flushes", 69 chars) draws
                # about 500px. An earlier 680 here overflowed the expander
                # and pushed the Coverage column out of view entirely, so
                # these are sized to leave Coverage its share.
                width="stretch",
                hide_index=True,
                column_config=_left_aligned(
                    adequacy_display[["Nutrient", *_PROVENANCE_COLS]],
                    Nutrient=st.column_config.TextColumn(width=270, alignment="left"),
                    Source=st.column_config.TextColumn(width=520, alignment="left"),
                ),
            )
        if hidden_main_names:
            st.caption("Not shown — no data from any ingredient: " + ", ".join(hidden_main_names))

        with st.expander("Vitamins and minerals not on the Nutrition Facts table"):
            clinical_df, hidden_clinical_names = generate_clinical_screen(
                intake_totals.nutrient_totals,
                targets,
                nutrient_coverage=intake_totals.nutrient_coverage,
                feed_names=_feeds_in_record(),
            )
            if len(clinical_df) > 0:
                # No Target / % Target / Status here, and so no status
                # colouring: none of these nutrients takes a target, so
                # generate_clinical_screen() drops those columns rather
                # than repeat an empty one 21 times (2026-08-21).
                st.dataframe(
                    stripe_rows(clinical_df),
                    width="stretch",
                    hide_index=True,
                    column_config=_left_aligned(clinical_df),
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

    st.divider()

    # --- Chart note: the delivery-method line, then totals by category
    # (author, 2026-08-10). The chronological timeline it used to open
    # with is gone -- the Intake Record above IS that list, and repeating
    # it as prose made the note too long to paste into an EHR. ---
    st.subheader("Chart Note")
    st.caption("Copy-paste into your own chart. No patient-identifying fields.")

    if intake_totals is None:
        # Says "something above", not "a blend has no measured volume":
        # totals are now also withheld when the record names a formula
        # this app doesn't know, and sending an RD to check a volume field
        # that is already filled in is worse than saying less. The warning
        # further up names the actual cause (2026-08-20 second review).
        st.caption(
            "The totals needed for this note cannot be calculated yet. See the "
            "warning above the Daily Intake Record for what is missing."
        )
    elif not st.session_state.intake_log:
        st.caption("Add Intake Record rows above to generate a chart note.")
    else:
        _note_text = build_chart_note(st.session_state.intake_log, intake_totals, delivery_method)
        _summary_lines = _note_text.split("\n")
        # render_copy_block, not st.code (2026-09-09). st.code gave this the
        # hover copy icon for free, which is elegant but names itself to
        # nobody -- and EN-Calc's chart note had a labelled button instead, so
        # the two tools disagreed about how you copy a note. copy_block.py is
        # shared between them; see its docstring.
        #
        # Stored in session state because AppTest has no accessor for a
        # Components v2 block the way it had at.code, and three scripts/
        # checks read this text. Same idiom EN-Calc already uses.
        st.session_state["_chart_note_generated_record"] = _note_text
        render_copy_block(
            "<br>".join(escape(line) for line in _summary_lines),
            block_id="btf_chart_note",
        )

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
    st.subheader("Save this record")

    # The report half needs totals; the RELOADABLE half never did. When a
    # blend has no measured volume the download therefore still works, just
    # without the worked-out sheets -- an RD must never be unable to save
    # their work because one number is missing (2026-08-17).
    _report_sheets: dict[str, pd.DataFrame] = {}
    if intake_totals is not None and st.session_state.intake_log:
        _report_sheets["Adequacy"] = generate_adequacy_report(
            intake_totals.nutrient_totals,
            targets,
            fluid_provided_mL=intake_totals.fluid_provided_mL,
            nutrient_coverage=intake_totals.nutrient_coverage,
            patient_weight_kg=patient_weight_kg if patient_weight_kg > 0 else None,
            feed_names=_feeds_in_record(),
        )[0]
        _report_sheets["Vitamins and Minerals"] = generate_clinical_screen(
            intake_totals.nutrient_totals,
            targets,
            nutrient_coverage=intake_totals.nutrient_coverage,
            feed_names=_feeds_in_record(),
        )[0]
        _report_sheets["Per-Source Breakdown"] = generate_source_breakdown(intake_totals)

    if intake_totals is not None:
        _wl = generate_water_ledger(intake_totals.water_sources)
        if not _wl.empty:
            _report_sheets["Water Sources"] = _wl
    # `_note_text` only exists when the Chart Note block above produced one,
    # which it can't without totals -- so this is guarded on intake_totals
    # too, not just on there being rows.
    if intake_totals is not None and st.session_state.intake_log:
        _report_sheets["Chart Note"] = pd.DataFrame({"Chart note": [_note_text]})

    # Chronological, and each row tagged with the readable source name so
    # the Intake sheet is legible to a person as well as reloadable by the
    # app (day_io writes it to a "Source" column and ignores it on load).
    _intake_for_file = [
        {**row, "_source_name": _intake_source_name(row)}
        for row in sorted_intake_log(st.session_state.intake_log)
    ]

    st.download_button(
        label="💾 Download this record",
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
        "Download this record to your computer as a spreadsheet. Reopen it "
        "later with “Open a saved record” at the top of the page, or file it "
        "as it is. The first worksheets hold what you entered (Record, "
        "Targets, Blends, Ingredients, Intake, Custom foods) and the rest hold "
        "the calculated reports: Adequacy, Vitamins and Minerals, Per-Source "
        "Breakdown, Water Sources and Chart Note. This record is not stored "
        "anywhere else; the file you download is the only copy."
    )
