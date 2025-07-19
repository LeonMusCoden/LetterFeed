import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import (
    _get_auth_credentials,
    create_access_token,
    is_auth_enabled,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.hashing import verify_password
from app.schemas.auth import Token

router = APIRouter()


@router.get("/auth/status")
def auth_status(auth_enabled: bool = Depends(is_auth_enabled)):
    """Check if authentication is enabled."""
    return {"auth_enabled": auth_enabled}


@router.post("/auth/login", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """Verify username and password and return an access token."""
    auth_creds = _get_auth_credentials(db)
    if not auth_creds.get("username") or not auth_creds.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not configured on the server",
        )

    correct_username = secrets.compare_digest(
        form_data.username, auth_creds["username"]
    )
    correct_password = verify_password(form_data.password, auth_creds["password_hash"])

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    try:
        access_token = create_access_token(
            data={"sub": form_data.username}, expires_delta=access_token_expires
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    return {"access_token": access_token, "token_type": "bearer"}
