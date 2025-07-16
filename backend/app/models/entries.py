import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Entry(Base):
    """Represents an entry (e.g., an email) associated with a newsletter."""

    __tablename__ = "entries"

    id = Column(Integer, primary_key=True, index=True)
    newsletter_id = Column(Integer, ForeignKey("newsletters.id"))
    subject = Column(String)
    body = Column(Text)
    received_at = Column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.UTC)
    )
    message_id = Column(String, unique=True, index=True, nullable=False)

    newsletter = relationship("Newsletter", back_populates="entries")
