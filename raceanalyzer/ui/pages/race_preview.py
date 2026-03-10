"""Race Preview page -- forward-looking race analysis."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.elevation import COURSE_TYPE_DESCRIPTIONS, course_type_display
from raceanalyzer.queries import finish_type_display_name
from raceanalyzer.ui.components import render_confidence_badge, render_empty_state
from raceanalyzer.ui.maps import render_course_map


def render():
    session = st.session_state.db_session

    # Back navigation
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

    series_id = st.query_params.get("series_id")
    if not series_id:
        series_id = st.session_state.get("preview_series_id")
    if not series_id:
        render_empty_state("No series selected for preview.")
        return

    selected_cat = st.query_params.get("category")

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

    # Card 1: Terrain
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

            # Terrain description
            desc = COURSE_TYPE_DESCRIPTIONS.get(course["course_type"], "")
            if desc:
                st.caption(desc)
        else:
            st.info("No course data available.")

        # Course map
        if series.get("encoded_polyline"):
            render_course_map(series["encoded_polyline"], series["display_name"])

    # Card 2: Prediction
    with st.container(border=True):
        st.subheader("Predicted Finish Type")
        pred = preview["prediction"]
        if pred:
            ft_display = finish_type_display_name(pred["predicted_finish_type"])
            st.markdown(f"### {ft_display}")

            # Confidence badge
            confidence = pred["confidence"]
            color_map = {"high": "green", "moderate": "orange", "low": "red"}
            label_map = {"high": "High confidence", "moderate": "Moderate confidence",
                         "low": "Low confidence"}
            render_confidence_badge(
                label_map.get(confidence, confidence),
                color_map.get(confidence, "gray"),
            )

            st.caption(f"Based on {pred['edition_count']} previous edition(s)")

            # Distribution
            if pred.get("distribution"):
                with st.expander("Finish type distribution"):
                    for ft, count in sorted(
                        pred["distribution"].items(), key=lambda x: -x[1]
                    ):
                        st.write(f"- {finish_type_display_name(ft)}: {count}")
        else:
            st.info("No historical data for predictions yet.")

    # Card 3: Top Contenders
    with st.container(border=True):
        st.subheader("Top Contenders")
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
                    team_str = f" -- {rider['team']}" if rider.get("team") else ""
                    col1.write(f"**{rider['name']}**{team_str}")
                    pts = rider.get("carried_points", 0)
                    col2.write(f"{pts:.0f} pts" if pts else "")
        else:
            st.info("No contender data available.")

    # Card 4: Post-race feedback (shown after race date)
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
                st.success("Thank you! Your feedback helps improve predictions.")


def _save_feedback(session, series_id, category, predicted_ft, choice, options):
    """Save user feedback as a UserLabel row."""
    from datetime import datetime

    from raceanalyzer.db.models import FinishType, Race, UserLabel

    # Find most recent race in series
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
        # Map display name back to enum
        for i, opt in enumerate(options):
            if finish_type_display_name(opt) == choice:
                actual_ft = FinishType(opt)
                is_correct = opt == predicted_ft
                break
        else:
            return

    # Session-based dedup
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
