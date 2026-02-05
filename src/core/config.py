"""Configuration management for KI-Essensplaner."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
LOCAL_DIR = DATA_DIR / "local"
DB_PATH = LOCAL_DIR / "mealplanner.db"

# Load .env file
load_dotenv(PROJECT_ROOT / ".env")


class AzureConfig:
    """Azure AD configuration for MS Graph API."""

    CLIENT_ID: str = os.getenv("AZURE_CLIENT_ID", "")
    # Use "consumers" for personal Microsoft accounts, "common" for both, or tenant ID for org only
    TENANT_ID: str = os.getenv("AZURE_TENANT_ID", "consumers")
    AUTHORITY: str = f"https://login.microsoftonline.com/{TENANT_ID}"
    SCOPES: list[str] = ["Notes.Read", "User.Read", "openid", "profile", "offline_access"]
    REDIRECT_URI: str = "http://localhost:8400"

    @classmethod
    def is_configured(cls) -> bool:
        """Check if Azure credentials are configured."""
        return bool(cls.CLIENT_ID)


class OpenAIConfig:
    """OpenAI configuration for future phases."""

    API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    @classmethod
    def is_configured(cls) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(cls.API_KEY)


def ensure_directories() -> None:
    """Create required data directories if they don't exist."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
