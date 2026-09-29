"""AppTest check for the links to the other tabs at the bottom of each tab.

Added 2026-09-28, matching ENCalc. Asserts that every tab ends with a
link to each of the other two tabs and none to itself, that each link
opens its tab, and that the links still work after loading the example
record (the record tab is the long one they exist for).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from app.tab_navigation import WORKSPACE_TABS, WORKSPACE_TAB_KEY, _tab_key  # noqa: E402

APP = str(ROOT / "app" / "streamlit_app.py")


def nav_button(at, from_tab, to_tab):
    key = f"workspace_nav_{_tab_key(from_tab)}_{_tab_key(to_tab)}"
    matches = [b for b in at.button if b.key == key]
    assert len(matches) == 1, f"expected one link {key}, found {len(matches)}"
    return matches[0]


at = AppTest.from_file(APP, default_timeout=180)
at.run()
assert not at.exception, at.exception
assert [t.label for t in at.tabs] == list(WORKSPACE_TABS)

nav_keys = {b.key for b in at.button if (b.key or "").startswith("workspace_nav_")}
assert len(nav_keys) == len(WORKSPACE_TABS) * (len(WORKSPACE_TABS) - 1), sorted(nav_keys)
for tab in WORKSPACE_TABS:
    own = f"workspace_nav_{_tab_key(tab)}_{_tab_key(tab)}"
    assert own not in nav_keys, f"{tab} links to itself"
print(f"OK: {len(nav_keys)} bottom links, none to its own tab")

for from_tab in WORKSPACE_TABS:
    for to_tab in WORKSPACE_TABS:
        if to_tab == from_tab:
            continue
        nav_button(at, from_tab, to_tab).click().run()
        assert not at.exception, at.exception
        assert at.session_state[WORKSPACE_TAB_KEY] == to_tab, (
            from_tab,
            to_tab,
            at.session_state[WORKSPACE_TAB_KEY],
        )
print("OK: every bottom link opens its tab")

next(b for b in at.button if "example" in b.label.lower()).click().run()
assert not at.exception, at.exception
nav_button(at, "Daily intake record", "Nutrition targets").click().run()
assert at.session_state[WORKSPACE_TAB_KEY] == "Nutrition targets"
print("OK: links still work with the example record loaded")
