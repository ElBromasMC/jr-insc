FROM ubuntu:oracular

RUN apt-get update \
    && apt-get install -y \
    python3 \
    python3-venv \
    curl \
    && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    gpg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Use venv to install Playwright dependencies
WORKDIR /playwright

RUN python3 -m venv venv \
    && . venv/bin/activate \
    && pip install playwright \
    && playwright install-deps chromium-headless-shell \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /playwright

# Create and change to non-root user
RUN useradd -m runner
USER runner

# Create required folders
RUN mkdir /home/runner/src \
    && mkdir /home/runner/data

WORKDIR /home/runner/src

# Install dependencies
RUN python3 -m venv venv \
    && . venv/bin/activate \
    && pip install playwright \
    pandas \
    xlrd \
    openpyxl \
    && playwright install --only-shell chromium-headless-shell

# Copy source files
COPY --chown=runner:runner main.py ./

# Create entrypoint
COPY --chown=runner:runner ./scripts/docker-run-prod.sh /home/runner/
ENTRYPOINT ["/home/runner/docker-run-prod.sh"]

