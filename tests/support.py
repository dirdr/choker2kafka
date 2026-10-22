import json


async def raw_request(app, path, method="GET", body=None, token=None, query=b""):
    messages = []
    headers = [(b"content-type", b"application/json")]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(body).encode() if body else b"",
        }

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query,
            "headers": headers,
            "server": ("test", 80),
            "client": ("test", 1),
            "root_path": "",
        },
        receive,
        send,
    )
    return (
        messages[0]["status"],
        dict(messages[0]["headers"]),
        b"".join(m.get("body", b"") for m in messages[1:]),
    )


async def request(app, path, method="GET", body=None, token=None, query=b""):
    status, _, content = await raw_request(app, path, method, body, token, query)
    return status, json.loads(content)
