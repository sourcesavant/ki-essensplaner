ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-wheel

# Set working directory
WORKDIR /app

# Copy requirements and install (using venv to comply with PEP 668)
COPY requirements.txt /app/
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=120
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --retries 5 -r requirements.txt

# Copy application code
COPY . /app/

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD [ "/run.sh" ]
