"""Caps the size of a booking request body.

The booking form can now carry a license photo, and the CSRF middleware reads the whole body into memory
before the route runs. Without a cap anyone could post a huge body. This refuses it with 413 as soon as the
declared size, or the bytes actually received (a chunked body declares none), go over the limit.
"""

import json


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int, prefix: str = "/book"):
        self.app = app
        self.max_bytes = max_bytes
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not scope["path"].startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await self._refuse(send)
            return

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge
            return message

        async def tracking_send(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._refuse(send)

    @staticmethod
    async def _refuse(send):
        body = json.dumps({"errors": ["That upload is too large. Use a photo under 5 MB."]}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
