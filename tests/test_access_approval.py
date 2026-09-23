from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException
import pytest
from sqlalchemy import select, delete

from app import cli
from app.access import service, tasks, mail
from app.auth.security import create_access_token, verify_password
from app.auth.service import register_user
from app.config import settings
from app.database import SessionLocal
from app.models.access_request import AccessEmail, AccessRequest
from app.models.user import User

_real_dispatch_email = service.dispatch_email


@pytest.fixture
def approvals(db_session, monkeypatch):
    monkeypatch.setattr(settings, 'registration_mode', 'approval')
    monkeypatch.setattr(service, 'reserve_notification', lambda email: True)
    monkeypatch.setattr(service, 'dispatch_email', lambda db, delivery_id: None)
    admin = register_user(db_session, 'owner@example.com', 'owner-test-password')
    admin.is_admin = True
    db_session.commit()
    return admin, {'Authorization': 'Bearer ' + create_access_token(admin.id)}


def request_and_approve(client, db_session, approvals):
    assert client.post('/auth/access-requests', json={'email': 'Reviewer@Example.com'}).status_code == 202
    req = db_session.scalar(select(AccessRequest).where(AccessRequest.email == 'reviewer@example.com'))
    assert client.post(f'/admin/access-requests/{req.id}/approve', headers=approvals[1]).status_code == 200
    return req, service.invitation_token(req)


def test_complete_flow_email_binding_and_single_use(client, db_session, approvals, monkeypatch):
    delivered = []
    monkeypatch.setattr(tasks, 'send_email', lambda *args: delivered.append(args))
    client.post('/auth/access-requests', json={'email': 'Reviewer@Example.com'})
    req = db_session.scalar(select(AccessRequest).where(AccessRequest.email == 'reviewer@example.com'))
    notification = db_session.scalar(select(AccessEmail).where(AccessEmail.request_id == req.id))
    assert tasks.deliver_once(db_session, notification.id) is False
    assert delivered[0][0] == 'tapangarasangi@gmail.com'
    assert '/admin/access-requests' in delivered[0][2]
    assert req.status == 'pending'  # Opening email/admin list cannot approve.
    assert client.post('/auth/register', json={'email': req.email, 'password': 'reviewer-password'}).status_code == 403
    result = client.post(f'/admin/access-requests/{req.id}/approve', headers=approvals[1])
    assert result.status_code == 200
    token = service.invitation_token(req)
    assert req.token_hash != token
    invitation = db_session.scalar(select(AccessEmail).where(AccessEmail.request_id == req.id, AccessEmail.kind == 'invitation'))
    assert tasks.deliver_once(db_session, invitation.id) is False
    assert delivered[-1][0] == req.email
    assert '#token=' + token in delivered[-1][2]
    assert token not in result.text
    validated = client.post('/auth/invitations/validate', json={'token': token})
    assert validated.json()['email'] == req.email
    assert validated.headers['cache-control'] == 'no-store'
    assert client.post('/auth/register', json={'email': 'other@example.com', 'password': 'reviewer-password', 'invitation_token': token}).status_code == 400
    result = client.post('/auth/register', json={'email': 'REVIEWER@example.com', 'password': 'reviewer-password', 'invitation_token': token, 'is_admin': True})
    assert result.status_code == 201
    assert result.json()['is_admin'] is False
    created = db_session.get(User, uuid.UUID(result.json()['id']))
    assert verify_password('reviewer-password', created.password_hash)
    assert req.status == 'registered'
    assert client.post('/auth/invitations/validate', json={'token': token}).status_code == 400
    assert client.post('/auth/register', json={'email': req.email, 'password': 'reviewer-password', 'invitation_token': token}).status_code == 400
    assert client.post('/auth/login', json={'email': req.email, 'password': 'reviewer-password'}).status_code == 200


def test_nonadmins_cannot_list_approve_reject_retry(client, db_session, approvals):
    req, _ = request_and_approve(client, db_session, approvals)
    reviewer = register_user(db_session, 'ordinary@example.com', 'ordinary-password')
    headers = {'Authorization': 'Bearer ' + create_access_token(reviewer.id)}
    assert client.get('/admin/access-requests').status_code in (401,403)
    assert client.get('/admin/access-requests', headers=headers).status_code == 403
    for suffix in ['approve', 'reject']:
        assert client.post(f'/admin/access-requests/{req.id}/{suffix}', headers=headers).status_code == 403
    assert client.post(f'/admin/access-emails/{uuid.uuid4()}/retry', headers=headers).status_code == 403
    assert req.status == 'approved'


def test_resend_reject_and_expiration_revoke_links(client, db_session, approvals):
    req, first = request_and_approve(client, db_session, approvals)
    client.post(f'/admin/access-requests/{req.id}/approve', headers=approvals[1])
    second = service.invitation_token(req)
    assert first != second
    assert client.post('/auth/invitations/validate', json={'token': first}).status_code == 400
    req.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.post('/auth/register', json={'email': req.email, 'password': 'reviewer-password', 'invitation_token': second}).status_code == 400
    client.post(f'/admin/access-requests/{req.id}/approve', headers=approvals[1])
    third = service.invitation_token(req)
    client.post(f'/admin/access-requests/{req.id}/reject', headers=approvals[1])
    assert client.post('/auth/invitations/validate', json={'token': third}).status_code == 400


def test_duplicate_requests_do_not_repeat_notification(client, db_session, approvals, monkeypatch):
    reservations = iter([True, False])
    monkeypatch.setattr(service, 'reserve_notification', lambda email: next(reservations))
    first = client.post('/auth/access-requests', json={'email':'reviewer@example.com'})
    second = client.post('/auth/access-requests', json={'email':'REVIEWER@example.com'})
    existing = client.post('/auth/access-requests', json={'email':'owner@example.com'})
    assert first.status_code == second.status_code == existing.status_code == 202
    assert first.json() == second.json() == existing.json()
    assert len(list(db_session.scalars(select(AccessRequest)))) == 1
    assert len(list(db_session.scalars(select(AccessEmail)))) == 1


def test_limits_and_redis_outage_fail_without_creating_request(client, db_session, approvals, monkeypatch):
    for code in (429,503):
        def fail(email): raise HTTPException(code, 'Temporarily unavailable')
        monkeypatch.setattr(service, 'reserve_notification', fail)
        assert client.post('/auth/access-requests', json={'email':'reviewer@example.com'}).status_code == code
        assert db_session.scalar(select(AccessRequest)) is None


def test_limiter_script_is_atomic_and_expires_keys():
    # Isolated test Redis namespace: no global flush and no existing app keys.
    from redis import Redis
    suffix = uuid.uuid4().hex
    global_key = f'test-access:{suffix}:hour'
    email_keys = [f'test-access:{suffix}:email:{i}' for i in range(11)]
    with Redis.from_url(settings.redis_url) as redis:
        try:
            assert redis.eval(service._NOTIFICATION_LIMIT, 2, email_keys[0], global_key) == 1
            assert redis.eval(service._NOTIFICATION_LIMIT, 2, email_keys[0], global_key) == 0
            def reserve(key): return redis.eval(service._NOTIFICATION_LIMIT, 2, key, global_key)
            with ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(reserve, email_keys[1:]))
            assert results.count(1) == 9 and results.count(-1) == 1
            assert 0 < redis.ttl(email_keys[0]) <= 86400
            assert 0 < redis.ttl(global_key) <= 3600
        finally: redis.delete(global_key, *email_keys)


def test_email_retries_are_bounded_safe_and_recoverable(client, db_session, approvals, monkeypatch):
    req, token = request_and_approve(client, db_session, approvals)
    delivery = db_session.scalar(select(AccessEmail).where(AccessEmail.kind == 'invitation'))
    def fail(*args): raise RuntimeError('sensitive SMTP detail '+token)
    monkeypatch.setattr(tasks, 'send_email', fail)
    assert tasks.deliver_once(db_session, delivery.id) is True
    assert tasks.deliver_once(db_session, delivery.id) is True
    assert tasks.deliver_once(db_session, delivery.id) is False
    assert delivery.status == 'failed' and delivery.attempts == 3
    assert token not in delivery.error
    assert client.post(f'/admin/access-emails/{delivery.id}/retry', headers=approvals[1]).status_code == 202
    monkeypatch.setattr(tasks, 'send_email', lambda *args: None)
    assert tasks.deliver_once(db_session, delivery.id) is False
    assert delivery.status == 'sent'
    assert client.post(f'/admin/access-emails/{delivery.id}/retry', headers=approvals[1]).status_code == 409


def test_stale_jobs_cancel_without_sending(client, db_session, approvals, monkeypatch):
    req, _ = request_and_approve(client, db_session, approvals)
    jobs = list(db_session.scalars(select(AccessEmail)))
    client.post(f'/admin/access-requests/{req.id}/reject', headers=approvals[1])
    monkeypatch.setattr(tasks, 'send_email', lambda *args: pytest.fail('Stale email must not send'))
    for job in jobs:
        tasks.deliver_once(db_session, job.id)
        assert job.status == 'cancelled'


def test_queue_failure_is_visible_and_retryable(client, db_session, approvals, monkeypatch):
    req, _ = request_and_approve(client, db_session, approvals)
    delivery = db_session.scalar(select(AccessEmail).where(AccessEmail.kind == 'invitation'))
    from app.access.tasks import deliver_access_email
    monkeypatch.setattr(deliver_access_email, 'apply_async', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('private broker detail')))
    _real_dispatch_email(db_session, delivery.id)
    assert delivery.status == 'failed'
    assert 'private broker' not in delivery.error


def test_closed_mode_and_legacy_behavior(client, db_session, approvals, monkeypatch):
    req, token = request_and_approve(client, db_session, approvals)
    monkeypatch.setattr(settings, 'registration_mode', 'closed')
    assert client.post('/auth/access-requests', json={'email':'new@example.com'}).status_code == 403
    assert client.post('/auth/register', json={'email':req.email,'password':'reviewer-password','invitation_token':token}).status_code == 403
    assert client.post('/auth/login', json={'email':'owner@example.com','password':'owner-test-password'}).status_code == 200
    monkeypatch.setattr(settings, 'registration_mode', 'open')
    assert client.post('/auth/register', json={'email':'new@example.com','password':'reviewer-password'}).status_code == 201


def test_cli_grants_existing_admin_only(db_session, monkeypatch, capsys):
    user = register_user(db_session, 'owner@example.com', 'owner-password')
    monkeypatch.setattr(cli, 'SessionLocal', lambda: nullcontext(db_session))
    assert cli.main(['grant-admin','--email','OWNER@example.com']) == 0
    assert user.is_admin
    assert cli.main(['grant-admin','--email','missing@example.com']) == 1
    assert cli.main(['grant-admin','--email','not-an-email']) == 2


def test_simultaneous_invitation_registration_creates_one_account(monkeypatch):
    # Committed setup is required: independent connections must see the same row.
    email = 'race-'+uuid.uuid4().hex+'@example.com'
    with SessionLocal() as db:
        req = AccessRequest(id=uuid.uuid4(),email=email,status='approved',token_version=uuid.uuid4(),expires_at=datetime.now(timezone.utc)+timedelta(days=7))
        token = service.invitation_token(req)
        req.token_hash = service.token_hash(token)
        db.add(req); db.commit()
    def register():
        with SessionLocal() as db:
            try:
                service.register_invited_user(db,email,'concurrent-password',token)
                return 201
            except HTTPException as error:return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: register(),range(2)))
        assert sorted(outcomes) == [201,400]
        with SessionLocal() as db:
            assert len(list(db.scalars(select(User).where(User.email == email)))) == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(AccessRequest).where(AccessRequest.email == email))
            db.execute(delete(User).where(User.email == email))
            db.commit()


def test_smtp_uses_starttls_and_app_password(monkeypatch):
    from pydantic import SecretStr
    calls = []
    class SMTP:
        def __init__(self, host, port, timeout): calls.append(('connect',host,port,timeout))
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def ehlo(self): calls.append(('ehlo',))
        def starttls(self,context):
            assert context.check_hostname
            calls.append(('tls',))
        def login(self,username,password): calls.append(('login',username,password))
        def send_message(self,message): calls.append(('send',message))
    monkeypatch.setattr(mail.smtplib,'SMTP',SMTP)
    monkeypatch.setattr(settings,'smtp_username','owner@example.com')
    monkeypatch.setattr(settings,'smtp_password',SecretStr('test-app-password'))
    mail.send_email('reviewer@example.com','Test subject','Test body')
    assert calls[2] == ('tls',)
    assert calls[4] == ('login','owner@example.com','test-app-password')
    assert calls[5][1]['To'] == 'reviewer@example.com'
    assert calls[5][1]['From'] == 'owner@example.com'
