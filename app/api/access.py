import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import service
from app.access.schemas import AccessRequestCreate, AccessRequestPublic, EmailPublic, InvitationCheck
from app.auth.dependencies import get_admin
from app.config import settings
from app.database import get_db
from app.models.access_request import AccessEmail, AccessRequest
from app.models.user import User

router = APIRouter(tags=['access'])


def require_approval_mode():
    if settings.effective_registration_mode != 'approval':
        raise HTTPException(403, 'Access requests are not enabled')


def public_request(db: Session, request: AccessRequest) -> AccessRequestPublic:
    result = AccessRequestPublic.model_validate(request)
    deliveries = db.scalars(select(AccessEmail).where(AccessEmail.request_id == request.id).order_by(AccessEmail.created_at.desc()).limit(5))
    result.deliveries = [EmailPublic.model_validate(delivery) for delivery in deliveries]
    return result


@router.post('/auth/access-requests', status_code=202, dependencies=[Depends(require_approval_mode)])
def create_request(payload: AccessRequestCreate, db: Session = Depends(get_db)):
    service.request_access(db, payload.email)
    return {'message': 'If eligible, your request will be reviewed. Check your email for an invitation after approval.'}


@router.post('/auth/invitations/validate', dependencies=[Depends(require_approval_mode)])
def validate_invitation(payload: InvitationCheck, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    request = service.checked_invitation(db, payload.token)
    return {'email': request.email, 'expires_at': request.expires_at}


@router.get('/admin/access-requests')
def list_requests(response: Response, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50), admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    requests = db.scalars(select(AccessRequest).order_by(AccessRequest.created_at.desc(), AccessRequest.id).offset(offset).limit(limit))
    return [public_request(db, request) for request in requests]


@router.post('/admin/access-requests/{request_id}/approve', response_model=AccessRequestPublic, dependencies=[Depends(require_approval_mode)])
def approve(request_id: uuid.UUID, admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    return public_request(db, service.approve_request(db, request_id, admin.id))


@router.post('/admin/access-requests/{request_id}/reject', response_model=AccessRequestPublic)
def reject(request_id: uuid.UUID, admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    return public_request(db, service.reject_request(db, request_id, admin.id))


@router.post('/admin/access-emails/{delivery_id}/retry', status_code=202, dependencies=[Depends(require_approval_mode)])
def retry(delivery_id: uuid.UUID, admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    service.retry_email(db, delivery_id)
    return {'message': 'Email delivery queued'}
