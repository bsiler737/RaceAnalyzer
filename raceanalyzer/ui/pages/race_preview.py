"""Race Preview page -- forward-looking race analysis (Sprint 011).

Sprint 020: Field-aware pivot — smart field picker, per-section data pivot,
per-section empty states, duplicate course map removal.
"""

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
    render_racer_profile_filters,
    render_scary_racer_card,
    render_selectivity_badge,
    render_similar_races,
    render_team_startlist,
    resolve_effective_category,
)
from raceanalyzer.ui.maps import render_course_map, render_interactive_course_profile

# Divider constant for the field picker selectbox
_FIELD_DIVIDER = "\u2500\u2500\u2500 Other fields \u2500\u2500\u2500"


def render():
    session = st.session_state.db_session

    # Sprint 018: Initialize filters from URL params
    _init_filters_from_params()

    # Sprint 020: Render sidebar filters (same as feed page)
    racer_profile = render_racer_profile_filters(session)

    # Back navigation (restore feed scroll position)
    if st.button("Back to Feed"):
        # Clear preview-specific state on back-nav
        st.query_params.pop("field", None)
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

    # Sprint 020: Resolve matched categories from racer profile dict
    matched_categories = []
    all_cats = queries.get_categories(session)
    if all_cats and any(
        racer_profile.get(k) for k in ("cat_level", "gender", "masters_on")
    ):
        matched_categories = queries.resolve_racer_profile_matches(
            all_cats,
            cat_level=racer_profile.get("cat_level"),
            gender=racer_profile.get("gender"),
            masters_on=racer_profile.get("masters_on", False),
            masters_age=racer_profile.get("masters_age"),
        )

    racer_profile_label = queries.build_racer_profile_label(
        cat_level=racer_profile.get("cat_level"),
        gender=racer_profile.get("gender"),
        masters_on=racer_profile.get("masters_on", False),
        masters_age=racer_profile.get("masters_age"),
    )

    # First fetch with no specific field to get the category list and overall data
    initial_cat = None
    if matched_categories:
        initial_cat = min(matched_categories, key=len)
    elif not st.session_state.get("global_category"):
        if all_cats:
            resolved, _ = resolve_effective_category(all_cats)
            initial_cat = resolved
    else:
        initial_cat = st.session_state.get("global_category")

    preview = queries.get_race_preview(
        session, int(series_id),
        category=initial_cat,
        matched_categories=matched_categories or None,
        racer_profile_label=racer_profile_label,
    )
    if preview is None:
        render_empty_state("Series not found.")
        return

    series = preview["series"]
    st.title(series["display_name"])
    st.caption("Race Preview")

    # === Sprint 020: Smart Field Picker with deduplication ===
    raw_categories = preview["categories"]
    chosen_field = None  # None = "All Categories" mode
    # Map from canonical display name back to raw category names for queries
    canon_to_raws: dict[str, list[str]] = {}

    if raw_categories:
        from raceanalyzer.queries import deduplicate_field_names, normalize_field_name

        categories, canon_to_raws = deduplicate_field_names(raw_categories)

        # Normalize matched_categories into canonical space
        matched_canon = set()
        for mc in (matched_categories or []):
            mc_norm = normalize_field_name(mc)
            if mc_norm in canon_to_raws:
                matched_canon.add(mc_norm)

        if len(categories) > 1:
            matched_set = matched_canon
            matched_fields = [c for c in categories if c in matched_set]
            other_fields = [c for c in categories if c not in matched_set]

            cat_options: list = [None]  # None = "All Categories"
            if matched_fields:
                cat_options += matched_fields
            if other_fields:
                if matched_fields:
                    cat_options.append(_FIELD_DIVIDER)
                cat_options += other_fields

            def _format_field(x):
                if x is None:
                    return "All Categories"
                if x == _FIELD_DIVIDER:
                    return _FIELD_DIVIDER
                if x in matched_set:
                    return f"\u2605 {x}"
                return f"  {x}"

            # Restore field from URL params
            url_field = st.query_params.get("field")
            default_idx = 0
            if url_field and url_field in categories:
                default_idx = cat_options.index(url_field)

            raw_choice = st.selectbox(
                "Field",
                options=cat_options,
                index=default_idx,
                format_func=_format_field,
            )

            # Divider selection is a no-op — revert to previous
            if raw_choice == _FIELD_DIVIDER:
                raw_choice = url_field if url_field in categories else None

            chosen_field = raw_choice

            # Persist to URL
            if chosen_field:
                st.query_params["field"] = chosen_field
            else:
                st.query_params.pop("field", None)

        elif len(categories) == 1:
            # Single field: auto-select, hide picker
            chosen_field = categories[0]
    # else: no categories at all

    # --- Re-fetch preview data if a specific field is chosen ---
    # Use the first raw category name for querying (any variant will match)
    query_category = None
    if chosen_field and chosen_field in canon_to_raws:
        query_category = canon_to_raws[chosen_field][0]

    if query_category:
        preview = queries.get_race_preview(
            session, int(series_id),
            category=query_category,
            matched_categories=None,  # field-specific, not multi-match
            racer_profile_label=racer_profile_label,
        )
        if preview is None:
            render_empty_state("Series not found.")
            return

    is_field_mode = chosen_field is not None

    # --- Extract preview data ---
    profile_points = preview.get("profile_points")
    climbs = preview.get("climbs")
    pred = preview["prediction"]
    course = preview.get("course")
    drop_rate = preview.get("drop_rate")
    typical_speed = preview.get("typical_speed")
    narrative = preview.get("narrative", "")
    ai_context = preview.get("ai_context", {})
    field_forecasts = preview.get("field_forecasts", [])
    cat_distance = preview.get("category_distance")
    cat_distance_unit = preview.get("category_distance_unit")
    distance_range = preview.get("distance_range")
    est_time_range = preview.get("estimated_time_range")

    # === 1. Two-column: What to Expect + Predicted Finish Type summary ===
    col_wte, col_pft = st.columns(2)
    with col_wte:
        with st.container(border=True):
            st.subheader("What to Expect")

            if is_field_mode:
                # Sprint 020: Single-field narrative
                if narrative:
                    st.markdown(f"**For {chosen_field}:** {narrative}")
                else:
                    st.info(f"No prediction available for {chosen_field}")
            else:
                # Multi-match / overall narrative
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
                if is_field_mode:
                    st.info(f"No prediction available for {chosen_field}")
                else:
                    st.info("No historical data for predictions yet.")

    # === 2. Course Profile (hero interactive chart + climb breakdown) ===
    # Sprint 020 PP-04: Course data does NOT pivot per field (series-level)
    # Sprint 020 PP-05: Remove duplicate render_course_map() from inside Course Profile
    if profile_points and len(profile_points) > 1:
        with st.container(border=True):
            st.subheader("Course Profile")
            if course:
                col1, col2, col3 = st.columns(3)
                ct_display = course_type_display(course["course_type"])
                col1.metric("Terrain", ct_display)
                if course.get("total_gain_m"):
                    col2.metric("Elevation", f"{course['total_gain_m']:.0f}m gain")
                # Sprint 020: Show field-specific distance if available, else range/course
                if is_field_mode and cat_distance is not None:
                    from raceanalyzer.queries import _format_unit_label
                    unit_label = _format_unit_label(cat_distance_unit)
                    dist_val = int(cat_distance) if cat_distance == int(cat_distance) else f"{cat_distance:.1f}"
                    col3.metric("Distance", f"{dist_val} {unit_label}")
                elif distance_range:
                    col3.metric("Distance", distance_range)
                elif course.get("distance_m"):
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

            # Sprint 020 PP-05: No render_course_map() here — standalone map below
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

            # Sprint 020 PP-05: No render_course_map() here either

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
                    session, int(series_id),
                    category=query_category if is_field_mode else initial_cat,
                )
                if detail and detail.get("editions_summary"):
                    st.markdown("**Historical Pattern:**")
                    render_finish_pattern(detail["editions_summary"])
                elif is_field_mode:
                    st.info(f"No historical results for {chosen_field}")
            else:
                if is_field_mode:
                    st.info(f"No prediction available for {chosen_field}")
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

    # Sprint 020 PP-13: Field forecasts only in "All Categories" mode
    if not is_field_mode and field_forecasts:
        with st.container(border=True):
            st.subheader("Field Forecasts")
            for forecast in field_forecasts:
                ft_display = finish_type_display_name(forecast["finish_type"])
                st.markdown(
                    f"**{forecast['category']}**: {ft_display} — {forecast['teaser']}"
                )

    # === 4. Scary Riders (category-gated) ===
    with st.container(border=True):
        st.subheader("Scary Riders")
        scary_cat = query_category if is_field_mode else initial_cat
        if scary_cat:
            latest_race = queries.get_latest_race_for_series(session, int(series_id))
            if latest_race:
                scary_racers = queries.get_scary_racers(
                    session, latest_race.id, category=scary_cat
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
                    if is_field_mode:
                        st.info(f"No registered riders found for {chosen_field}")
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
        startlist_cat = query_category if is_field_mode else None
        team_blocks = queries.get_startlist_team_blocks(
            session, int(series_id), category=startlist_cat, team_name=team_name,
        )
        if team_blocks:
            render_team_startlist(team_blocks, user_team_name=team_name)
        else:
            if is_field_mode:
                st.info(f"No startlist data for {chosen_field}")
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

            feedback_cat = query_category or initial_cat or ""
            if st.button("Submit Feedback"):
                _save_feedback(
                    session, int(series_id), feedback_cat,
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
