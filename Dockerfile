FROM python:3.12-slim
WORKDIR /app

# Install Tailwind CLI for CSS compilation
RUN apt-get update && apt-get install -y curl && \
    curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 && \
    chmod +x tailwindcss-linux-x64 && \
    mv tailwindcss-linux-x64 /usr/local/bin/tailwindcss && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY raceanalyzer/ raceanalyzer/
COPY tailwind.config.js .

# Compile Tailwind CSS
RUN tailwindcss -i raceanalyzer/static/css/input.css -o raceanalyzer/static/css/style.css --minify

# Seed DB for first-deploy fallback (volume takes priority at runtime)
COPY data/raceanalyzer.db /app/seed/raceanalyzer.db

ENV RACEANALYZER_DB_PATH=/data/raceanalyzer.db
EXPOSE 8000

# Copy seed DB to volume if volume is empty, then start server
CMD ["sh", "-c", \
  "if [ ! -f /data/raceanalyzer.db ]; then cp /app/seed/raceanalyzer.db /data/raceanalyzer.db; fi && \
   python -m raceanalyzer serve --host 0.0.0.0 --port 8000"]
