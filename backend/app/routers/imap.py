from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.imap import _test_imap_connection, get_folders
from app.core.logging import get_logger
from app.crud.settings import create_or_update_settings, get_settings
from app.schemas.settings import Settings, SettingsCreate
from app.services.email_processor import EmailProcessingError, process_emails

logger = get_logger(__name__)
router = APIRouter()


@router.get("/imap/settings", response_model=Settings)
def read_settings(db: Session = Depends(get_db)):
    """Retrieve IMAP settings."""
    logger.info("Request to read IMAP settings")
    settings = get_settings(db)
    if not settings:
        logger.warning("IMAP settings not found")
        raise HTTPException(status_code=404, detail="IMAP settings not found")
    return settings


@router.post("/imap/settings", response_model=Settings)
def update_settings(settings: SettingsCreate, db: Session = Depends(get_db)):
    """Update IMAP settings."""
    logger.info("Request to update IMAP settings")
    return create_or_update_settings(db=db, settings=settings)


@router.post("/imap/test")
def test_connection(db: Session = Depends(get_db)):
    """Test the IMAP connection with current settings."""
    logger.info("Request to test IMAP connection")
    settings = get_settings(db, with_password=True)
    if not settings:
        logger.error("IMAP settings not found, cannot test connection")
        raise HTTPException(status_code=404, detail="IMAP settings not found")

    is_successful, message = _test_imap_connection(
        server=settings.imap_server,
        username=settings.imap_username,
        password=settings.imap_password,
    )

    if not is_successful:
        logger.warning(f"IMAP connection test failed: {message}")
        raise HTTPException(status_code=400, detail=message)

    logger.info("IMAP connection test successful")
    return {"message": message}


@router.get("/imap/folders", response_model=List[str])
def read_folders(db: Session = Depends(get_db)):
    """Retrieve a list of IMAP folders from the configured server."""
    logger.info("Request to fetch IMAP folders")
    settings = get_settings(db, with_password=True)
    if not settings:
        logger.error("IMAP settings not found, cannot fetch folders")
        raise HTTPException(status_code=404, detail="IMAP settings not found")

    folders = get_folders(
        server=settings.imap_server,
        username=settings.imap_username,
        password=settings.imap_password,
    )

    logger.info(f"Found {len(folders)} IMAP folders")
    return folders


@router.post("/imap/process")
def trigger_email_processing(db: Session = Depends(get_db)):
    """Trigger the email processing manually."""
    logger.info("Request to manually trigger email processing")
    try:
        process_emails(db)
        return {"message": "Email processing triggered successfully."}
    except EmailProcessingError as e:
        logger.warning(f"Email processing failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error triggering email processing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
