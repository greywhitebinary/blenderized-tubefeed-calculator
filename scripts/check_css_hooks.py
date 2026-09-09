"""Every data-testid app/styles.css relies on still exists in Streamlit.

WHY THIS EXISTS
---------------
This repo pins streamlit exactly because app/styles.css reaches into
Streamlit's internal DOM, and those `data-testid` attributes carry no
stability guarantee. Streamlit Community Cloud once resolved a loose spec
against whatever was newest at deploy time, landed on 1.60.0, and silently
broke the tab-label CSS (CONTEXT.md §11, 2026-07-23). The pin exists to stop
that recurring.

Nothing in the test suite could have caught it. AppTest drives Streamlit's
*Python* API and never sees a stylesheet, so a renamed test id breaks the
page while all 284 tests stay green. That is exactly how the 1.60 breakage
got through, and it is the hole this script fills: it reads the selectors
the stylesheet actually depends on and asserts each one still appears in the
frontend bundle Streamlit ships.

It earns its keep twice. Against the pinned Streamlit it guards the status
quo, which is nearly free. Against the *latest* Streamlit -- which is what
.github/workflows/canary.yml runs it under -- it answers the question the
pin otherwise makes expensive to ask: is the next upgrade safe to attempt?

TWO LIMITS, DELIBERATE
----------------------
1. This catches a test id that was RENAMED or REMOVED. It does not catch a
   restructured DOM where the id survives but its nesting, order or
   defaulted styles change, which would break a descendant or sibling
   selector just as thoroughly. This is the cheap majority of the
   protection, not all of it. A green run means the hooks exist, not that
   the page looks right -- only opening it does that.

2. It checks `data-testid` only, NOT `data-baseweb`. styles.css uses
   `data-baseweb="input"` and `data-baseweb="base-input"`; those strings are
   short enough to occur somewhere in a 20 MB bundle by coincidence, so
   checking them would report confidence it had not actually established.
   A false PASS is worse here than no check, because it is the one people
   trust and stop thinking about.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import streamlit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STYLESHEET = PROJECT_ROOT / "app" / "styles.css"


def referenced_test_ids(stylesheet: Path) -> list[str]:
    """Every distinct data-testid the stylesheet selects on, in sorted order."""
    return sorted(set(re.findall(r'data-testid="([^"]+)"', stylesheet.read_text())))


def frontend_bundle_text() -> str:
    """Concatenate Streamlit's shipped JS so ids can be looked up in it.

    The static/ directory is the built frontend, so a test id that still
    exists appears here as a literal string. Read errors are ignored rather
    than raised: the bundle carries minified and occasionally non-UTF-8
    chunks, and one unreadable file should not fail a check about names.
    """
    static_dir = Path(streamlit.__file__).parent / "static"
    if not static_dir.is_dir():
        sys.exit(f"FAIL no Streamlit static/ directory at {static_dir}")
    return "".join(p.read_text(errors="ignore") for p in static_dir.rglob("*.js"))


def main() -> int:
    test_ids = referenced_test_ids(STYLESHEET)
    if not test_ids:
        # An empty list would otherwise pass vacuously, which is the same
        # failure mode the CI workflow guards against for scripts/check_*.py.
        print(f"FAIL no data-testid selectors found in {STYLESHEET} -- has it moved?")
        return 1

    bundle = frontend_bundle_text()
    missing = [test_id for test_id in test_ids if test_id not in bundle]

    print(f"Streamlit {streamlit.__version__}: checking {len(test_ids)} CSS hooks.")
    for test_id in test_ids:
        print(f"  {'ok     ' if test_id not in missing else 'MISSING'} {test_id}")

    if missing:
        print(
            f"\nFAIL {len(missing)} selector(s) no longer exist in Streamlit "
            f"{streamlit.__version__}: {', '.join(missing)}\n"
            "app/styles.css silently stops applying to these. Find what each "
            "element is called now and update the stylesheet, or hold the "
            "upgrade."
        )
        return 1

    print(f"\nOK all {len(test_ids)} CSS hooks present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
