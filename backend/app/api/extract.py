from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.core.dependencies import get_current_user
from app.core.upload_security import validate_and_read_upload
from app.models.user import User
from extractor.main import extract_from_path


router = APIRouter(tags=["Universal Extraction"])
logger = logging.getLogger("extract.api")


@router.post("/extract")
async def extract_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    payload, ext = await validate_and_read_upload(file, request=request)
    suffix = f".{ext}" if ext else ""

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(payload)
            temp_path = tmp.name

        return extract_from_path(temp_path, original_name=file.filename)

    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Extraction failed")
        raise HTTPException(status_code=500, detail="Failed to extract document") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
