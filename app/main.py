from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import init_db
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="GTM Signal Intelligence Engine",
    description="Detects buying signals, scores them by urgency, and generates evidence-backed outreach.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")
