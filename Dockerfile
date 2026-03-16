FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy app code and data
COPY raceanalyzer/ raceanalyzer/
COPY data/raceanalyzer.db data/
COPY .streamlit/ .streamlit/

ENV RACEANALYZER_DB_PATH=/app/data/raceanalyzer.db
ENV RACEANALYZER_PROD=1

EXPOSE 8501

CMD ["streamlit", "run", "raceanalyzer/ui/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
