"""Anonymous browser workspaces and bounded, per-process creation throttling."""

import hashlib
import math
import re
import secrets
import time
from collections import OrderedDict
from threading import Lock

from fastapi import HTTPException, Request, Response

COOKIE_NAME = "shortener_workspace"
TOKEN_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def initialize_workspace(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME, "")
    if not TOKEN_PATTERN.fullmatch(token):
        token = secrets.token_hex(32)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=365 * 24 * 60 * 60,
        httponly=True,
        samesite="strict",
        path="/",
        secure=request.app.state.settings.base_url.startswith("https://"),
    )


def get_owner(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME, "")
    if not TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(401, "Open /api/v1/session first and keep its workspace cookie")
    return hashlib.sha256(token.encode()).hexdigest()


class CreationLimiter:
    """Fixed window limit for a single web process; not a distributed abuse system."""

    def __init__(self, limit: int, max_clients: int = 5000) -> None:
        self.limit = limit
        self.max_clients = max_clients
        self.entries: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self.lock = Lock()

    def check(self, key: str) -> int:
        now = time.monotonic()
        with self.lock:
            started, count = self.entries.get(key, (now, 0))
            if now - started >= 60:
                started, count = now, 0
            if count >= self.limit:
                return max(1, math.ceil(60 - (now - started)))
            self.entries[key] = (started, count + 1)
            self.entries.move_to_end(key)
            if len(self.entries) > self.max_clients:
                self.entries.popitem(last=False)
        return 0


def limit_creation(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    retry_after = request.app.state.creation_limiter.check(key)
    if retry_after:
        raise HTTPException(
            429, "Too many links. Please try again in a minute.", headers={"Retry-After": str(retry_after)}
        )
