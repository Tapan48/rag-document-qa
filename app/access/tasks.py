import hmac
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.access.mail import send_email
from app.access.service import invitation_token, token_hash
from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models.access_request import AccessEmail, AccessRequest

MAX_ATTEMPTS = 3


def deliver_once(db, delivery_id: uuid.UUID) -> bool:
    """Return whether a transient SMTP failure should be retried.

    Locks serialize duplicate jobs and approval/rejection. Only IDs enter the
    broker. SMTP may accept an email before disconnecting: delivery is at least
    once, so duplicates are possible but never create additional accounts.
    """
    delivery = db.scalar(select(AccessEmail).where(AccessEmail.id == delivery_id).with_for_update())
    if not delivery or delivery.status in ('sent', 'cancelled') or delivery.attempts >= MAX_ATTEMPTS:
        return False
    request = db.scalar(select(AccessRequest).where(AccessRequest.id == delivery.request_id).with_for_update())
    url = settings.public_app_url.rstrip('/')
    valid = request and (request.status == 'pending' if delivery.kind == 'notification' else (
        request.status == 'approved' and delivery.token_version == request.token_version and
        request.expires_at > datetime.now(timezone.utc)
    ))
    if not valid:
        delivery.status = 'cancelled'
        delivery.error = None
        db.commit()
        return False
    if delivery.kind == 'notification':
        recipient = settings.access_notification_email
        subject = 'RAG app: access request'
        body = f'{request.email} requested access to your RAG app.\n\nReview requests after signing in:\n{url}/admin/access-requests\n\nOpening this link does not approve anyone.'
    else:
        token = invitation_token(request)
        if not hmac.compare_digest(token_hash(token), request.token_hash or ''):
            delivery.status = 'failed'
            delivery.error = 'Invitation signing configuration changed. Resend invitation.'
            db.commit()
            return False
        recipient = request.email
        subject = 'Your RAG app access is approved'
        body = f'Your request was approved. Set your own password using this single-use link:\n\n{url}/register#token={token}\n\nUse this link before {request.expires_at.isoformat()}.\nIf you did not request access, ignore this email.'
    delivery.attempts += 1
    try:
        send_email(recipient, subject, body)
    except Exception:
        retry = delivery.attempts < MAX_ATTEMPTS
        delivery.status = 'retrying' if retry else 'failed'
        delivery.error = 'Email delivery failed. Check SMTP configuration and retry.'
        db.commit()
        return retry
    delivery.status = 'sent'
    delivery.error = None
    db.commit()
    return False


@celery_app.task(bind=True, max_retries=2, acks_late=True, reject_on_worker_lost=True, ignore_result=True)
def deliver_access_email(self, delivery_id: str):
    with SessionLocal() as db:
        retry = deliver_once(db, uuid.UUID(delivery_id))
    if retry:
        # A sanitized exception prevents recipient, SMTP response, or token logs.
        raise self.retry(exc=RuntimeError('Email delivery temporarily unavailable'), countdown=60)
