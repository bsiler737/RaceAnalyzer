# User Journeys: Beginning Bike Racer

> **Persona:** Beginner PNW road racer (Cat 4/5, 1-3 seasons). See [BEGINNER_RACER_PERSONA.md](BEGINNER_RACER_PERSONA.md).
>
> **Source:** Derived from the use cases in [USE_CASES_FEED_FIRST_GLANCE.md](USE_CASES_FEED_FIRST_GLANCE.md).

---

## 1. "What's happening this weekend?"

**Trigger:** It's Tuesday evening. The racer opens the app to see if there's anything worth racing this Saturday.

**Journey:** They open the feed and immediately see races grouped by month, with the current week's races at the top showing "in 4 days" and "in 5 days" countdowns. They scan 4-5 collapsed cards on screen — each showing name, date, location, and terrain at a glance. They spot a crit in Seattle (20 min away, in 4 days) and a road race in Drain, OR (4 hours away, in 5 days). They skip the road race instantly — too far — and tap into the crit. Total time to find a relevant race: under 10 seconds.

**Use cases:** FO-05, FO-06, FO-08, FG-01

---

## 2. "Can I survive this race?"

**Trigger:** The racer found an upcoming road race and wants to know if they'll get dropped.

**Journey:** On the card, they see "Rolling — 62 km — 800m gain" and "12% drop rate (low)." The finish type prediction reads: "The group usually stays together and sprints for the finish." They think: "Low drop rate, bunch sprint — I can sit in the pack." They tap into the race preview and see the interactive elevation profile with climb callouts: "Climb 1: km 18-20, 2.1 km at 6.2% avg — this is where the field usually thins but regroups on the descent." They study the profile, mentally rehearse surviving the climb, and decide they're in.

**Use cases:** FG-03, FG-04, FG-06, DD-01, DD-02

---

## 3. "Are my friends doing this one?"

**Trigger:** The racer is on the fence about a race and wants to know if anyone from their team is going.

**Journey:** They previously entered their team name ("Audi Cycling") in the sidebar — a one-time setup. Now, scanning the feed, they notice a badge on the Seward Park Crit card: "Jake, Maria registered." That's the tipping point. They click the card, see the full startlist grouped by team — their team has 3 riders, Team Rapha has 6. They text Jake to coordinate logistics and hit the register button.

**Use cases:** MT-01, MT-02, FG-02, DD-03

---

## 4. "I only race crits — show me just crits"

**Trigger:** The racer has done three criteriums and isn't ready for a road race yet. The feed is showing road races, gravel events, and time trials they'll never do.

**Journey:** They open the discipline filter in the sidebar, select "Road" to remove gravel and MTB events. Then they use the race type filter to select "Criterium" only. The feed shrinks from 40 races to 12 — all crits, sorted by month. They set their state filter to "WA" since they won't drive to Oregon for a Cat 5 crit. Now they see 7 crits across March-June, all within driving distance. These filters persist — next time they open the app, the same view is waiting.

**Use cases:** FO-01, FO-02, FO-03, FO-04

---

## 5. "What kind of racer does well at Banana Belt?"

**Trigger:** The racer keeps hearing about Banana Belt Road Race and wants to know if it suits their strengths.

**Journey:** They find Banana Belt in the feed. The card shows "Hilly — 85 km — 1200m gain" and "The field splits apart on the climbs." They think: "That sounds hard." They tap into the preview and read the expanded racer type description: "This race favors climbers and riders comfortable with repeated efforts. In 4 of 5 recent editions, the field split on the main climb and never regrouped. Riders who can sustain threshold power on 3-5 minute climbs tend to finish well." Below that, a historical finish type visualization shows "selective" icons for 4 of 5 years. They decide to skip this one and look for flatter races.

**Use cases:** FG-03, FG-04, DD-04, DD-05

---

## 6. "This race looks like that crit I did last month"

**Trigger:** The racer did the Seward Park Crit and liked it. They want to find similar races.

**Journey:** They open the Seward Park Crit detail page and see a "Similar to" section: "Cherry Pie Crit, Marymoor Monday Night Crit." Both are flat crits with similar distances and bunch sprint finishes. They recognize Marymoor — a friend mentioned it. They tap through to the Marymoor card, see it's "in 12 days," and the course profile looks almost identical to Seward Park. Familiarity collapses their anxiety. They register.

**Use cases:** DD-06, FG-03, FG-04

---

## 7. "Plan my spring season"

**Trigger:** It's early March. The racer wants to map out which races to target through June.

**Journey:** They set their filters (Road discipline, WA + OR, Cat 5) and see the feed in month-grouped agenda view. March has 3 races, April has 5, May has 4, June has 3. They scan the collapsed cards — each showing name, countdown, location, terrain, and finish type — and mentally flag: "March: one crit to warm up. April: two crits and that flat road race. May: try Banana Belt if I'm feeling strong." They don't expand a single card during this scan — the collapsed view gives them everything they need to sketch a season. They come back later to dive deep into the ones they flagged.

**Use cases:** FO-01, FO-03, FO-06, FO-08, FG-01, FG-03

---

## 8. "How big is the field — will I be racing alone?"

**Trigger:** The racer is looking at a small-town road race and wonders if it's worth the drive.

**Journey:** On the card, they see "Usually 8-12 starters" next to the field size indicator. That's tiny — basically a group ride with a finish line. They compare it to the next weekend's crit showing "Usually 45-55 starters." A bigger field means a real peloton, more drafting, and a more authentic race experience. They skip the small-town race and target the larger crit. The field size data — visible without any clicks — saved them a wasted decision.

**Use cases:** FG-05, FO-06

---

## 9. "I want to study the course before race day"

**Trigger:** The racer has registered for a road race happening Saturday. It's Thursday evening and they want to know what they're getting into.

**Journey:** They find the race in the feed (showing "in 2 days") and tap into the full preview. The hero visualization is the interactive elevation profile with color-coded climb segments and gradient bands. They see three climbs: a gentle 2% roller at km 5, a sustained 5% climb at km 22, and a sharp 8% kicker at km 35. Each climb has a callout: "Climb 2 at km 22 is where the selection usually happens — expect the pace to increase here." Below the profile is a course map showing the route geographically, with start/finish and climb locations marked. They screenshot the profile and share it with their teammate: "Survive climb 2, recover on the descent, hang on through the kicker."

**Use cases:** DD-01, DD-02, DD-07, FO-05

---

## 10. "I just opened the app for the first time — show me what this is"

**Trigger:** A teammate sent the racer a link. They've done two races total and don't really know what they're looking at.

**Journey:** The feed loads fast (under 1 second). They see month-grouped cards with plain-English descriptions they actually understand — no jargon, no power data, no insider terminology. The first card says "Seward Park Crit — in 6 days — Seattle, WA" with "Flat — 30 km — 50m gain" and "The group usually stays together and sprints for the finish. 8% drop rate (low)." They think: "Oh, flat, everyone finishes, bunch sprint — I know what that is." They set their team name in the sidebar when prompted. They browse a few cards, expand one to see the course profile, and realize: "This app tells me what races are like before I show up." They bookmark it and come back the next week.

**Use cases:** PF-01, PF-02, FO-06, FG-01, FG-03, FG-04, FG-06, MT-01

---

## Use Case Coverage Matrix

| Journey | First Glance | Detail Dive | My Team | Feed Org | Performance |
|---------|-------------|-------------|---------|----------|-------------|
| 1. Weekend races | FG-01 | | | FO-05, FO-06, FO-08 | |
| 2. Can I survive? | FG-03, FG-04, FG-06 | DD-01, DD-02 | | | |
| 3. Friends going? | FG-02 | DD-03 | MT-01, MT-02 | | |
| 4. Just crits | | | | FO-01, FO-02, FO-03, FO-04 | |
| 5. Racer type fit | FG-03, FG-04 | DD-04, DD-05 | | | |
| 6. Similar races | FG-03, FG-04 | DD-06 | | | |
| 7. Season planning | FG-01, FG-03 | | | FO-01, FO-03, FO-06, FO-08 | |
| 8. Field size | FG-05 | | | FO-06 | |
| 9. Course study | | DD-01, DD-02, DD-07 | | FO-05 | |
| 10. First visit | FG-01, FG-03, FG-04, FG-06 | | MT-01 | FO-06 | PF-01, PF-02 |
