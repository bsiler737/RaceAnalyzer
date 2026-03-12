# Running RaceAnalyzer

All commands use `python3 -m raceanalyzer`. Add `--verbose` (`-v`) for debug logging, or `--db PATH` to use a different database file.

## Setup

Initialize the database (creates all tables):

```bash
python3 -m raceanalyzer init
```

## Scraping Historical Race Data

Scrape results from road-results.com:

```bash
# Single race by ID
python3 -m raceanalyzer scrape --race-id 1000

# Range of race IDs
python3 -m raceanalyzer scrape --start 1 --end 500

# Re-scrape already-scraped races
python3 -m raceanalyzer scrape --start 1 --end 500 --no-skip
```

Re-ingest from previously archived raw HTML/JSON files (useful after a DB reset):

```bash
python3 -m raceanalyzer ingest-raw
```

## Building Series & Classifying

Group races into series by normalized name:

```bash
python3 -m raceanalyzer build-series
```

Classify finish types (bunch sprint, breakaway, etc.):

```bash
# All unclassified races
python3 -m raceanalyzer classify --all

# Single race
python3 -m raceanalyzer classify --race-id 1000

# Custom gap threshold (default: 3.0 seconds)
python3 -m raceanalyzer classify --all --gap-threshold 2.5
```

## Course & Elevation Data

Match series to RideWithGPS routes:

```bash
python3 -m raceanalyzer match-routes

# Preview without saving
python3 -m raceanalyzer match-routes --dry-run
```

Extract elevation data from matched RWGPS routes:

```bash
python3 -m raceanalyzer elevation-extract

# Re-extract even if data exists
python3 -m raceanalyzer elevation-extract --force
```

Extract course profiles and detect climbs:

```bash
python3 -m raceanalyzer course-profile-extract

# Re-extract
python3 -m raceanalyzer course-profile-extract --force
```

Manually override a series' RWGPS route:

```bash
python3 -m raceanalyzer override-route SERIES_ID RWGPS_ROUTE_ID
```

## Upcoming Races & Startlists

Discover upcoming PNW races from road-results/GraphQL:

```bash
python3 -m raceanalyzer fetch-calendar

# Fall back to BikeReg API
python3 -m raceanalyzer fetch-calendar --source bikereg --region WA --days-ahead 60
```

Fetch pre-registered riders with power rankings from road-results predictor:

```bash
python3 -m raceanalyzer fetch-startlists

# Preview which races would be refreshed
python3 -m raceanalyzer fetch-startlists --dry-run

# Fall back to BikeReg
python3 -m raceanalyzer fetch-startlists --source bikereg
```

Each race is refreshed at most once per 24 hours. Past-dated races are automatically skipped.

## UI

Launch the Streamlit web interface:

```bash
python3 -m raceanalyzer ui

# Custom port
python3 -m raceanalyzer ui --port 8502
```

Opens at http://localhost:8501 by default. You can also set `RACEANALYZER_DB_PATH` before launching.

## Demo Data

Generate synthetic data for testing:

```bash
python3 -m raceanalyzer seed-demo --num-races 50 --seed 42
```

Remove demo data:

```bash
python3 -m raceanalyzer clear-demo --yes
```

## Typical Workflow

```bash
# 1. Initialize
python3 -m raceanalyzer init

# 2. Scrape historical results
python3 -m raceanalyzer scrape --start 1 --end 15000

# 3. Group into series and classify
python3 -m raceanalyzer build-series
python3 -m raceanalyzer classify --all

# 4. Match routes and extract elevation
python3 -m raceanalyzer match-routes
python3 -m raceanalyzer elevation-extract
python3 -m raceanalyzer course-profile-extract

# 5. Discover upcoming races and fetch startlists
python3 -m raceanalyzer fetch-calendar
python3 -m raceanalyzer fetch-startlists

# 6. Launch UI
python3 -m raceanalyzer ui
```
