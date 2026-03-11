"""Series Detail page -- aggregated view across all editions of a race."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.charts import build_series_classification_chart
from raceanalyzer.ui.components import (
    render_confidence_badge,
    render_empty_state,
    render_terrain_badge,
)
from raceanalyzer.ui.maps import geocode_location, render_course_map, render_location_map


def render():
    session = st.session_state.db_session

    # Back navigation
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

    series_id = st.query_params.get("series_id")
    if not series_id:
        series_id = st.session_state.get("selected_series_id")
    if not series_id:
        render_empty_state("No series selected.")
        return

    detail = queries.get_series_detail(session, int(series_id))
    if detail is None:
        render_empty_state("Series not found.")
        return

    series = detail["series"]
    editions = detail["editions"]
    trend_df = detail["trend"]

    # --- Header: Overall badge + name ---
    st.title(series["display_name"])

    col1, col2, col3 = st.columns([3, 1, 1])
    overall_ft = detail["overall_finish_type"]
    display_name = queries.finish_type_display_name(overall_ft)
    tooltip = queries.FINISH_TYPE_TOOLTIPS.get(overall_ft, "")
    col1.markdown(
        f'**Overall Classification:** <span title="{tooltip}">'
        f'<strong>{display_name}</strong></span>',
        unsafe_allow_html=True,
    )
    ed_suffix = "s" if series["edition_count"] != 1 else ""
    col2.write(f"**{series['edition_count']} edition{ed_suffix}**")

    # Terrain badge (if course data exists)
    from raceanalyzer.db.models import Course
    course = (
        session.query(Course)
        .filter(Course.series_id == int(series_id))
        .first()
    )
    if course and course.course_type:
        with col1:
            render_terrain_badge(course.course_type.value)

    # Preview button
    with col3:
        if st.button("Race Preview"):
            st.query_params["series_id"] = str(series_id)
            st.switch_page("pages/race_preview.py")

    # --- Course map (prominent, near top) ---
    if series.get("encoded_polyline"):
        render_course_map(series["encoded_polyline"], series["display_name"])
    else:
        # Fallback to area map from most recent edition
        if editions:
            race = editions[0]["race"]
            location = race.get("location")
            state = race.get("state_province", "")
            if location and location != "Unknown":
                coords = geocode_location(location, state)
                if coords:
                    render_location_map(*coords)

    st.divider()

    # --- Classification trend chart ---
    if not trend_df.empty and trend_df["year"].nunique() >= 3:
        st.subheader("Classification Trends")
        fig = build_series_classification_chart(trend_df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    elif not trend_df.empty:
        # Fewer than 3 editions: show simple summary table
        st.subheader("Classification Summary")
        summary = (
            trend_df.groupby("finish_type")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        summary["finish_type"] = summary["finish_type"].map(queries.finish_type_display_name)
        st.dataframe(summary, hide_index=True, use_container_width=True)

    # --- Category selector ---
    categories = detail["categories"]
    if categories and not trend_df.empty:
        # Default to global category if set
        global_cat = st.session_state.get("global_category")
        default_idx = 0
        if global_cat and global_cat in categories:
            default_idx = categories.index(global_cat) + 1

        selected_cat = st.selectbox(
            "Filter by category:",
            options=[None] + categories,
            index=default_idx,
            format_func=lambda x: "All Categories" if x is None else x,
        )
        if selected_cat:
            cat_trend = trend_df[trend_df["category"] == selected_cat]
            if not cat_trend.empty:
                st.subheader(f"Classification Trend: {selected_cat}")
                fig = build_series_classification_chart(cat_trend)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption(f"No classification data for {selected_cat}.")

    st.divider()

    # --- Per-edition expandable sections ---
    st.subheader("Race Editions")
    for i, edition in enumerate(editions):
        race = edition["race"]
        date_str = f"{race['date']:%B %d, %Y}" if race.get("date") else "Unknown date"
        with st.expander(f"{race['name']} -- {date_str}", expanded=(i == 0)):
            # Classifications for this edition
            cls_df = edition["classifications"]
            if not cls_df.empty:
                for _, row in cls_df.iterrows():
                    cols = st.columns([2, 2, 1])
                    cols[0].write(f"**{row['category']}**")
                    ft_display = queries.finish_type_display_name(row["finish_type"])
                    cols[1].write(ft_display)
                    with cols[2]:
                        render_confidence_badge(
                            row["confidence_label"], row["confidence_color"]
                        )
            else:
                st.caption("No classification data for this edition.")

            # Link to full detail
            if st.button("View Full Detail", key=f"edition_{race['id']}"):
                st.session_state["selected_race_id"] = race["id"]
                st.session_state["back_to_series"] = series["id"]
                st.query_params["race_id"] = str(race["id"])
                st.switch_page("pages/race_detail.py")


render()
