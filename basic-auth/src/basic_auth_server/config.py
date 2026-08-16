from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    port: int
    test_username: str
    test_password: str


def load_settings() -> Settings:
    return Settings(
        port=int(os.environ.get("PORT", "8080")),
        test_username=os.environ["TEST_USERNAME"],
        test_password=os.environ["TEST_PASSWORD"],
    )
