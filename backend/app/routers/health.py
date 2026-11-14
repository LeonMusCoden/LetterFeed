from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.core.scheduler import get_scheduler_status

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health")
def health_check():
    """Report API health and whether the email scheduler is making progress.

    A run that never returns keeps the process alive and the API responsive, so
    the plain "is uvicorn up?" check cannot see it. This endpoint also fails
    when a job has been running, or has not succeeded, for too long.
    """
    status = get_scheduler_status()
    if status["running"]:
        stale_after = timedelta(minutes=2 * status["interval_minutes"] + 15)
        now = datetime.now(UTC)
        started = status["last_started_at"]
        succeeded = status["last_success_at"]
        if status["job_running"] and started and now - started > stale_after:
            logger.warning("Health check failed: email job is still running.")
            raise HTTPException(status_code=503, detail="Email job stalled")
        if succeeded and now - succeeded > stale_after:
            logger.warning("Health check failed: email job is not succeeding.")
            raise HTTPException(status_code=503, detail="Email ingestion stalled")
    return {"status": "ok"}
