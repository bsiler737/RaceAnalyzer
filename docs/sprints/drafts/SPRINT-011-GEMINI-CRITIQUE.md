# Sprint 011: Draft Critiques

This document provides a detailed critique of both the Claude and Codex drafts for Sprint 011, evaluating them against the original use cases, technical constraints, and Streamlit realities.

## 1. Claude Draft Critique

The Claude draft provides an excellent, detailed architectural roadmap with highly pragmatic Python-level implementations, but it critically misses the primary UX directive of the sprint.

### Strengths
*   **Phasing Strategy:** The 5-phase approach is logically sequenced. Putting Performance & Query Foundation (Phase 1) first is exactly correct—building UI features on top of N+1 queries would be a disaster.
*   **Data Architecture:** The explicit definition of `FeedItemTier1` and `FeedItemTier2` dataclasses cleanly separates always-needed data from lazy-loaded data.
*   **Code Completeness:** The provided `get_feed_items_batch` implementation is robust, handling the merge of multiple query results in Python efficiently without overly complex SQL.
*   **State Management:** The use of `st.session_state` synced with `st.query_params` for filter persistence is idiomatic Streamlit and well-designed.

### Weaknesses & Under-specified Use Cases
*   **Critical UX Failure (FG-08 & No Click Required):** The draft fails the core "First Glance" mandate. The use cases explicitly state that factors 1-6 must be visible *without expanding or clicking*. Claude attempts to squeeze Date and Location into the plain-text expander label, but hides Teammates (FG-02), Course Character (FG-03), Field Size (FG-05), and Drop Rate (FG-06) inside the expander (Row 1 of the expanded view). This violates the "no click required" design principle.
*   **Streamlit Expander Limitations:** Claude acknowledges that expander labels are plain text (Risk #3), but fails to pivot the UI strategy. You cannot put rich UI (badges, icons, columns) on the outside of an `st.expander`.

### Missing Edge Cases & Risk Gaps
*   **Fuzzy Team Matching:** The proposed `Startlist.team.ilike(f"%{team_name}%")` is too loose. If a user enters "Team", it matches every team with the word "Team". If they enter a short string, it yields massive false positives.
*   **Data Staleness in Precompute:** The risk of `series_predictions` getting out of sync with newly scraped results is mentioned, but there is no explicit fallback logic if a series is queried before the `precompute_all` task finishes.

### Definition of Done Completeness
*   **Strengths:** Excellent phase-by-phase breakdown makes it easy to track during the sprint.
*   **Gaps:** Missing verification of the fuzzy-matching edge cases. The DoD item for "Card Row 1" incorrectly validates putting those badges inside the card rather than on the summary view.

---

## 2. Codex Draft Critique

The Codex draft astutely catches the UI limitations of Streamlit and proposes a technically sound database strategy, but suffers from severe sequencing and UX-flow risks.

### Strengths
*   **UI Strategy (FG-08):** Correctly identifies that `st.expander` must be abandoned to satisfy the "no click required" use cases. Proposing `st.container(border=True)` with a "Details" button is the right path to surface badges and metrics immediately.
*   **SQL Batching:** The use of SQLite window functions (`ROW_NUMBER() OVER`) for fetching the upcoming and most recent races is highly efficient and pushes the heavy lifting to the database.
*   **Migration Awareness:** Explicitly calls out that adding `series_predictions` requires a schema migration tool, which is a practical reality often overlooked in SQLite-backed prototyping.

### Weaknesses & Under-specified Use Cases
*   **Dangerous Phasing:** Codex places Performance (PF-01 to PF-06) in Phase 5, *after* the UI redesign (Phase 1) and feature additions (Phases 2-4). Adding more complex UI rendering and data requirements to a feed that already suffers from N+1 queries will render the app unusable during development. Performance must be the foundation.
*   **Detail Dive (DD-01):** The draft mentions the course profile should be the hero visualization but doesn't actually specify how the preview layout should be structured to incorporate it with the new components.
*   **Similar Races Scoring (DD-06):** The scoring logic is vaguely defined ("minus normalized distance diff") which could easily result in negative scores or poor scaling if not carefully bounded.

### Missing Edge Cases & Risk Gaps
*   **Streamlit Page Jumps:** Replacing the native `st.expander` with an `st.button("Details")` introduces a major Streamlit risk: clicking a button triggers a full script rerun, which often causes the page scroll to jump back to the top. This would completely ruin the feed scanning experience unless mitigated (e.g., using `st.experimental_fragment` or `st.dialog`).
*   **Window Function Compatibility:** Relies on SQLite window functions. While supported in SQLite >= 3.25, it's a risk if the deployment environment uses an older compiled version of SQLite.

### Definition of Done Completeness
*   **Strengths:** Captures the high-level goals of each feature area effectively.
*   **Gaps:** Because the DoD is organized by feature area rather than chronological implementation phases, it's harder to use as a sprint checklist.

---

## 3. Synthesis & Recommendations for Final Plan

A successful Sprint 011 implementation must combine the strengths of both drafts while mitigating their blind spots:

1.  **Phase Ordering (Winner: Claude):** Strictly follow Claude's phasing. Do Performance and Batch Queries *first*. Build the UI on top of the fast, batched data structures.
2.  **UI Container Strategy (Winner: Codex):** Abandon `st.expander` for feed items. Use `st.container(border=True)` to build a rich summary card that displays all P0/P1 decision factors without clicking.
3.  **Detail Expansion UX (Mitigation):** To avoid the Streamlit scroll-jump issue identified in the Codex critique, either use `@st.experimental_fragment` for the detail expansion, or use a combination of a summary container and an attached `st.expander("Deeper Context")` specifically for Tier 2 data. The summary container holds the "First Glance" info, and the expander holds the "Detail Dive" info.
4.  **SQL Strategy (Hybrid):** Use Codex's elegant window functions if the SQLite version allows it, but fall back to Claude's Python-level merging if window functions prove problematic or slow.
5.  **Team Matching Logic:** Implement exact matching or normalized matching (lowercase, stripped punctuation) rather than simple SQL `ILIKE "%string%"` to avoid false positives.