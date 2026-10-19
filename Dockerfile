# Enveliq server image.
# Build:  docker build -t enveliq .
# Run:    see docker-compose.yml (put an HTTPS reverse proxy in front).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Unprivileged service user; the code is owned by root and read-only to it.
RUN groupadd --system --gid 10001 enveliq \
 && useradd --system --uid 10001 --gid enveliq --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin enveliq

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY web ./web
COPY brand/web ./brand/web
COPY prototype/index.html ./prototype/index.html
COPY run.py .

RUN mkdir -p /data && chown enveliq:enveliq /data && chmod 700 /data

# Inside the container the server listens on all interfaces; the compose file
# publishes it to the host's loopback only, for a reverse proxy to use.
# The official release and preview builds pass the push relay's address here (docs/PUSH_RELAY.md); a build without it offers no Google push.
ARG ENVELIQ_PUSH_RELAY=
ENV ENVELIQ_PUSH_RELAY=${ENVELIQ_PUSH_RELAY} \
    ENVELIQ_DATA_DIR=/data \
    ENVELIQ_BIND=0.0.0.0 \
    ENVELIQ_ALLOW_NON_LOOPBACK=1 \
    ENVELIQ_PORT=8765

USER 10001:10001
EXPOSE 8765
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health', timeout=3).status == 200 else 1)"]

CMD ["python", "run.py"]
