"""Configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    cosmos_endpoint: str = os.getenv("COSMOS_ENDPOINT", "")
    cosmos_database: str = os.getenv("COSMOS_DATABASE", "ami")
    foundry_endpoint: str = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
    aoai_deployment: str = os.getenv("AOAI_DEPLOYMENT_NAME", "gpt-4o")
    azure_client_id: str = os.getenv("AZURE_CLIENT_ID", "")
    enable_simulator: bool = os.getenv("ENABLE_SIMULATOR", "true").lower() == "true"
    meter_count: int = int(os.getenv("AMI_METER_COUNT", "5000"))
    substation_count: int = int(os.getenv("AMI_SUBSTATION_COUNT", "6"))
    seed: int = int(os.getenv("AMI_SEED", "42"))
    appinsights_conn: str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")


settings = Settings()
