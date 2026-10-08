"""Covers the behaviours the assignment asks to test.

- Creating a generation job
- Input validation
- Certificate generation
- Job status and progress
- One certificate failing while the rest of the job continues
- Retrieving generated certificates
"""

import io
import zipfile

from pypdf import PdfReader

from app.schemas import JobCreate
from app.service import create_job, process_job
from tests.conftest import job_payload


def test_create_generation_job_returns_queued_progress(client):
    created = client.post("/api/certificate-jobs", json=job_payload())
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "queued"
    assert body["total"] == 2
    assert body["pending"] == 2
    assert body["succeeded"] == 0
    assert body["progress_percent"] == 0
    assert body["id"]


def test_job_status_reports_progress_before_and_after_generation(client):
    factory = client.app.state.session_factory
    db = factory()
    job = create_job(db, JobCreate.model_validate(job_payload()))
    job_id = job.id
    db.close()

    waiting = client.get(f"/api/certificate-jobs/{job_id}")
    assert waiting.status_code == 200
    waiting_body = waiting.json()
    assert waiting_body["status"] == "queued"
    assert waiting_body["pending"] == 2
    assert waiting_body["progress_percent"] == 0

    process_job(job_id, factory, client.app.state.storage_dir)

    finished = client.get(f"/api/certificate-jobs/{job_id}")
    finished_body = finished.json()
    assert finished_body["status"] == "completed"
    assert finished_body["succeeded"] == 2
    assert finished_body["failed"] == 0
    assert finished_body["pending"] == 0
    assert finished_body["progress_percent"] == 100
    assert finished_body["completed_at"] is not None


def test_request_shape_is_validated(client):
    missing_event = client.post(
        "/api/certificate-jobs",
        json=job_payload(event_name="  "),
    )
    assert missing_event.status_code == 422

    empty_batch = client.post("/api/certificate-jobs", json=job_payload(recipients=[]))
    assert empty_batch.status_code == 422

    bad_date = client.post("/api/certificate-jobs", json=job_payload(issued_on="tomorrow"))
    assert bad_date.status_code == 422

    too_many = job_payload(recipients=[{"name": f"Person {index}"} for index in range(1001)])
    assert client.post("/api/certificate-jobs", json=too_many).status_code == 422


def test_invalid_recipient_does_not_block_valid_ones(client):
    payload = job_payload(
        recipients=[
            {"name": "Ada Lovelace", "email": "ada@example.com"},
            {"name": "   ", "email": "missing-name@example.com"},
            {"name": "Grace Hopper", "email": "not-an-email"},
        ]
    )
    created = client.post("/api/certificate-jobs", json=payload)
    assert created.status_code == 202
    job_id = created.json()["id"]

    body = client.get(f"/api/certificate-jobs/{job_id}").json()
    assert body["status"] == "completed_with_errors"
    assert body["succeeded"] == 1
    assert body["failed"] == 2
    assert body["pending"] == 0

    by_name = {item["recipient_name"]: item for item in body["certificates"]}
    assert by_name["Ada Lovelace"]["status"] == "succeeded"
    assert by_name["Ada Lovelace"]["download_url"]
    assert by_name[""]["status"] == "failed"
    assert by_name[""]["error"] == "Recipient name is required"
    assert by_name["Grace Hopper"]["status"] == "failed"
    assert by_name["Grace Hopper"]["error"] == "Recipient email is not a valid email address"


def test_one_generation_failure_does_not_stop_the_job(client, monkeypatch):
    def explode(destination, **kwargs):
        if kwargs["recipient_name"] == "Grace Hopper":
            raise RuntimeError("disk full")
        from app.pdf import render_certificate

        render_certificate(destination, **kwargs)

    monkeypatch.setattr("app.service.render_certificate", explode)
    created = client.post("/api/certificate-jobs", json=job_payload())
    job_id = created.json()["id"]
    body = client.get(f"/api/certificate-jobs/{job_id}").json()

    assert body["status"] == "completed_with_errors"
    by_name = {item["recipient_name"]: item for item in body["certificates"]}
    assert by_name["Ada Lovelace"]["status"] == "succeeded"
    assert by_name["Grace Hopper"]["status"] == "failed"
    assert by_name["Grace Hopper"]["error"] == "Certificate generation failed"
    assert by_name["Grace Hopper"]["download_url"] is None

    grace_id = by_name["Grace Hopper"]["id"]
    failed_download = client.get(f"/api/certificate-jobs/{job_id}/certificates/{grace_id}")
    assert failed_download.status_code == 409


def test_certificate_generation_and_retrieval(client):
    created = client.post(
        "/api/certificate-jobs",
        json=job_payload(recipients=[{"name": "Ada Lovelace", "email": "ada@example.com", "detail": "Track: API design"}]),
    )
    job = client.get(f"/api/certificate-jobs/{created.json()['id']}").json()
    certificate = job["certificates"][0]
    assert certificate["status"] == "succeeded"

    downloaded = client.get(certificate["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/pdf")
    assert downloaded.content.startswith(b"%PDF")

    reader = PdfReader(io.BytesIO(downloaded.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Ada Lovelace" in text
    assert "Backend Engineering Workshop" in text
    assert "Aereo Academy" in text
    assert "ada@example.com" in text
    assert "Track: API design" in text
    assert "08 October 2026" in text

    archive = client.get(f"/api/certificate-jobs/{job['id']}/archive")
    assert archive.status_code == 200
    assert archive.headers["content-type"].startswith("application/zip")
    packaged = zipfile.ZipFile(io.BytesIO(archive.content))
    assert len(packaged.namelist()) == 1
    assert packaged.read(packaged.namelist()[0]).startswith(b"%PDF")


def test_missing_job_and_archive_before_processing(client):
    missing = client.get("/api/certificate-jobs/does-not-exist")
    assert missing.status_code == 404

    factory = client.app.state.session_factory
    db = factory()
    job = create_job(db, JobCreate.model_validate(job_payload()))
    job_id = job.id
    db.close()

    early_archive = client.get(f"/api/certificate-jobs/{job_id}/archive")
    assert early_archive.status_code == 409

    unknown_file = client.get(f"/api/certificate-jobs/{job_id}/certificates/missing")
    assert unknown_file.status_code == 404


def test_all_invalid_recipients_mark_the_job_failed(client):
    created = client.post(
        "/api/certificate-jobs",
        json=job_payload(recipients=[{"name": ""}, {"name": "!!!"}]),
    )
    body = client.get(f"/api/certificate-jobs/{created.json()['id']}").json()
    assert body["status"] == "failed"
    assert body["succeeded"] == 0
    assert body["failed"] == 2
    archive = client.get(f"/api/certificate-jobs/{body['id']}/archive")
    assert archive.status_code == 404
