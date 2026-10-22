import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sentinel.detection.postgres import DetectionRepository
from sentinel.detection.service import DetectionWorker
from sentinel.detection.web import router as detection_router
from sentinel.health import router as health_router
from sentinel.investigation.postgres import InvestigationRepository
from sentinel.investigation.service import InvestigationWorker
from sentinel.investigation.web import router as investigation_router
from sentinel.readiness import router as readiness_router
from sentinel.stream.kafka import KafkaStream
from sentinel.stream.postgres import PostgresRepository
from sentinel.stream.service import StreamWorker
from sentinel.stream.web import router as stream_router
from sentinel.workbench.settings import router as workbench_settings_router
from sentinel.workbench.web import ROOT as WORKBENCH_ROOT
from sentinel.workbench.web import router as workbench_router

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.repository = PostgresRepository()
    app.state.detection_repository = DetectionRepository(app.state.repository)
    app.state.investigation_repository = InvestigationRepository(app.state.repository)
    workers = []
    tasks = []
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
        workers.append(worker)
    if os.getenv("DETECTION_ENABLED", "true").lower() == "true":
        detector = DetectionWorker(
            app.state.detection_repository, os.getenv("KAFKA_TOPIC", "orders")
        )
        app.state.detection_worker = detector
        workers.append(detector)
    if os.getenv("INVESTIGATION_ENABLED", "true").lower() == "true":
        investigator = InvestigationWorker(app.state.investigation_repository)
        app.state.investigation_worker = investigator
        workers.append(investigator)
    tasks = [asyncio.create_task(asyncio.to_thread(worker.run)) for worker in workers]
    try:
        yield
    finally:
        for worker in workers:
            worker.stop()
        await asyncio.gather(*tasks)
        for name in ("stream_worker", "detection_worker", "investigation_worker"):
            if hasattr(app.state, name):
                delattr(app.state, name)


app = FastAPI(title="Kafka Contract Sentinel", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(readiness_router)
app.include_router(stream_router)
app.include_router(detection_router)
app.include_router(investigation_router)
app.mount("/static", StaticFiles(directory=WORKBENCH_ROOT / "static"), name="static")
app.include_router(workbench_settings_router)
app.include_router(workbench_router)
