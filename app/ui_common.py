"""Small shared UI primitives.

Split out of streamlit_app.py 2026-08-17 so app/add_food.py can use them
without importing the whole app module back (which would be circular).
Both are presentation-only: they render, they decide nothing.
"""

from html import escape

import streamlit as st


def render_alert(kind: str, message: str, *, allow_html: bool = False) -> None:
    """Render a call-out box in the workspace palette.

    Shared with EN-Calc, which carries the same function and the same
    .app-alert CSS, so a warning looks the same in both calculators.

    Streamlit's own alerts carry a cool, saturated palette that belongs to no
    other part of this page, and their kinds are told apart only by generated
    class names, so they cannot be restyled from a stylesheet with any
    confidence that the selector will survive an upgrade. This renders the
    same thing in the project's own markup instead, which is how every other
    styled block here is built.

    `kind` is one of warning, error, success, info or guidance. Guidance is
    the empty-state "nothing here yet" box this app used to draw with
    _note(), and it keeps that function's maroon rather than the info blue --
    a recorded decision from 2026-07-20.

    `role` follows the same rule Streamlit uses: a problem or a caution
    interrupts a screen reader, while a confirmation does not.

    The message is ESCAPED unless `allow_html` says otherwise. _note() never
    escaped, and several of its callers passed str(exc) or CNF-derived text
    straight into a div, so a food name containing "<" could break the box.
    Pass allow_html=True only for markup this module's own callers build --
    never for anything that came from a file, a widget or an exception.
    """
    role = "alert" if kind in {"error", "warning"} else "status"
    body = message if allow_html else escape(message)
    st.markdown(
        f'<div class="app-alert app-alert--{escape(kind)}" role="{role}">{body}</div>',
        unsafe_allow_html=True,
    )


def _narrow(left: int = 1, right: int = 2):
    """Column pair with an empty spacer -- keeps a short field from running
    the full page width. Streamlit stacks columns on a narrow viewport, so
    on a phone the field goes back to full width by itself."""
    col, _spacer = st.columns([left, right])
    return col


def _left_aligned(frame, **overrides):
    """Column config that left-aligns every column of `frame`.

    Streamlit aligns a column by its DTYPE -- numbers right, text left --
    so alignment across this app's ten tables followed how each one
    happened to be built rather than anything a reader could see. Five
    read as all-left only because src/report.py formats their numbers as
    text; the three that kept real numbers had a right-aligned column or
    six sitting among left-aligned ones (author, 2026-08-27: "I don't
    care what it is as long as it's consistent").

    `overrides` carries the per-column settings a caller already had --
    widths, mostly. Those come through unchanged, so a caller that sets a
    width keeps it; it just has to set its own alignment too, since a
    column named in overrides replaces the default entry entirely.
    """
    config = {column: st.column_config.Column(alignment="left") for column in frame.columns}
    config.update(overrides)
    return config
