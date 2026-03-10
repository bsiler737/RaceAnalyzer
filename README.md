# Race Analyzer

Race Analyzer is an analysis tool that helps bike racers understand the results of road races in the Pacific Northwest (WA, OR, ID, BC). The tool classifies race finishes by type (sprint, breakaway, individual/selective), with future goals to predict race outcomes and recommend races to riders based on their cycling phenotype.

This project was bootstrapped by a Gemini agent.

## Sprint 001: Data Pipeline Foundation

This initial sprint focused on building the foundational data pipeline to acquire, store, and classify race results from [road-results.com](https://road-results.com).

### Key Features
- **Scraper**: A robust, asynchronous scraper to fetch race data from the unofficial `road-results.com` JSON API.
- **Database**: An SQLite database managed with SQLAlchemy ORM to store races, riders, and results in a relational schema.
- **Classifier**: A rule-based finish type classifier that analyzes time gaps between finishers to categorize races as "Bunch Sprint," "Breakaway," "Selective," etc.
- **Testing**: A suite of unit tests using `pytest` to verify the functionality of the scraper and classifier.

## Project Structure

```
/
├── raceanalyzer/            # Main application package
│   ├── data/                # SQLAlchemy models and DB session management
│   ├── scraper/             # Scraper for road-results.com
│   └── classification/      # Finish type classification logic
├── scripts/                 # Standalone scripts for running tasks
│   ├── scrape.py            # Executes the scraping process
│   └── classify.py          # Runs the classification on stored data
├── tests/                   # Unit tests
│   ├── fixtures/            # Mock data for testing
│   ├── test_classifier.py
│   └── test_scraper.py
├── docs/sprints/drafts/     # Sprint planning documents
├── pyproject.toml           # Project dependencies
└── README.md
```

## How to Run

### 1. Installation

It is recommended to use a virtual environment.

```bash
# Create and activate a virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt 
```
*Note: A `requirements.txt` file would need to be generated from `pyproject.toml` for this method.*


### 2. Scrape Data

The scraper fetches data from `road-results.com` based on a range of race IDs.

```bash
# Scrape races with IDs from 12000 to 12100
python3 scripts/scrape.py 12000 12100
```
This will create and populate `data/race_analyzer.db`.

### 3. Classify Finishes

After scraping, run the classifier to analyze the results and update the races with a `finish_type`.

```bash
python3 scripts/classify.py
```

### 4. Run Tests

To verify the installation and code integrity:

```bash
python3 -m pytest tests/
```
