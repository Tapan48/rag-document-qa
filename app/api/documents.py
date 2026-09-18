import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.documents.queries import get_owned_document
from app.documents.schemas import DocumentList, DocumentPublic
from app.ingestion.tasks import process_document
from app.models.document import Document, DocumentStatus
from app.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
_UPLOAD_CHUNK_BYTES = 1024 * 1024


@router.post("", response_model=DocumentPublic, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Unsupported file type")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    storage_path = Path(settings.upload_dir) / f"{uuid.uuid4()}{extension}"

    size = 0
    try:
        with open(storage_path, "wb") as out:
            while data := await file.read(_UPLOAD_CHUNK_BYTES):
                size += len(data)
                if size > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds size limit"
                    )
                out.write(data)
    except HTTPException:
        storage_path.unlink(missing_ok=True)
        raise
    except OSError:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not read uploaded file")

    document = Document(
        owner_id=current_user.id,
        filename=file.filename or storage_path.name,
        storage_path=str(storage_path),
        status=DocumentStatus.QUEUED,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        process_document.delay(str(document.id))
    except Exception:
        document.status = DocumentStatus.FAILED
        document.error_message = "Could not queue document for processing"
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Processing queue unavailable")

    return document


@router.get("", response_model=DocumentList)
def list_documents(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentList:
    total = db.scalar(
        select(func.count()).select_from(Document).where(Document.owner_id == current_user.id)
    )
    items = list(
        db.execute(
            select(Document)
            .where(Document.owner_id == current_user.id)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return DocumentList(items=items, total=total or 0, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentPublic)
def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    return get_owned_document(db, document_id, current_user.id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    document = db.execute(
        select(Document)
        .where(Document.id == document_id, Document.owner_id == current_user.id)
        .with_for_update()
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    storage_path = Path(document.storage_path)
    db.delete(document)
    db.commit()
    storage_path.unlink(missing_ok=True)
