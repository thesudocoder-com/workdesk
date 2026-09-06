from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
load_dotenv(PROJECT_DIR / ".env", override=False)


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "WorkDesk"
    environment: str = os.getenv("WORKDESK_ENV", "development")
    database_url: str = os.getenv(
        "WORKDESK_DATABASE_URL", f"sqlite:///{PROJECT_DIR / 'workdesk.db'}"
    )
    session_secret: str = os.getenv(
        "WORKDESK_SESSION_SECRET", "dev-only-change-this-workdesk-secret"
    )
    session_secure: bool = os.getenv("WORKDESK_SESSION_SECURE", "false").lower() == "true"
    public_url: str = os.getenv("WORKDESK_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    setup_token: str = os.getenv("WORKDESK_SETUP_TOKEN", "development-setup-token")

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


settings = Settings()
