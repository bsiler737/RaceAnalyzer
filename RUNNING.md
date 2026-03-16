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

## Web UI

### Local Development

Start the FastAPI server with auto-reload:

```bash
python3 -m raceanalyzer serve --reload

# Custom port
python3 -m raceanalyzer serve --port 9000 --reload
```

Opens at http://localhost:8000 by default. The `--reload` flag watches for file changes.

You can also set `RACEANALYZER_DB_PATH` to point at a different database:

```bash
RACEANALYZER_DB_PATH=/path/to/raceanalyzer.db python3 -m raceanalyzer serve --reload
```

### Legacy Streamlit UI (deprecated)

```bash
python3 -m raceanalyzer ui
```

This still works but shows a deprecation warning. Use `serve` instead.

## Demo Data

Generate synthetic data for testing:

```bash
python3 -m raceanalyzer seed-demo --num-races 50 --seed 42
```

Remove demo data:

```bash
python3 -m raceanalyzer clear-demo --yes
```

## Typical Workflow (Local)

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

# 6. Launch web UI
python3 -m raceanalyzer serve --reload
```

---

## Fly.io Deployment

The app runs on Fly.io at **https://raceanalyzer.fly.dev** (or custom domain `raceanalyzer.app` if configured).

### Architecture

- **1 shared-CPU machine**, 512MB RAM, `sjc` (San Jose) region
- **1GB persistent volume** (`ra_data`) mounted at `/data` for the SQLite database
- Machine auto-stops when idle, auto-starts on incoming requests (~3-5s cold start)
- Health check at `/health` every 30s
- Feed query cache (5-minute TTL) keeps warm page loads at ~550ms

### First-Time Setup

If you're setting up from scratch (one-time):

```bash
# Install flyctl if you haven't
brew install flyctl

# Auth
fly auth login

# Create the app
fly apps create raceanalyzer

# Create persistent volume (1GB, sjc region)
fly volumes create ra_data --region sjc --size 1

# First deploy — the Dockerfile copies data/raceanalyzer.db into the image
# as a seed. The CMD auto-copies it to the volume on first boot.
fly deploy
```

### Deploying Code Updates

After making code changes locally:

```bash
# 1. Commit your changes
git add -A && git commit -m "your message"

# 2. Push to GitHub
git push origin main

# 3. Deploy to Fly.io
fly deploy

# Or deploy immediately (skip build cache):
fly deploy --now
```

The deploy builds a Docker image, pushes it to Fly's registry, and rolls it out. Typical deploy time: ~30-60 seconds.

### Updating the Database on Fly.io

The data pipelines (scraping, startlists, predictions) run via `fly ssh console`. This executes commands directly on the running machine where the volume-mounted DB lives.

```bash
# Discover upcoming races
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db fetch-calendar"

# Fetch startlists with power rankings
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db fetch-startlists"

# Fetch RWGPS polylines for course maps
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db fetch-polylines"

# Extract elevation/course profiles
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db elevation-extract"
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db course-profile-extract"

# Compute predictions
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db compute-predictions"

# Build/rebuild series groupings
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db build-series"

# Classify finish types
fly ssh console -C "python -m raceanalyzer --db /data/raceanalyzer.db classify --all"
```

**Important:** Always pass `--db /data/raceanalyzer.db` so it writes to the persistent volume, not the seed copy.

#### Replacing the Database Entirely

If you've built a fresh DB locally and want to push it to Fly:

```bash
# 1. Copy the local DB to the running machine's volume
fly ssh sftp shell
>> put data/raceanalyzer.db /data/raceanalyzer.db

# 2. Restart so the app picks up the new DB and clears the query cache
fly machines restart
```

### Monitoring & Troubleshooting

#### Check app status

```bash
fly status          # Machine state, health checks, version
fly logs            # Live logs (Ctrl-C to stop)
fly logs --no-tail  # Recent logs snapshot
```

#### Health check

```bash
curl https://raceanalyzer.fly.dev/health
# Expected: {"status":"ok","series_count":798}
```

#### Common Issues

**503 "no known healthy instances"**

The Fly proxy lost track of the machine, usually after a scaling operation or OOM. Fix:

```bash
fly machines restart
```

Wait 10-15 seconds for health checks to pass, then try again.

**500 Internal Server Error**

Check the logs for the traceback:

```bash
fly logs --no-tail | grep -E "Error|Traceback|File" | tail -20
```

Common causes:
- `ModuleNotFoundError` — a new import was added but not included in the Docker build. Check `.dockerignore` and `pyproject.toml`.
- `sqlite3.OperationalError: no such table` — the seed DB is out of date. Re-deploy or SFTP the current DB.

**Machine won't start / OOM**

```bash
# Check memory usage
fly scale show

# If stuck, destroy and recreate
fly machines destroy <MACHINE_ID>
fly deploy
```

The volume persists even if the machine is destroyed — your DB is safe.

**Cold start is slow (~3-5s)**

This is expected with `min_machines_running = 0`. The machine sleeps when idle and wakes on the first request. To eliminate cold starts (~$2/mo extra):

Edit `fly.toml`:
```toml
min_machines_running = 1
```

Then `fly deploy`.

**Query cache is stale**

The feed query cache has a 5-minute TTL. After running pipeline commands via `fly ssh console`, the cache will refresh automatically within 5 minutes. To force an immediate refresh, restart the machine:

```bash
fly machines restart
```

### Fly.io Configuration Reference

Key settings in `fly.toml`:

| Setting | Value | Purpose |
|---------|-------|---------|
| `primary_region` | `sea` | Seattle (closest to PNW users) |
| `internal_port` | `8000` | FastAPI listens here |
| `force_https` | `true` | Redirect HTTP to HTTPS |
| `auto_stop_machines` | `stop` | Sleep when idle |
| `auto_start_machines` | `true` | Wake on request |
| `min_machines_running` | `0` | No always-on cost |
| `soft_limit` | `25` | Max concurrent requests before queuing |
| `hard_limit` | `50` | Max concurrent requests before rejection |
| `memory` | `512mb` | RAM (256MB is too small, causes OOM) |
| `mounts.source` | `ra_data` | Persistent volume name |
| `mounts.destination` | `/data` | Where the DB lives in the container |
