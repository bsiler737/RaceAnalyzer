# RaceAnalyzer — New Racer User Stories (Prioritized)

> 50 user stories focused on the **new racer** persona, ranked by consensus across Claude, Gemini, and Codex.
>
> **Guiding principle:** The best user stories help a racer understand how the **strategy and tactics** of a race will play out — race classification, selection moments, and course-driven dynamics. Social, logistics, post-race, and visual polish features are deferred.

---

## Priority Bands

| Band | Meaning | Count |
|------|---------|-------|
| **P0** | Essential — directly answers "what kind of race is this and where will it be decided?" | 12 |
| **P1** | Supporting — provides context that strengthens tactical understanding | 11 |
| **P2** | Deferred — useful but not core to pre-race strategy; build later | 27 |

---

## P0 — Core Race Intelligence

These stories are the product. They answer the fundamental questions: What kind of race is this? Where does it split? What should I expect?

### 11. See a Predicted Finish Type for My Category `P0`
**As a** new racer, **I want to** see whether my specific category (e.g., Cat 4/5) historically ends in a bunch sprint, breakaway, or strung-out finish **so that** I know what kind of race to prepare for.

> **Consensus:** Unanimous P0 across all three models. This is the single most important feature — it classifies the race and sets the entire strategic frame.

---

### 19. See Predicted Key Moments on the Course Map `P0`
**As a** new racer, **I want** pins on the course map showing where the race typically splits apart, where attacks stick, and where regrouping happens **so that** I can anticipate the critical moments.

> **Consensus:** Unanimous P0. This is the holy grail — mapping selection moments onto the course. Gemini called it "the holy grail of race intelligence."

---

### 18. See a "What to Expect" Summary `P0`
**As a** new racer, **I want** a plain-language narrative describing what my race will probably look like — the pace off the start, where attacks happen, how the finish typically plays out — **so that** I can mentally prepare even though I've never done this event before.

> **Consensus:** Unanimous P0. Translates raw data into an actionable race script. This is where the product becomes indispensable.

---

### 3. See Climb Segments Highlighted on the Map `P0`
**As a** new racer, **I want** individual climbs color-coded by gradient on the course map **so that** I can immediately spot where the hard efforts will be.

> **Consensus:** Unanimous P0. Climbs are the primary selection mechanism in road racing. Gradient visualization directly shows where the race will be decided.

---

### 10. See Wind Exposure Zones on the Map `P0`
**As a** new racer, **I want** the map to show which sections are exposed (open farmland, ridgelines) versus sheltered **so that** I can anticipate where crosswinds and echelons might form.

> **Consensus:** Claude and Gemini P0. The most critical non-gravity selection factor. Echelons end races for riders who are out of position.

---

### 1. See an Interactive Course Map `P0`
**As a** new racer, **I want to** see the race course on a full interactive map with zoom and pan **so that** I can explore the route in detail and identify key turns, climbs, and landmarks before race day.

> **Consensus:** Claude and Gemini P0. Foundation for all spatial tactical intelligence — P0 features #3, #10, and #19 all live on this map.

---

### 2. View Elevation Profile Overlaid on the Map `P0`
**As a** new racer, **I want to** see an elevation profile synced to the map view **so that** when I hover over a climb on the profile, the corresponding section highlights on the map.

> **Consensus:** Claude and Gemini P0. Essential for understanding the physiological demands and pacing strategy.

---

### 12. See My Odds of Finishing in the Pack `P0`
**As a** new racer, **I want to** see an estimated probability of finishing with the main group versus getting dropped **so that** I can set realistic goals for myself.

> **Consensus:** Claude P0, Gemini P1. Directly shapes tactical approach — a racer expecting to get dropped races very differently from one expecting to contest the finish.

---

### 17. See a Drop Rate for My Category `P0`
**As a** new racer, **I want to** see what percentage of starters historically DNF or get pulled in my category **so that** I know how selective the race is and can prepare accordingly.

> **Consensus:** Claude P0, Gemini P1. Signals race selectivity — a 40% drop rate tells you the course is brutally selective.

---

### 20. See Weather-Adjusted Predictions `P0`
**As a** new racer, **I want** race predictions to factor in the weather forecast (wind, rain, heat) **so that** I understand how conditions might change the race dynamics.

> **Consensus:** Gemini P0, Claude P1. Weather fundamentally changes race classification — a flat course becomes a war of attrition in crosswinds.

---

### 28. See an Animated Race Replay from Past Editions `P0`
**As a** new racer, **I want to** watch a simplified animated replay showing how the gaps developed in previous editions **so that** I can visually understand where the race was decided.

> **Consensus:** Gemini P0. Visually proving where gaps opened in past editions is the most compelling way to show decisive race moments.

---

### 16. See Typical Finishing Speeds for My Category `P0`
**As a** new racer, **I want to** see average speeds from previous editions in my category **so that** I know whether I have the fitness to be competitive.

> **Consensus:** Claude P0, Gemini P1. Helps racers calibrate whether the race pace is within their ability — a prerequisite for any tactical plan.

---

## P1 — Supporting Context

These features add valuable context that strengthens the P0 core but aren't the primary tactical intelligence.

### 4. View Turn-by-Turn Course Notes `P1`
**As a** new racer, **I want** annotated turn-by-turn notes on the map (sharp corners, technical descents, narrow roads) **so that** I'm not surprised by dangerous sections on race day.

> **Rationale:** Gemini elevated this to P0 (positioning through technical sections is tactical), but Claude sees it as safety context rather than selection intelligence. Consensus: strong P1.

---

### 5. See Start and Finish Locations Clearly Marked `P1`
**As a** new racer, **I want** the start line, finish line, and any intermediate landmarks (KOM, sprint points) clearly marked on the map **so that** I understand the course flow at a glance.

> **Rationale:** Important for timing the final sprint effort and understanding course flow. Supporting, not central.

---

### 8. See a Road Surface and Conditions Summary `P1`
**As a** new racer, **I want to** know whether the course is fully paved, has gravel sections, or includes rough pavement **so that** I can choose the right tires and equipment.

> **Rationale:** Gemini elevated this (rough roads cause splits), but it's more about equipment prep than tactical strategy. Consensus: P1.

---

### 13. See a Difficulty Rating for My Category `P1`
**As a** new racer, **I want** each race rated on a 1-5 difficulty scale specific to my category **so that** I can pick beginner-friendly events to start with.

> **Rationale:** Useful for race selection, but drop rate (#17) and finish type (#11) provide richer tactical info. This is a simplified summary badge.

---

### 15. See How Big My Field Typically Is `P1`
**As a** new racer, **I want to** see the average and expected field size for my category at an upcoming race **so that** I know if I'll be in a group of 12 or 60.

> **Rationale:** Field size materially changes race dynamics (small fields = more attacks, large fields = bunch sprints). Important supporting context.

---

### 27. Learn Race Tactics for My Predicted Finish Type `P1`
**As a** new racer, **I want** tactical tips specific to the predicted race outcome (e.g., "In a bunch sprint: hold a wheel in the top 15 into the final corner") **so that** I have an actionable strategy even without experience.

> **Rationale:** Gemini rated P0 (actionable strategy), Claude rated P1 (derivative of finish type prediction). Consensus: strong P1 — very valuable but only useful after P0 predictions exist.

---

### 9. Download the Course to My Bike Computer `P1`
**As a** new racer, **I want to** export the course as a GPX file directly from the race page **so that** I can load it onto my Garmin or Wahoo for a pre-ride or race-day navigation.

> **Rationale:** Standard utility that enables pre-riding the course, which is itself tactical preparation.

---

### 7. Compare Two Courses Side by Side `P1`
**As a** new racer, **I want to** compare the elevation profiles of two races side by side **so that** I can pick the event that best matches my fitness and abilities.

> **Rationale:** Helps with race selection, not race-day tactics. Useful supporting feature.

---

### 30. See "Races Like This One" Comparisons `P1`
**As a** new racer, **I want to** see other races with similar course profiles and finish patterns **so that** if I liked one race, I can find more like it.

> **Rationale:** Leverages the race classification engine for discovery. Useful but not core race intelligence.

---

### 37. See Race Finish Type as a Visual Icon `P1`
**As a** new racer, **I want** finish types represented by distinctive icons (sprint bolt, breakaway figure, mountain peak) **so that** I can identify race character at a glance without reading labels.

> **Rationale:** Good UI shorthand for the P0 race classification. Small but valuable visual affordance.

---

### 40. Read Tips from Other Racers About This Event `P1`
**As a** new racer, **I want to** read short tips from people who've done this race before ("the final turn is sketchy when wet," "parking fills up early") **so that** I benefit from community knowledge.

> **Rationale:** Gemini elevated this — crowdsourced local knowledge often reveals hidden tactical nuances. Consensus: P1 (valuable but requires community infrastructure).

---

## P2 — Deferred

These stories are valuable but don't directly serve the core mission of pre-race tactical intelligence. Build after the P0/P1 foundation is solid.

### Race Day Preparation (all P2)

### 21. See a Pre-Race Checklist `P2`
**As a** new racer, **I want** a customized pre-race checklist based on the event type (crit vs. road race vs. TT) **so that** I don't forget essential gear, nutrition, or logistics.

---

### 22. See Parking and Venue Information `P2`
**As a** new racer, **I want to** see parking locations, registration hours, and venue details on a map **so that** I can plan my drive and arrive stress-free.

---

### 23. See the Race Schedule and My Start Time `P2`
**As a** new racer, **I want to** see when my category starts and the full day's schedule **so that** I can plan warmup time and know when to be at the line.

---

### 24. Get a Race-Day Timeline Notification Plan `P2`
**As a** new racer, **I want** a suggested timeline (arrive by X, warm up at Y, staging at Z) **so that** I don't show up too late or waste hours waiting around.

---

### 25. See Kit and Equipment Recommendations `P2`
**As a** new racer, **I want** suggestions on what to wear and bring based on weather, course type, and race format **so that** I show up with the right gear.

---

### Learning & Education (all P2)

### 26. See a Visual Explainer of Race Finish Types `P2`
**As a** new racer, **I want** illustrated explanations of what a bunch sprint, breakaway, solo win, and small group sprint look like **so that** I understand the terminology the app uses.

---

### 29. See a Glossary of Racing Terms in Context `P2`
**As a** new racer, **I want** racing jargon (peloton, echelon, domestique, field sprint) linked to quick definitions wherever it appears **so that** I'm never confused by the terminology.

---

### Visual Design & Experience (all P2)

### 6. View a 3D Terrain Flythrough of the Course `P2`
**As a** new racer, **I want to** watch a 3D flythrough animation of the course **so that** I can visualize the terrain and mentally rehearse the route before I drive out to the event.

> Expensive to build, lower tactical value than 2D course notes and climb highlighting.

---

### 31. See a Beautiful Race Card with Hero Image `P2`
**As a** new racer, **I want** each race displayed as a visually striking card with a course map thumbnail, terrain badge, and key stats **so that** browsing races feels engaging and informative.

---

### 32. See Color-Coded Difficulty Badges `P2`
**As a** new racer, **I want** difficulty ratings shown as color-coded badges (green = beginner-friendly, red = very hard) **so that** I can scan a list and quickly identify appropriate races.

---

### 33. See a Polished Race Preview Page `P2`
**As a** new racer, **I want** the race preview page to feel like a magazine feature — hero map, stats sidebar, narrative description, and contender photos — **so that** I get excited about the event.

---

### 34. See Smooth Animations and Transitions `P2`
**As a** new racer, **I want** the app to feel modern with smooth page transitions and micro-animations **so that** the experience feels premium and trustworthy.

---

### 35. View the App Beautifully on My Phone `P2`
**As a** new racer, **I want** the entire app to work flawlessly on mobile with touch-friendly maps and swipeable race cards **so that** I can browse races on my phone at a coffee shop.

---

### 36. See a Dark Mode Option `P2`
**As a** new racer, **I want** a dark mode toggle **so that** I can browse race info late at night without blinding myself.

---

### Social & Community (all P2)

### 38. See How Many People from My Club Are Registered `P2`
**As a** new racer, **I want to** see which of my teammates or club members are registered for a race **so that** I can coordinate and feel less alone as a newcomer.

---

### 39. See First-Timer Friendliness Rating `P2`
**As a** new racer, **I want** races tagged with a "first-timer friendly" badge when field sizes are small, courses are simple, and drop rates are low **so that** I can confidently choose my first event.

> Redundant if we ship drop rates (#17), field sizes (#15), and difficulty rating (#13).

---

### Calendar & Planning (all P2)

### 14. Get a Personalized Race Recommendation `P2`
**As a** new racer, **I want** the app to suggest my next best race based on my category, location, and skill level **so that** I don't have to guess which events are appropriate for me.

> Race selection is valuable, but the core product is race understanding, not matchmaking.

---

### 41. See a Visual Season Calendar Filtered to My Category `P2`
**As a** new racer, **I want** a beautifully designed calendar view showing only races available for my category, color-coded by difficulty **so that** I can plan my season at a glance.

---

### 42. Build a Personal Race Calendar `P2`
**As a** new racer, **I want to** "bookmark" races into a personal calendar **so that** I can plan my season and track which events I want to do.

---

### 43. See Distance from My Home to Each Race `P2`
**As a** new racer, **I want** each race card to show the driving distance and time from my location **so that** I can factor travel into my decision.

---

### 44. Get a "Season Starter Pack" of Recommended Races `P2`
**As a** new racer, **I want** the app to suggest a curated season of 5-8 races that progressively increase in difficulty **so that** I have a structured path from my first race to competitive fitness.

---

### 45. See Which Races Have Open Registration `P2`
**As a** new racer, **I want** a clear "Register Now" badge on races with open registration and a link to sign up **so that** I can go from discovery to registration in one click.

---

### Post-Race & Progress (all P2)

### 46. See My Result in Context After a Race `P2`
**As a** new racer, **I want to** see my finish position visualized — which gap group I was in, how far off the leaders — **so that** I understand how my race went beyond just a number.

---

### 47. Track My Progress Across Races `P2`
**As a** new racer, **I want to** see my results over time on a chart (finish percentile, gap to winner) **so that** I can see myself improving even if I'm not winning.

---

### 48. See How I Compare to Category Averages `P2`
**As a** new racer, **I want to** see how my finishing position and time compare to the category median **so that** I know whether I'm above or below the midpack.

---

### 49. Get a Post-Race "What Happened" Narrative `P2`
**As a** new racer, **I want** an auto-generated narrative of my race — "You finished in the second group, 45 seconds behind the lead group that split on the climb at mile 8" — **so that** I can understand the race story even if I was too deep in the pain cave to notice.

---

### 50. See Suggested Next Races Based on My Results `P2`
**As a** new racer, **I want** the app to suggest my next race based on how I performed — easier if I struggled, similar if I did well, harder if I dominated — **so that** I'm always challenged but not overwhelmed.

---

## Summary

| Band | Count | Stories |
|------|-------|---------|
| **P0** | 12 | #1, #2, #3, #10, #11, #12, #16, #17, #18, #19, #20, #28 |
| **P1** | 11 | #4, #5, #7, #8, #9, #13, #15, #27, #30, #37, #40 |
| **P2** | 27 | #6, #14, #21–26, #29, #31–36, #38–39, #41–50 |

### Consensus Notes

**Models consulted:** Claude (Opus 4.6), Gemini CLI, OpenAI Codex (GPT-5.4)

**Key agreements:**
- All three models agreed that #11 (Predicted Finish Type), #18 (What to Expect), and #19 (Key Moments on Map) are the most important features
- All three agreed that Race Day Prep (#21-25), Social (#38-40), Calendar (#41-45), Post-Race (#46-50), and Visual Polish (#31-36) are P2
- Gemini was most aggressive on P0 scope, including #4 (Turn-by-Turn), #8 (Road Surface), #27 (Tactics), and #28 (Replay)
- Codex (reviewing the implementation stories) reinforced that the product's core value is **predictive intelligence**, not logistics or post-race analytics
- Claude placed #12 (Pack Odds) and #17 (Drop Rate) in P0 where Gemini had them P1; consensus elevated them since they directly inform tactical approach

**Key disagreements resolved:**
- **#20 Weather-Adjusted:** Gemini P0, Claude P1 → Elevated to P0 because weather fundamentally changes race classification
- **#28 Animated Replay:** Gemini P0, Claude P1 → Elevated to P0 because visually showing where past races split is the strongest evidence for selection moments
- **#27 Tactics Tips:** Gemini P0, Claude P1 → Kept P1 because it's derivative of #11 (needs finish type prediction first)
- **#4 Turn-by-Turn:** Gemini P0, Claude P1 → Kept P1 because it's more safety than selection intelligence
