# Sprint 003 Draft: Synthetic Demo Data Generation

## Overview

This sprint focuses on creating a synthetic data generation mechanism to populate the application's database with realistic, fake data. This is a temporary but critical measure to unblock UI development and testing, which is currently stalled due to an IP block from the live data source (`road-results.com`). The generator will be driven by CLI commands, allowing for easy creation and destruction of the demo dataset.

## Use Cases

1.  **UI Development:** Enable developers to build and test UI components against a populated database, verifying that pages for the race calendar, race details, and analytics dashboards render correctly.
2.  **Feature Demonstration:** Provide a rich, realistic dataset to demonstrate all existing UI features to stakeholders without relying on a live data connection.
3.  **Edge Case Testing:** Intentionally generate data that covers all `FinishType` classifications, various data quality scenarios (to test confidence badges), and different race structures to ensure the UI is robust.
4.  **Developer Onboarding:** Allow new developers to quickly set up a working local environment with representative data.

## Architecture

The proposed solution involves extending the existing `click`-based CLI with two new commands and creating a dedicated module for data generation logic.

1.  **CLI Commands:**
    *   `python -m raceanalyzer seed-demo`: A new command in `raceanalyzer/cli.py`. It will initialize a database session and invoke the core data generation logic. It will be responsible for creating all necessary `Race`, `Rider`, `Result`, and `RaceClassification` objects.
    *   `python -m raceanalyzer clear-demo`: A corresponding command in `raceanalyzer/cli.py` that connects to the database and deletes all records from the `RaceClassification`, `Result`, `Rider`, and `Race` tables, providing a clean slate.

2.  **Data Generation Module:**
    *   A new module, `raceanalyzer/data/synthetic.py`, will house the data generation logic. This keeps the concerns separated from the CLI entrypoint.
    *   The module will contain functions that produce realistic-sounding PNW race names, rider names, and team names.
    *   The core of the module will be a set of strategies to generate result times based on a given `FinishType`. For example:
        *   **`BUNCH_SPRINT`**: The top 10-20 riders will have identical times, with places 1-3 having sub-second differences. The main field will finish in one large group with the same time.
        *   **`BREAKAWAY`**: A small group of 2-5 riders will be generated with a time gap of 1-3 minutes over a large main group.
        *   **`GC_SELECTIVE`**: Results will be characterized by many small groups and individual finishers with significant, varied time gaps between them.
        *   **`UNKNOWN`**: Data will be generated with missing time information or inconsistent gaps to ensure the `UNKNOWN` classification and low-confidence badges are exercised.

3.  **Data Model:**
    *   The generator will use the existing SQLAlchemy ORM models from `raceanalyzer/db/models.py` exclusively. No schema changes will be made.
    *   Data will be generated to span approximately 5 years, across the 4 primary PNW regions (WA, OR, ID, BC), and for a variety of common race categories (e.g., "Pro/1/2 Men", "Cat 3 Women", "Masters 40+").

## Implementation Plan

1.  **Create `raceanalyzer/data/synthetic.py`:**
    *   Define static lists for generating names (e.g., PNW cities, cycling-related adjectives, common first/last names).
    *   Implement a `create_riders(session, count)` function to populate the `Rider` table.
    *   Implement a `generate_results_for_finish_type(finish_type, num_finishers)` function that returns a list of `Result` objects with appropriate `race_time_seconds` distributions.
    *   Implement the main `generate_demo_data(session)` function that orchestrates the creation of ~50 races, calling the other functions to build a complete and varied dataset. Ensure all 8 `FinishType` enums are represented.

2.  **Modify `raceanalyzer/cli.py`:**
    *   Add a new `@main.command()` named `seed-demo`. This function will get a DB session and call `generate_demo_data(session)`.
    *   Add a new `@main.command()` named `clear-demo`. This function will get a DB session, query the models (`Race`, `Rider`, etc.), and perform bulk deletes.

3.  **Testing and Verification:**
    *   After running `seed-demo`, manually run the `ui` command to inspect all pages.
    *   Verify the calendar page shows races across multiple years and states.
    *   Verify the race detail page correctly displays results and shows green, yellow, and red confidence badges.
    *   Verify the dashboard charts show meaningful distributions and trends.

## Files Summary

*   **New Files:**
    *   `raceanalyzer/data/synthetic.py`: Contains all logic for generating the synthetic dataset.
*   **Modified Files:**
    *   `raceanalyzer/cli.py`: Add the `seed-demo` and `clear-demo` commands.

## Definition of Done

1.  A `python -m raceanalyzer seed-demo` command is implemented and populates the database with approximately 50 races across 5 years, 4 states, 5+ categories, and all 8 `FinishType` classifications.
2.  A `python -m raceanalyzer clear-demo` command is implemented and successfully removes all demo data from the relevant tables.
3.  After seeding, the UI launches and displays meaningful, populated data on the Calendar, Race Detail, and Dashboard pages.
4.  The "Finish Type Trends" chart on the Dashboard page shows patterns across multiple years for at least one race.
5.  The confidence badges on the Race Detail page demonstrate all three states (green, yellow, red) across different generated race categories.

## Risks

*   **Lack of Realism:** The generated data, particularly time distributions, may not perfectly mimic real-world race dynamics, potentially making demos feel artificial. (Mitigation: Use simple, plausible heuristics for time gaps based on finish type.)
*   **Scope Creep:** The data generation logic could become overly complex in an attempt to achieve perfect realism for this disposable feature. (Mitigation: Strictly adhere to the goal of "good enough for UI testing" and avoid intricate simulations.)

## Open Questions

1.  Are there specific statistical distributions (e.g., Poisson, Normal) that should be preferred for generating time gaps for different finish types, or is a simpler rule-based approach sufficient?
2.  Should the number of generated races, riders, and the time span be configurable via CLI options, or are the fixed targets (~50 races, 5 years) adequate for this sprint's purpose?
