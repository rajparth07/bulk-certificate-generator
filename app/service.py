"""Create a bulk job and generate each certificate independently.

The HTTP request only stores the job and returns. PDF work runs afterwards so
one large batch does not hold the connection open. Each recipient is committed
on its own: a bad row or a failed PDF does not roll back the certificates that
already succeeded.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
    CERT_FAILED,
    COMPLETED,
    COMPLETED_WITH_ERRORS,
    FAILED,
    PENDING,
    PROCESSING,
    QUEUED,
    SUCCEEDED,
    Certificate,
    Job,
)
from app.pdf import render_certificate
from app.schemas import JobCreate
from app.validation import validate_recipient

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_job(db: Session, data: JobCreate) -> Job:
    now = utcnow()
    job = Job(
        id=str(uuid4()),
        title=data.title,
        event_name=data.event_name,
        issuer=data.issuer,
        issued_on=data.issued_on,
        status=QUEUED,
        total=len(data.recipients),
        succeeded=0,
        failed=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    for position, recipient in enumerate(data.recipients):
        job.certificates.append(
            Certificate(
                id=str(uuid4()),
                position=position,
                recipient_name=recipient.name.strip(),
                email=_blank_to_none(recipient.email),
                detail=_blank_to_none(recipient.detail),
                status=PENDING,
                error=None,
                file_path=None,
                created_at=now,
                updated_at=now,
            )
        )
    db.add(job)
    db.commit()
    return job


def process_job(job_id: str, session_factory, storage_dir: Path) -> None:
    db = session_factory()
    try:
        job = db.get(Job, job_id)
        if job is None or job.status != QUEUED:
            return
        job.status = PROCESSING
        job.updated_at = utcnow()
        db.commit()

        certificates = (
            db.query(Certificate)
            .filter(Certificate.job_id == job_id)
            .order_by(Certificate.position)
            .all()
        )
        for certificate in certificates:
            if certificate.status != PENDING:
                continue
            _generate_one(db, job, certificate, storage_dir)

        _finish_job(db, job)
    except Exception:
        logger.exception("Job %s crashed while generating certificates", job_id)
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None and job.status == PROCESSING:
            job.status = FAILED
            job.updated_at = utcnow()
            job.completed_at = utcnow()
            db.commit()
    finally:
        db.close()


def _generate_one(db: Session, job: Job, certificate: Certificate, storage_dir: Path) -> None:
    try:
        message = validate_recipient(certificate.recipient_name, certificate.email, certificate.detail)
        if message:
            certificate.status = CERT_FAILED
            certificate.error = message
        else:
            destination = storage_dir / job.id / f"{certificate.id}.pdf"
            render_certificate(
                destination,
                recipient_name=certificate.recipient_name,
                email=certificate.email,
                detail=certificate.detail,
                event_name=job.event_name,
                title=job.title,
                issuer=job.issuer,
                issued_on=job.issued_on,
                certificate_id=certificate.id,
            )
            certificate.file_path = str(destination)
            certificate.status = SUCCEEDED
            certificate.error = None
    except Exception:
        logger.exception("Certificate %s failed", certificate.id)
        certificate.status = CERT_FAILED
        certificate.error = "Certificate generation failed"
    certificate.updated_at = utcnow()
    db.commit()


def _finish_job(db: Session, job: Job) -> None:
    certificates = db.query(Certificate).filter(Certificate.job_id == job.id).all()
    succeeded = sum(item.status == SUCCEEDED for item in certificates)
    failed = sum(item.status == CERT_FAILED for item in certificates)
    job.total = len(certificates)
    job.succeeded = succeeded
    job.failed = failed
    if succeeded and failed:
        job.status = COMPLETED_WITH_ERRORS
    elif succeeded:
        job.status = COMPLETED
    else:
        job.status = FAILED
    job.updated_at = utcnow()
    job.completed_at = utcnow()
    db.commit()


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
