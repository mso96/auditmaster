"""Bound the inline request before FastAPI decodes JSON, including chunked bodies."""

from starlette.responses import JSONResponse

MAX_BODY_BYTES = 10 * 1024 * 1024


class AnalysisBodyLimit:
    def __init__(self, app, max_bytes=MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path", "").rstrip("/") != "/analysis/run"
        ):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length is not None:
            try:
                too_large = int(length) > self.max_bytes
            except ValueError:
                return await JSONResponse({"detail": "Geçersiz gövde boyutu."}, 400)(
                    scope, receive, send
                )
            if too_large:
                return await self.reject(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                return await self.reject(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def reject(self, scope, receive, send):
        await JSONResponse({"detail": "İstek gövdesi 10 MB sınırını aşıyor."}, 413)(
            scope, receive, send
        )
