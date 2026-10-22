from fastapi import FastAPI

from sentinel.health import router as health_router

app = FastAPI(title="Kafka Contract Sentinel", version="0.1.0")
app.include_router(health_router)
