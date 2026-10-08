"""Request and response models for the certificate job API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CERT_FAILED, Certificate, Job, PENDING, SUCCEEDED

JobStatus = Literal[
    "queued",
    "processing",
    "completed",
    "completed_with_errors",
    "failed",
]
CertificateStatus = Literal["pending", "succeeded", "failed"]


class RecipientIn(BaseModel):
    name: str = Field(default="", max_length=500)
    email: str | None = Field(default=None, max_length=500)
    detail: str | None = Field(default=None, max_length=1000)


class JobCreate(BaseModel):
    title: str = Field(default="Certificate of Completion", min_length=1, max_length=200)
    event_name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(min_length=1, max_length=200)
    issued_on: date
    recipients: list[RecipientIn] = Field(min_length=1, max_length=1000)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Certificate of Completion",
                "event_name": "Backend Engineering Workshop",
                "issuer": "Aereo Academy",
                "issued_on": "2026-10-08",
                "recipients": [
                    {
                        "name": "Ada Lovelace",
                        "email": "ada@example.com",
                        "detail": "Track: API design",
                    }
                ],
            }
        }
    )

    @field_validator("title", "event_name", "issuer")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class CertificateOut(BaseModel):
    id: str
    position: int
    recipient_name: str
    email: str | None
    detail: str | None
    status: CertificateStatus
    error: str | None
    download_url: str | None


class JobOut(BaseModel):
    id: str
    title: str
    event_name: str
    issuer: str
    issued_on: date
    status: JobStatus
    total: int
    succeeded: int
    failed: int
    pending: int
    progress_percent: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    certificates: list[CertificateOut]


def to_job_out(job: Job) -> JobOut:
    certificates = list(job.certificates)
    succeeded = sum(item.status == SUCCEEDED for item in certificates)
    failed = sum(item.status == CERT_FAILED for item in certificates)
    total = len(certificates)
    pending = sum(item.status == PENDING for item in certificates)
    progress = 0 if total == 0 else round((succeeded + failed) * 100 / total)
    return JobOut(
        id=job.id,
        title=job.title,
        event_name=job.event_name,
        issuer=job.issuer,
        issued_on=job.issued_on,
        status=job.status,  # type: ignore[arg-type]
        total=total,
        succeeded=succeeded,
        failed=failed,
        pending=pending,
        progress_percent=progress,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        certificates=[_certificate_out(job.id, item) for item in certificates],
    )


def _certificate_out(job_id: str, certificate: Certificate) -> CertificateOut:
    download_url = None
    if certificate.status == SUCCEEDED and certificate.file_path:
        download_url = f"/api/certificate-jobs/{job_id}/certificates/{certificate.id}"
    return CertificateOut(
        id=certificate.id,
        position=certificate.position,
        recipient_name=certificate.recipient_name,
        email=certificate.email,
        detail=certificate.detail,
        status=certificate.status,  # type: ignore[arg-type]
        error=certificate.error,
        download_url=download_url,
    )
