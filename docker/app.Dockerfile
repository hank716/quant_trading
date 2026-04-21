FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc g++ curl libgomp1 git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/workspace/hotdata /app/workspace/runs \
             /app/workspace/outputs /app/workspace/logs /app/workspace/tmp

ENV PYTHONUNBUFFERED=1
ENV CACHE_DIR=/app/workspace/hotdata
ENV OUTPUT_DIR=/app/workspace/outputs
ENV LOG_DIR=/app/workspace/logs
