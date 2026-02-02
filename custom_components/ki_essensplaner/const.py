"""Constants for the KI-Essensplaner integration."""

DOMAIN = "ki_essensplaner"

# Configuration keys
CONF_API_URL = "api_url"
CONF_API_TOKEN = "api_token"

# Default values
DEFAULT_API_URL = "http://localhost:8099"
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes

# Sensor states
STATE_HEALTHY = "healthy"
STATE_CACHED = "cached"
STATE_OFFLINE = "offline"

# Attribute keys
ATTR_DATABASE_OK = "database_ok"
ATTR_PROFILE_AGE_DAYS = "profile_age_days"
ATTR_BIOLAND_AGE_DAYS = "bioland_age_days"
ATTR_CACHED = "cached"
