"""Persistence operations; ownership is enforced in every management query."""

from datetime import datetime, timezone

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import Url


class UrlRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        original_url: str,
        short_code: str,
        owner_hash: str,
        ttl_seconds: int | None,
        expires_at: datetime | None,
    ) -> Url:
        url = Url(
            original_url=original_url,
            short_code=short_code,
            owner_hash=owner_hash,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
        )
        self.session.add(url)
        self.session.flush()
        return url

    def get_owned(self, short_code: str, owner_hash: str) -> Url | None:
        return self.session.scalar(
            select(Url).where(Url.short_code == short_code, Url.owner_hash == owner_hash)
        )

    def resolve(self, short_code: str, count_click: bool = True) -> str | None:
        now = datetime.now(timezone.utc)
        conditions = (Url.short_code == short_code, or_(Url.expires_at.is_(None), Url.expires_at > now))
        if not count_click:
            return self.session.scalar(select(Url.original_url).where(*conditions))
        # One atomic write prevents lost increments and expires links before counting.
        statement = (
            update(Url)
            .where(*conditions)
            .values(clicks=Url.clicks + 1, last_accessed=now)
            .returning(Url.original_url)
        )
        destination = self.session.scalar(statement)
        self.session.commit()
        return destination

    def list_recent(self, owner_hash: str, limit: int, offset: int, query: str) -> tuple[list[Url], int]:
        conditions = [Url.owner_hash == owner_hash]
        if query:
            conditions.append(
                or_(
                    Url.original_url.icontains(query, autoescape=True),
                    Url.short_code.icontains(query, autoescape=True),
                )
            )
        total = self.session.scalar(select(func.count()).select_from(Url).where(*conditions))
        items = self.session.scalars(
            select(Url)
            .where(*conditions)
            .order_by(Url.created_at.desc(), Url.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return list(items), total

    def summary(self, owner_hash: str) -> dict:
        now = datetime.now(timezone.utc)
        total, clicks, expired = self.session.execute(
            select(
                func.count(Url.id),
                func.coalesce(func.sum(Url.clicks), 0),
                func.coalesce(func.sum(case((Url.expires_at <= now, 1), else_=0)), 0),
            ).where(Url.owner_hash == owner_hash)
        ).one()
        return {
            "total_links": total,
            "total_clicks": clicks,
            "active_links": total - expired,
            "expired_links": expired,
        }

    def delete_owned(self, short_code: str, owner_hash: str) -> bool:
        result = self.session.execute(
            delete(Url).where(Url.short_code == short_code, Url.owner_hash == owner_hash)
        )
        self.session.commit()
        return result.rowcount > 0
