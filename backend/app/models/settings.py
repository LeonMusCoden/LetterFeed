from sqlalchemy import Boolean, Column, Integer, String

from app.core.database import Base


class Settings(Base):
    """Represents application settings."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    imap_server = Column(String, index=True, nullable=True, default="")
    imap_username = Column(String, nullable=True, default="")
    imap_password = Column(String, nullable=True)
    search_folder = Column(String, default="INBOX")
    move_to_folder = Column(String, nullable=True)
    mark_as_read = Column(Boolean, default=False)
    email_check_interval = Column(Integer, default=15)  # Interval in minutes
    auto_add_new_senders = Column(Boolean, default=False)
    max_entries_per_feed = Column(Integer, default=0)
    auth_username = Column(String, nullable=True)
    auth_password_hash = Column(String, nullable=True)
