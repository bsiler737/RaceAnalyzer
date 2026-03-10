"""RaceAnalyzer Streamlit application."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from raceanalyzer.config import Settings
from raceanalyzer.db.engine import get_session


def main():
    st.set_page_config(page_title="RaceAnalyzer", page_icon="\U0001f6b4", layout="wide")

    if "db_session" not in st.session_state:
        db_path = os.environ.get("RACEANALYZER_DB_PATH")
        if db_path:
            settings = Settings(db_path=Path(db_path))
        else:
            settings = Settings()
        st.session_state.db_session = get_session(settings.db_path)
        st.session_state.settings = settings

    calendar_page = st.Page(
        "pages/calendar.py", title="Race Calendar", icon="\U0001f4c5", default=True,
    )
    series_page = st.Page("pages/series_detail.py", title="Series Detail", icon="\U0001f3c6")
    detail_page = st.Page("pages/race_detail.py", title="Race Detail", icon="\U0001f3c1")
    preview_page = st.Page("pages/race_preview.py", title="Race Preview", icon="\U0001f52e")
    dashboard_page = st.Page("pages/dashboard.py", title="Finish Type Dashboard", icon="\U0001f4ca")

    pg = st.navigation([calendar_page, series_page, detail_page, preview_page, dashboard_page])
    pg.run()


if __name__ == "__main__":
    main()
