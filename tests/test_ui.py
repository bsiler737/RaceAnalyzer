"""Smoke tests for UI chart builders."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from raceanalyzer.ui.charts import (
    build_distribution_bar_chart,
    build_distribution_pie_chart,
    build_group_structure_chart,
    build_trend_stacked_area_chart,
)


class TestChartBuilders:
    def test_pie_chart(self):
        df = pd.DataFrame({
            "finish_type": ["bunch_sprint", "breakaway"],
            "count": [10, 5],
            "percentage": [66.7, 33.3],
        })
        fig = build_distribution_pie_chart(df)
        assert isinstance(fig, go.Figure)

    def test_bar_chart(self):
        df = pd.DataFrame({
            "finish_type": ["bunch_sprint", "breakaway"],
            "count": [10, 5],
            "percentage": [66.7, 33.3],
        })
        fig = build_distribution_bar_chart(df)
        assert isinstance(fig, go.Figure)

    def test_stacked_area_chart(self):
        df = pd.DataFrame({
            "year": [2022, 2022, 2023, 2023],
            "finish_type": ["bunch_sprint", "breakaway", "bunch_sprint", "breakaway"],
            "count": [10, 5, 12, 8],
        })
        fig = build_trend_stacked_area_chart(df)
        assert isinstance(fig, go.Figure)

    def test_group_structure_chart(self):
        df = pd.DataFrame({
            "gap_group_id": [1, 1, 1, 2, 2],
            "place": [1, 2, 3, 4, 5],
        })
        fig = build_group_structure_chart(df)
        assert isinstance(fig, go.Figure)

    def test_group_structure_chart_no_data(self):
        df = pd.DataFrame({"gap_group_id": [None, None], "place": [1, 2]})
        fig = build_group_structure_chart(df)
        assert fig is None
