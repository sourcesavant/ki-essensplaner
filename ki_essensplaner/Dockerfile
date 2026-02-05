ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-wheel \
    git

# Set working directory
WORKDIR /app

# Copy requirements and install (using venv to comply with PEP 668)
COPY requirements.txt /app/
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_CONFIG_FILE=/dev/null
ENV PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_EXTRA_INDEX_URL=
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --isolated --no-cache-dir --index-url https://pypi.org/simple --timeout 300 --retries 10 -r requirements.txt

# Fetch application code from repo root (avoid duplicated src in addon folder)
ARG APP_REPO=https://github.com/sourcesavant/ki-essensplaner.git
ARG APP_REF=master
RUN git clone --depth 1 --branch ${APP_REF} ${APP_REPO} /app/app

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD [ "/run.sh" ]
