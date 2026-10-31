"""End-to-end coverage of library queries, aggregates, pause, and bulk tools."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.database import init_db
from app.db.models import DailyClick, LinkDetails, Url
from app.main import create_app
from app.repositories.url_repository import UrlRepository
from app.services.shortener import record_click_task


def create(client, name='example', **extra):
    response = client.post('/api/v1/shorten', json={'url':f'https://example.com/{name}', **extra})
    assert response.status_code == 201
    return response.json()['short_code']


def test_metadata_survives_restart_and_schema_setup_is_repeatable(client, settings, session_factory):
    code = create(client)
    response = client.patch('/api/v1/urls/'+code, json={'title':' Summer guide ', 'tag':' newsletter '})
    assert response.json()['title'] == 'Summer guide'
    assert response.json()['tag'] == 'newsletter'
    with session_factory() as session:
        init_db(session.get_bind())
        init_db(session.get_bind())
    restarted = TestClient(create_app(settings), headers={'X-Admin-Token':settings.admin_token})
    page = restarted.get('/api/v1/library?q=summer').json()
    assert page['total'] == 1
    assert page['items'][0]['short_code'] == code
    assert restarted.get('/'+code,follow_redirects=False).status_code == 307


def test_pause_resume_blocks_cached_redirects_and_qr_without_losing_counts(client):
    code = create(client)
    assert client.get('/'+code,follow_redirects=False).status_code == 307
    assert client.patch('/api/v1/urls/'+code,json={'is_paused':True}).json()['is_paused'] is True
    assert client.get('/'+code,follow_redirects=False).status_code == 404
    assert client.get('/api/v1/qr/'+code).status_code == 404
    data = client.get('/api/v1/analytics/'+code).json()
    assert data['link']['clicks'] == 1 and data['link']['is_paused']
    assert client.get('/api/v1/library?state=paused').json()['total'] == 1
    assert client.patch('/api/v1/urls/'+code,json={'is_paused':False}).json()['is_paused'] is False
    assert client.get('/'+code,follow_redirects=False).status_code == 307
    assert client.get('/api/v1/stats/'+code).json()['clicks'] == 2


def test_library_queries_across_pages_and_correct_global_totals(client, db_session):
    codes=[]
    # Both public and bulk creation share a fixed window. Advance the test clock for later rows.
    for i in range(23):
        if i == 20:
            with patch('app.core.security.monotonic',return_value=10**12):
                codes.append(create(client,f'link-{i}'))
        else:
            codes.append(create(client,f'link-{i}'))
    for code in codes[:2]:
        client.patch('/api/v1/urls/'+code,json={'title':'Launch guide', 'tag':'marketing'})
    client.patch('/api/v1/urls/'+codes[0],json={'is_paused':True})
    record=db_session.query(Url).filter_by(short_code=codes[1]).one()
    record.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    db_session.commit()
    page=client.get('/api/v1/library?page_size=20').json()
    assert page['total']==23 and len(page['items'])==20 and page['total_pages']==2
    assert page['summary']=={'links':23,'clicks':0,'active':21,'paused':1,'expired':1}
    assert page['tags']==['marketing']
    next_page=client.get('/api/v1/library?page=2&page_size=20').json()
    assert len(next_page['items'])==3
    assert not set(i['short_code'] for i in page['items']) & set(i['short_code'] for i in next_page['items'])
    assert client.get('/api/v1/library?q=LAUNCH').json()['total']==2
    assert client.get('/api/v1/library?tag=marketing&state=expired').json()['total']==1
    assert client.get('/api/v1/library?q=%25').json()['total']==0  # '%' is a literal, not a wildcard.
    assert client.get('/api/v1/library?sort=oldest').json()['items'][0]['short_code']==codes[0]
    assert client.get('/api/v1/library?page=999').json()['page']==2
    assert client.get('/api/v1/library?sort=unsafe').status_code==422


def test_bulk_partial_results_and_limit_do_not_bypass_rate_limits(client):
    response=client.post('/api/v1/bulk',json={'urls':['https://example.com/one','javascript:alert(1)','https://example.org/two']})
    assert response.status_code==200
    results=response.json()
    assert results[0]['short_url'] and results[2]['short_url']
    assert results[1]['error']=='Invalid URL' and results[1]['index']==1
    assert client.get('/api/v1/library').json()['total']==2
    response=client.post('/api/v1/bulk',json={'urls':['https://example.com']*20})
    assert sum(bool(r['short_url']) for r in response.json())==17
    assert all(r['error'] for r in response.json()[17:])
    assert client.post('/api/v1/shorten',json={'url':'https://example.com'}).status_code==429
    assert client.post('/api/v1/bulk',json={'urls':['https://example.com']*21}).status_code==422


def test_new_private_routes_never_expose_data_without_authentication(settings):
    client=TestClient(create_app(settings))
    for method, endpoint, body in [('GET','library',None),('GET','analytics/secret',None),('POST','bulk',{'urls':['https://example.com']})]:
        assert client.request(method,'/api/v1/'+endpoint,json=body).status_code==401
    assert client.patch('/api/v1/urls/secret',json={'is_paused':True}).status_code==401


def test_daily_counts_zero_fill_concurrent_updates_and_delete_cascade(client, session_factory, db_session):
    code=create(client)
    # Exercise separate background-task sessions as concurrent redirects do.
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _:record_click_task(session_factory,code),range(12)))
    data=client.get('/api/v1/analytics/'+code).json()
    assert len(data['days'])==14
    assert sum(d['clicks'] for d in data['days'])==12
    assert data['days'][-1]['clicks']==12
    assert data['link']['clicks']==12 and data['last_accessed']
    assert all(d['clicks']==0 for d in data['days'][:-1])
    assert 'No visitor identifiers' in data['tracking_note']
    client.patch('/api/v1/urls/'+code,json={'title':'A title'})
    assert client.delete('/api/v1/urls/'+code).status_code==200
    assert db_session.scalar(select(func.count()).select_from(DailyClick))==0
    assert db_session.scalar(select(func.count()).select_from(LinkDetails))==0
    assert client.get('/api/v1/analytics/'+code).status_code==404
