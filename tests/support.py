import json


async def request(app, path, method="GET", body=None, token=None, query=b""):
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
            "asgi": {"version": "3.0"},
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
    return messages[0]["status"], json.loads(
        b"".join(m.get("body", b"") for m in messages[1:])
    )
