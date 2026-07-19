#!/bin/bash
# Double-click this file in Finder to start the BTF Calculator locally.
# No Terminal typing needed -- this does the same thing as running
# `.venv/bin/streamlit run app/streamlit_app.py` from the project folder.
#
# It opens a Terminal window (Streamlit needs one to run in) and starts
# the app; your browser opens automatically to http://localhost:8501.
# To stop the app, go back to that Terminal window and press Ctrl+C.

cd "$(dirname "$0")"
echo "Starting BTF Calculator..."
echo "(Leave this window open while using the app. Press Ctrl+C here to stop it.)"
echo
.venv/bin/streamlit run app/streamlit_app.py
