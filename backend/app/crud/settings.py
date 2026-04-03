from sqlalchemy.orm import Session

from app.core.config import settings as env_settings
from app.core.hashing import get_password_hash
from app.core.logging import get_logger
from app.models.settings import Settings as SettingsModel
from app.schemas.settings import Settings as SettingsSchema
from app.schemas.settings import SettingsCreate

logger = get_logger(__name__)


def create_initial_settings(db: Session):
    """Create initial settings in the database if they don't exist."""
    logger.debug("Checking for initial settings.")
    db_settings = db.query(SettingsModel).first()
    if not db_settings:
        logger.info(
            "No settings found in the database, creating new default settings from environment variables."
        )

        # Get env settings, but only for fields that exist in the DB model
        model_fields = {c.name for c in SettingsModel.__table__.columns}
        env_data_for_db = {
            k: v for k, v in env_settings.model_dump().items() if k in model_fields
        }

        if env_settings.auth_password:
            env_data_for_db["auth_password_hash"] = get_password_hash(
                env_settings.auth_password
            )
        if "auth_password" in env_data_for_db:
            del env_data_for_db["auth_password"]

        db_settings = SettingsModel(**env_data_for_db)
        db.add(db_settings)
        db.commit()
        db.refresh(db_settings)
        logger.info("Default settings created from environment variables.")


def get_settings(db: Session, with_password: bool = False) -> SettingsSchema:
    """Retrieve application settings, prioritizing environment variables over database."""
    logger.debug("Querying for settings")
    db_settings = db.query(SettingsModel).first()

    if not db_settings:
        # This should not happen if create_initial_settings is called at startup.
        raise RuntimeError("Settings not initialized.")

    # Build dictionary from DB model attributes, handling possible None values
    db_data = {
        "id": db_settings.id,
        "imap_server": db_settings.imap_server or "",
        "imap_username": db_settings.imap_username or "",
        "search_folder": db_settings.search_folder,
        "move_to_folder": db_settings.move_to_folder,
        "mark_as_read": db_settings.mark_as_read,
        "email_check_interval": db_settings.email_check_interval,
        "auto_add_new_senders": db_settings.auto_add_new_senders,
        "max_entries_per_feed": db_settings.max_entries_per_feed,
        "auth_username": db_settings.auth_username,
    }

    # Get all environment settings that were explicitly set.
    env_data = env_settings.model_dump(exclude_unset=True)

    # Merge them. env_data takes precedence.
    merged_data = {**db_data, **env_data}

    # The fields that came from env are the "locked" ones.
    locked_fields = list(env_data.keys())
    logger.debug(f"Locked fields from environment variables: {locked_fields}")

    # Handle password separately for security
    if with_password:
        logger.debug("Including IMAP password in settings data")
        if "imap_password" in locked_fields:
            merged_data["imap_password"] = env_settings.imap_password
        else:
            merged_data["imap_password"] = db_settings.imap_password
    elif "imap_password" in merged_data:
        # Ensure password is not in the data if not requested
        del merged_data["imap_password"]

    # Create the final schema object
    settings_schema = SettingsSchema.model_validate(merged_data)
    settings_schema.locked_fields = locked_fields

    return settings_schema


def create_or_update_settings(db: Session, settings: SettingsCreate):
    """Create or update application settings."""
    logger.info("Creating or updating settings")
    db_settings = db.query(SettingsModel).first()
    if not db_settings:
        logger.info("No existing settings found, creating new ones.")
        db_settings = SettingsModel()
        db.add(db_settings)

    update_data = settings.model_dump(exclude_unset=True)

    # Do not update fields that are set by environment variables
    locked_fields = list(env_settings.model_dump(exclude_unset=True).keys())
    logger.debug(f"Fields locked by environment variables: {locked_fields}")

    for key, value in update_data.items():
        if key in locked_fields:
            continue

        if key == "auth_password":
            if value:
                db_settings.auth_password_hash = get_password_hash(value)
            else:
                db_settings.auth_password_hash = None
        elif key == "imap_password":
            if value:  # Only update password if a new one is provided
                setattr(db_settings, key, value)
        elif hasattr(db_settings, key):
            setattr(db_settings, key, value)

    db.commit()
    db.refresh(db_settings)
    logger.info("Successfully updated settings.")

    # Return the updated settings including locked fields for a complete view
    return get_settings(db)
