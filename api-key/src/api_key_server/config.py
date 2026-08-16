from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    port: int
    test_api_key: str
    # Matches the "Header Name" field in the platform's API Key auth form --
    # X-API-Key is that form's own default, so it's the default here too.
    header_name: str


def load_settings() -> Settings:
    return Settings(
        port=int(os.environ.get("PORT", "8080")),
        test_api_key=os.environ["TEST_API_KEY"],
        header_name=os.environ.get("API_KEY_HEADER_NAME", "X-API-Key").lower(),
    )
