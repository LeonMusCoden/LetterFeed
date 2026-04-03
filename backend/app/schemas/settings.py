from typing import List

from pydantic import BaseModel, ConfigDict, Field


class SettingsBase(BaseModel):
    """Base schema for application settings."""

    imap_server: str
    imap_username: str
    search_folder: str = "INBOX"
    move_to_folder: str | None = None
    mark_as_read: bool = False
    email_check_interval: int = 15
    auto_add_new_senders: bool = False
    max_entries_per_feed: int = 0
    auth_username: str | None = None


class SettingsCreate(SettingsBase):
    """Schema for creating or updating settings, including the IMAP password."""

    imap_password: str | None = None
    auth_password: str | None = None


class Settings(SettingsBase):
    """Schema for retrieving settings, with password excluded by default."""

    id: int
    imap_password: str | None = Field(None, exclude=True)
    auth_password: str | None = Field(None, exclude=True)
    locked_fields: List[str] = []

    model_config = ConfigDict(from_attributes=True)
