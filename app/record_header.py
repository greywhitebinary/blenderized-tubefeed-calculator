"""Example controls, saved-day upload, and record heading."""

from base64 import b64encode
from html import escape
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from src.day_io import (
    DayFileError,
    workbook_bytes_to_day,
)
from app.ui_common import _narrow, render_alert


from app.example_record import load_example_record

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
# "Open a saved record" stays top right as the returning-user action.
def render_record_header(fn, lookup):
    with st.container(horizontal=True):
        _demo_clicked = st.button("▶️ How this works — a 3-minute demo")
        load_example_clicked = st.button("📋 Load example record")
    if _demo_clicked:
        _show_demo_video()

    # vertical_alignment="bottom" aligns the popover with the text input
    # exactly; the old st.write("") spacer only guessed at the label height.
    #
    # 3:1, not 4:1 (author, 2026-08-16): at a fifth of the page the popover
    # label wrapped onto two lines, and "Open a saved record" is a word longer
    # than the "day" version it replaced. The label field on the left keeps
    # three quarters, which is still far more than a patient label needs.
    top_l, top_r = st.columns([3, 1], vertical_alignment="bottom")
    with top_r:
        with st.popover("📂 Open a saved record", width="stretch"):
            # In a popover so the top bar keeps its shape -- the UI is pinned
            # (CONTEXT.md §9), and a file uploader is a tall control.
            _day_file = st.file_uploader(
                "Open a saved record",
                type=["xlsx"],
                key="day_upload",
                label_visibility="collapsed",
                help="A record saved from this app. Recipes load from the Feed Recipes tab.",
            )

    if _day_file is not None and st.session_state.get("_last_day_upload") != _day_file.name:
        try:
            st.session_state["_pending_day"] = workbook_bytes_to_day(_day_file.getvalue())
        except DayFileError as _exc:
            render_alert("guidance", str(_exc))
        else:
            st.session_state["_last_day_upload"] = _day_file.name
            st.rerun()

    # Confirm before replacing. Opening a saved record overwrites the blends,
    # the intake record and the targets currently on screen, and an RD who
    # has been working for ten minutes should get to say no.
    _pending_day = st.session_state.get("_pending_day")
    if _pending_day is not None:
        render_alert(
            "warning",
            f"**Open this saved record?** {_pending_day.summary}. "
            "This replaces the blends, intake record and targets currently on screen.",
        )
        for _w in _pending_day.warnings:
            render_alert("guidance", _w)
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
    # "Patient / record label" text_input is instantiated (even though that input
    # renders visually to the LEFT of the button -- `with top_l:`/`with top_r:`
    # only control layout POSITION, not script execution order). This lets the
    # handler preset st.session_state["recipe_name_input"] before that widget's
    # key is ever created this run -- setting a keyed widget's session_state
    # entry AFTER it has already been instantiated in the same script run
    # raises StreamlitAPIException (the §11 widget-state gotcha); setting it
    # before instantiation is exactly how a "Load example" button is supposed
    # to preset a widget it doesn't itself own.
    if load_example_clicked:
        load_example_record(fn, lookup)

    with top_l:
        # Seed the default only the very first time this key ever exists,
        # rather than passing value= on every run -- passing BOTH a hardcoded
        # value= and relying on the Load Example handler's session_state
        # preset triggers Streamlit's (harmless but noisy) "created with a
        # default value but also had its value set via Session State" warning.
        if "recipe_name_input" not in st.session_state:
            st.session_state["recipe_name_input"] = "My BTF record"
        recipe_name = _narrow(2, 1).text_input("Patient / record label", key="recipe_name_input")

    _tubing_icon = b64encode(
        (PROJECT_ROOT / "assets" / "enteral-enfit-tubing.svg").read_bytes()
    ).decode("ascii")
    _record_title = escape(recipe_name or "BTF record")
    st.markdown(
        f'<h1 class="record-title"><span>🥕🥦🥤</span><span>{_record_title}</span><img '
        f'src="data:image/svg+xml;base64,{_tubing_icon}" alt="Enteral tubing with purple ENFit connectors">'
        # 🫙 sits immediately after the tubing, the same order as the Intake
        # Record's sections: the tube feed, then the modulars beside it.
        "<span>🫙💧🍌</span></h1>",
        unsafe_allow_html=True,
    )
    # This compact note identifies the calculator, the Feed. Form. Flow. project,
    # and its Canadian data scope before giving the workflow. Detailed sources and
    # clinical-use information remain in the footer's About section.
    with st.container(key="pagenote"):
        st.caption(
            "Blenderized Tube Feeding Calculator, a [Feed. Form. Flow.]"
            "(https://feedformflow.substack.com/p/feed-form-flow) project. "
            "Uses Canadian food and commercial product information.  \n"
            "Work left to right: set optional targets, build or select a blend, "
            "then record the daily intake and review the totals."
        )

    return recipe_name, _tubing_icon
