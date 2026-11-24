"""FastAPI dependencies shared by the routers."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .admin_security import admin_access_configured, valid_session_token
from .database import get_session


def require_admin(admin_session: Annotated[str | None, Cookie()] = None) -> None:
    if not admin_access_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ยังไม่ได้ตั้งค่ารหัสผ่านผู้ดูแล")
    if not valid_session_token(admin_session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ต้องเข้าสู่ระบบผู้ดูแล")


SessionDep = Annotated[Session, Depends(get_session)]
"""A database session that is closed after the request."""

AdminDep = Annotated[None, Depends(require_admin)]
"""Reject the request unless it carries a valid administrator session."""
