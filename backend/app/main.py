from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import protected_route
from app.core.database import Base, SessionLocal, engine
from app.core.logging import get_logger, setup_logging
from app.core.scheduler import scheduler, start_scheduler_with_interval
from app.crud.settings import create_initial_settings
from app.routers import auth, feeds, health, imap, newsletters


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    setup_logging()
    logger = get_logger(__name__)
    from app.core.config import settings

    logger.info(f"DATABASE_URL used: {settings.database_url}")
    logger.info("Starting up Letterfeed backend...")
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        create_initial_settings(db)

    start_scheduler_with_interval()
    yield
    if scheduler.running:
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()
    logger.info("...Letterfeed backend shut down.")


app = FastAPI(lifespan=lifespan)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(imap.router, dependencies=[Depends(protected_route)])
app.include_router(newsletters.router, dependencies=[Depends(protected_route)])
app.include_router(feeds.router)
