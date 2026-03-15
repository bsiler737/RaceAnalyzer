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

    # Sprint 018: Hide toolbar in production
    if os.environ.get("RACEANALYZER_PROD"):
        st.markdown(
            '<style>[data-testid="stToolbar"] { display: none; }'
            '[data-testid="stDecoration"] { display: none; }</style>',
            unsafe_allow_html=True,
        )

    # RWGPS-inspired light mode: warm gray background, white card surfaces
    st.markdown(
        """<style>
        /* Sidebar: darker warm gray */
        [data-testid="stSidebar"],
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            background-color: #e2ddd8 !important;
        }

        /* Popover and expander content: white */
        [data-testid="stPopoverBody"],
        [data-testid="stExpander"] {
            background-color: #ffffff !important;
        }

        /* Pill-style filter buttons: white background */
        [data-testid="stBaseButton-pills"] {
            background-color: #ffffff !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    # JS to set white bg on bordered containers (Streamlit strips <script>
    # from st.markdown, so use st.html which renders in an iframe that can
    # access the parent document)
    import streamlit.components.v1 as components
    components.html(
        """<script>
        function whiteCards() {
            const doc = window.parent.document;
            doc.querySelectorAll('[data-testid="stVerticalBlock"]').forEach(el => {
                if (window.parent.getComputedStyle(el).borderStyle !== 'none') {
                    el.style.backgroundColor = '#ffffff';
                    el.style.borderRadius = '8px';
                }
            });
        }
        // Run after Streamlit finishes rendering
        setTimeout(whiteCards, 500);
        setTimeout(whiteCards, 1500);
        setTimeout(whiteCards, 3000);
        new MutationObserver(whiteCards).observe(
            window.parent.document.body, {childList: true, subtree: true}
        );
        </script>""",
        height=0,
    )

    # Seed global session state from query params (Sprint 010)
    st.session_state.setdefault("global_category", st.query_params.get("category"))
    st.session_state.setdefault("search_query", st.query_params.get("q", ""))
    st.session_state.setdefault("feed_page_size", 20)

    feed_page = st.Page("pages/feed.py", title="Race Feed", icon="\U0001f3c1", default=True)
    calendar_page = st.Page("pages/calendar.py", title="Browse All", icon="\U0001f4c5")
    series_page = st.Page("pages/series_detail.py", title="Series Detail", icon="\U0001f3c6")
    detail_page = st.Page("pages/race_detail.py", title="Race Detail", icon="\U0001f3c1")
    preview_page = st.Page("pages/race_preview.py", title="Race Preview", icon="\U0001f52e")
    dashboard_page = st.Page("pages/dashboard.py", title="Finish Type Dashboard", icon="\U0001f4ca")

    all_pages = [
        feed_page, calendar_page, series_page, detail_page, preview_page, dashboard_page,
    ]

    # NS-01: Hide default nav, use custom breadcrumbs
    try:
        pg = st.navigation(all_pages, position="hidden")
    except TypeError:
        # Fallback if position="hidden" unsupported in this Streamlit version
        pg = st.navigation(all_pages)
        # Hide auto-generated nav entries via CSS
        st.markdown(
            '<style>[data-testid="stSidebarNav"] { display: none; }</style>',
            unsafe_allow_html=True,
        )

    # NS-02: Custom sidebar breadcrumbs
    st.sidebar.page_link(feed_page, label="Race Feed", icon="\U0001f3c1")
    if pg != feed_page:
        st.sidebar.page_link(pg, label=f"  \u21b3 {pg.title}")

    pg.run()


if __name__ == "__main__":
    main()
