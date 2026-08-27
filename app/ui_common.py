"""Small shared UI primitives.

Split out of streamlit_app.py 2026-08-17 so app/add_food.py can use them
without importing the whole app module back (which would be circular).
Both are presentation-only: they render, they decide nothing.
"""

import streamlit as st


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
    st.write("")


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
