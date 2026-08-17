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
