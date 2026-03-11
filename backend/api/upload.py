"""
Document upload endpoint.
Saves files to disk and records them in the Redis session.
The chat agent checks documents_uploaded when processing the document_upload stage.
"""
import os
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from core.redis_client import get_session, set_session
from db import repository as repo

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTS   = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
UPLOAD_DIR     = os.environ.get("UPLOAD_DIR", "/app/uploads")

VALID_DOC_TYPES = {"paystub", "tax_return", "bank_statement", "id_document", "other"}


@router.post("/document")
async def upload_document(
    session_id:    str        = Form(...),
    document_type: str        = Form(...),
    file:          UploadFile = File(...),
):
    # ── Validate session ─────────────────────────────────────
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # ── Validate document type ────────────────────────────────
    if document_type not in VALID_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document_type.")

    # ── Validate file extension ───────────────────────────────
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="File type not allowed. Use PDF, JPG, or PNG.")

    contents = await file.read()
    if len(contents) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    # ── Save to disk ──────────────────────────────────────────
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path   = os.path.join(session_dir, stored_name)
    with open(file_path, "wb") as f:
        f.write(contents)

    logger.info(f"Saved {document_type} for session {session_id}: {stored_name} ({len(contents)} bytes)")

    # ── Update Redis session ──────────────────────────────────
    docs = session.get("documents_uploaded", [])
    docs.append({
        "type":              document_type,
        "original_filename": file.filename,
        "stored_filename":   stored_name,
        "file_path":         file_path,
        "size_bytes":        len(contents),
    })
    session["documents_uploaded"] = docs
    await set_session(session_id, session)

    # ── Persist to PostgreSQL ─────────────────────────────────
    application_id = session.get("application_id")
    if application_id:
        mime_map = {
            ".pdf":  "application/pdf",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".webp": "image/webp",
        }
        mime = mime_map.get(ext, "application/octet-stream")
        try:
            await repo.save_document(
                application_id=application_id,
                document_type=document_type,
                original_filename=file.filename or stored_name,
                stored_filename=stored_name,
                file_path=file_path,
                mime_type=mime,
                file_size_bytes=len(contents),
            )
        except Exception as e:
            logger.warning(f"[DB] save_document failed: {e}")

    return {
        "status":        "ok",
        "document_type": document_type,
        "filename":      file.filename,
        "size_bytes":    len(contents),
        "docs_uploaded": len(docs),
    }
