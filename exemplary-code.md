# Exemplary Code from Reference Projects

The top 5 projects from our cloned examples, ranked by alignment with the research best practices from `research-findings.md`. For each project, we identify the specific code patterns worth emulating when building RaceAnalyzer.

---

## 1. `road-results` — The Road-Results.com Scraper

**Why #1**: This is the only project that scrapes our primary data source. It discovered the hidden JSON API, implements async parallel fetching, stores results in a relational schema, and applies TrueSkill ratings — hitting 4 of our 6 pipeline stages in one project.

### Best Practice A: JSON API Discovery Over HTML Scraping

The project bypasses fragile HTML parsing by constructing a direct JSON download URL from each race page. This is the single most important shortcut for our project.

**File**: [examples/road-results/scraping.py](examples/road-results/scraping.py), lines 54-65

```python
def scrape_race_page(race_id, html):
    """Scrapes a single race page for metadata and the JSON download URL."""
    metadata = get_metadata(html)
    if metadata:
        name, date, loc = metadata
        return {
            'race_id': race_id,
            'name': name,
            'date': date,
            'loc': loc,
            'json_url': f'downloadrace.php?raceID={race_id}&json=1',
        }
```

**What it accomplishes**: Instead of parsing complex HTML tables for every result field, it constructs the `downloadrace.php?raceID={ID}&json=1` endpoint URL, which returns structured JSON with 29 fields per result (place, time, rider name, team, points, DNF flags, age, license, field size). Only race metadata (name, date, location) requires HTML parsing.

### Best Practice B: Lightweight Regex for Metadata Extraction

For the small amount of HTML parsing needed (race name, date, location), the project uses compiled regex rather than a full HTML parser — simpler and faster for well-structured pages.

**File**: [examples/road-results/scraping.py](examples/road-results/scraping.py), lines 10-12, 28-46

```python
metadata_regex = re.compile(r'resultstitle" >(.*?)[\n\r]')
date_regex = re.compile(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})')

def get_metadata(html):
    """Parses race metadata from HTML using regex."""
    m = metadata_regex.search(html)
    if m:
        metadata = m.group(1)
        items = metadata.split('&bull;')
        name = items[0].strip()
        date = items[1].strip()
        loc = items[2].split()[0] if len(items) > 2 else None
        return name, date, loc
```

**What it accomplishes**: Two regex patterns extract all needed metadata from the resultstitle HTML tag, splitting on the `&bull;` separator. This avoids importing BeautifulSoup for a trivial extraction task.

### Best Practice C: Async Parallel Fetching with FuturesSession

Scraping 13,000+ races sequentially would take days. The project uses `requests_futures` with 8 workers for concurrent HTTP requests.

**File**: [examples/road-results/scraping.py](examples/road-results/scraping.py), lines 17-26

```python
def get_futures(max_id=13000):
    """Fetches race pages asynchronously."""
    session = FuturesSession(max_workers=8)
    url = 'https://results.bikereg.com/race/'
    futures = {i: session.get(url + str(i)) for i in range(1, max_id) if i not in BAD_IDS}
    return futures

def get_results_futures(races):
    """Fetches JSON results asynchronously."""
    session = FuturesSession(max_workers=8)
    url = 'https://results.bikereg.com/'
    futures = {r.race_id: session.get(url + r.json_url) for r in races}
    return futures
```

**What it accomplishes**: Two-phase async fetching — first fetch all race HTML pages in parallel to extract metadata and JSON URLs, then fetch all JSON result files in parallel. The 8-worker pool balances throughput against rate limiting.

### Best Practice D: Three-Table Relational Schema

The database design cleanly separates races, results, and racers with TrueSkill rating columns built in.

**File**: [examples/road-results/model.py](examples/road-results/model.py), lines 105-115 (Races), 287-310 (Results), 217-230 (Racers)

```python
class Races(db.Model):
    race_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    date = db.Column(db.DateTime)
    loc = db.Column(db.String)
    json_url = db.Column(db.String)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    categories = db.Column(ARRAY(db.String))
    num_racers = db.Column(ARRAY(db.Integer))

class Results(db.Model):
    ResultID = db.Column(db.Integer, primary_key=True)
    Place = db.Column(db.Integer)
    Name = db.Column(db.String)
    Age = db.Column(db.Integer)
    RaceName = db.Column(db.String)
    RaceCategoryName = db.Column(db.String)
    race_id = db.Column(db.Integer)
    RacerID = db.Column(db.Integer)
    # TrueSkill rating columns
    prior_mu = db.Column(db.Float)
    prior_sigma = db.Column(db.Float)
    mu = db.Column(db.Float)
    sigma = db.Column(db.Float)
    predicted_place = db.Column(db.Integer)

class Racers(db.Model):
    RacerID = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String)
    mu = db.Column(db.Float)
    sigma = db.Column(db.Float)
    num_races = db.Column(db.Integer)
```

**What it accomplishes**: Rating columns (`mu`, `sigma`, `prior_mu`, `prior_sigma`) live directly on Results, enabling per-race rating snapshots. Racers holds the current cumulative rating. The `predicted_place` column stores pre-race predictions for later validation.

### Best Practice E: TrueSkill Rating with Chronological Processing

Races are processed in date order, and ratings are updated per category within each race.

**File**: [examples/road-results/ratings.py](examples/road-results/ratings.py), lines 13-14, 16-89

```python
env = ts.TrueSkill(mu=MU, sigma=SIGMA, draw_probability=0)

def get_all_ratings(session):
    """Process all races chronologically, updating TrueSkill ratings."""
    races = session.query(Races).order_by(Races.date).all()
    for race in races:
        results = session.query(Results).filter_by(race_id=race.race_id)
        categories = results.with_entities(Results.RaceCategoryName).distinct()
        for cat in categories:
            cat_results = results.filter_by(RaceCategoryName=cat[0])
            cat_results = cat_results.order_by(Results.Place).all()
            # Store prior ratings, run TrueSkill, update results and racers
            predicted_places = get_predicted_places(cat_results, session)
            new_ratings = run_trueskill(cat_results, session)
            # Update both Results (per-race snapshot) and Racers (cumulative)
```

**What it accomplishes**: Chronological processing ensures ratings reflect only past performance. Per-category processing within each race means a Cat 3 rider's rating isn't affected by Pro/1/2 results at the same event. The dual update (Results for snapshots, Racers for current) enables both historical analysis and prediction.

---

## 2. `PerfoRank` — Race Clustering + Cluster-Specific TrueSkill

**Why #2**: This is the most academically rigorous approach to the core prediction problem. It implements the exact architecture our research recommends: cluster races by type, then rate riders per cluster. Published in *Machine Learning* (Springer, 2024).

### Best Practice A: Elevation-Based Race Clustering with Climb Detection

Automatically classifies race courses by terrain using GPX elevation data and scipy peak detection.

**File**: [examples/PerfoRank/FEClustering.ipynb](examples/PerfoRank/FEClustering.ipynb), lines 89-112

```python
from scipy.signal import find_peaks

def get_number_peaks(elevation_profile, prominence):
    """Count climbs of a given difficulty using peak prominence."""
    peaks, properties = find_peaks(elevation_profile, prominence=prominence)
    return len(peaks)

# Climb category thresholds (prominence in meters):
# Cat 4: 80m, Cat 3: 160m, Cat 2: 320m, Cat 1: 640m, HC: 800m
features['cat4_climbs'] = get_number_peaks(elev, 80)
features['cat3_climbs'] = get_number_peaks(elev, 160)
features['cat2_climbs'] = get_number_peaks(elev, 320)
features['cat1_climbs'] = get_number_peaks(elev, 640)
features['hc_climbs'] = get_number_peaks(elev, 800)

# Location of last climb as fraction of race distance (per category)
features['last_cat4_position'] = last_peak_position(elev, 80) / len(elev)
features['last_cat3_position'] = last_peak_position(elev, 160) / len(elev)
```

**What it accomplishes**: Transforms raw GPX elevation profiles into 10 structured features (5 climb counts + 5 last-climb positions) plus 15 surface type features. The prominence thresholds match standard cycling climb categories. The "last climb position" feature captures whether the race ends with a climb (summit finish) or on flat ground — a key predictor of finish type.

### Best Practice B: Constrained K-Means with Domain Knowledge

Uses must-link and cannot-link constraints from expert annotations to guide clustering.

**File**: [examples/PerfoRank/FEClustering.ipynb](examples/PerfoRank/FEClustering.ipynb), lines 3167-3240

```python
def transitive_closure(must_link_pairs):
    """Propagate must-link constraints through connected components."""
    # If A must-link B and B must-link C, then A must-link C
    graph = defaultdict(set)
    for a, b in must_link_pairs:
        graph[a].add(b)
        graph[b].add(a)
    # BFS to find all connected components
    ...

def violate_constraints(point, cluster_id, must_link, cannot_link):
    """Check if assigning point to cluster violates any constraint."""
    for ml_point in must_link.get(point, []):
        if assignments[ml_point] != cluster_id:
            return True
    for cl_point in cannot_link.get(point, []):
        if assignments[cl_point] == cluster_id:
            return True
    return False
```

**What it accomplishes**: Standard K-Means can't encode domain knowledge like "Paris-Roubaix and Tour of Flanders are the same type of race" or "a sprint stage is fundamentally different from a mountain stage." COP-KMeans enforces these constraints during assignment, producing clusters that align with cycling experts' understanding. The transitive closure propagation means annotating a few pairs constrains many more.

### Best Practice C: XGBoost LambdaMART for Ranking Prediction

Uses a learn-to-rank objective that naturally handles variable-size race fields.

**File**: [examples/PerfoRank/CaseStudy.ipynb](examples/PerfoRank/CaseStudy.ipynb), lines 9380-9390, 21783

```python
import xgboost as xgb

model = xgb.XGBRanker(
    booster='gbtree',
    objective='rank:pairwise',   # Pairwise ranking loss
    random_state=42,
    learning_rate=learning_rate,
    max_depth=max_depth,
    reg_alpha=reg_alpha
)

# Group structure: tells XGBoost which rows belong to the same race
groups = train_data.groupby('RaceName').size().to_numpy()

model.fit(X_train, y_train, group=groups, verbose=True)
```

**What it accomplishes**: The `rank:pairwise` objective internally decomposes each race into all (i,j) rider pairs and learns to score higher-finishing riders above lower-finishing ones. The `group` parameter defines race boundaries so pairs are only formed within the same race. This handles the variable field size problem (15-rider race vs. 200-rider race) naturally, without padding or truncation.

### Best Practice D: Cluster-Specific Skill as Prediction Features

The key innovation: TrueSkill ratings computed per race cluster become features for the final prediction model.

**File**: [examples/PerfoRank/CaseStudy.ipynb](examples/PerfoRank/CaseStudy.ipynb), lines 21228-21231

```python
# Merge cluster-specific TrueSkill ratings into training data
stacked_skills = pd.concat(list_of_dfs)  # 9 cluster rating tables stacked
stacked_skills = stacked_skills.rename(columns={'index': 'ActualName'})

# Join on BOTH race name and rider name — ensures correct cluster's rating
train_sel = pd.merge(
    train_sel, stacked_skills,
    on=['RaceName', 'ActualName'], how='left'
)

# Default rating for riders never seen in this cluster
train_sel.loc[train_sel['Mu'].isna(), ['Mu', 'Sigma']] = [25, 8.3333]
```

**What it accomplishes**: A sprinter's mountain cluster rating will be low (default 25), while their sprint cluster rating will be high. When predicting a sprint stage, the model sees the high sprint rating and predicts well. When predicting a mountain stage, the model sees the low mountain rating and correctly predicts poorly. This is the two-stage architecture our research recommends: classify the race type, then use type-specific ratings.

---

## 3. `procyclingstats` — The Gold Standard Scraping Library

**Why #3**: Best-in-class architecture for a cycling data scraping library. Its class-per-entity pattern, flexible field selection, and layered error handling are exactly what we need for our road-results.com scraper.

### Best Practice A: Class-Per-Entity with Auto-Discovery

Each cycling entity (Race, Stage, Rider, Team) has a dedicated scraper class. A universal `parse()` method auto-discovers all parsing methods via introspection.

**File**: [examples/procyclingstats/procyclingstats/scraper.py](examples/procyclingstats/procyclingstats/scraper.py), lines 179-227

```python
def parse(self,
          exceptions_to_ignore=(ExpectedParsingError,),
          none_when_unavailable=True):
    """Auto-discover and call all parsing methods, returning a unified dict."""
    parsing_methods = self._parsing_methods()
    parsed_data = {}
    for method_name, method in parsing_methods:
        try:
            parsed_data[method_name] = method()
        except exceptions_to_ignore:
            if none_when_unavailable:
                parsed_data[method_name] = None
    return parsed_data

def _parsing_methods(self):
    """Introspect class for all public parsing methods."""
    return [
        (name, getattr(self, name))
        for name in dir(self)
        if not name.startswith('_')
        and callable(getattr(self, name))
        and name not in self._public_nonparsing_methods
    ]
```

**What it accomplishes**: Adding a new field to a scraper is as simple as adding a new public method — `parse()` will automatically discover and call it. Users can call `race.parse()` for everything, or `race.name()` for a single field. The exception handling means one broken field doesn't crash the entire parse.

### Best Practice B: Flexible Field Selection with Validation

Table-returning methods accept `*args` to request only specific fields, with validation against available fields.

**File**: [examples/procyclingstats/procyclingstats/utils.py](examples/procyclingstats/procyclingstats/utils.py), lines 193-209

```python
def parse_table_fields_args(args, available_fields, table_parser):
    """Validate requested fields against available fields."""
    if args:
        for arg in args:
            if arg not in available_fields:
                raise ValueError(
                    f"Invalid field '{arg}'. Available: {available_fields}")
        return list(args)
    return list(available_fields)
```

Usage in [examples/procyclingstats/procyclingstats/stage_scraper.py](examples/procyclingstats/procyclingstats/stage_scraper.py), lines 354-380:

```python
def results(self, *args):
    """
    Parse stage results.

    :param args: Fields to include. Available:
        rank, status, rider_name, rider_url, rider_number,
        team_name, team_url, age, nationality, time, bonus,
        pcs_points, uci_points
    """
    available_fields = ("rank", "status", "rider_name", "rider_url",
                       "rider_number", "team_name", "team_url", "age",
                       "nationality", "time", "bonus", "pcs_points",
                       "uci_points")
    fields = parse_table_fields_args(args, available_fields, ...)
```

**What it accomplishes**: `stage.results("rank", "rider_name", "time")` returns only 3 fields instead of all 13 — faster parsing and cleaner output. Invalid field names raise `ValueError` immediately with a helpful message listing available options. This pattern is directly transferable to our road-results scraper.

### Best Practice C: Two-Tier Error Semantics

Separates "expected missing data" from "unexpected structural changes" with distinct exception types.

**File**: [examples/procyclingstats/procyclingstats/errors.py](examples/procyclingstats/procyclingstats/errors.py), lines 4-30

```python
class ExpectedParsingError(Exception):
    """Data can't be parsed due to known missing/unavailable data.

    Examples: race cancelled, page type doesn't have this field,
    edition unavailable. Caught by default in parse().
    """

class UnexpectedParsingError(Exception):
    """Unknown parsing issue, likely HTML structure change.

    Examples: parsed field count doesn't match table rows,
    CSS selector returns unexpected content.
    NOT caught by parse() — forces developer attention.
    """
```

**What it accomplishes**: `ExpectedParsingError` is silently caught (returns None), because a cancelled race or missing stage data is normal. `UnexpectedParsingError` propagates and crashes, because it signals the website changed its HTML structure and the scraper needs updating. This prevents silent data quality degradation — the most dangerous failure mode for a scraping pipeline.

### Best Practice D: Resilient HTTP with Cloudflare Bypass

Shared session with retry logic, exponential backoff, and optional Cloudflare bypass.

**File**: [examples/procyclingstats/procyclingstats/scraper.py](examples/procyclingstats/procyclingstats/scraper.py), lines 105-159

```python
class Scraper:
    _session = requests.Session()        # Shared session for cookies
    _scraper = None                       # Optional cloudscraper

    def _make_request(self, url):
        """Fetch with 3 retries, exponential backoff, Cloudflare detection."""
        for attempt in range(3):
            try:
                if self._scraper:
                    response = self._scraper.get(url)
                else:
                    response = self._session.get(url, headers=BROWSER_HEADERS)

                if response.status_code == 403 or 'Just a moment' in response.text:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return response.text
            except Exception:
                time.sleep(2 ** attempt)
                continue
        raise ConnectionError(f"Failed after 3 retries: {url}")
```

**What it accomplishes**: Class-level session sharing maintains cookies across requests. The retry loop with exponential backoff (1s, 2s, 4s) handles transient failures. Cloudflare "Just a moment" detection triggers retries rather than parsing garbage HTML. This is essential for scraping thousands of pages reliably.

---

## 4. `skelo` — Elo Ratings with sklearn Interface

**Why #4**: Cleanest implementation of a rating system with the exact interface pattern we need. Its temporal validity tracking prevents data leakage — a critical requirement for honest prediction evaluation.

### Best Practice A: sklearn-Compatible Rating Estimator

Wraps Elo/Glicko-2 into sklearn's `fit/predict/predict_proba` API, enabling use with GridSearchCV and Pipelines.

**File**: [examples/skelo/skelo/model/elo.py](examples/skelo/skelo/model/elo.py), lines 74-105

```python
class EloEstimator(RatingEstimator):
    """sklearn-compatible Elo rating estimator."""
    RATING_MODEL_CLS = EloModel
    RATING_MODEL_ATTRIBUTES = [
        'default_k',
        'k_fn',
        'initial_value',
        'initial_time',
    ]

    def __init__(self, initial_value=1500, default_k=20, k_fn=None, initial_time=0):
        self.initial_value = initial_value
        self.default_k = default_k
        self.k_fn = k_fn
        self.initial_time = initial_time
```

Usage pattern:
```python
from skelo.model.elo import EloEstimator

elo = EloEstimator(initial_value=1500, default_k=20)
elo.fit(X_train, y_train)           # X = (player1, player2, timestamp)
probs = elo.predict_proba(X_test)   # Returns [P(p1 wins), P(p2 wins)]

# Works with sklearn GridSearchCV:
from sklearn.model_selection import GridSearchCV
grid = GridSearchCV(EloEstimator(), {'default_k': [10, 20, 32]})
```

**What it accomplishes**: Rating system hyperparameters (K factor, initial value) become tunable via sklearn's grid search. The `RATING_MODEL_ATTRIBUTES` list tells the factory which constructor parameters to forward, keeping the adapter thin. This pattern lets us swap Elo for Glicko-2 by changing one class reference.

### Best Practice B: Temporal Validity Intervals Prevent Data Leakage

Every rating has a `valid_from` and `valid_to` timestamp. The `get()` method uses binary search with a `strict_past_data` flag to prevent accidentally using future information.

**File**: [examples/skelo/skelo/model/base.py](examples/skelo/skelo/model/base.py), lines 90-162

```python
def get(self, key, timestamp=None, strict_past_data=True):
    """Retrieve rating at a specific point in time.

    strict_past_data=True:  Returns rating from BEFORE timestamp (for prediction)
    strict_past_data=False: Returns rating at or before timestamp (for analysis)

    Example:
      ratings = [
        {'valid_from': 0, 'valid_to': 2, 'rating': 1500},
        {'valid_from': 2, 'valid_to': 3, 'rating': 1520},
      ]
      get(key, 2, strict_past_data=True)  -> 1500  (safe for prediction)
      get(key, 2, strict_past_data=False) -> 1520  (includes current match)
    """
    ratings = self.ratings[key]
    start_ts = [r['valid_from'] for r in ratings]
    bisect_fn = bisect.bisect_left if strict_past_data else bisect.bisect_right
    idx = bisect_fn(start_ts, timestamp) - 1
    idx = max(0, min(idx, len(ratings) - 1))
    return ratings[idx]['rating']
```

**What it accomplishes**: When predicting a race outcome, `strict_past_data=True` ensures we only see ratings from before that race — not ratings updated by that race's results. This is the most common source of inflated prediction accuracy in sports analytics. The binary search via `bisect` is O(log n) even for players with thousands of historical ratings.

### Best Practice C: Configurable K-Factor Strategies

Supports both constant K and rating-dependent K via a pluggable function, matching Elo's original design intent.

**File**: [examples/skelo/skelo/model/elo.py](examples/skelo/skelo/model/elo.py), lines 46-72

```python
class EloModel(RatingModel):
    def __init__(self, default_k=20, k_fn=None, initial_value=1500, initial_time=0):
        self.default_k = default_k
        self.k_fn = k_fn  # Optional: k_fn(rating) -> float
        ...

    def k(self, rating):
        """Return K factor, optionally dependent on current rating."""
        if self.k_fn:
            return self.k_fn(rating)
        return self.default_k

    def evolve_rating(self, r1, r2, label):
        """Standard Elo update: r1 + K * (actual - expected)."""
        expected = self.compute_prob(r1, r2)
        return r1 + self.k(r1) * (label - expected)

    @staticmethod
    def compute_prob(r1, r2):
        """Win probability: 1 / (1 + 10^((r2-r1)/400))."""
        return 1.0 / (1 + 10 ** ((r2 - r1) / 400.0))
```

**File**: [examples/skelo/skelo/utils/elo_data.py](examples/skelo/skelo/utils/elo_data.py), lines 30-52

```python
def sigmoid_k_fn_builder(r1, r2, k1, k2):
    """Build a sigmoid K-factor function: high K for low ratings, low K for high.

    New players (low rating) get large updates (high K).
    Established players (high rating) get small updates (low K).
    """
    def k_fn(rating):
        t = (rating - r1) / (r2 - r1)
        return k1 + (k2 - k1) / (1 + math.exp(-10 * (t - 0.5)))
    return k_fn
```

**What it accomplishes**: For amateur cycling where rider quality varies widely, a rating-dependent K makes new riders converge faster while preventing established riders from bouncing around. The sigmoid builder creates a smooth transition. This is directly applicable to our system where a Cat 5 newcomer's rating should update quickly, while a consistent Cat 1 racer's rating should be stable.

### Best Practice D: Rating History Export to DataFrame

One-call export of the complete rating history for analysis and visualization.

**File**: [examples/skelo/skelo/model/base.py](examples/skelo/skelo/model/base.py), lines 308-327

```python
def to_frame(self):
    """Export complete rating history as a pandas DataFrame.

    Returns:
        DataFrame with columns: key, rating, valid_from, valid_to
    """
    records = []
    for key, history in self.ratings.items():
        for entry in history:
            records.append({
                'key': key,
                'rating': entry['rating'],
                'valid_from': entry['valid_from'],
                'valid_to': entry['valid_to'],
            })
    return pd.DataFrame(records)
```

**What it accomplishes**: The full rating trajectory for every rider can be exported, pivoted, and visualized with one call. This enables "rating over time" charts, season form analysis, and debugging of rating anomalies. The `valid_from`/`valid_to` columns make it trivial to join ratings with race results at the correct point in time.

---

## 5. `Cycling-predictions` — Feature Engineering for Race Outcome Prediction

**Why #5**: The most thorough feature engineering for cycling prediction. Its multi-timescale rider features (form windows, status windows, race-specific history) and team aggregation patterns are directly transferable to amateur racing.

### Best Practice A: Multi-Timescale Feature Windows

Computes rider performance at multiple time horizons — form (2-8 weeks) captures current fitness, status (1-5 years) captures baseline ability.

**File**: [examples/Cycling-predictions/2_3. Data wrangling and analysis.R](examples/Cycling-predictions/2_3.%20Data%20wrangling%20and%20analysis.R), lines 207-285

```r
# Form features: recent results (sliding window in weeks)
N_form_days_2w  <- nrow(filter(past, date >= race_date - weeks(2)))
N_form_days_4w  <- nrow(filter(past, date >= race_date - weeks(4)))
N_form_days_6w  <- nrow(filter(past, date >= race_date - weeks(6)))
N_form_days_8w  <- nrow(filter(past, date >= race_date - weeks(8)))
sum_form_PCS_2w <- sum(filter(past, date >= race_date - weeks(2))$PCS)
sum_form_PCS_4w <- sum(filter(past, date >= race_date - weeks(4))$PCS)

# Status features: sustained performance (sliding window in years)
N_status_days_1y <- nrow(filter(past, date >= race_date - years(1)))
N_status_days_3y <- nrow(filter(past, date >= race_date - years(3)))
N_status_days_5y <- nrow(filter(past, date >= race_date - years(5)))
sum_status_PCS_1y <- sum(filter(past, date >= race_date - years(1))$PCS)

# Race-specific experience: how this rider performs at THIS race
N_race <- nrow(filter(past, race_id == this_race_id))
sum_race_PCS <- sum(filter(past, race_id == this_race_id)$PCS)
N_race_status_1y <- nrow(filter(past, race_id == this_race_id &
                                      date >= race_date - years(1)))
```

**What it accomplishes**: Three feature families capture fundamentally different signals. Form (weeks) shows current fitness — did the rider just win two crits? Status (years) shows baseline quality — is this a consistent top-10 finisher? Race-specific history shows course knowledge — has this rider done well here before? The grid search over window sizes (lines 940-946) finds the optimal combination, which our research identified as a key advantage of the Learn-to-Rank approach.

### Best Practice B: Team Strength Aggregation

Aggregates individual rider features to team level, then scales within-team to identify the protected rider.

**File**: [examples/Cycling-predictions/2_3. Data wrangling and analysis.R](examples/Cycling-predictions/2_3.%20Data%20wrangling%20and%20analysis.R), lines 457-541

```r
# Team strength: sum of all teammates' abilities
team_agg <- dataset %>%
  group_by(race_year_team_id) %>%
  summarise(
    Team_form_PCS = sum(sum_form_PCS_4w),
    Team_status_PCS = sum(sum_status_PCS_3y),
    Team_career_PCS = sum(sum_career_PCS),
    Team_race_PCS = sum(sum_race_PCS),
    N_riders_team = n()
  )

# Within-team scaling: identifies the "star" rider
dataset <- dataset %>%
  group_by(race_year_team_id) %>%
  mutate(
    Team_status = scale(sum_status_PCS_3y),  # z-score within team
  ) %>%
  ungroup()
```

**What it accomplishes**: `Team_form_PCS` captures collective team quality (strong team = better leadout, more tactical options). The within-team z-score (`Team_status`) identifies which rider the team is likely working for — the highest-scoring rider on a strong team is the protected sprinter or GC contender. This is relevant even in amateur racing where team tactics exist in Cat 1/2 fields.

### Best Practice C: Race-Level Train/Test Split to Prevent Leakage

Splits data at the race level, not the rider level, to avoid leaking race-specific information.

**File**: [examples/Cycling-predictions/2_3. Data wrangling and analysis.R](examples/Cycling-predictions/2_3.%20Data%20wrangling%20and%20analysis.R), lines 619-625

```r
# Split by RACE, not by rider-race row
set.seed(42)
race_ids <- unique(dataset$race_year_id)

# 80% of races for training, 20% for testing
test_idx <- sample(length(race_ids), size = round(0.2 * length(race_ids)))
test_races <- race_ids[test_idx]   # 26 complete races
train_races <- race_ids[-test_idx] # 104 complete races

# Cross-validation also stratifies by race
CV_folds <- groupKFold(dataset$race_year_id, k = 5)
```

**What it accomplishes**: If you split by row, the same race's riders appear in both train and test — the model can "memorize" race-specific patterns (weather, crash dynamics) rather than learning generalizable rider quality. Race-level splitting ensures the model predicts entirely unseen races. The `groupKFold` function enforces this within cross-validation folds too.

### Best Practice D: Course Profile as Prediction Feature with Time-Gap Grouping

Classifies courses into 5 profile types and uses time gaps to identify riders who "fought" for positions together.

**File**: [examples/Cycling-predictions/1. Data extraction.R](examples/Cycling-predictions/1.%20Data%20extraction.R), lines 186-196, 376-436

```r
# Course profile classification (5 types from PCS)
race_profile <- case_when(
  profile == "p1" ~ "Flat",
  profile == "p2" ~ "Hills, flat finish",
  profile == "p3" ~ "Hills, uphill finish",
  profile == "p4" ~ "Mountains, flat finish",
  profile == "p5" ~ "Mountains, uphill finish"
)

# Time-gap grouping: riders within 10 seconds are "in the same fight"
results <- results %>%
  arrange(position) %>%
  mutate(
    time_gap = time_seconds - lag(time_seconds, default = 0),
    group_break = time_gap > 10,        # 10-second threshold
    group_id = cumsum(group_break),
    group_position = row_number()        # Position within group
  )

# Target variables derived from group position
fight_top10 <- group_position <= 10     # Primary prediction target
fight_podium <- group_position <= 3
fight_win <- group_position == 1
```

**What it accomplishes**: The 10-second time-gap grouping is a concrete implementation of the finish-type classification our research identified as the core analytical engine. Riders finishing within 10 seconds were "in the same fight" — they had a tactical interaction. The `group_position` within each group gives a truer measure of relative performance than raw finishing position when a breakaway has a 5-minute gap.

---

## Summary: Patterns to Carry Forward

| Pattern | Source Project | Apply To |
|---------|---------------|----------|
| JSON API over HTML scraping | road-results | road-results.com data acquisition |
| Async parallel fetching | road-results | Bulk historical scraping |
| Class-per-entity scraper architecture | procyclingstats | Our scraper library design |
| Two-tier error semantics | procyclingstats | Scraper reliability |
| Flexible field selection with `*args` | procyclingstats | API ergonomics |
| Temporal validity intervals | skelo | Rating system, data leakage prevention |
| sklearn-compatible rating interface | skelo | Integration with ML pipeline |
| Rating-dependent K factors | skelo | Amateur fitness variance handling |
| Race clustering by elevation features | PerfoRank | Course profile classification |
| Cluster-specific TrueSkill ratings | PerfoRank | Two-stage prediction architecture |
| XGBoost LambdaMART ranking | PerfoRank | Final outcome prediction |
| Multi-timescale feature windows | Cycling-predictions | Rider form vs. status vs. career |
| Race-level train/test split | Cycling-predictions | Honest evaluation |
| Time-gap grouping for finish type | Cycling-predictions | Finish type classification |
| Team strength aggregation | Cycling-predictions | Team dynamics modeling |
