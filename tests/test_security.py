"""Authorization, session lifecycle, privacy, and abuse regression coverage."""
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import COOKIE_NAME
from app.main import create_app


def public_client(settings):
    return TestClient(create_app(settings))


def test_management_fails_closed_without_a_key(settings):
    client = public_client(replace(settings, admin_token=None))
    assert client.get('/api/v1/urls').status_code == 503
    assert client.post('/api/v1/auth/login', json={'key':'anything'}).status_code == 503
    assert client.post('/api/v1/shorten', json={'url':'https://example.com'}).status_code == 201


def test_private_endpoints_deny_requests_without_authorization(settings):
    client = public_client(settings)
    code = client.post('/api/v1/shorten', json={'url':'https://example.com/private-marker'}).json()['short_code']
    for method, path, body in [('GET','urls',None),('GET',f'stats/{code}',None),('DELETE',f'urls/{code}',None),('PATCH',f'urls/{code}',{'url':'https://example.org'})]:
        response = client.request(method, '/api/v1/'+path, json=body)
        assert response.status_code == 401
        assert 'private-marker' not in response.text
        assert response.headers['cache-control'] == 'no-store'
    # A short link deliberately exposes its destination; it isn't an access control.
    assert client.get('/'+code, follow_redirects=False).headers['location'] == 'https://example.com/private-marker'


def test_session_cookie_logout_csrf_and_expiry(settings):
    client = public_client(settings)
    code = client.post('/api/v1/shorten', json={'url':'https://example.com'}).json()['short_code']
    assert client.post('/api/v1/auth/login', json={'key':settings.admin_token}, headers={'Origin':'https://evil.example'}).status_code == 403
    response = client.post('/api/v1/auth/login', json={'key':settings.admin_token})
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    token = client.cookies.get(COOKIE_NAME)
    assert client.get('/api/v1/urls').status_code == 200
    for origin in (None, 'https://evil.example'):
        headers = {'Origin':origin} if origin else {}
        assert client.delete('/api/v1/urls/'+code, headers=headers).status_code == 403
    assert client.post('/api/v1/auth/logout', headers={'Origin':settings.base_url}).status_code == 200
    client.cookies.set(COOKIE_NAME, token, path='/api/v1')
    assert client.get('/api/v1/urls').status_code == 401  # Revoked even if the cookie is replayed.
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'key':settings.admin_token})
    with patch('app.core.security.monotonic', return_value=10**12):
        assert client.get('/api/v1/urls').status_code == 401


def test_https_cookie_and_key_rotation_invalidate_sessions(settings):
    configured = replace(settings, base_url='https://testserver')
    client = TestClient(create_app(configured), base_url=configured.base_url)
    response = client.post('/api/v1/auth/login', json={'key':settings.admin_token})
    assert 'Secure' in response.headers['set-cookie']
    assert client.get('/api/v1/urls').status_code == 200
    client.app.state.settings = replace(configured, admin_token='rotated-key')
    assert client.get('/api/v1/urls').status_code == 401
    assert client.get('/').headers['strict-transport-security'] == 'max-age=31536000'


def test_rate_limits_login_and_public_creation(settings):
    client = public_client(settings)
    for _ in range(5):
        assert client.post('/api/v1/auth/login', json={'key':'wrong-key'}).status_code == 401
    response = client.post('/api/v1/auth/login', json={'key':'wrong-key'})
    assert response.status_code == 429 and int(response.headers['retry-after']) > 0
    for _ in range(20):
        assert client.post('/api/v1/shorten', json={'url':'https://example.com'}).status_code == 201
    assert client.post('/api/v1/shorten', json={'url':'https://example.com'}).status_code == 429
    with patch('app.core.security.monotonic', return_value=10**12):
        assert client.post('/api/v1/shorten', json={'url':'https://example.com'}).status_code == 201


def test_large_and_chunked_requests_are_rejected(client):
    assert client.post('/api/v1/shorten', content=b'X'*16385).status_code == 413
    assert client.post('/api/v1/shorten', content=iter([b'X'*9000,b'X'*9000])).status_code == 413


def test_security_headers_and_no_public_schema(client):
    response = client.get('/')
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['referrer-policy'] == 'no-referrer'
    for path in ('/docs','/openapi.json','/redoc','/static/../core/config.py','/.env','/requirements.lock'):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize('url', ['https://user:secret@example.com','https://example.com:bad','https://exam\nple.com', 'https://example.com\\@evil.example','javascript:alert(1)'])
def test_unsafe_destinations_rejected(client, url):
    assert client.post('/api/v1/shorten',json={'url':url}).status_code == 400


def test_update_preserves_code_clicks_and_expiry_and_invalidates_cache(client):
    created = client.post('/api/v1/shorten',json={'url':'https://example.com','ttl_seconds':60}).json()
    code = created['short_code']
    assert client.get('/'+code,follow_redirects=False).status_code == 307
    response = client.patch('/api/v1/urls/'+code,json={'url':'https://example.org/updated'})
    assert response.status_code == 200
    data = response.json()
    assert data['short_code'] == code and data['clicks'] == 1
    assert datetime.fromisoformat(data['expires_at']).replace(tzinfo=timezone.utc) == datetime.fromisoformat(created['expires_at']).replace(tzinfo=timezone.utc)
    assert client.get('/'+code,follow_redirects=False).headers['location'] == 'https://example.org/updated'
    response = client.patch('/api/v1/urls/'+code,json={'url':'https://example.org/updated','ttl_seconds':None})
    assert response.json()['expires_at'] is None
    assert client.patch('/api/v1/urls/'+code,json={'url':'javascript:alert(1)'}).status_code == 400
    assert client.patch('/api/v1/urls/missing',json={'url':'https://example.com'}).status_code == 404


def test_destinations_not_written_to_app_logs(client, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        code = client.post('/api/v1/shorten',json={'url':'https://example.com/?private=never-log-this'}).json()['short_code']
        client.get('/'+code,follow_redirects=False)
    assert 'never-log-this' not in caplog.text
