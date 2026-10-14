# syntax = docker/dockerfile:1.4
FROM python:3.12-slim

# ---- System deps ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc && \
    rm -rf /var/lib/apt/lists/*

# ---- Application ---------------------------------------------------------
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY loader.py .

# Run the script as the container's entrypoint
ENTRYPOINT ["python", "-u", "loader.py"]
