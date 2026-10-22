# choker2kafka

The first deployable slice of Kafka Contract Sentinel: a FastAPI application with an HTTP health endpoint. PostgreSQL, Kafka, and agent features will follow in separate commits after this deployment works.

## Deploy on Aiven Runtime

1. Push this version to GitHub.
2. In your Aiven project, open **Runtime → Deploy application**.
3. Select **dirdr/choker2kafka**, branch **main**.
4. Select the root **Dockerfile** and scan it. Use **HTTP**, port **8080**.
5. Deploy, then open the application's public URL with `/health` appended.

Expected response:

```json
{"status":"ok"}
```

The root URL returns the same response. This endpoint checks that the application is running; it does not check Kafka or PostgreSQL. No environment variables or connected services are required for this first deployment.

For subsequent commits, use **Actions → Deploy latest commit** in Runtime. Git pushes do not trigger redeployment automatically.

[Aiven deployment documentation](https://aiven.io/docs/products/runtime/deploy-apps)

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root:

```sh
uv sync
uv run uvicorn sentinel.main:app --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080/health`.

Python is pinned to 3.14.9 for compatibility with the Kafka client's published wheels. Dependencies are pinned in `pyproject.toml`; `uv sync` generates the lockfile. The Docker build also resolves dependencies with uv.

## Run with Docker

```sh
docker build -t choker2kafka .
docker run --rm -p 8080:8080 choker2kafka
```

## Check service connections separately

Configure `.env` using `.env.example` and place the Kafka CA certificate at `secrets/ca.pem`. These files are excluded from Git and the Docker build.

```sh
uv run --group connectivity scripts/check_connections.py
```

This command authenticates to PostgreSQL and Kafka and checks whether `orders` exists. It does not create topics or change data.

## Code layout

`sentinel/main.py` assembles the application. `sentinel/health.py` contains the first feature slice. New features will keep their routes and behavior together in their own slices.
