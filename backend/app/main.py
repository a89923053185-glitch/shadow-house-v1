import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router as api_router
from app.core.config import get_settings
from app.db.session import Base, engine

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:
            if attempt == max_attempts:
                logger.error("Database init skipped after %s failed attempts: %s", max_attempts, exc)
                return
            time.sleep(2)


app.include_router(api_router, prefix="/api/v1")
