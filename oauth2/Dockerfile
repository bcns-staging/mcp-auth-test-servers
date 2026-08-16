# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app

# Patch OS-level packages to whatever's currently latest within this Debian
# release -- the base image itself is a point-in-time snapshot and
# accumulates known CVEs in glibc/openssl/etc. between snapshots even
# though nothing in this Dockerfile touches them directly.
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Norton MITM cert trust (local builds only; no-op in Cloud Build) ---
COPY certs/ /tmp/extra-certs/
RUN for f in /tmp/extra-certs/*.crt; do [ -f "$f" ] && cat "$f" >> /etc/ssl/certs/ca-certificates.crt; done; \
    rm -rf /tmp/extra-certs
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_DIR=/etc/ssl/certs \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "oauth2_server"]
