from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.services.feed_generator import generate_feed, generate_master_feed

logger = get_logger(__name__)
router = APIRouter()


@router.get("/feeds/all")
def get_master_feed(db: Session = Depends(get_db)):
    """Generate a master Atom feed for all newsletters."""
    logger.info("Generating master feed for all newsletters")
    feed = generate_master_feed(db)
    logger.info("Successfully generated master feed")
    return Response(content=feed, media_type="application/atom+xml")


@router.get("/feeds/{feed_identifier}")
def get_newsletter_feed(feed_identifier: str, db: Session = Depends(get_db)):
    """Generate an Atom feed for a specific newsletter."""
    logger.info(f"Generating feed for newsletter with identifier={feed_identifier}")
    feed = generate_feed(db, feed_identifier)
    if not feed:
        logger.warning(
            f"Newsletter with identifier={feed_identifier} not found, cannot generate feed."
        )
        raise HTTPException(status_code=404, detail="Newsletter not found")

    logger.info(
        f"Successfully generated feed for newsletter with identifier={feed_identifier}"
    )
    return Response(content=feed, media_type="application/atom+xml")
