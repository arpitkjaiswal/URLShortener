"""Regression checks for deployment and link-management features."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.db.models import Url
from app.db.database import create_engine_for_database


def test_custom_alias_conflict_reserved_and_validation(client):
    response = client.post('/api/v1/shorten', json={'url':'https://example.com', 'custom_alias':'summer-sale'})
    assert response.status_code == 201
    assert response.json()['short_code'] == 'summer-sale'
    assert client.get('/summer-sale', follow_redirects=False).status_code == 307
    assert client.post('/api/v1/shorten', json={'url':'https://example.com', 'custom_alias':'summer-sale'}).status_code == 400
    assert client.post('/api/v1/shorten', json={'url':'https://example.com', 'custom_alias':'health'}).status_code == 400
    assert client.post('/api/v1/shorten', json={'url':'https://example.com', 'custom_alias':'bad/alias'}).status_code == 422
    assert client.post('/api/v1/shorten', json={'url':'https://example.com', 'ttl_seconds':315360001}).status_code == 422


def test_management_key_protects_management_but_not_creation(settings):
    with TestClient(create_app(replace(settings, admin_token='test-only-key'))) as client:
        response = client.post('/api/v1/shorten', json={'url':'https://example.com'})
        assert response.status_code == 201
        code = response.json()['short_code']
        for method, path in [('GET','/api/v1/urls'), ('GET',f'/api/v1/stats/{code}'), ('DELETE',f'/api/v1/urls/{code}')]:
            assert client.request(method, path).status_code == 401
            assert client.request(method, path, headers={'X-Admin-Token':'wrong'}).status_code == 401
        headers = {'X-Admin-Token':'test-only-key'}
        assert len(client.get('/api/v1/urls', headers=headers).json()) == 1
        assert client.get(f'/{code}', follow_redirects=False).status_code == 307
        assert client.get(f'/api/v1/stats/{code}', headers=headers).json()['clicks'] == 1
        assert client.delete(f'/api/v1/urls/{code}', headers=headers).status_code == 200
        assert client.get(f'/{code}', follow_redirects=False).status_code == 404


def test_qr_download_and_delete_invalidation(client):
    code = client.post('/api/v1/shorten', json={'url':'https://example.com'}).json()['short_code']
    response = client.get(f'/api/v1/qr/{code}')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('image/svg+xml')
    assert b'<svg' in response.content
    assert client.get(f'/api/v1/stats/{code}').json()['clicks'] == 0
    assert client.delete(f'/api/v1/urls/{code}').status_code == 200
    assert client.get(f'/api/v1/qr/{code}').status_code == 404


def test_expiry_from_database_survives_cached_lookup(client, db_session):
    code = client.post('/api/v1/shorten', json={'url':'https://example.com', 'ttl_seconds':60}).json()['short_code']
    client.app.state.url_cache.clear()
    assert client.get(f'/{code}', follow_redirects=False).status_code == 307
    assert client.get(f'/{code}', follow_redirects=False).status_code == 307
    assert client.get(f'/api/v1/stats/{code}').json()['clicks'] == 2


def test_render_postgres_url_selects_installed_driver():
    with patch('app.db.database.create_engine') as create:
        create_engine_for_database('postgres://user:password@localhost/test')
        assert create.call_args.args[0] == 'postgresql+psycopg://user:password@localhost/test'


def test_missing_link_gives_browser_recovery_page(client):
    response = client.get('/unknown-link', headers={'Accept':'text/html'})
    assert response.status_code == 404
    assert 'This link is unavailable.' in response.text
    assert 'Create a new short link' in response.text
    assert client.get('/unknown-link').json() == {'detail':'Short URL not found'}


def test_render_requires_persistent_storage_and_management_key(monkeypatch):
    import pytest
    from app.core.config import get_settings
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match='external PostgreSQL'):
            get_settings()
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:unused@example.invalid/db?sslmode=require')
        with pytest.raises(ValueError, match='ADMIN_TOKEN'):
            get_settings()
        monkeypatch.setenv('ADMIN_TOKEN', 'test-only')
        assert get_settings().database_url.endswith('sslmode=require')
    finally:
        get_settings.cache_clear()
