"""Runtime settings loaded from the environment."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///./data/certificates.db"),
            storage_dir=Path(os.environ.get("CERTIFICATE_STORAGE_DIR", "./data/certificates")),
        )
