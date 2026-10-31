"""Single-worker sessions, bounded abuse controls, and browser security policy."""
from collections import OrderedDict
from hashlib import sha256
from secrets import token_urlsafe, compare_digest
from threading import RLock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

COOKIE_NAME = 'linkly_session'
SESSION_TTL = 1800


class AccessControl:
    """Bound memory usage. Sessions and limits intentionally reset on restart."""
    def __init__(self):
        self.sessions = OrderedDict()
        self.attempts = OrderedDict()
        self.lock = RLock()

    def limit(self, key, maximum, window=60):
        now = monotonic()
        with self.lock:
            count, expires = self.attempts.get(key, (0, now + window))
            if expires <= now:
                count, expires = 0, now + window
            self.attempts[key] = (count + 1, expires)
            self.attempts.move_to_end(key)
            while len(self.attempts) > 4096:
                self.attempts.popitem(last=False)
            if count >= maximum:
                raise HTTPException(429, 'Too many attempts. Please wait a minute and try again.', headers={'Retry-After': str(max(1, int(expires - now)))})

    def issue(self, admin_key):
        token = token_urlsafe(32)
        with self.lock:
            self.sessions[sha256(token.encode()).digest()] = (monotonic() + SESSION_TTL, sha256(admin_key.encode()).digest())
            while len(self.sessions) > 256:
                self.sessions.popitem(last=False)
        return token

    def valid(self, token, admin_key):
        digest = sha256(token.encode()).digest()
        with self.lock:
            entry = self.sessions.get(digest)
            if not entry:
                return False
            expires, key_hash = entry
            if expires <= monotonic() or not compare_digest(key_hash, sha256(admin_key.encode()).digest()):
                self.sessions.pop(digest, None)
                return False
            return True

    def remaining(self, token):
        with self.lock:
            entry = self.sessions.get(sha256(token.encode()).digest())
            return max(0, int(entry[0] - monotonic())) if entry else 0

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(sha256(token.encode()).digest(), None)


def client_key(request):
    # Rely on the ASGI server's trusted proxy configuration, never user-supplied X-Forwarded-For.
    return request.client.host if request.client else 'unknown'


def check_origin(request: Request, required=False):
    origin = request.headers.get('origin')
    public = urlsplit(request.app.state.settings.base_url)
    allowed = f'{public.scheme}://{public.netloc}'
    if (required and not origin) or (origin and origin != allowed):
        raise HTTPException(403, 'This action must be performed from this website.')


class SecurityMiddleware:
    """Cap API input before parsing and apply headers to errors and redirects too."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers.extend([
                    (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'),
                    (b'referrer-policy', b'no-referrer'),
                    (b'permissions-policy', b'camera=(), microphone=(), geolocation=()'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                    (b'cache-control', b'no-store'),
                ])
                if scope.get('scheme') == 'https':
                    headers.append((b'strict-transport-security', b'max-age=31536000'))
                message['headers'] = headers
            await send(message)

        if scope['path'].startswith('/api/') and scope['method'] in {'POST', 'PUT', 'PATCH'}:
            body = bytearray()
            while True:
                event = await receive()
                if event['type'] == 'http.disconnect':
                    return
                body.extend(event.get('body', b''))
                if len(body) > 16384:
                    return await JSONResponse({'detail': 'Request is too large.'}, status_code=413)(scope, receive, secure_send)
                if not event.get('more_body', False):
                    break
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()
            return await self.app(scope, replay, secure_send)
        await self.app(scope, receive, secure_send)
