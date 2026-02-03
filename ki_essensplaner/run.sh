#!/usr/bin/with-contenv bashio
# ==============================================================================
# KI-Essensplaner Add-on Startup Script
# ==============================================================================

# Read configuration from Home Assistant
export API_TOKEN=$(bashio::config 'api_token')
export OPENAI_API_KEY=$(bashio::config 'openai_api_key')
export AZURE_CLIENT_ID=$(bashio::config 'azure_client_id')
export AZURE_TENANT_ID=$(bashio::config 'azure_tenant_id')
export LOG_LEVEL=$(bashio::config 'log_level')

# Set data directory to Home Assistant share
export DATA_DIR="/share/ki_essensplaner"

# Create data directory if it doesn't exist
mkdir -p "${DATA_DIR}"

# Log startup
bashio::log.info "Starting KI-Essensplaner API..."
bashio::log.info "API will be available at port 8099"

if [ -z "${API_TOKEN}" ]; then
    bashio::log.warning "No API token configured. Protected endpoints will be unavailable."
fi

# Start the API server using venv
cd /app
exec /app/venv/bin/python -m src.api
