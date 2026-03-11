"""Race Preview page -- forward-looking race analysis (Sprint 011)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.elevation import COURSE_TYPE_DESCRIPTIONS, course_type_display
from raceanalyzer.queries import finish_type_display_name
from raceanalyzer.ui.components import (
    render_climb_breakdown,
    render_climb_legend,
    render_confidence_badge,
    render_empty_state,
    render_finish_pattern,
    render_selectivity_badge,
    render_similar_races,
    render_team_startlist,
)
from raceanalyzer.ui.maps import render_course_map, render_interactive_course_profile


def render():
    session = st.session_state.db_session

    # Back navigation
    if st.button("Back to Feed"):
        st.switch_page("pages/feed.py")

    series_id = st.query_params.get("series_id")
    if not series_id:
        series_id = st.session_state.get("preview_series_id")
    if not series_id:
        render_empty_state("No series selected for preview.")
        return

    selected_cat = st.query_params.get("category")
    if not selected_cat:
        selected_cat = st.session_state.get("global_category")

    preview = queries.get_race_preview(session, int(series_id), category=selected_cat)
    if preview is None:
        render_empty_state("Series not found.")
        return

    series = preview["series"]
    st.title(series["display_name"])
    st.caption("Race Preview")

    # Category selector
    categories = preview["categories"]
    if categories:
        cat_options = [None] + categories
        default_idx = 0
        if selected_cat and selected_cat in categories:
            default_idx = categories.index(selected_cat) + 1

        chosen_cat = st.selectbox(
            "Category",
            options=cat_options,
            index=default_idx,
            format_func=lambda x: "All Categories" if x is None else x,
        )
        if chosen_cat != selected_cat:
            st.query_params["category"] = chosen_cat or ""
            st.rerun()

    # DD-01: Hero Course Profile (moved to top)
    profile_points = preview.get("profile_points")
    climbs = preview.get("climbs")

    if profile_points and len(profile_points) > 1:
        with st.container(border=True):
            st.subheader("Course Profile")
            course = preview["course"]
            if course:
                col1, col2, col3 = st.columns(3)
                ct_display = course_type_display(course["course_type"])
                col1.metric("Terrain", ct_display)
                if course.get("total_gain_m"):
                    col2.metric("Elevation", f"{course['total_gain_m']:.0f}m gain")
                if course.get("distance_m"):
                    col3.metric("Distance", f"{course['distance_m']/1000:.1f} km")

            if climbs:
                render_climb_legend()
            render_interactive_course_profile(
                profile_points, climbs or [],
                race_name=series["display_name"],
            )

    # DD-02: Climb Breakdown with race context
    if climbs:
        with st.container(border=True):
            st.subheader("Climb Breakdown")
            course = preview.get("course")
            distance_m = course["distance_m"] if course else None
            pred = preview.get("prediction")
            pred_ft = pred["predicted_finish_type"] if pred else None
            drop_rate = preview.get("drop_rate")
            render_climb_breakdown(
                climbs, distance_m=distance_m,
                finish_type=pred_ft, drop_rate=drop_rate,
            )

    # Card: "What to Expect" with expanded racer type (DD-04)
    narrative = preview.get("narrative", "")
    if narrative:
        with st.container(border=True):
            st.subheader("What to Expect")
            st.write(narrative)

            # Expanded racer type
            from raceanalyzer.predictions import racer_type_long_form

            course = preview.get("course")
            pred = preview.get("prediction")
            ct = course["course_type"] if course else None
            pred_ft = pred["predicted_finish_type"] if pred else None
            edition_count = pred["edition_count"] if pred else 0
            drop_rate = preview.get("drop_rate")
            long_desc = racer_type_long_form(
                ct, pred_ft, drop_rate=drop_rate, edition_count=edition_count,
            )
            if long_desc:
                st.markdown(f"**Who does well here?** {long_desc}")

    # Course metrics (if no profile but course data exists)
    if not (profile_points and len(profile_points) > 1):
        course = preview["course"]
        if course:
            with st.container(border=True):
                st.subheader("Course Profile")
                col1, col2, col3 = st.columns(3)
                ct_display = course_type_display(course["course_type"])
                col1.metric("Terrain", ct_display)
                if course.get("total_gain_m"):
                    col2.metric("Elevation", f"{course['total_gain_m']:.0f}m gain")
                if course.get("distance_m"):
                    col3.metric("Distance", f"{course['distance_m']/1000:.1f} km")

                desc = COURSE_TYPE_DESCRIPTIONS.get(course["course_type"], "")
                if desc:
                    st.caption(desc)

                if series.get("encoded_polyline"):
                    render_course_map(
                        series["encoded_polyline"], series["display_name"],
                    )

    # Card: Predicted Finish Type + DD-05: Historical Pattern
    with st.container(border=True):
        st.subheader("Predicted Finish Type")
        pred = preview["prediction"]
        if pred:
            ft_display = finish_type_display_name(pred["predicted_finish_type"])
            st.markdown(f"### {ft_display}")

            confidence = pred["confidence"]
            color_map = {
                "high": "green", "moderate": "orange", "low": "red",
            }
            label_map = {
                "high": "High confidence",
                "moderate": "Moderate confidence",
                "low": "Low confidence",
            }
            render_confidence_badge(
                label_map.get(confidence, confidence),
                color_map.get(confidence, "gray"),
            )

            st.caption(f"Based on {pred['edition_count']} previous edition(s)")

            if pred.get("distribution"):
                with st.expander("Finish type distribution"):
                    for ft, count in sorted(
                        pred["distribution"].items(), key=lambda x: -x[1]
                    ):
                        st.write(f"- {finish_type_display_name(ft)}: {count}")

            # DD-05: Historical finish type visualization
            detail = queries.get_feed_item_detail(
                session, int(series_id), category=selected_cat,
            )
            if detail and detail.get("editions_summary"):
                st.markdown("**Historical Pattern:**")
                render_finish_pattern(detail["editions_summary"])
        else:
            st.info("No historical data for predictions yet.")

    # Card: Historical Stats
    drop_rate = preview.get("drop_rate")
    typical_speed = preview.get("typical_speed")
    if drop_rate or typical_speed:
        with st.container(border=True):
            st.subheader("Historical Stats")

            if drop_rate:
                rate_pct = round(drop_rate["drop_rate"] * 100)
                col1, col2 = st.columns([2, 1])
                col1.metric("Drop Rate", f"{rate_pct}%")
                with col2:
                    render_selectivity_badge(drop_rate["label"])
                st.caption(
                    f"Based on {drop_rate['edition_count']} edition(s) "
                    f"({drop_rate['total_starters']} total starters, "
                    f"{drop_rate['total_dropped']} dropped)"
                )

            if typical_speed:
                st.divider()
                col1, col2 = st.columns(2)
                col1.metric(
                    "Winning Speed",
                    f"{typical_speed['median_winner_speed_mph']} mph",
                )
                col2.metric(
                    "Field Speed",
                    f"{typical_speed['median_field_speed_mph']} mph",
                )
                st.caption(
                    f"Median across {typical_speed['edition_count']} edition(s). "
                    f"({typical_speed['median_winner_speed_kph']} / "
                    f"{typical_speed['median_field_speed_kph']} kph)"
                )

    # DD-03: Team-grouped startlist
    with st.container(border=True):
        st.subheader("Startlist")
        team_name = st.query_params.get("team", "")
        team_blocks = queries.get_startlist_team_blocks(
            session, int(series_id), category=selected_cat, team_name=team_name,
        )
        if team_blocks:
            render_team_startlist(team_blocks, user_team_name=team_name)
        else:
            # Fallback to original contender display
            contenders = preview["contenders"]
            if not contenders.empty:
                source = contenders["source"].iloc[0]
                source_labels = {
                    "startlist": "From registered riders",
                    "series_history": "Based on past editions (no startlist available)",
                    "category": "Top-rated riders in this category",
                }
                st.caption(source_labels.get(source, ""))

                for _, rider in contenders.iterrows():
                    with st.container():
                        col1, col2 = st.columns([3, 1])
                        team_str = (
                            f" -- {rider['team']}" if rider.get("team") else ""
                        )
                        col1.write(f"**{rider['name']}**{team_str}")
                        pts = rider.get("carried_points", 0)
                        col2.write(f"{pts:.0f} pts" if pts else "")
            else:
                st.info("No startlist or contender data available.")

    # DD-06: Similar Races
    with st.container(border=True):
        st.subheader("Similar Races")
        similar = queries.get_similar_series(session, int(series_id))
        render_similar_races(similar)

    # DD-07: Course map with climb markers
    if series.get("encoded_polyline") and profile_points and len(profile_points) > 1:
        with st.container(border=True):
            st.subheader("Course Map")
            render_course_map(
                series["encoded_polyline"], series["display_name"],
                climbs=climbs,
            )

    # Post-race feedback
    latest_date = preview.get("latest_date")
    pred = preview["prediction"]
    if latest_date and pred and latest_date < datetime.now():
        with st.container(border=True):
            st.subheader("Was this prediction right?")
            predicted_ft = finish_type_display_name(pred["predicted_finish_type"])
            st.write(f"We predicted: **{predicted_ft}**")

            from raceanalyzer.db.models import FinishType

            options = [ft.value for ft in FinishType if ft != FinishType.UNKNOWN]
            display_options = ["Yes, correct"] + [
                finish_type_display_name(ft) for ft in options
            ]

            choice = st.radio(
                "What actually happened?",
                options=display_options,
                index=0,
            )

            if st.button("Submit Feedback"):
                _save_feedback(
                    session, int(series_id), selected_cat or "",
                    pred["predicted_finish_type"], choice, options,
                )
                st.success(
                    "Thank you! Your feedback helps improve predictions."
                )


def _save_feedback(session, series_id, category, predicted_ft, choice, options):
    """Save user feedback as a UserLabel row."""
    from datetime import datetime

    from raceanalyzer.db.models import FinishType, Race, UserLabel

    race = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .first()
    )
    if not race:
        return

    if choice == "Yes, correct":
        actual_ft = FinishType(predicted_ft)
        is_correct = True
    else:
        for i, opt in enumerate(options):
            if finish_type_display_name(opt) == choice:
                actual_ft = FinishType(opt)
                is_correct = opt == predicted_ft
                break
        else:
            return

    session_id = st.session_state.get("_feedback_session_id", "anonymous")

    existing = (
        session.query(UserLabel)
        .filter(
            UserLabel.race_id == race.id,
            UserLabel.category == category,
            UserLabel.session_id == session_id,
        )
        .first()
    )

    if existing:
        existing.actual_finish_type = actual_ft
        existing.is_correct = is_correct
        existing.submitted_at = datetime.utcnow()
    else:
        label = UserLabel(
            race_id=race.id,
            category=category,
            predicted_finish_type=FinishType(predicted_ft),
            actual_finish_type=actual_ft,
            is_correct=is_correct,
            submitted_at=datetime.utcnow(),
            session_id=session_id,
        )
        session.add(label)

    session.commit()


render()
