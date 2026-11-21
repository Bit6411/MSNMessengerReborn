from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.crud.conversation import require_member
from app.models import Attachment
from app.schemas.message import AttachmentRead
from app.services.media import inspect_media, resolve_storage_path

router = APIRouter(tags=["Media"])


def to_read(item: Attachment) -> AttachmentRead:
    return AttachmentRead(
        id=item.id,
        original_name=item.original_name,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        url=f"/api/v1/media/{item.id}",
    )


@router.post("/conversations/{conversation_id}/attachments",
             response_model=AttachmentRead, status_code=status.HTTP_201_CREATED)
def upload_attachment(
    conversation_id: int, db: SessionDep, current_user: CurrentUser,
    file: UploadFile = File(...),
):
    require_member(db, conversation_id, current_user.id)
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    # Use the actual signature, not a user-supplied filename/MIME type.
    header = file.file.read(32)
    content_type, extension = inspect_media(header)
    stored_name = f"{uuid4().hex}{extension}"
    dest = resolve_storage_path(stored_name)
    max_size = settings.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with dest.open("wb") as target:
            size += len(header)
            target.write(header)
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise HTTPException(status_code=413, detail="File too large")
                target.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        attachment = Attachment(
            conversation_id=conversation_id,
            uploader_id=current_user.id,
            stored_name=stored_name,
            original_name=Path(file.filename or "upload").name[:255],
            content_type=content_type,
            size_bytes=size,
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
        return to_read(attachment)
    except Exception:
        db.rollback()
        dest.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()


@router.get("/media/{attachment_id}")
def download_attachment(attachment_id: int, db: SessionDep, current_user: CurrentUser):
    item = db.get(Attachment, attachment_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    require_member(db, item.conversation_id, current_user.id)
    # Don't reveal a staged upload to the other participant until it's sent.
    if item.message_id is None and item.uploader_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = resolve_storage_path(item.stored_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file missing")
    return FileResponse(path, media_type=item.content_type, filename=item.original_name,
                        content_disposition_type="inline",
                        headers={"X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "private, no-store"})
