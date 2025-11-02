import json
from starlette.types import ASGIApp, Receive, Scope, Send

class InjectRequestPathMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_path = scope["path"]
        status = None
        headers = None
        body_chunks = []

        async def send_wrapper(message):
            nonlocal status, headers

            # Capture headers and status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = message.get("headers", [])
                return  # DO NOT send yet

            # Capture body chunks
            if message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    body_chunks.append(chunk)

                # If this is the last chunk, rewrite response
                if not message.get("more_body", False):
                    body = b"".join(body_chunks)

                    try:
                        data = json.loads(body)
                        if isinstance(data, dict) and "request" in data:
                            data["request"] = request_path
                            body = json.dumps(data).encode()
                    except:
                        pass  # not json, return raw

                    # Rewrite headers: remove old content-length
                    new_headers = [
                        (k, v) for (k, v) in headers
                        if k.lower() != b"content-length"
                    ]
                    new_headers.append((b"content-length", str(len(body)).encode()))

                    await send({
                        "type": "http.response.start",
                        "status": status,
                        "headers": new_headers,
                    })

                    await send({
                        "type": "http.response.body",
                        "body": body,
                        "more_body": False,
                    })
                return  # DON'T fall through

            await send(message)

        await self.app(scope, receive, send_wrapper)
