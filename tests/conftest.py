import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "certificates",
    )
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client


def job_payload(**overrides):
    body = {
        "title": "Certificate of Completion",
        "event_name": "Backend Engineering Workshop",
        "issuer": "Aereo Academy",
        "issued_on": "2026-10-08",
        "recipients": [
            {"name": "Ada Lovelace", "email": "ada@example.com", "detail": "Track: API design"},
            {"name": "Grace Hopper", "email": "grace@example.com", "detail": "Track: Systems"},
        ],
    }
    body.update(overrides)
    return body
