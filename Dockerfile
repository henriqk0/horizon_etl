# Stage 1: Build Python dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Chromium + ChromeDriver (auto-versioned pair) + Playwright system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxkbcommon0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libasound2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# gosu for dropping privileges in entrypoint
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates wget; \
    rm -rf /var/lib/apt/lists/*; \
    dpkgArch="$(dpkg --print-architecture)"; \
    case "$dpkgArch" in \
        amd64) gosuUrl="https://github.com/tianon/gosu/releases/download/1.17/gosu-amd64" ;; \
        arm64) gosuUrl="https://github.com/tianon/gosu/releases/download/1.17/gosu-arm64" ;; \
        *) echo "unsupported arch: $dpkgArch"; exit 1 ;; \
    esac; \
    wget -O /usr/local/bin/gosu "$gosuUrl"; \
    chmod +x /usr/local/bin/gosu; \
    apt-get purge -y --auto-remove ca-certificates wget

COPY --from=builder /root/.local /usr/local

ENV PATH=/usr/local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/ms-playwright \
    PREFECT_HOME=/tmp/prefect

COPY . /app
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

# Create runtime user so gosu sets HOME correctly (gosu 1.17 fallback HomeDir=/)
RUN echo "appuser:x:1000:1000:App User:/tmp:/usr/sbin/nologin" >> /etc/passwd && \
    echo "appuser:x:1000:" >> /etc/group

# Runtime user (from user: "${UID:-1000}:${GID:-1000}") needs write access
RUN chmod 777 /app

# Install Playwright's own Chromium + its system deps
RUN python -m playwright install --with-deps chromium

ENTRYPOINT ["/entrypoint.sh", "python"]
CMD ["src/flows/all.py"]
