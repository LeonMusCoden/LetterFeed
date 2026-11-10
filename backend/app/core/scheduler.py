from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.crud.settings import get_settings
from app.services.email_processor import process_emails

"""Scheduler for background tasks like email processing."""

logger = get_logger(__name__)

# Extra time allowed on top of two polling intervals before /health reports the
# job as stalled. Covers a slow mailbox without flapping.
_STALE_GRACE_MINUTES = 15

_last_started_at: datetime | None = None
_last_success_at: datetime | None = None
_job_running = False
_interval_minutes = 15

scheduler = BackgroundScheduler()


def job():
    """Process emails as a scheduled job."""
    global _last_started_at, _last_success_at, _job_running
    _last_started_at = datetime.now(UTC)
    _job_running = True
    logger.info("Scheduler job starting: process_emails")
    db = SessionLocal()
    try:
        process_emails(db)
        _last_success_at = datetime.now(UTC)
        logger.info("Scheduler job finished: process_emails")
    except Exception as e:
        logger.error(f"Error in scheduled job process_emails: {e}", exc_info=True)
    finally:
        _job_running = False
        db.close()


def get_scheduler_status() -> dict:
    """Return the scheduler state used by the health check.

    `job_running` and `last_started_at` let the health check detect a run that
    never returns, which is the failure mode that silently stops ingestion.
    """
    scheduled = scheduler.get_job("email_check_job")
    return {
        "running": scheduler.running,
        "job_running": _job_running,
        "interval_minutes": _interval_minutes,
        "last_started_at": _last_started_at,
        "last_success_at": _last_success_at,
        "next_run_at": getattr(scheduled, "next_run_time", None),
    }


def start_scheduler_with_interval():
    """Start the scheduler with an interval based on application settings."""
    global _interval_minutes
    logger.info("Attempting to start scheduler...")
    db = SessionLocal()
    try:
        settings = get_settings(db)
        interval = settings.email_check_interval if settings else 15
        _interval_minutes = interval
        logger.info(f"Setting scheduler interval to {interval} minutes")
        scheduler.add_job(
            job,
            "interval",
            minutes=interval,
            id="email_check_job",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60 * 5,
        )
        if not scheduler.running:
            scheduler.add_job(
                job,
                "date",
                run_date=datetime.now(),
                id="initial_email_check",
                replace_existing=True,
            )
            scheduler.start()
            logger.info("Scheduler started.")
        else:
            logger.info("Scheduler is already running.")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
    finally:
        db.close()
