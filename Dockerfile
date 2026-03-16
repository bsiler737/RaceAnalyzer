FROM python:3.12-slim
WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY raceanalyzer/ raceanalyzer/

# Seed DB for first-deploy fallback (volume takes priority at runtime)
COPY data/raceanalyzer.db /app/seed/raceanalyzer.db

ENV RACEANALYZER_DB_PATH=/data/raceanalyzer.db
EXPOSE 8000

# Copy seed DB to volume if volume is empty, then start server
CMD ["sh", "-c", \
  "if [ ! -f /data/raceanalyzer.db ]; then cp /app/seed/raceanalyzer.db /data/raceanalyzer.db; fi && \
   python -m raceanalyzer --db /data/raceanalyzer.db serve --host 0.0.0.0 --port 8000"]
