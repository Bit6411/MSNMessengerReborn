from pathlib import Path

from fastapi import HTTPException

from app.core.config import get_settings

# Detect actual file signatures, not just the untrusted Content-Type header.
def inspect_media(header: bytes) -> tuple[str, str]:
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "video/mp4", ".mp4"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm", ".webm"
    raise HTTPException(status_code=415, detail="Only JPEG, PNG, GIF, WebP, MP4 and WebM are supported")


def resolve_storage_path(stored_name: str) -> Path:
    # stored_name is always generated on the server, never supplied by a user.
    return get_settings().upload_path / stored_name
