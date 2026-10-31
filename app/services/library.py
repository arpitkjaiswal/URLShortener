"""Private library queries and analytics, independent of the browser's current page."""
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import contains_eager

from app.db.models import DailyClick, LinkDetails, Url
from app.schemas.url import LibraryPage, LibraryQuery, LibrarySummary, UrlListItem


def list_item(url, service):
    return UrlListItem(
        short_code=url.short_code, original_url=url.original_url,
        short_url=service.build_short_url(url.short_code), clicks=url.clicks,
        created_at=url.created_at, expires_at=url.expires_at,
        title=url.title, tag=url.tag, is_paused=url.is_paused,
    )


def conditions(query, now):
    live = or_(Url.expires_at.is_(None), Url.expires_at > now)
    paused = func.coalesce(LinkDetails.is_paused, False)
    filters = []
    term = query.q.strip().lower()
    if term:
        filters.append(or_(*[
            func.lower(field).contains(term, autoescape=True)
            for field in (Url.short_code, Url.original_url, LinkDetails.title, LinkDetails.tag)
        ]))
    if query.tag:
        filters.append(LinkDetails.tag == query.tag)
    if query.state == 'active':
        filters.extend([live, paused.is_(False)])
    elif query.state == 'paused':
        filters.extend([live, paused.is_(True)])
    elif query.state == 'expired':
        filters.append(Url.expires_at <= now)
    return filters


def library_page(service, query: LibraryQuery):
    session = service.repository.session
    now = datetime.now(timezone.utc)
    filters = conditions(query, now)
    count = select(func.count(Url.id)).outerjoin(Url.details).where(*filters)
    total = session.scalar(count) or 0
    page = min(query.page, max(1, ceil(total / query.page_size)))
    ordering = {'newest': Url.id.desc(), 'oldest': Url.id.asc(), 'clicks': Url.clicks.desc()}[query.sort]
    stmt = (select(Url).outerjoin(Url.details).options(contains_eager(Url.details))
            .where(*filters).order_by(ordering, Url.id.desc())
            .offset((page - 1) * query.page_size).limit(query.page_size))
    items = [list_item(url, service) for url in session.scalars(stmt).all()]
    live = or_(Url.expires_at.is_(None), Url.expires_at > now)
    paused = func.coalesce(LinkDetails.is_paused, False)
    summary = session.execute(select(
        func.count(Url.id), func.coalesce(func.sum(Url.clicks), 0),
        func.coalesce(func.sum(case((live & paused.is_(False), 1), else_=0)), 0),
        func.coalesce(func.sum(case((live & paused.is_(True), 1), else_=0)), 0),
        func.coalesce(func.sum(case((Url.expires_at <= now, 1), else_=0)), 0),
    ).outerjoin(Url.details)).one()
    tags = session.scalars(select(LinkDetails.tag).where(LinkDetails.tag != '').distinct().order_by(LinkDetails.tag).limit(100)).all()
    return LibraryPage(items=items, total=total, page=page, page_size=query.page_size,
                       total_pages=max(1, ceil(total / query.page_size)),
                       summary=LibrarySummary(**dict(zip(('links', 'clicks', 'active', 'paused', 'expired'), summary))), tags=tags)


def analytics(service, code):
    session = service.repository.session
    url = service.repository.get_by_short_code(code)
    if url is None:
        return None
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=13)
    rows = session.execute(select(DailyClick.day, DailyClick.clicks).where(
        DailyClick.url_id == url.id, DailyClick.day >= first, DailyClick.day <= today)).all()
    counts = dict(rows)
    return {
        'link': list_item(url, service), 'last_accessed': url.last_accessed,
        'days': [{'day': (first + timedelta(days=i)).isoformat(),
                  'clicks': counts.get(first + timedelta(days=i), 0)} for i in range(14)],
        'tracking_note': 'UTC daily totals since this upgrade. Earlier clicks remain in the all-time total. No visitor identifiers are collected.',
    }
