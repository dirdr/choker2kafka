import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from sentinel.health import router as health_router
from sentinel.readiness import router as readiness_router
from sentinel.stream.kafka import KafkaStream
from sentinel.stream.postgres import PostgresRepository
from sentinel.stream.service import StreamWorker
from sentinel.stream.web import router as stream_router

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.repository = PostgresRepository()
    worker = None
    task = None
    if os.getenv("STREAM_ENABLED", "true").lower() == "true":
        worker = StreamWorker(
            app.state.repository,
            KafkaStream(
                os.getenv("KAFKA_TOPIC", "orders"),
                os.getenv("KAFKA_GROUP_ID", "sentinel-orders-v1"),
            ),
            os.getenv("CODE_VERSION", "0.1.0"),
        )
        app.state.stream_worker = worker
        task = asyncio.create_task(asyncio.to_thread(worker.run))
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()
            await task


app = FastAPI(title="Kafka Contract Sentinel", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(readiness_router)
app.include_router(stream_router)
