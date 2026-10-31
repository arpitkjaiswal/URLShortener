"""Link creation and validation, independent of HTTP concerns."""

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Url
from app.repositories.url_repository import UrlRepository
from app.schemas.url import UrlCreate
from app.utils.base62 import ALPHABET
from app.utils.validators import is_valid_url


class CodeGenerationError(Exception):
    pass


class ShortenerService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.repository = UrlRepository(session)
        self.settings = settings

    def shorten_url(self, payload: UrlCreate, owner_hash: str) -> Url:
        if not is_valid_url(payload.url):
            raise ValueError("Enter a valid http(s) URL without credentials or whitespace")
        destination = payload.url.strip()
        target = urlsplit(destination)
        own_origin = urlsplit(self.settings.normalized_base_url)
        if target.hostname == own_origin.hostname and target.port == own_origin.port:
            raise ValueError("Use an external destination, not a link to this shortener")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=payload.ttl_seconds)
            if payload.ttl_seconds is not None
            else None
        )
        for _ in range(5):
            short_code = "".join(secrets.choice(ALPHABET) for _ in range(7))
            try:
                url = self.repository.create(
                    destination, short_code, owner_hash, payload.ttl_seconds, expires_at
                )
                self.repository.session.commit()
                return url
            except IntegrityError as error:
                self.repository.session.rollback()
                # Only retry a short-code uniqueness violation, not other DB errors.
                constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", "")
                if constraint not in {
                    "ix_urls_short_code",
                    "urls_short_code_key",
                } and "UNIQUE constraint failed: urls.short_code" not in str(error.orig):
                    raise
        raise CodeGenerationError("Unable to allocate a link. Please try again.")

    def build_short_url(self, short_code: str) -> str:
        return f"{self.settings.normalized_base_url}/{short_code}"
