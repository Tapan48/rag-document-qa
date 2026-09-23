import hashlib
import hmac
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from redis import Redis, RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.service import _normalize_email, register_user
from app.config import settings
from app.models.access_request import AccessEmail, AccessRequest
from app.models.user import User

# Atomic admission across all API processes; no IP/proxy trust assumptions.
_NOTIFICATION_LIMIT = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
local count = tonumber(redis.call('GET', KEYS[2]) or '0')
if count >= 10 then return -1 end
redis.call('SET', KEYS[1], '1', 'EX', 86400)
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], 3600)
return 1
"""


def reserve_notification(email: str) -> bool:
    email_key = hashlib.sha256(email.encode()).hexdigest()
    try:
        with Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3) as redis:
            result = redis.eval(_NOTIFICATION_LIMIT, 2, f'access:email:{email_key}', f'access:hour:{int(time.time()) // 3600}')
    except RedisError:
        raise HTTPException(503, "Access requests are temporarily unavailable")
    if result == -1:
        raise HTTPException(429, "Too many access requests. Please try again later.")
    return result == 1


def invitation_token(request: AccessRequest) -> str:
    # Derive an opaque token so mail retries need neither plaintext DB storage
    # nor a secret in Celery arguments. Changing version revokes old links.
    message = f'access-invitation:{request.id}:{request.token_version}'.encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def enqueue_email(db: Session, request: AccessRequest, kind: str) -> AccessEmail:
    delivery = AccessEmail(request_id=request.id, kind=kind, token_version=request.token_version if kind == 'invitation' else None)
    db.add(delivery)
    db.flush()
    return delivery


def dispatch_email(db: Session, delivery_id: uuid.UUID) -> None:
    try:
        from app.access.tasks import deliver_access_email
        deliver_access_email.apply_async(args=[str(delivery_id)], retry=False)
    except Exception:
        # Durable delivery row remains visible/retryable in the admin UI.
        delivery = db.get(AccessEmail, delivery_id)
        if delivery and delivery.status == 'pending':
            delivery.status = 'failed'
            delivery.error = 'Could not queue email. Retry from Access requests.'
            db.commit()


def request_access(db: Session, email: str) -> None:
    email = _normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)):
        return
    existing = db.scalar(select(AccessRequest).where(AccessRequest.email == email))
    if existing and existing.status != 'pending':
        return
    if not reserve_notification(email):
        return
    db.execute(insert(AccessRequest).values(id=uuid.uuid4(), email=email, status='pending').on_conflict_do_nothing(index_elements=['email']))
    request = db.scalar(select(AccessRequest).where(AccessRequest.email == email).with_for_update())
    if request.status != 'pending':
        db.rollback()
        return
    delivery = enqueue_email(db, request, 'notification')
    delivery_id = delivery.id
    db.commit()
    dispatch_email(db, delivery_id)


def get_request(db: Session, request_id: uuid.UUID) -> AccessRequest:
    request = db.scalar(select(AccessRequest).where(AccessRequest.id == request_id).with_for_update())
    if request is None:
        raise HTTPException(404, 'Access request not found')
    return request


def approve_request(db: Session, request_id: uuid.UUID, admin_id: uuid.UUID) -> AccessRequest:
    request = get_request(db, request_id)
    if request.status == 'registered' or db.scalar(select(User.id).where(User.email == request.email)):
        raise HTTPException(409, 'An account already exists for this email')
    request.status = 'approved'
    request.reviewed_by = admin_id
    request.token_version = uuid.uuid4()
    request.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    request.token_hash = token_hash(invitation_token(request))
    delivery = enqueue_email(db, request, 'invitation')
    delivery_id = delivery.id
    db.commit()
    dispatch_email(db, delivery_id)
    return request


def reject_request(db: Session, request_id: uuid.UUID, admin_id: uuid.UUID) -> AccessRequest:
    request = get_request(db, request_id)
    if request.status == 'registered':
        raise HTTPException(409, 'This request has already been registered')
    request.status = 'rejected'
    request.reviewed_by = admin_id
    request.token_hash = None
    request.token_version = None
    request.expires_at = None
    db.commit()
    return request


def checked_invitation(db: Session, token: str, lock: bool = False) -> AccessRequest:
    query = select(AccessRequest).where(AccessRequest.token_hash == token_hash(token))
    if lock:
        query = query.with_for_update()
    request = db.scalar(query)
    if not request or request.status != 'approved' or not request.expires_at or request.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(400, 'Invitation is invalid, expired, or already used. Contact the person who invited you.')
    return request


def register_invited_user(db: Session, email: str, password: str, token: str) -> User:
    request = checked_invitation(db, token, lock=True)
    if request.email != _normalize_email(email):
        raise HTTPException(400, 'Use the email address this invitation was sent to')
    user = register_user(db, request.email, password, commit=False)
    request.status = 'registered'
    request.token_hash = None
    db.commit()
    db.refresh(user)
    return user


def retry_email(db: Session, delivery_id: uuid.UUID) -> None:
    # Same lock order as delivery tasks: delivery, then request.
    delivery = db.scalar(select(AccessEmail).where(AccessEmail.id == delivery_id).with_for_update())
    if delivery is None:
        raise HTTPException(404, 'Email delivery not found')
    stale = delivery.updated_at <= datetime.now(timezone.utc) - timedelta(minutes=5)
    if delivery.status not in ('failed', 'pending', 'retrying') or (delivery.status != 'failed' and not stale):
        raise HTTPException(409, 'Email is already sent or is still being processed')
    request = get_request(db, delivery.request_id)
    valid = request.status == 'pending' if delivery.kind == 'notification' else (
        request.status == 'approved' and delivery.token_version == request.token_version and
        request.expires_at > datetime.now(timezone.utc)
    )
    if not valid:
        raise HTTPException(409, 'Request changed or invitation expired. Use Approve / Resend invitation instead.')
    delivery.status = 'pending'
    delivery.attempts = 0
    delivery.error = None
    db.commit()
    dispatch_email(db, delivery_id)
