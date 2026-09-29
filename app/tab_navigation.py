"""Links to the other tabs at the bottom of each tab.

The same pattern as ENCalc's render_workspace_navigation() (author,
2026-09-28): a long tab ends with the other tab names, so the reader does
not have to scroll back to the strip at the top to move on. The names come
from WORKSPACE_TABS, the one list the tab strip is also built from, so the
two cannot drift apart.
"""

import re

import streamlit as st

WORKSPACE_TABS = ("Nutrition targets", "Feed recipes", "Daily intake record")

# Session-state key of the tab strip. Setting it before the strip is drawn
# opens that tab, which is how the bottom links work.
WORKSPACE_TAB_KEY = "workspace_tab"


def _open_workspace_tab(tab_label: str) -> None:
    """Open a tab from the bottom links. Runs as a button callback, so
    before the tab strip is drawn on the next run."""
    st.session_state[WORKSPACE_TAB_KEY] = tab_label


def _tab_key(tab_label: str) -> str:
    """Slug for widget keys, which Streamlit also emits as a CSS class."""
    return "_".join(part for part in re.split(r"[^a-z0-9]+", tab_label.lower()) if part)


def render_workspace_navigation(active_tab: str) -> None:
    """The other tabs as links, in tab-strip order, below a thin rule."""
    active_key = _tab_key(active_tab)
    with st.container(key=f"workspace_navigation_{active_key}"):
        columns = st.columns(len(WORKSPACE_TABS))
        for position, tab_label in enumerate(WORKSPACE_TABS):
            if tab_label == active_tab:
                continue
            columns[position].button(
                tab_label,
                type="tertiary",
                key=f"workspace_nav_{active_key}_{_tab_key(tab_label)}",
                on_click=_open_workspace_tab,
                args=(tab_label,),
            )
