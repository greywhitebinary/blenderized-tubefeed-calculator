"""The Streamlit layer.

Everything here may import streamlit; nothing in src/ may (verified: no
`import streamlit` appears anywhere under src/). That boundary is what
makes src/ unit-testable and this package testable only through the
AppTest scripts in scripts/check_*.py -- so any logic that does not need
Streamlit belongs in src/, not here.

This file exists so `app` is a package and streamlit_app.py can do
`from app.add_food import render_add_food_ui`; the project root is put on
sys.path by streamlit_app.py before that import runs.
"""
