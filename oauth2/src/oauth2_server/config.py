from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    port: int
    test_client_id: str
    test_client_secret: str
    code_ttl_seconds: int
    token_ttl_seconds: int


def load_settings() -> Settings:
    return Settings(
        port=int(os.environ.get("PORT", "8080")),
        test_client_id=os.environ["TEST_CLIENT_ID"],
        test_client_secret=os.environ["TEST_CLIENT_SECRET"],
        code_ttl_seconds=int(os.environ.get("CODE_TTL_SECONDS", "60")),
        token_ttl_seconds=int(os.environ.get("TOKEN_TTL_SECONDS", "3600")),
    )
