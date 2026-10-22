from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from sentinel.health import router as health_router
from sentinel.readiness import router as readiness_router

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Kafka Contract Sentinel", version="0.1.0")
app.include_router(health_router)
app.include_router(readiness_router)
