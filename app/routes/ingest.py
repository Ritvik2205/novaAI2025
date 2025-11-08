from __future__ import annotations

from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.ingest import pipeline
from app.routes.deps import get_tenant
from app.schemas import JobStatusResponse, WebsiteIngestRequest

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])
JOB_STATUS: Dict[str, str] = {}


@router.post("/website")
def ingest_website(payload: WebsiteIngestRequest, tenant=Depends(get_tenant)) -> dict[str, str]:
    if tenant.id != payload.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    job_id = pipeline.enqueue_website_ingest(payload.dict())
    JOB_STATUS[job_id] = "queued"
    return {"job_id": job_id}


@router.post("/upload")
def ingest_upload(tenant_id: int, files: list[UploadFile] = File(...), tenant=Depends(get_tenant)) -> dict[str, str]:
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    job_id = None
    for upload in files:
        tmp_path = Path("tmp")
        tmp_path.mkdir(exist_ok=True)
        path = tmp_path / upload.filename
        with path.open("wb") as fh:
            fh.write(upload.file.read())
        job_id = pipeline.enqueue_upload_ingest(tenant_id, str(path))
        JOB_STATUS[job_id] = "queued"
    return {"job_id": job_id or ""}


@router.get("/job/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str) -> JobStatusResponse:
    status = JOB_STATUS.get(job_id, "unknown")
    return JobStatusResponse(job_id=job_id, status=status)
