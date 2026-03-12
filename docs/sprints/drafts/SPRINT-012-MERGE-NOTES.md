# Sprint 012 Merge Notes

## Draft Strengths

### Claude Draft
- Complete, executable Python algorithm with every rule branch visible
- Climb-aware predictions (steep/long/late climb modifiers) that produce richer predictions
- Explicit RACER_TYPE_DESCRIPTIONS gap awareness in Phase 2
- Clean deep-link fix (force-expand existing card, reuse container card renderer)
- Thorough test plan mapping 1:1 to rule branches

### Codex Draft
- Pure-function predictor design (zero DB dependencies)
- Conservative 0.75 confidence ceiling
- road_race without course data returns None (honest, not guessing)
- Cleaner separation of concerns: predictor in classification/, orchestration in precompute.py
- Exhaustive race_type inheritance edge cases

### Gemini Draft
- "Data quality cascade" framing — best architecture documentation of the three
- Broader decision matrix covering gravel/stage_race
- Crit m/km offset (_CRIT_OFFSET = -2.0) — genuine domain insight
- Three-tier prediction priority (time-gap > course_profile > race_type_only)
- Source-aware narrative language with concrete text examples
- Past-only series as "race profile" reframe

## Valid Critiques Accepted

| Critique | Source | Resolution |
|----------|--------|------------|
| hill_climb should map to GC_SELECTIVE, not INDIVIDUAL_TT | Gemini critique, Codex critique | Accepted — hill climbs are mass-start events |
| m_per_km formatting crashes when None | Codex critique, Gemini critique | Accepted — add guards for None m_per_km in reasoning strings |
| RACER_TYPE_DESCRIPTIONS missing 3 entries | All three critiques | Accepted — add (hilly, breakaway_selective), (hilly, small_group_sprint), (mountainous, breakaway_selective) |
| generate_narrative() misleads when prediction_source is "course" | All three critiques | Accepted — add prediction_source param, use hedged language |
| Base.metadata.create_all() doesn't add columns to existing tables | All three critiques | Accepted — add explicit ALTER TABLE migration |
| No crit-specific threshold adjustment in Claude draft | Codex critique, Gemini critique | Accepted — adopt Gemini's _CRIT_OFFSET concept |
| Fallback logic belongs in precompute.py, not predictions.py | Codex draft, Gemini critique | Accepted — keeps predict_series_finish_type() contract unchanged |
| CourseType enum vs string comparison issue | Codex critique | Accepted — integration layer must convert .value |
| Need prediction coverage stats in CLI output | Codex critique | Accepted — add --stats flag |
| Multi-course series needs resolution strategy | Codex critique, Claude critique | Accepted — use most recent by extracted_at |
| backfill_race_types() is scope creep | Codex critique | Accepted — drop it, only inherit for upcoming races |

## Valid Critiques Rejected

| Critique | Source | Reason for Rejection |
|----------|--------|---------------------|
| Use lookup table over decision tree | Codex draft | User explicitly chose decision tree with climb rules for richer predictions |
| 80% threshold for race_type inheritance | Claude draft, Gemini draft | User explicitly chose simple majority (>50%) |
| Build render_series_profile() component | Gemini draft | Too ambitious for this sprint; force-expanding existing card achieves the same core fix with less risk |
| Include Alberta in PNW whitelist | Codex draft | Not PNW cycling market; WA, OR, ID, BC, MT is sufficient |
| Use FinishType enum in predictor interface | Gemini critique | String interface is simpler to test and matches predictions.py patterns; enum conversion happens at integration layer |
| prediction_source should be an SAEnum | Claude critique | String column is simpler and these values are set only by server code |

## Interview Refinements Applied

1. **Decision tree with climb rules** — adopted from Claude draft, enhanced with Gemini's crit offset
2. **Simple majority (>50%) threshold** — lower than any draft proposed; maximizes coverage for small series
3. **PNW whitelist** — {"WA", "OR", "ID", "BC", "MT"}
4. **Hedged language** — adopted from Gemini draft's source-aware narrative treatment

## Final Architecture Decisions

1. **Predictor**: Decision tree in `classification/course_predictor.py` with climb-aware rules AND crit m/km offset
2. **Orchestration**: In `precompute.py` (not predictions.py) — keeps predict_series_finish_type() unchanged
3. **Priority**: time-gap > course_profile > race_type_only (Gemini's three-tier)
4. **Confidence cap**: 0.75 for course_profile, 0.60 for race_type_only (never exceeds time-gap)
5. **prediction_source**: String column on SeriesPrediction ("time_gap", "course_profile", "race_type_only")
6. **Race type inheritance**: >50% threshold, minimum 2 editions
7. **Past-only series**: Force-expand existing container card (not new component)
8. **Narrative**: Source-aware hedged language in generate_narrative() and finish_type_plain_english_with_source()
9. **Migration**: Explicit ALTER TABLE for prediction_source column
