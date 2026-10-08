"""HTTP endpoints for submitting a bulk job and collecting the PDFs."""

import io
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.models import QUEUED, PROCESSING, SUCCEEDED, Certificate, Job, TERMINAL_JOB_STATUSES
from app.schemas import JobCreate, JobOut, to_job_out
from app.service import create_job, process_job

router = APIRouter(prefix="/api/certificate-jobs", tags=["certificate jobs"])


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


@router.post("", status_code=202, response_model=JobOut)
def submit_job(
    payload: JobCreate,
    background: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    job = create_job(db, payload)
    background.add_task(
        process_job,
        job.id,
        request.app.state.session_factory,
        request.app.state.storage_dir,
    )
    return to_job_out(job)


@router.get("/{job_id}", response_model=JobOut)
def read_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Certificate job not found")
    return to_job_out(job)


@router.get("/{job_id}/certificates/{certificate_id}")
def download_certificate(job_id: str, certificate_id: str, request: Request, db: Session = Depends(get_db)):
    certificate = db.get(Certificate, certificate_id)
    if certificate is None or certificate.job_id != job_id:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if certificate.status != SUCCEEDED or not certificate.file_path:
        raise HTTPException(status_code=409, detail=certificate.error or "Certificate is not available")

    path = Path(certificate.file_path).resolve()
    root = Path(request.app.state.storage_dir).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Certificate file not found")

    filename = _download_name(certificate.recipient_name, certificate.id)
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("/{job_id}/archive")
def download_archive(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Certificate job not found")
    if job.status in {QUEUED, PROCESSING} or job.status not in TERMINAL_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Certificate generation is still in progress")

    ready = [item for item in job.certificates if item.status == SUCCEEDED and item.file_path]
    if not ready:
        raise HTTPException(status_code=404, detail="No generated certificates to download")

    root = Path(request.app.state.storage_dir).resolve()
    buffer = io.BytesIO()
    written = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for certificate in ready:
            path = Path(certificate.file_path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            arcname = _download_name(certificate.recipient_name, certificate.id)
            archive.write(path, arcname=arcname)
            written += 1
    if written == 0:
        raise HTTPException(status_code=404, detail="No generated certificates to download")
    buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="certificates-{job.id}.zip"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)


def _download_name(recipient_name: str, certificate_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", recipient_name).strip("._") or "certificate"
    return f"{safe}-{certificate_id[:8]}.pdf"
