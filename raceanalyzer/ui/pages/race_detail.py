"""Race Detail page -- per-category classifications and results for a single race."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.db.models import Race, RaceSeries
from raceanalyzer.ui.charts import build_group_structure_chart
from raceanalyzer.ui.components import (
    render_confidence_badge,
    render_empty_state,
    render_scary_racer_card,
)
from raceanalyzer.ui.maps import geocode_location, render_course_map, render_location_map

_QUALIFIERS = {
    "High confidence": "Likely",
    "Moderate confidence": "Probable",
    "Low confidence": "Possible",
}


def render():
    from raceanalyzer.ui.app import ensure_db_session
    ensure_db_session()
    session = st.session_state.db_session

    # Back navigation (series-aware)
    back_series = st.session_state.get("back_to_series")
    if back_series:
        if st.button("Back to Series"):
            st.query_params["series_id"] = str(back_series)
            st.switch_page("pages/series_detail.py")
    else:
        if st.button("Back to Calendar"):
            st.switch_page("pages/calendar.py")

    # Build a race selector in the sidebar so users can pick a race directly
    all_races = queries.get_races(session)
    if not all_races.empty:
        race_options = dict(
            zip(
                all_races["name"] + " (" + all_races["date"].astype(str) + ")",
                all_races["id"],
            )
        )
        option_labels = list(race_options.keys())

        # Pre-select from session state or query params if available
        preselected_id = None
        race_id_str = st.query_params.get("race_id")
        if not race_id_str and "selected_race_id" in st.session_state:
            race_id_str = str(st.session_state["selected_race_id"])
        if race_id_str:
            try:
                preselected_id = int(race_id_str)
            except (ValueError, TypeError):
                pass

        # Find the index of the preselected race
        default_idx = 0
        if preselected_id is not None:
            for i, (_, rid) in enumerate(race_options.items()):
                if rid == preselected_id:
                    default_idx = i
                    break

        selected_label = st.sidebar.selectbox(
            "Select a race:", options=option_labels, index=default_idx,
        )
        race_id = int(race_options[selected_label])
        st.session_state["selected_race_id"] = race_id
    else:
        render_empty_state("No races in the database. Seed some data first.")
        return

    detail = queries.get_race_detail(session, race_id)
    if detail is None:
        render_empty_state(f"Race ID {race_id} not found.")
        return

    race = detail["race"]
    classifications = detail["classifications"]
    results = detail["results"]

    # --- Other Editions sidebar ---
    race_obj = session.get(Race, race_id)
    if race_obj and race_obj.series_id:
        other_editions = queries.get_series_editions(session, race_obj.series_id)
        if len(other_editions) > 1:
            st.sidebar.divider()
            st.sidebar.subheader("Other Editions")
            for ed in other_editions:
                if ed["id"] == race_id:
                    continue
                date_str = f"{ed['date']:%Y}" if ed.get("date") else "?"
                if st.sidebar.button(
                    f"{ed['name']} ({date_str})",
                    key=f"edition_nav_{ed['id']}",
                ):
                    st.session_state["selected_race_id"] = ed["id"]
                    st.query_params["race_id"] = str(ed["id"])
                    st.rerun()

    # Header
    st.title(race["name"])
    col1, col2 = st.columns(2)
    if race["date"]:
        col1.write(f"**Date:** {race['date']:%B %d, %Y}")
    else:
        col1.write("**Date:** Unknown")
    location = race["location"] or "Unknown"
    state = race["state_province"] or ""
    col2.write(f"**Location:** {location}, {state}" if state else f"**Location:** {location}")

    # Course map (Folium polyline) or area map fallback
    polyline = None
    if race_obj:
        # Check race-level override first, then series-level
        if race_obj.rwgps_route_id:
            # Per-race polyline would need to be fetched/cached separately
            pass
        if race_obj.series_id:
            series_obj = session.get(RaceSeries, race_obj.series_id)
            if series_obj and series_obj.rwgps_encoded_polyline:
                polyline = series_obj.rwgps_encoded_polyline

    if polyline:
        render_course_map(polyline, race["name"])
    elif location and location != "Unknown":
        coords = geocode_location(location, state)
        if coords:
            render_location_map(*coords)

    st.divider()

    if classifications.empty:
        render_empty_state(
            "No classifications available for this race. "
            "Run `raceanalyzer classify` first."
        )
        return

    # Classifications
    st.subheader("Finish Type Classifications")
    for _, row in classifications.iterrows():
        with st.container():
            cols = st.columns([2, 3, 1, 1])
            cols[0].write(f"**{row['category']}**")

            display_name = queries.finish_type_display_name(row["finish_type"])
            qualifier = _QUALIFIERS.get(row["confidence_label"], "")
            qualifier_text = f"{qualifier} {display_name}" if qualifier else display_name
            tooltip = queries.FINISH_TYPE_TOOLTIPS.get(row["finish_type"], "")
            if tooltip:
                cols[1].markdown(
                    f'<span title="{tooltip}">{qualifier_text}</span>',
                    unsafe_allow_html=True,
                )
            else:
                cols[1].write(qualifier_text)

            with cols[2]:
                render_confidence_badge(row["confidence_label"], row["confidence_color"])

            finishers = row["num_finishers"] or 0
            groups = row["num_groups"] or 0
            gap = row["gap_to_second_group"]
            gap_text = f"{gap:.1f}s gap" if gap is not None else ""
            cols[3].write(f"{finishers} finishers, {groups} groups {gap_text}")

            # Expandable results per category
            if not results.empty:
                cat_results = results[results["category"] == row["category"]]
                if not cat_results.empty:
                    with st.expander(f"View {len(cat_results)} results"):
                        st.dataframe(
                            cat_results[["place", "name", "team", "race_time",
                                         "gap_to_leader", "gap_group_id"]],
                            use_container_width=True,
                            hide_index=True,
                        )
                        fig = build_group_structure_chart(cat_results)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)

    # --- Scary Racers Section ---
    st.divider()
    st.subheader("Scary Racers")
    st.caption(
        "Predicted top performers based on road-results ranking points. "
        "Higher points = scarier competition."
    )

    if classifications.empty:
        st.info("No categories available for scary racer analysis.")
    else:
        for _, cls_row in classifications.iterrows():
            category = cls_row["category"]
            scary_df = queries.get_scary_racers(session, race_id, category)

            if scary_df.empty:
                continue

            with st.expander(f"Scary Racers: {category}", expanded=True):
                for _, racer in scary_df.iterrows():
                    render_scary_racer_card(racer.to_dict())
                    st.markdown("---")


render()
