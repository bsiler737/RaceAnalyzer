"""Race Preview page -- forward-looking race analysis (Sprint 011)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.elevation import COURSE_TYPE_DESCRIPTIONS, course_type_display
from raceanalyzer.queries import finish_type_display_name
from raceanalyzer.ui.components import (
    _init_filters_from_params,
    render_climb_breakdown,
    render_climb_legend,
    render_confidence_badge,
    render_empty_state,
    render_finish_pattern,
    render_scary_racer_card,
    render_selectivity_badge,
    render_similar_races,
    render_team_startlist,
    resolve_effective_category,
)
from raceanalyzer.ui.maps import render_course_map, render_interactive_course_profile


def render():
    session = st.session_state.db_session

    # Sprint 018: Initialize filters from URL params
    _init_filters_from_params()

    # Back navigation (restore feed scroll position)
    if st.button("Back to Feed"):
        # Restore pagination to where user left off
        scroll_idx = st.session_state.get("feed_scroll_index")
        if scroll_idx:
            st.session_state["feed_page_size"] = scroll_idx
        st.switch_page("pages/feed.py")

    series_id = st.query_params.get("series_id")
    if not series_id:
        series_id = st.session_state.get("preview_series_id")
    if not series_id:
        render_empty_state("No series selected for preview.")
        return

    # Sprint 018/019: Resolve category + matched categories from racer profile
    selected_cat = st.query_params.get("category")
    if not selected_cat:
        selected_cat = st.session_state.get("global_category")
    matched_categories = []
    if not selected_cat:
        all_cats = queries.get_categories(session)
        if all_cats:
            matched_categories = queries.resolve_racer_profile_matches(
                all_cats,
                cat_level=st.session_state.get("cat_level"),
                gender=st.session_state.get("gender"),
                masters_on=st.session_state.get("masters_on", False),
                masters_age=st.session_state.get("masters_age"),
            )
            if matched_categories:
                selected_cat = min(matched_categories, key=len)
            else:
                resolved, _ = resolve_effective_category(all_cats)
                if resolved:
                    selected_cat = resolved

    racer_profile_label = queries.build_racer_profile_label(
        cat_level=st.session_state.get("cat_level"),
        gender=st.session_state.get("gender"),
        masters_on=st.session_state.get("masters_on", False),
        masters_age=st.session_state.get("masters_age"),
    )
    preview = queries.get_race_preview(
        session, int(series_id),
        category=selected_cat,
        matched_categories=matched_categories or None,
        racer_profile_label=racer_profile_label,
    )
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

    # --- Sprint 018/019: Restructured layout ---
    profile_points = preview.get("profile_points")
    climbs = preview.get("climbs")
    pred = preview["prediction"]
    course = preview.get("course")
    drop_rate = preview.get("drop_rate")
    typical_speed = preview.get("typical_speed")
    narrative = preview.get("narrative", "")
    ai_context = preview.get("ai_context", {})
    field_forecasts = preview.get("field_forecasts", [])

    # === 1. Two-column: What to Expect + Predicted Finish Type summary ===
    col_wte, col_pft = st.columns(2)
    with col_wte:
        with st.container(border=True):
            st.subheader("What to Expect")

            # Sprint 019: Category-aware narrative rendering
            mode = ai_context.get("mode", "overall") if ai_context else "overall"
            if mode == "single_match" and ai_context.get("best_category"):
                if narrative:
                    st.markdown(
                        f"**For {ai_context['best_category']}:** {narrative}"
                    )
            elif mode == "multi_match":
                if narrative:
                    st.write(narrative)
                if field_forecasts:
                    finish_types = {f["finish_type"] for f in field_forecasts}
                    if len(finish_types) == 1:
                        st.markdown(
                            "Your matched fields all point to the same outcome."
                        )
                    else:
                        st.markdown("**Field-specific forecasts:**")
                        for forecast in field_forecasts:
                            st.markdown(
                                f"- **{forecast['category']}**: "
                                f"{forecast['teaser']}"
                            )
            elif narrative:
                st.write(narrative)

            from raceanalyzer.predictions import racer_type_long_form

            ct = course["course_type"] if course else None
            pred_ft = pred["predicted_finish_type"] if pred else None
            edition_count = pred["edition_count"] if pred else 0
            long_desc = racer_type_long_form(
                ct, pred_ft, drop_rate=drop_rate, edition_count=edition_count,
            )
            if long_desc:
                st.markdown(f"**Who does well here?** {long_desc}")

    with col_pft:
        with st.container(border=True):
            st.subheader("Predicted Finish Type")
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
            else:
                st.info("No historical data for predictions yet.")

    # === 2. Course Profile (hero interactive chart + climb breakdown) ===
    if profile_points and len(profile_points) > 1:
        with st.container(border=True):
            st.subheader("Course Profile")
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

            # Climb breakdown inline
            if climbs:
                st.divider()
                distance_m = course["distance_m"] if course else None
                render_climb_breakdown(
                    climbs, distance_m=distance_m,
                    finish_type=pred_ft, drop_rate=drop_rate,
                )

            # Course map if available
            if series.get("encoded_polyline"):
                render_course_map(
                    series["encoded_polyline"], series["display_name"],
                    climbs=climbs,
                )
    elif course:
        # Fallback: course metrics without profile
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

    # === 3. Two-column: Predicted Finish Type details + Historical Stats ===
    col_pred, col_stats = st.columns(2)
    with col_pred:
        with st.container(border=True):
            st.subheader("Finish Type Details")
            if pred:
                if pred.get("distribution"):
                    import pandas as pd

                    from raceanalyzer.ui.charts import build_distribution_bar_chart

                    dist_data = [
                        {"finish_type": ft, "count": count}
                        for ft, count in pred["distribution"].items()
                    ]
                    dist_df = pd.DataFrame(dist_data)
                    fig = build_distribution_bar_chart(dist_df)
                    fig.update_layout(height=max(200, len(dist_data) * 40))
                    fig.update_traces(
                        texttemplate="%{x}",
                        textposition="outside",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # Historical finish type pattern
                detail = queries.get_feed_item_detail(
                    session, int(series_id), category=selected_cat,
                )
                if detail and detail.get("editions_summary"):
                    st.markdown("**Historical Pattern:**")
                    render_finish_pattern(detail["editions_summary"])
            else:
                st.info("No prediction data available.")

    with col_stats:
        with st.container(border=True):
            st.subheader("Historical Stats")
            if drop_rate or typical_speed:
                if drop_rate:
                    rate_pct = round(drop_rate["drop_rate"] * 100)
                    c1, c2 = st.columns([2, 1])
                    c1.metric("Drop Rate", f"{rate_pct}%")
                    with c2:
                        render_selectivity_badge(drop_rate["label"])
                    st.caption(
                        f"Based on {drop_rate['edition_count']} edition(s) "
                        f"({drop_rate['total_starters']} total starters, "
                        f"{drop_rate['total_dropped']} dropped)"
                    )

                if typical_speed:
                    if drop_rate:
                        st.divider()
                    c1, c2 = st.columns(2)
                    c1.metric(
                        "Winning Speed",
                        f"{typical_speed['median_winner_speed_mph']} mph",
                    )
                    c2.metric(
                        "Field Speed",
                        f"{typical_speed['median_field_speed_mph']} mph",
                    )
                    st.caption(
                        f"Median across {typical_speed['edition_count']} edition(s). "
                        f"({typical_speed['median_winner_speed_kph']} / "
                        f"{typical_speed['median_field_speed_kph']} kph)"
                    )
            else:
                st.info("No historical stats available yet.")

    # === 4. Scary Riders (category-gated) ===
    with st.container(border=True):
        st.subheader("Scary Riders")
        if selected_cat:
            latest_race = queries.get_latest_race_for_series(session, int(series_id))
            if latest_race:
                scary_racers = queries.get_scary_racers(
                    session, latest_race.id, category=selected_cat
                )
                if not scary_racers.empty:
                    source = scary_racers["source"].iloc[0]
                    if source == "startlist":
                        st.caption("Based on registered riders")
                    else:
                        st.caption("Based on past editions (no startlist imported yet)")
                    for _, racer in scary_racers.iterrows():
                        render_scary_racer_card(racer.to_dict())
                else:
                    st.info("No scary rider data for this category.")
            else:
                st.info("No scary rider data for this category.")
        else:
            st.info(
                "Pick a category to see the :ghost: spooky riders :ghost: "
                "for your category."
            )

    # === 5. Startlist (actual registrations only) ===
    with st.container(border=True):
        st.subheader("Startlist")
        team_name = st.session_state.get("team", "") or st.query_params.get("team", "")
        team_blocks = queries.get_startlist_team_blocks(
            session, int(series_id), category=selected_cat, team_name=team_name,
        )
        if team_blocks:
            render_team_startlist(team_blocks, user_team_name=team_name)
        else:
            st.info("No startlist data available yet.")

    # === 6. Similar Races ===
    with st.container(border=True):
        st.subheader("Similar Races")
        similar = queries.get_similar_series(session, int(series_id))
        render_similar_races(similar)

    # === 7. Post-race Feedback ===
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
