FROM python:3.12-slim

WORKDIR /app

ENV GEO_CHECK_RUNS=/workspace/runs

COPY . /app

RUN python -m pip install --no-cache-dir ".[web]"

ENTRYPOINT ["geo-seo-hub"]
