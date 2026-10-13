from __future__ import annotations

from fastapi import HTTPException, Request, UploadFile
from app.config import settings

ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx", "txt"}


async def validate_and_read_upload(
    file: UploadFile,
    request: Request | None = None,
    allowed_extensions: set[str] = ALLOWED_UPLOAD_EXTENSIONS,
    max_size_mb: int = settings.MAX_UPLOAD_SIZE_MB,
) -> tuple[bytes, str]:
    """
    Validates file extension and enforces MAX_UPLOAD_SIZE_MB.
    Rejects oversized files BEFORE loading them fully into memory by:
      1. Checking Content-Length header if present.
      2. Streaming the file in 64KB chunks and halting immediately if size exceeds limit.
    Returns (file_bytes, extension).
    """
    filename = file.filename or ""
    if "." not in filename:
        raise HTTPException(
            status_code=400,
            detail=f"File must have a valid extension. Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed types: {', '.join(sorted(allowed_extensions))}",
        )

    max_bytes = max_size_mb * 1024 * 1024

    # 1. Fast reject if Content-Length header is present and oversized
    if request:
        content_length_str = request.headers.get("content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum upload size of {max_size_mb} MB",
                    )
            except ValueError:
                pass

    # 2. Stream in chunks to avoid buffering oversized payloads into RAM
    chunks: list[bytes] = []
    total_size = 0
    chunk_size = 64 * 1024  # 64 KB

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum upload size of {max_size_mb} MB",
            )
        chunks.append(chunk)

    if total_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_bytes = b"".join(chunks)
    return file_bytes, ext
